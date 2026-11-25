import json
import os
from pathlib import Path
import queue
import shutil
import signal
import subprocess
import tempfile
import threading
import time
import urllib.parse

from .validation import AppError, strict_json_constant, unique_json_object
from . import __version__


MAX_LINE = 13 * 1024 * 1024
MAX_EVENT = 2 * 1024 * 1024
MAX_REQUEST = 13 * 1024 * 1024
RPC_TIMEOUT = 15
TURN_TIMEOUT = 150
DISABLED_FEATURES = (
    "shell_tool", "shell_snapshot", "apps", "plugins", "remote_plugin", "multi_agent",
    "view_image", "skill_mcp_dependency_install", "hooks", "codex_hooks", "memories",
    "browser_use", "browser_use_external", "in_app_browser", "computer_use",
    "in_app_local_automation", "workspace_dependencies", "realtime_conversation",
)
SAFE_CONFIG = {
    "model_provider": "openai", "forced_login_method": "chatgpt",
    "cli_auth_credentials_store": "file", "history.persistence": "none",
    "web_search": "disabled", "sandbox_mode": "read-only", "approval_policy": "never",
    "project_doc_max_bytes": 0, "skills.bundled.enabled": False,
    "features.code_mode.enabled": False, "analytics.enabled": False, "feedback.enabled": False,
    "check_for_update_on_startup": False, "shell_environment_policy.inherit": "none",
    "chatgpt_base_url": "https://chatgpt.com/backend-api/",
    **{"features." + name: False for name in DISABLED_FEATURES},
}


def official_auth_url(value):
    if not isinstance(value, str) or not 1 <= len(value) <= 8192 or "\\" in value or any(ord(char) < 33 or ord(char) > 126 for char in value):
        raise AppError("Codex 返回的登录地址无效，已拒绝打开", 502)
    try:
        parsed = urllib.parse.urlsplit(value)
        if parsed.scheme != "https" or parsed.hostname not in ("auth.openai.com", "chatgpt.com") or parsed.port not in (None, 443) or parsed.username or parsed.password or parsed.fragment:
            raise ValueError()
    except ValueError:
        raise AppError("登录地址不属于允许的 OpenAI 官方 HTTPS 来源", 502)
    return value


def private_directory(path):
    if path.is_symlink():
        raise AppError("Codex 隔离目录不能是符号链接", 422)
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    if os.name != "nt":
        path.chmod(0o700)
    return path


class CodexRPC:
    def __init__(self, root, executable=None):
        self.root = Path(root)
        candidate = executable or shutil.which("codex")
        self.executable = str(Path(candidate).resolve()) if candidate else None
        self.process = None
        self.temporary = None
        self.workdir = None
        self.lock = threading.RLock()
        self.close_lock = threading.Lock()
        self.pending = {}
        self.events = queue.Queue(maxsize=32)
        self.outbound = queue.Queue(maxsize=8)
        self.sequence = 0
        self._auth_epoch = 0
        self.failed = False
        self.workers = []

    @property
    def alive(self):
        return self.process is not None and self.process.poll() is None and not self.failed

    @property
    def auth_epoch(self):
        with self.lock:
            return self._auth_epoch

    @auth_epoch.setter
    def auth_epoch(self, value):
        with self.lock:
            self._auth_epoch = value

    def start(self):
        if self.process is not None:
            raise AppError("请先断开旧的 Codex 连接", 409)
        if not self.executable or not Path(self.executable).is_file():
            raise AppError("未找到 Codex CLI。请从 OpenAI 官方渠道安装，或通过 --codex-bin 指定可执行文件后重启", 422)
        root = private_directory(self.root)
        credentials = private_directory(root / "auth")
        self.temporary = tempfile.TemporaryDirectory(prefix="session-", dir=root)
        session = Path(self.temporary.name)
        home = private_directory(session / "home")
        self.workdir = private_directory(session / "work")
        environment = {key: os.environ[key] for key in ("PATH", "SystemRoot", "WINDIR", "COMSPEC", "PATHEXT", "LANG", "LC_ALL") if key in os.environ}
        environment.update(HOME=str(home), USERPROFILE=str(home), CODEX_HOME=str(credentials), TMPDIR=str(session), TMP=str(session), TEMP=str(session))
        command = [str(self.executable), "app-server", "--listen", "stdio://"]
        for key, value in SAFE_CONFIG.items():
            command.extend(["-c", key + "=" + json.dumps(value)])
        try:
            self.process = subprocess.Popen(command, cwd=self.workdir, env=environment, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, start_new_session=os.name != "nt")
            for target in (self._read, self._write):
                worker = threading.Thread(target=target, daemon=True)
                self.workers.append(worker)
                worker.start()
            self.call("initialize", {"clientInfo": {"name": "health_journal_local", "title": "知己健康手记", "version": __version__}})
            self.send({"method": "initialized", "params": {}})
            effective = self.call("config/read", {"includeLayers": False}).get("config", {})
            self.check_config(effective)
        except (OSError, ValueError, TypeError, AttributeError, AppError):
            self.close()
            raise AppError("Codex 启动或安全配置校验失败。请核对官方 CLI 版本与系统策略；没有发送健康资料，不会降级隔离设置", 503)

    @staticmethod
    def check_config(config):
        for key, expected in SAFE_CONFIG.items():
            current = config
            for part in key.split("."):
                current = current.get(part) if isinstance(current, dict) else None
            if type(current) is not type(expected) or current != expected:
                raise AppError("Codex 未确认所需安全配置：" + key, 503)
        for key in ("mcp_servers", "plugins", "hooks"):
            if config.get(key):
                raise AppError("隔离连接不能载入 MCP、插件或钩子", 503)

    def send(self, message):
        payload = json.dumps(message, ensure_ascii=False, allow_nan=False).encode("utf-8") + b"\n"
        if len(payload) > MAX_REQUEST or not self.alive:
            raise AppError("Codex 连接不可用或请求超过限制", 503)
        try:
            self.outbound.put_nowait(payload)
        except queue.Full:
            self._fail()
            raise AppError("Codex 请求队列已满；未自动重试", 503)

    def call(self, method, params, timeout=RPC_TIMEOUT):
        waiter = {"event": threading.Event()}
        with self.lock:
            self.sequence += 1
            request_id = self.sequence
            self.pending[request_id] = waiter
        try:
            self.send({"method": method, "id": request_id, "params": params})
            if not waiter["event"].wait(timeout):
                self.close()
                raise AppError("Codex 响应超时；未自动重试，已发送的请求可能占用额度", 504)
            response = waiter.get("response", {})
            if "error" in response or not isinstance(response.get("result"), dict):
                raise AppError("Codex 拒绝请求或连接中断。请检查登录、额度和 CLI 兼容性；未自动重试", 502)
            return response["result"]
        finally:
            with self.lock:
                self.pending.pop(request_id, None)

    def _write(self):
        try:
            while self.alive:
                try:
                    payload = self.outbound.get(timeout=0.2)
                except queue.Empty:
                    continue
                self.process.stdin.write(payload)
                self.process.stdin.flush()
        except (OSError, ValueError):
            self._fail()

    def _read(self):
        try:
            while True:
                line = self.process.stdout.readline(MAX_LINE + 1)
                if not line or len(line) > MAX_LINE or not line.endswith(b"\n"):
                    break
                message = json.loads(line, parse_constant=strict_json_constant, object_pairs_hook=unique_json_object)
                if not isinstance(message, dict):
                    break
                if "method" in message:
                    if "id" in message or not isinstance(message["method"], str) or not isinstance(message.get("params", {}), dict):
                        break
                    if message["method"] == "account/updated":
                        with self.lock:
                            self._auth_epoch += 1
                    method = message["method"]
                    item = message.get("params", {}).get("item")
                    user_echo = method in ("item/started", "item/completed") and isinstance(item, dict) and item.get("type") == "userMessage"
                    if user_echo:
                        message["params"]["item"] = {"type": "userMessage", "id": item.get("id")}
                    elif len(line) > MAX_EVENT:
                        break
                    if method in ("account/updated", "account/login/completed", "item/started", "item/completed", "turn/completed"):
                        self.events.put_nowait(message)
                else:
                    if len(line) > MAX_EVENT:
                        break
                    request_id = message.get("id")
                    if type(request_id) is not int:
                        break
                    with self.lock:
                        waiter = self.pending.get(request_id)
                        if waiter:
                            waiter["response"] = message
                            waiter["event"].set()
        except (OSError, ValueError, TypeError, RecursionError, queue.Full):
            pass
        finally:
            self._fail()

    def _fail(self):
        with self.lock:
            self.failed = True
            for waiter in self.pending.values():
                waiter["event"].set()
        self._terminate()

    def _terminate(self):
        process = self.process
        if process is not None and process.poll() is None:
            try:
                if os.name == "nt":
                    process.terminate()
                else:
                    os.killpg(process.pid, signal.SIGTERM)
            except OSError:
                pass

    def next_event(self, deadline):
        while time.monotonic() < deadline:
            if not self.alive:
                raise AppError("Codex 连接已断开或请求了不允许的工具操作；没有自动重试", 503)
            try:
                return self.events.get(timeout=min(0.2, max(0.01, deadline - time.monotonic())))
            except queue.Empty:
                continue
        raise AppError("Codex 分析超过时间限制；未自动重试，服务商可能已处理请求", 504)

    def close(self):
        with self.close_lock:
            self._close()

    def _close(self):
        self._fail()
        process = self.process
        if process is not None:
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                try:
                    if os.name == "nt":
                        process.kill()
                    else:
                        os.killpg(process.pid, signal.SIGKILL)
                except OSError:
                    pass
                process.wait(timeout=2)
            for worker in self.workers:
                if worker is not threading.current_thread():
                    worker.join(timeout=1)
            for stream in (process.stdin, process.stdout):
                if stream is not None:
                    stream.close()
        if self.temporary is not None:
            self.temporary.cleanup()
