import datetime
import hmac
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import secrets
import time
import urllib.parse

from . import __version__
from .assistant import EMERGENCY, grounded_answer, model_answer, ollama_request
from .cloud import CloudAI
from .codex_ai import CodexAI
from .apple_health import MAX_UPLOAD
from .wearables import Wearables, summary as wearable_summary
from .food_journal import FoodJournal
from .departments import CATALOG
from .nutrition import BY_ID, MEALS, NOTICE, RECIPES, eligible, make_plan, restrictions, validate_plan
from .store import MAX_BACKUP, MAX_FILE, Store, encode
from .transfer import MAX_TRANSFER, export_transfer, read_transfer
from .validation import ALLERGENS, AppError, boolean, choice, date_value, strict_json_constant, text, unique_json_object


WEB = Path(__file__).resolve().parent / "web"


class JournalServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address, store, codex_executable=None):
        if address[0] != "127.0.0.1":
            raise ValueError("Only loopback binding is supported")
        self.store = store
        self.token = secrets.token_hex(32)
        self.cloud = CloudAI(store)
        self.codex = CodexAI(store, codex_executable)
        self.wearables = Wearables(store)
        self.food = FoodJournal(store)
        super().__init__(address, Handler)

    def server_close(self):
        self.codex.close()
        self.wearables.close()
        super().server_close()


class Handler(BaseHTTPRequestHandler):
    server_version = "HealthJournal/" + __version__
    sys_version = ""
    protocol_version = "HTTP/1.1"

    def setup(self):
        super().setup()
        self.connection.settimeout(20)

    def log_message(self, format_string, *arguments):
        pass

    def send(self, status, content, mime="application/json; charset=utf-8", filename=None):
        self.send_response(status)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Connection", "close")
        self.close_connection = True
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Cross-Origin-Resource-Policy", "same-origin")
        self.send_header("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' blob:; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'")
        if filename:
            self.send_header("Content-Disposition", "attachment; filename*=UTF-8''" + urllib.parse.quote(filename, safe=""))
        self.end_headers()
        self.wfile.write(content)

    def json_response(self, value, status=200):
        self.send(status, encode(value).encode("utf-8"))

    def guard(self, require_token=True):
        for header in ("Host", "Origin", "Sec-Fetch-Site", "X-Journal-Token", "Content-Type", "Content-Length", "X-Confirm-Transfer", "X-Filename"):
            if len(self.headers.get_all(header, [])) > 1:
                raise AppError("拒绝重复的请求头", 400)
        port = self.server.server_address[1]
        hosts = {"127.0.0.1:" + str(port), "localhost:" + str(port)}
        if self.headers.get("Host") not in hosts:
            raise AppError("仅允许本机地址访问", 403)
        origin = self.headers.get("Origin")
        if origin and origin not in {"http://" + host for host in hosts}:
            raise AppError("拒绝跨站请求", 403)
        if self.headers.get("Sec-Fetch-Site", "none") not in ("same-origin", "none"):
            raise AppError("拒绝跨站请求", 403)
        if require_token:
            supplied = self.headers.get("X-Journal-Token", "")
            if not supplied.isascii() or not hmac.compare_digest(supplied, self.server.token):
                raise AppError("本地会话已失效，请刷新页面", 401)

    def body(self, maximum=1024 * 1024):
        if self.headers.get("Transfer-Encoding"):
            raise AppError("不支持分块请求体", 400)
        lengths = self.headers.get_all("Content-Length", [])
        if len(lengths) != 1:
            raise AppError("请求长度缺失或重复", 411)
        try:
            size = int(lengths[0])
        except ValueError:
            raise AppError("请求长度无效")
        if not 0 <= size <= maximum:
            raise AppError("请求超过大小限制", 413)
        content = self.rfile.read(size)
        if len(content) != size:
            raise AppError("请求内容不完整")
        return content

    def json_body(self):
        if self.headers.get("Content-Type", "").split(";")[0] != "application/json":
            raise AppError("请求须使用 JSON", 415)
        try:
            raw = json.loads(self.body(), parse_constant=strict_json_constant, object_pairs_hook=unique_json_object)
        except (ValueError, UnicodeDecodeError, RecursionError):
            raise AppError("JSON 格式无效")
        if not isinstance(raw, dict):
            raise AppError("请求必须是 JSON 对象")
        return raw

    def apple_upload(self):
        if self.headers.get("Content-Type", "").split(";")[0] != "application/octet-stream" or self.headers.get("Transfer-Encoding"):
            raise AppError("Apple 导出须作为二进制文件上传", 415)
        try:
            size = int(self.headers.get("Content-Length", ""))
        except ValueError:
            raise AppError("缺少有效文件长度", 411)
        if not 0 < size <= MAX_UPLOAD:
            raise AppError("单个 ZIP/XML 最多 256 MiB；可以解压后选择主 XML，仍须遵守限额", 413)
        job = self.server.wearables.reserve(urllib.parse.unquote(self.headers.get("X-Filename", "")))
        try:
            path = Path(job["temporary"].name) / "input"
            digest = hashlib.sha256()
            remaining = size
            deadline = time.monotonic() + 180
            with path.open("xb") as output:
                while remaining:
                    if job["cancelled"].is_set() or time.monotonic() > deadline:
                        raise AppError("导入已取消", 409)
                    chunk = self.rfile.read(min(65536, remaining))
                    if not chunk:
                        raise AppError("文件上传不完整")
                    output.write(chunk)
                    digest.update(chunk)
                    remaining -= len(chunk)
            return self.server.wearables.launch(job, path, digest.hexdigest())
        except Exception:
            self.server.wearables.upload_failed(job)
            raise

    def do_GET(self):
        self.dispatch("GET")

    def do_POST(self):
        self.dispatch("POST")

    def do_PUT(self):
        self.dispatch("PUT")

    def do_DELETE(self):
        self.dispatch("DELETE")

    def do_OPTIONS(self):
        self.dispatch("OPTIONS")

    def dispatch(self, method):
        try:
            path = urllib.parse.urlsplit(self.path).path
            self.guard(require_token=path.startswith("/api/"))
            if not path.startswith("/api/"):
                if method != "GET":
                    raise AppError("不支持的方法", 405)
                assets = {"/": ("index.html", "text/html; charset=utf-8"), "/app.js": ("app.js", "text/javascript; charset=utf-8"), "/style.css": ("style.css", "text/css; charset=utf-8"), "/favicon.svg": ("favicon.svg", "image/svg+xml")}
                assets["/wearables.js"] = ("wearables.js", "text/javascript; charset=utf-8")
                assets["/daily.css"] = ("daily.css", "text/css; charset=utf-8")
                if path == "/phone/catalog.json":
                    self.json_response(CATALOG)
                    return
                for asset, mime in {"index.html": "text/html; charset=utf-8", "phone.css": "text/css; charset=utf-8", "phone.js": "text/javascript; charset=utf-8", "core.js": "text/javascript; charset=utf-8", "db.js": "text/javascript; charset=utf-8", "sw.js": "text/javascript; charset=utf-8", "manifest.webmanifest": "application/manifest+json", "icon.svg": "image/svg+xml", "LICENSE.txt": "text/plain; charset=utf-8"}.items():
                    assets["/phone/" + asset] = ("phone/" + asset, mime)
                assets["/phone/"] = ("phone/index.html", "text/html; charset=utf-8")
                if path not in assets:
                    raise AppError("页面不存在", 404)
                filename, mime = assets[path]
                content = (WEB / filename).read_bytes()
                if path == "/":
                    content = content.replace(b"__LOCAL_TOKEN__", self.server.token.encode())
                self.send(200, content, mime)
                return
            self.api(method, path)
        except AppError as error:
            self.close_connection = True
            self.json_response({"error": error.message}, error.status)
        except (BrokenPipeError, ConnectionResetError, TimeoutError):
            self.close_connection = True
        except Exception:
            self.close_connection = True
            self.json_response({"error": "本地处理失败，未能完成操作。请保留数据目录并检查磁盘空间或联系维护者。"}, 500)

    def api(self, method, path):
        store = self.server.store
        parts = path.strip("/").split("/")
        if method == "GET" and path == "/api/state":
            with store.lock:
                snapshot = {"version": __version__, "today": datetime.date.today().isoformat(), "profile": store.profile(), "profile_version": store.profile_version(), "records": store.records(), "documents": store.documents(), "plans": store.plans(), "recipes": RECIPES, "allergens": ALLERGENS, "nutrition_restrictions": restrictions(store.profile(), store.records()), "audits": store.audits(), "model": store.setting("model"), "demo": bool(store.setting("demo")), "data_directory": str(store.directory), "nutrition_notice": NOTICE, "safety": EMERGENCY, "departments": CATALOG, "analyses": store.analyses()}
                with store.connection() as database:
                    snapshot["wearables"] = wearable_summary(database)
            snapshot["cloud"] = self.server.cloud.config()
            snapshot["codex"] = self.server.codex.config()
            self.json_response(snapshot)
        elif path == "/api/wearables/import" and method == "POST":
            self.json_response(self.apple_upload(), 202)
        elif path == "/api/food" and method in ("POST", "PUT"):
            self.json_response(self.server.food.save(self.json_body(), update=method == "PUT"), 201 if method == "POST" else 200)
        elif path == "/api/food" and method == "DELETE":
            self.json_response(self.server.food.delete(self.json_body()))
        elif path in ("/api/food", "/api/day") and method == "GET":
            query = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query, keep_blank_values=True)
            allowed = {"from", "to"} if path == "/api/food" else {"date", "steps_source", "sleep_source", "heart_rate_source", "distance_source"}
            if set(query) - allowed or any(len(value) != 1 for value in query.values()):
                raise AppError("日记查询参数无效")
            values = {key: value[0] for key, value in query.items()}
            if path == "/api/food":
                self.json_response(self.server.food.entries(values.get("from", ""), values.get("to", "")))
            else:
                self.json_response(self.server.wearables.day(values.get("date", ""), {key.removesuffix("_source"): value for key, value in values.items() if key != "date"}))
        elif path == "/api/wearables/import" and method == "GET":
            self.json_response(self.server.wearables.status())
        elif path == "/api/wearables/import" and method == "DELETE":
            self.json_response(self.server.wearables.cancel(self.json_body().get("id")))
        elif path == "/api/wearables/commit" and method == "POST":
            self.json_response(self.server.wearables.commit(self.json_body()))
        elif path == "/api/wearables/batches" and method == "DELETE":
            self.json_response(self.server.wearables.delete(self.json_body()))
        elif path in ("/api/wearables", "/api/wearables/details") and method == "GET":
            query = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query, keep_blank_values=True)
            allowed = {"from", "to", "metric", "source"} if path == "/api/wearables" else {"day", "metric", "source", "offset"}
            if set(query) - allowed or any(len(value) != 1 for value in query.values()):
                raise AppError("健康数据查询参数无效")
            values = {key: value[0] for key, value in query.items()}
            if path == "/api/wearables":
                self.json_response(self.server.wearables.overview(values.get("from", ""), values.get("to", ""), values.get("metric", "steps"), values.get("source", "")))
            else:
                offset = values.get("offset", "0")
                if not offset.isascii() or not offset.isdigit():
                    raise AppError("分页参数无效")
                self.json_response(self.server.wearables.details(values.get("day", ""), values.get("metric", "steps"), values.get("source", ""), int(offset)))
        elif path == "/api/codex/config" and method == "PUT":
            self.json_response(self.server.codex.configure(self.json_body()))
        elif path == "/api/codex/prepare" and method == "POST":
            self.json_response(self.server.codex.prepare(self.json_body()))
        elif path == "/api/codex/run" and method == "POST":
            self.json_response(self.server.codex.run(self.json_body()))
        elif path == "/api/codex/cancel" and method == "POST":
            self.json_response(self.server.codex.cancel(self.json_body()))
        elif len(parts) == 3 and parts[1] == "codex" and parts[2] in ("connect", "login", "refresh", "cancel-login", "logout", "disconnect") and method == "POST":
            self.json_response(self.server.codex.control(parts[2], self.json_body()))
        elif path == "/api/ai/config" and method == "PUT":
            self.json_response(self.server.cloud.configure(self.json_body()))
        elif path == "/api/ai/key" and method == "DELETE":
            self.json_response(self.server.cloud.clear_key())
        elif path == "/api/ai/prepare" and method == "POST":
            self.json_response(self.server.cloud.prepare(self.json_body()))
        elif path == "/api/ai/run" and method == "POST":
            self.json_response(self.server.cloud.run(self.json_body()))
        elif len(parts) == 3 and parts[1] == "analyses" and method == "PUT":
            self.json_response(store.update_intake(parts[2], self.json_body()))
        elif len(parts) == 3 and parts[1] == "analyses" and method == "DELETE":
            store.delete_analysis(parts[2], self.json_body().get("version"))
            self.json_response({"ok": True})
        elif len(parts) == 4 and parts[1] == "documents" and parts[3] == "routing" and method == "PUT":
            self.json_response(store.route_document(parts[2], self.json_body()))
        elif path == "/api/profile" and method == "PUT":
            raw = self.json_body()
            expected = text(raw.get("_version", ""), "档案版本（请刷新页面）", 64, True)
            self.json_response(store.profile(raw, expected))
        elif path == "/api/records" and method == "POST":
            self.json_response(store.save_record(self.json_body()), 201)
        elif len(parts) == 3 and parts[1] == "records":
            if method == "PUT":
                self.json_response(store.save_record(self.json_body(), parts[2]))
            elif method == "DELETE":
                store.delete_record(parts[2], self.json_body().get("version"))
                self.json_response({"ok": True})
            else:
                raise AppError("不支持的方法", 405)
        elif path == "/api/documents" and method == "POST":
            filename = urllib.parse.unquote(self.headers.get("X-Filename", ""))
            self.json_response(store.add_document(filename, self.body(MAX_FILE)), 201)
        elif path == "/api/transfer" and method == "GET":
            self.send(200, export_transfer(store), "application/octet-stream", "health-journal.hj-transfer.json")
        elif path == "/api/transfer" and method == "POST":
            if self.headers.get("X-Confirm-Transfer") != "append-originals":
                raise AppError("请确认只新增原件；互传不含病历、模型密钥或餐单", 400)
            if self.headers.get("Content-Type", "").split(";")[0] != "application/json":
                raise AppError("资料互传须使用 JSON", 415)
            self.json_response(store.merge_documents(read_transfer(self.body(MAX_TRANSFER))))
        elif len(parts) == 3 and parts[1] == "documents":
            if method == "GET":
                item, content = store.get_document(parts[2])
                self.send(200, content, item["mime"], item["filename"])
            elif method == "DELETE":
                store.delete_document(parts[2])
                self.json_response({"ok": True})
            else:
                raise AppError("不支持的方法", 405)
        elif path == "/api/backup" and method == "GET":
            self.send(200, store.backup(), "application/zip", "健康手记备份-" + datetime.date.today().isoformat() + ".zip")
        elif path == "/api/restore" and method == "POST":
            if self.headers.get("X-Confirm-Restore") != "empty-vault":
                raise AppError("恢复需明确确认")
            self.json_response(store.restore(self.body(MAX_BACKUP)))
        elif path == "/api/plans" and method == "POST":
            raw = self.json_body()
            day = date_value(raw.get("date", ""), "餐单日期", True)
            with store.lock:
                existing = next((plan for plan in store.plans() if plan["date"] == day), None)
                if existing and any(item["eaten"] or item["note"] for item in existing["meals"].values()):
                    raise AppError("此餐单已有实际饮食记录，不会被重新生成覆盖。可单独替换未记录的一餐", 409)
                revision = existing["revision"] + 1 if existing else 0
                plan = make_plan(day, store.profile(), store.records(), revision)
                self.json_response(store.save_plan(plan))
        elif len(parts) == 3 and parts[1] == "plans" and method == "PUT":
            day = date_value(parts[2], "餐单日期", True)
            raw = self.json_body()
            meal = choice(raw.get("meal"), MEALS, "餐次")
            with store.lock:
                plan = next((item for item in store.plans() if item["date"] == day), None)
                if not plan:
                    raise AppError("餐单不存在", 404)
                if type(raw.get("revision")) is not int or raw["revision"] != plan["revision"]:
                    raise AppError("餐单已修改，请刷新后重试", 409)
                if boolean(raw.get("swap", False), "替换餐单选项"):
                    if plan["meals"][meal]["eaten"] or plan["meals"][meal]["note"]:
                        raise AppError("已有实际饮食记录的一餐不能替换", 409)
                    profile = store.profile()
                    reasons = restrictions(profile, store.records())
                    if reasons:
                        raise AppError("；".join(reasons), 422)
                    candidates = [recipe for recipe in RECIPES if recipe["meal"] == meal and recipe["id"] != plan["meals"][meal]["recipe_id"] and eligible(recipe, profile)]
                    if not candidates:
                        raise AppError("当前限制下没有可替换菜谱", 422)
                    plan["meals"][meal]["recipe_id"] = candidates[plan["revision"] % len(candidates)]["id"]
                else:
                    eaten = boolean(raw.get("eaten", False), "用餐状态")
                    note = text(raw.get("note", ""), "实际饮食备注", 1000)
                    if (eaten or note) and day > datetime.date.today().isoformat():
                        raise AppError("实际饮食不能记录在未来日期；未来餐单仅用于计划")
                    plan["meals"][meal]["eaten"] = eaten
                    plan["meals"][meal]["note"] = note
                plan["revision"] += 1
                self.json_response(store.save_plan(validate_plan(plan)))
        elif path == "/api/assistant" and method == "POST":
            raw = self.json_body()
            question = text(raw.get("question", ""), "问题", 1000, True)
            if boolean(raw.get("use_model", False), "本机模型使用选项"):
                self.json_response(model_answer(question, store.records(), store.setting("model") or ""))
            else:
                self.json_response(grounded_answer(question, store.records()))
        elif path == "/api/models" and method == "GET":
            response = ollama_request("tags")
            models = response.get("models", [])
            if not isinstance(models, list):
                raise AppError("本机模型列表格式无效", 502)
            names = [item.get("name") for item in models if isinstance(item, dict) and isinstance(item.get("name"), str)]
            self.json_response({"models": names[:100]})
        elif path == "/api/model" and method == "PUT":
            model = text(self.json_body().get("model", ""), "模型名称", 120)
            self.json_response({"model": store.set_setting("model", model)})
        else:
            raise AppError("接口不存在", 404)


def create_server(directory, port=8765, codex_executable=None):
    return JournalServer(("127.0.0.1", port), Store(directory), codex_executable)
