import queue
import secrets
import threading
import time

from .assistant import EMERGENCY
from .cloud import CloudAI, parse_result
from .codex_rpc import CodexRPC, TURN_TIMEOUT, official_auth_url
from .departments import NAMES
from .validation import AppError, boolean, text


DESTINATION = "OpenAI Codex（ChatGPT 账号权益；非通用 API）"


def output_schema(task):
    string = {"type": "string"}
    def array(item):
        return {"type": "array", "items": item}
    def object_schema(properties):
        return {"type": "object", "properties": properties, "required": list(properties), "additionalProperties": False}
    properties = {"summary": string, "uncertainties": array(string), "questions": array(string)}
    if task == "document":
        department = {"type": "string", "enum": list(NAMES)}
        properties["departments"] = array(object_schema({"name": department, "evidence": string}))
        properties["excerpts"] = array(object_schema({"title": string, "quote": string, "location": string, "department": department}))
    else:
        properties["suggestions"] = array(string)
        if task == "breakfast":
            properties["foods"] = array(object_schema({"name": string, "portion": string, "confidence": {"type": "string", "enum": ["low", "medium", "high"]}}))
    return object_schema(properties)


def account_info(raw):
    account = raw.get("account")
    if account is None:
        return None
    if not isinstance(account, dict) or account.get("type") != "chatgpt":
        raise AppError("此连接只允许官方 ChatGPT 登录，不接受 API Key 或外部 Token", 422)
    return {"email": text(account.get("email") or "", "账号", 254), "plan": text(account.get("planType") or "unknown", "套餐", 80)}


class CodexAI(CloudAI):
    def __init__(self, store, executable=None, rpc_factory=CodexRPC):
        super().__init__(store)
        self.executable = executable
        self.rpc_factory = rpc_factory
        self.rpc = None
        self.account = None
        self.models = []
        self.login = None
        self.epoch = -1
        self.operation = None
        self.cancelled = threading.Event()
        self.control_lock = threading.Lock()
        self.closed = False

    def invalidate(self):
        self.pending.clear()
        self.revision = secrets.token_hex(12)

    def config(self):
        with self.lock:
            selected = self.store.setting("codex_config") or {"model": "", "vision": False}
            connected = bool(self.rpc and self.rpc.alive)
            authenticated = bool(not self.closed and connected and self.account and self.rpc.auth_epoch == self.epoch)
            return {"provider": "codex", "base_url": DESTINATION, "model": selected["model"], "vision": selected["vision"], "revision": self.revision,
                    "connected": connected, "authenticated": authenticated, "account": dict(self.account) if authenticated else None,
                    "models": [dict(item) for item in self.models] if authenticated else [], "login": dict(self.login) if connected and self.login else None,
                    "busy": self.busy, "operation": self.operation, "has_key": authenticated and any(item["model"] == selected["model"] for item in self.models),
                    "credential_storage": "本档案目录 .codex-connection/auth，由 Codex 管理；不是应用数据库加密的一部分"}

    def ready(self, config):
        if not config["has_key"]:
            raise AppError("请先连接 Codex、完成 ChatGPT 官方登录并选择可用模型", 422)
        return True

    def destination(self, config):
        return DESTINATION

    def consent_notice(self):
        return "确认后经本机 Codex 向 OpenAI 发送本次文字及图片，使用你的 ChatGPT/Codex 权益和额度，不是离线分析。附件未经脱敏。登录凭证由隔离目录中的 Codex 管理；模型输出只是草稿。取消不能撤回已发送内容或已消耗额度。"

    def configure(self, raw):
        model = text(raw.get("model"), "Codex 模型", 120, True)
        vision = boolean(raw.get("vision", False), "图像能力确认")
        with self.lock:
            if self.closed or self.busy or self.control_lock.locked() or raw.get("revision") != self.revision:
                raise AppError("配置已变化或仍在分析，请刷新后重试", 409)
            current = self.config()
            selected = next((item for item in current["models"] if item["model"] == model), None)
            if not current["authenticated"] or not selected:
                raise AppError("请先登录并刷新可用模型列表，不接受手填未知模型", 422)
            if vision and not selected["vision"]:
                raise AppError("Codex 未报告此模型支持图片，不能启用图像分析", 422)
            self.store.set_setting("codex_config", {"model": model, "vision": vision})
            self.invalidate()
            return self.config()

    def control(self, action, raw):
        if raw.get("confirm") is not True:
            raise AppError("请确认操作本机 Codex 连接")
        if not self.control_lock.acquire(blocking=False):
            raise AppError("正在处理另一项 Codex 连接操作，请稍候", 409)
        try:
            with self.lock:
                if self.closed or self.busy:
                    raise AppError("服务已停止或正在分析；请先取消分析", 409)
                self.invalidate()
            if action == "connect":
                with self.lock:
                    previous_rpc = self.rpc
                    self.rpc = self.rpc_factory(self.store.directory / ".codex-connection", self.executable)
                    self.account = None
                    self.models = []
                    self.login = None
                    current_rpc = self.rpc
                if previous_rpc:
                    previous_rpc.close()
                current_rpc.start()
                self._refresh()
            elif action in ("login", "refresh", "cancel-login", "logout"):
                if not self.rpc or not self.rpc.alive:
                    raise AppError("请先连接本机 Codex", 409)
                if action == "login":
                    if self.account or self.login:
                        raise AppError("请先退出当前账号或取消已有登录", 409)
                    result = self.rpc.call("account/login/start", {"type": "chatgpt"})
                    with self.lock:
                        self.login = {"id": text(result.get("loginId"), "登录标识", 100, True), "url": official_auth_url(result.get("authUrl"))}
                elif action == "cancel-login":
                    if self.login:
                        self.rpc.call("account/login/cancel", {"loginId": self.login["id"]})
                    with self.lock:
                        self.login = None
                    self._refresh()
                elif action == "logout":
                    self.rpc.call("account/logout", {})
                    with self.lock:
                        self.account = None
                        self.models = []
                        self.login = None
                        self.epoch = self.rpc.auth_epoch
                else:
                    self._refresh()
            elif action == "disconnect":
                with self.lock:
                    current_rpc = self.rpc
                    self.account = None
                    self.models = []
                    self.login = None
                if current_rpc:
                    current_rpc.close()
            else:
                raise AppError("未知 Codex 操作", 404)
            return self.config()
        except AppError as error:
            if error.status >= 500 and self.rpc:
                self.rpc.close()
                with self.lock:
                    self.account = None
                    self.models = []
                    self.login = None
            raise
        except Exception:
            if self.rpc:
                self.rpc.close()
            with self.lock:
                self.account = None
                self.models = []
                self.login = None
            raise AppError("Codex 连接操作失败，请重新连接；未发送健康资料", 502) from None
        finally:
            if self.closed and self.rpc:
                self.rpc.close()
            self.control_lock.release()

    def _refresh(self):
        epoch = self.rpc.auth_epoch
        with self.lock:
            self.account = None
            self.models = []
        account = account_info(self.rpc.call("account/read", {"refreshToken": False}))
        models = []
        if account:
            response = self.rpc.call("model/list", {"limit": 100})
            rows = response.get("data")
            if not isinstance(rows, list) or len(rows) > 100:
                raise AppError("Codex 模型列表格式不兼容", 502)
            for item in rows:
                if not isinstance(item, dict):
                    raise AppError("Codex 模型列表格式无效", 502)
                name = text(item.get("model"), "模型", 120, True)
                modalities = item.get("inputModalities") or []
                if not isinstance(modalities, list) or any(value not in ("text", "image") for value in modalities) or any(row["model"] == name for row in models):
                    raise AppError("Codex 模型能力格式不兼容", 502)
                models.append({"model": name, "name": text(item.get("displayName") or name, "模型名称", 160), "vision": "image" in modalities})
            with self.lock:
                self.login = None
        while True:
            try:
                event = self.rpc.events.get_nowait()
            except queue.Empty:
                break
            if event.get("method") == "account/login/completed" and event.get("params", {}).get("success") is False:
                with self.lock:
                    self.login = None
                raise AppError("官方登录未完成或已取消，请重新发起登录", 422)
        with self.lock:
            if self.closed or epoch != self.rpc.auth_epoch:
                self.account = None
                self.models = []
                raise AppError("登录状态刚刚变化，请再刷新一次账号状态", 409)
            self.account = account
            self.models = models
            self.epoch = epoch

    def prepare(self, raw):
        with self.lock:
            if self.closed or self.busy or self.control_lock.locked():
                raise AppError("Codex 正在处理请求，请稍候", 409)
            if raw.get("document_id") and self.store.get_document(raw["document_id"])[0]["mime"] == "application/pdf":
                raise AppError("Codex 不直传 PDF，请使用报告页面的 JPG/PNG 或必要文字摘录", 422)
            consent = super().prepare(raw)
            self.pending[consent["approval_id"]]["auth_epoch"] = self.epoch
            return consent

    def run(self, raw):
        if raw.get("confirm") is not True:
            raise AppError("需要确认本次具体外发内容")
        approval = text(raw.get("approval_id"), "授权标识", 100, True)
        with self.lock:
            if self.closed or self.busy or self.control_lock.locked():
                raise AppError("Codex 已有请求处理中", 409)
            pending = self.pending.pop(approval, None)
            if not pending or pending["expires"] <= time.monotonic() or pending["revision"] != self.revision or not self.config()["has_key"] or pending["auth_epoch"] != self.rpc.auth_epoch:
                raise AppError("登录、模型或授权已变化，请重新预览确认", 409)
            source = pending["consent"]["source"]
            if source:
                self.store.get_document(source["id"])
            self.busy = True
            self.operation = approval
            self.cancelled.clear()
            rpc = self.rpc
        try:
            if account_info(rpc.call("account/read", {"refreshToken": False})) != self.account:
                raise AppError("登录账号已改变，请重新登录和授权", 409)
            content = self._complete(rpc, pending)
            result = parse_result(content, pending["consent"]["task"])
            with self.lock:
                if self.cancelled.is_set() or self.closed or pending["auth_epoch"] != rpc.auth_epoch:
                    raise AppError("分析已取消或账号已变化；未保存草稿，已发送内容不能撤回", 409)
                provenance = {"provider": "codex", "endpoint": DESTINATION, "model": pending["config"]["model"], "source": source, "submitted_text": pending["consent"]["text"], "safety": EMERGENCY}
                return self.store.save_analysis(pending["consent"]["task"], result, provenance)
        except AppError:
            rpc.close()
            if self.cancelled.is_set():
                raise AppError("分析已取消；未保存本次草稿，已发送内容和额度无法撤回", 409) from None
            raise
        except Exception:
            rpc.close()
            raise AppError("Codex 返回不兼容的数据或保存失败；未自动重试，请检查本地草稿列表", 502) from None
        finally:
            with self.lock:
                self.busy = False
                self.operation = None

    def _complete(self, rpc, pending):
        deadline = time.monotonic() + TURN_TIMEOUT
        model = pending["config"]["model"]
        response = rpc.call("thread/start", {"model": model, "modelProvider": "openai", "cwd": str(rpc.workdir), "approvalPolicy": "never", "sandbox": "read-only", "ephemeral": True, "baseInstructions": pending["consent"]["system_prompt"]})
        if response.get("modelProvider") != "openai" or response.get("model") != model or response.get("approvalPolicy") != "never" or response.get("sandbox", {}).get("type") != "readOnly":
            raise AppError("Codex 未保持指定模型或隔离策略；未发送健康资料", 502)
        thread_id = text(response.get("thread", {}).get("id"), "线程标识", 160, True)
        inputs = []
        for part in pending["messages"][1]["content"]:
            if part["type"] == "text":
                inputs.append({"type": "text", "text": part["text"]})
            elif part["type"] == "image_url":
                inputs.append({"type": "image", "url": part["image_url"]["url"]})
            else:
                raise AppError("Codex 此版本仅支持文字与 JPG/PNG，不直传 PDF", 422)
        if self.cancelled.is_set() or pending["auth_epoch"] != rpc.auth_epoch:
            raise AppError("授权已取消或登录已变化", 409)
        started = rpc.call("turn/start", {"threadId": thread_id, "model": model, "input": inputs, "approvalPolicy": "never", "sandboxPolicy": {"type": "readOnly", "access": {"type": "restricted", "includePlatformDefaults": False, "readableRoots": [str(rpc.workdir)]}}, "outputSchema": output_schema(pending["consent"]["task"])})
        turn_id = text(started.get("turn", {}).get("id"), "轮次标识", 160, True)
        answers = {}
        try:
            while True:
                event = rpc.next_event(deadline)
                params = event.get("params", {})
                if not isinstance(params, dict) or params.get("threadId") != thread_id:
                    continue
                method = event.get("method")
                if method in ("item/started", "item/completed") and params.get("turnId") == turn_id:
                    item = params.get("item", {})
                    if item.get("type") not in ("userMessage", "agentMessage", "reasoning", "plan"):
                        raise AppError("模型尝试执行未授权工具，已停止分析", 502)
                    if method == "item/completed" and item.get("type") == "agentMessage" and item.get("phase") in (None, "final_answer"):
                        answer = text(item.get("text"), "模型输出", 50000, True)
                        answers[text(item.get("id"), "输出标识", 160, True)] = answer
                        if len(answers) > 4:
                            raise AppError("模型输出片段异常，未保存草稿", 502)
                if method == "turn/completed" and params.get("turn", {}).get("id") == turn_id:
                    if params["turn"].get("status") != "completed" or len(answers) != 1:
                        raise AppError("Codex 分析失败、被中断或缺少完整结果；未自动重试", 502)
                    return next(iter(answers.values()))
        finally:
            if rpc.alive:
                try:
                    rpc.call("thread/unsubscribe", {"threadId": thread_id}, timeout=3)
                except AppError:
                    rpc.close()

    def cancel(self, raw):
        approval = text(raw.get("approval_id"), "待取消请求", 100, True)
        with self.lock:
            if self.operation != approval or not self.busy:
                raise AppError("该分析已结束或不属于当前请求", 409)
            self.cancelled.set()
            self.invalidate()
            rpc = self.rpc
        if rpc:
            rpc.close()
        return {"ok": True, "notice": "已停止本地等待；服务商可能已经处理请求，无法撤回内容或额度"}

    def close(self):
        with self.lock:
            self.closed = True
            self.cancelled.set()
            self.invalidate()
            rpc = self.rpc
        if rpc:
            rpc.close()
