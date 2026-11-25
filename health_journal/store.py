import contextlib
import datetime
import hashlib
import io
import json
import os
from pathlib import Path
import re
import sqlite3
import threading
import uuid
import zipfile
import zlib

from .validation import AppError, boolean, identifier, safe_filename, strict_json_constant, timestamp_value, unique_json_object, validate_profile, validate_record
from .departments import suggest_departments, validate_routing
from .wearables import SCHEMA as WEARABLE_SCHEMA, export_backup as export_wearable_backup, validate_backup as validate_wearable_backup
from .food_journal import SCHEMA as FOOD_SCHEMA, FoodJournal, validate_food


MAX_FILE = 20 * 1024 * 1024
MAX_BACKUP = 64 * 1024 * 1024
MAX_EXPANDED = 60 * 1024 * 1024
DEFAULT_PROFILE = validate_profile({})


def timestamp():
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


def encode(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":"))


def check_document(filename, content):
    filename = safe_filename(filename)
    if not content or len(content) > MAX_FILE:
        raise AppError("文件为空或超过 20 MB 限制", 413)
    suffix = Path(filename).suffix.lower()
    signatures = {".pdf": (b"%PDF-", "application/pdf"), ".png": (b"\x89PNG\r\n\x1a\n", "image/png"), ".jpg": (b"\xff\xd8\xff", "image/jpeg"), ".jpeg": (b"\xff\xd8\xff", "image/jpeg")}
    if suffix == ".txt":
        try:
            decoded = content.decode("utf-8-sig")
        except UnicodeDecodeError:
            raise AppError("文字文件须使用 UTF-8 编码")
        if "\x00" in decoded:
            raise AppError("文字文件含无效字符")
        return filename, "text/plain"
    if suffix not in signatures:
        raise AppError("支持 PDF、PNG、JPG 和 UTF-8 TXT；不接受可执行文件或网页")
    signature, mime = signatures[suffix]
    if not content.startswith(signature):
        raise AppError("文件内容与扩展名不一致")
    return filename, mime


class Store:
    def __init__(self, directory):
        self.directory = Path(directory).expanduser().resolve()
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.files = self.directory / "attachments"
        self.files.mkdir(exist_ok=True, mode=0o700)
        self.database = self.directory / "journal.sqlite3"
        self.lock = threading.RLock()
        with self.connection() as database:
            version = database.execute("PRAGMA user_version").fetchone()[0]
            if version not in (0, 1, 2, 3, 4):
                raise AppError("数据库版本高于当前程序，请使用相应版本，不要覆盖原库")
            database.executescript("""
                CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS documents (
                    id TEXT PRIMARY KEY, filename TEXT NOT NULL, mime TEXT NOT NULL,
                    sha256 TEXT UNIQUE NOT NULL, size INTEGER NOT NULL, created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS records (
                    id TEXT PRIMARY KEY, kind TEXT NOT NULL, title TEXT NOT NULL,
                    date TEXT NOT NULL, department TEXT NOT NULL, topic TEXT NOT NULL,
                    notes TEXT NOT NULL, source_label TEXT NOT NULL,
                    document_id TEXT REFERENCES documents(id) ON DELETE RESTRICT,
                    verification TEXT NOT NULL, data TEXT NOT NULL,
                    version INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL, updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS records_date ON records(date DESC);
                CREATE INDEX IF NOT EXISTS records_kind ON records(kind);
                CREATE TABLE IF NOT EXISTS meal_plans (
                    date TEXT PRIMARY KEY, data TEXT NOT NULL, updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS audit (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, at TEXT NOT NULL,
                    action TEXT NOT NULL, entity TEXT NOT NULL, entity_id TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS document_routes (
                    document_id TEXT PRIMARY KEY REFERENCES documents(id) ON DELETE CASCADE,
                    data TEXT NOT NULL, version INTEGER NOT NULL DEFAULT 1
                );
                CREATE TABLE IF NOT EXISTS analyses (
                    id TEXT PRIMARY KEY, task TEXT NOT NULL, result TEXT NOT NULL,
                    provenance TEXT NOT NULL, document_id TEXT REFERENCES documents(id) ON DELETE RESTRICT,
                    intake TEXT NOT NULL, version INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL
                );
            """)
            database.executescript(WEARABLE_SCHEMA + FOOD_SCHEMA + "PRAGMA user_version = 4;")
            database.execute("INSERT OR IGNORE INTO settings VALUES (?, ?)", ("profile", encode(DEFAULT_PROFILE)))
            database.execute("INSERT OR IGNORE INTO settings VALUES (?, ?)", ("model", encode("")))
            for doc in database.execute("SELECT * FROM documents WHERE id NOT IN (SELECT document_id FROM document_routes)").fetchall():
                content = b""
                if doc["mime"] == "text/plain":
                    try:
                        with (self.files / doc["sha256"]).open("rb") as attachment:
                            content = attachment.read(MAX_FILE + 1)
                        if len(content) != doc["size"] or len(content) > MAX_FILE or hashlib.sha256(content).hexdigest() != doc["sha256"]:
                            content = b""
                    except OSError:
                        pass
                routing = suggest_departments(doc["filename"], content.decode("utf-8-sig", errors="replace"))
                database.execute("INSERT INTO document_routes VALUES (?,?,1)", (doc["id"], encode(routing)))
        os.chmod(self.database, 0o600)

    @contextlib.contextmanager
    def connection(self):
        database = sqlite3.connect(str(self.database), timeout=15)
        database.row_factory = sqlite3.Row
        database.execute("PRAGMA foreign_keys = ON")
        try:
            with database:
                yield database
        finally:
            database.close()

    def audit(self, database, action, entity, entity_id):
        database.execute("INSERT INTO audit(at,action,entity,entity_id) VALUES (?,?,?,?)", (timestamp(), action, entity, entity_id))

    def setting(self, key):
        with self.lock, self.connection() as database:
            row = database.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
            return json.loads(row["value"]) if row else None

    def set_setting(self, key, value):
        with self.lock, self.connection() as database:
            database.execute("INSERT OR REPLACE INTO settings VALUES (?,?)", (key, encode(value)))
            self.audit(database, "update", "settings", key)
        return value

    def profile_version(self):
        return hashlib.sha256(encode(self.profile()).encode("utf-8")).hexdigest()

    def profile(self, value=None, expected=None):
        if value is not None:
            with self.lock:
                if expected is not None and expected != self.profile_version():
                    raise AppError("档案设置已在其他窗口修改，请刷新后核对再保存", 409)
                return self.set_setting("profile", validate_profile(value))
        return self.setting("profile")

    @staticmethod
    def unpack(row):
        item = dict(row)
        item["data"] = json.loads(item["data"])
        return item

    def records(self):
        with self.lock, self.connection() as database:
            return [self.unpack(row) for row in database.execute("SELECT * FROM records ORDER BY date DESC,created_at DESC,id")]

    def get_record(self, record_id):
        identifier(record_id)
        with self.lock, self.connection() as database:
            row = database.execute("SELECT * FROM records WHERE id=?", (record_id,)).fetchone()
            if not row:
                raise AppError("记录不存在", 404)
            return self.unpack(row)

    def save_record(self, raw, record_id=None):
        item = validate_record(raw)
        now = timestamp()
        with self.lock, self.connection() as database:
            if item["document_id"] and not database.execute("SELECT id FROM documents WHERE id=?", (item["document_id"],)).fetchone():
                raise AppError("关联的原始文件不存在")
            if record_id:
                identifier(record_id)
                old = database.execute("SELECT * FROM records WHERE id=?", (record_id,)).fetchone()
                if not old:
                    raise AppError("记录不存在", 404)
                if type(raw.get("version")) is not int or raw["version"] != old["version"]:
                    raise AppError("记录已在其他窗口修改，请重新打开后再保存", 409)
                item.update(id=record_id, version=old["version"] + 1, created_at=old["created_at"], updated_at=now)
                fields = [key for key in item if key != "id"]
                database.execute("UPDATE records SET " + ",".join(key + "=?" for key in fields) + " WHERE id=?", [encode(item[key]) if key == "data" else item[key] for key in fields] + [record_id])
                self.audit(database, "update", item["kind"], record_id)
            else:
                item.update(id=str(uuid.uuid4()), version=1, created_at=now, updated_at=now)
                self.insert_record(database, item)
                self.audit(database, "create", item["kind"], item["id"])
        return item

    @staticmethod
    def insert_record(database, item):
        keys = list(item)
        database.execute("INSERT INTO records (" + ",".join(keys) + ") VALUES (" + ",".join("?" for key in keys) + ")", [encode(item[key]) if key == "data" else item[key] for key in keys])

    def delete_record(self, record_id, version):
        identifier(record_id)
        with self.lock, self.connection() as database:
            row = database.execute("SELECT kind,version FROM records WHERE id=?", (record_id,)).fetchone()
            if not row:
                raise AppError("记录不存在", 404)
            if type(version) is not int or row["version"] != version:
                raise AppError("记录已修改，请刷新后重试", 409)
            database.execute("DELETE FROM records WHERE id=?", (record_id,))
            self.audit(database, "delete", row["kind"], record_id)

    def documents(self):
        with self.lock, self.connection() as database:
            rows = database.execute("SELECT d.*, ((SELECT COUNT(*) FROM records r WHERE r.document_id=d.id) + (SELECT COUNT(*) FROM food_entries f WHERE f.document_id=d.id)) AS links, routes.data AS routing_data, routes.version AS routing_version FROM documents d LEFT JOIN document_routes routes ON routes.document_id=d.id ORDER BY created_at DESC,id").fetchall()
            documents = []
            for row in rows:
                item = dict(row)
                routing = item.pop("routing_data")
                item["routing"] = json.loads(routing) if routing else suggest_departments(item["filename"])
                documents.append(item)
            return documents

    def route_document(self, document_id, raw):
        identifier(document_id)
        routing = validate_routing(raw)
        with self.lock, self.connection() as database:
            current = database.execute("SELECT version FROM document_routes WHERE document_id=?", (document_id,)).fetchone()
            if not current:
                raise AppError("原件不存在", 404)
            if type(raw.get("version")) is not int or raw["version"] != current["version"]:
                raise AppError("科室关联已修改，请刷新后重新核对", 409)
            routing["status"] = "confirmed"
            routing["method"] = "manual" if raw.get("method") != "ai-reviewed" else "ai-reviewed"
            database.execute("UPDATE document_routes SET data=?,version=version+1 WHERE document_id=?", (encode(routing), document_id))
            self.audit(database, "update", "document_routes", document_id)
        return routing

    def add_document(self, filename, content):
        filename, mime = check_document(filename, content)
        digest = hashlib.sha256(content).hexdigest()
        with self.lock, self.connection() as database:
            existing = database.execute("SELECT * FROM documents WHERE sha256=?", (digest,)).fetchone()
            if existing:
                self.get_document(existing["id"])
                return {**dict(existing), "duplicate": True}
            item = {"id": str(uuid.uuid4()), "filename": filename, "mime": mime, "sha256": digest, "size": len(content), "created_at": timestamp()}
            path = self.files / digest
            self.write_attachment(path, content)
            database.execute("INSERT INTO documents VALUES (?,?,?,?,?,?)", tuple(item.values()))
            routing = suggest_departments(filename, content.decode("utf-8-sig", errors="replace") if mime == "text/plain" else "")
            database.execute("INSERT INTO document_routes VALUES (?,?,1)", (item["id"], encode(routing)))
            self.audit(database, "import", "document", item["id"])
        return {**item, "duplicate": False}

    @staticmethod
    def write_attachment(path, content):
        temporary = path.with_name(".pending-" + str(uuid.uuid4()))
        try:
            with temporary.open("xb") as output:
                os.chmod(temporary, 0o600)
                output.write(content)
                output.flush()
                os.fsync(output.fileno())
            os.replace(temporary, path)
        finally:
            with contextlib.suppress(FileNotFoundError):
                temporary.unlink()

    def merge_documents(self, entries):
        approved = [(check_document(filename, content), content, hashlib.sha256(content).hexdigest()) for filename, content in entries]
        added, duplicates, written = 0, 0, []
        with self.lock:
            try:
                with self.connection() as database:
                    for (filename, mime), content, digest in approved:
                        existing = database.execute("SELECT id FROM documents WHERE sha256=?", (digest,)).fetchone()
                        if existing:
                            self.get_document(existing["id"])
                            duplicates += 1
                            continue
                        item = (str(uuid.uuid4()), filename, mime, digest, len(content), timestamp())
                        destination = self.files / digest
                        self.write_attachment(destination, content)
                        written.append(destination)
                        database.execute("INSERT INTO documents VALUES (?,?,?,?,?,?)", item)
                        routing = suggest_departments(filename, content.decode("utf-8-sig", errors="replace") if mime == "text/plain" else "")
                        database.execute("INSERT INTO document_routes VALUES (?,?,1)", (item[0], encode(routing)))
                        self.audit(database, "import", "document", item[0])
                        added += 1
            except Exception:
                for destination in written:
                    with contextlib.suppress(OSError):
                        destination.unlink()
                raise
        return {"imported": added, "duplicates": duplicates}

    def get_document(self, document_id):
        identifier(document_id)
        with self.lock, self.connection() as database:
            row = database.execute("SELECT * FROM documents WHERE id=?", (document_id,)).fetchone()
            if not row:
                raise AppError("原始文件不存在", 404)
            item = dict(row)
            try:
                with (self.files / item["sha256"]).open("rb") as attachment:
                    content = attachment.read(MAX_FILE + 1)
            except FileNotFoundError:
                raise AppError("附件文件缺失，请从备份恢复", 409)
            if len(content) != item["size"] or len(content) > MAX_FILE or hashlib.sha256(content).hexdigest() != item["sha256"]:
                raise AppError("附件完整性检查失败，请保留原文件并从备份恢复", 409)
            return item, content

    def delete_document(self, document_id):
        identifier(document_id)
        with self.lock:
            with self.connection() as database:
                row = database.execute("SELECT * FROM documents WHERE id=?", (document_id,)).fetchone()
                if not row:
                    raise AppError("原始文件不存在", 404)
                if database.execute("SELECT id FROM records WHERE document_id=? LIMIT 1", (document_id,)).fetchone():
                    raise AppError("此原件仍被记录引用，请先解除关联，防止丢失依据", 409)
                if database.execute("SELECT id FROM analyses WHERE document_id=? LIMIT 1", (document_id,)).fetchone():
                    raise AppError("此原件仍被 AI 草稿引用，请先删除对应草稿，防止丢失依据", 409)
                if database.execute("SELECT id FROM food_entries WHERE document_id=? LIMIT 1", (document_id,)).fetchone():
                    raise AppError("此原件仍被饮食日记引用，请先编辑日记解除关联", 409)
                database.execute("DELETE FROM documents WHERE id=?", (document_id,))
                self.audit(database, "delete", "document", document_id)
            with contextlib.suppress(FileNotFoundError):
                (self.files / row["sha256"]).unlink()

    def plans(self):
        with self.lock, self.connection() as database:
            return [json.loads(row["data"]) for row in database.execute("SELECT data FROM meal_plans ORDER BY date DESC")]

    def save_plan(self, plan):
        with self.lock, self.connection() as database:
            database.execute("INSERT OR REPLACE INTO meal_plans VALUES (?,?,?)", (plan["date"], encode(plan), timestamp()))
            self.audit(database, "update", "meal_plan", plan["date"])
        return plan

    def audits(self):
        with self.lock, self.connection() as database:
            return [dict(row) for row in database.execute("SELECT * FROM audit ORDER BY id DESC LIMIT 100")]

    def analyses(self):
        with self.lock, self.connection() as database:
            results = []
            for row in database.execute("SELECT * FROM analyses ORDER BY created_at DESC,id"):
                item = dict(row)
                for key in ("result", "provenance", "intake"):
                    item[key] = json.loads(item[key])
                results.append(item)
            return results

    def save_analysis(self, task, result, provenance):
        from .cloud import validate_analysis
        item = validate_analysis({"id": str(uuid.uuid4()), "task": task, "result": result, "provenance": provenance, "document_id": provenance["source"]["id"] if provenance.get("source") else None, "intake": {}, "version": 1, "created_at": timestamp()})
        with self.lock, self.connection() as database:
            if item["document_id"] and not database.execute("SELECT id FROM documents WHERE id=?", (item["document_id"],)).fetchone():
                raise AppError("分析期间原件已被删除，草稿未入库。服务商可能已计费，请保留原件后再试", 409)
            self.insert_analysis(database, item)
            self.audit(database, "create", "ai_draft", item["id"])
        return item

    @staticmethod
    def insert_analysis(database, item):
        database.execute("INSERT INTO analyses VALUES (?,?,?,?,?,?,?,?)", (item["id"], item["task"], encode(item["result"]), encode(item["provenance"]), item["document_id"], encode(item["intake"]), item["version"], item["created_at"]))

    def update_intake(self, analysis_id, raw):
        from .cloud import validate_intake
        identifier(analysis_id)
        intake = validate_intake(raw)
        with self.lock, self.connection() as database:
            row = database.execute("SELECT task,version FROM analyses WHERE id=?", (analysis_id,)).fetchone()
            if not row:
                raise AppError("草稿不存在", 404)
            if row["task"] != "breakfast":
                raise AppError("只有饮食分析可关联实际饮食")
            if type(raw.get("version")) is not int or row["version"] != raw["version"]:
                raise AppError("饮食记录已修改，请刷新", 409)
            database.execute("UPDATE analyses SET intake=?,version=version+1 WHERE id=?", (encode(intake), analysis_id))
            self.audit(database, "update", "food_intake", analysis_id)
        return intake

    def delete_analysis(self, analysis_id, version):
        identifier(analysis_id)
        with self.lock, self.connection() as database:
            row = database.execute("SELECT version FROM analyses WHERE id=?", (analysis_id,)).fetchone()
            if not row:
                raise AppError("草稿不存在", 404)
            if type(version) is not int or version != row["version"]:
                raise AppError("草稿已修改，请刷新", 409)
            database.execute("DELETE FROM analyses WHERE id=?", (analysis_id,))
            self.audit(database, "delete", "ai_draft", analysis_id)

    def backup(self):
        with self.lock:
            documents = self.documents()
            manifest = {"format": "health-journal", "version": 2, "created_at": timestamp(), "demo": bool(self.setting("demo")), "profile": self.profile(), "records": self.records(), "documents": [{key: value for key, value in item.items() if key != "links"} for item in documents], "meal_plans": self.plans(), "analyses": self.analyses()}
            with self.connection() as database:
                wearable_bytes = export_wearable_backup(database)
            if wearable_bytes:
                manifest.update(version=3, wearable={"path": "wearable.jsonl", "sha256": hashlib.sha256(wearable_bytes).hexdigest()})
            food_entries = FoodJournal(self).entries()
            if food_entries:
                manifest.update(version=4, food_entries=food_entries)
            manifest_bytes = encode(manifest).encode("utf-8")
            if len(documents) > 500 or len(manifest["records"]) > 10000 or len(manifest["meal_plans"]) > 3660 or len(manifest["analyses"]) > 2000 or len(manifest_bytes) > 4 * 1024 * 1024 or len(wearable_bytes) + len(manifest_bytes) + sum(item["size"] for item in documents) > MAX_EXPANDED:
                raise AppError("超出便携 ZIP 恢复范围（解压后 60 MB、500 份原件、10000 条记录）。请停止应用后完整复制资料目录进行备份，不要删除原件", 413)
            output = io.BytesIO()
            with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
                archive.writestr("manifest.json", manifest_bytes)
                if wearable_bytes:
                    archive.writestr("wearable.jsonl", wearable_bytes)
                for document in documents:
                    metadata, content = self.get_document(document["id"])
                    archive.writestr("attachments/" + metadata["sha256"], content)
            if output.tell() > MAX_BACKUP:
                raise AppError("ZIP 超过恢复大小限制，请停止应用后完整复制资料目录", 413)
            with self.connection() as database:
                self.audit(database, "export", "backup", "local")
            return output.getvalue()

    def restore(self, content):
        from .nutrition import validate_plan
        from .cloud import validate_analysis
        if len(content) > MAX_BACKUP:
            raise AppError("备份超过 64 MB 限制", 413)
        wearable_database = None
        try:
            archive = zipfile.ZipFile(io.BytesIO(content))
            with archive:
                infos = archive.infolist()
                names = [entry.filename for entry in infos]
                if len(infos) > 502 or len(names) != len(set(names)) or sum(entry.file_size for entry in infos) > MAX_EXPANDED:
                    raise AppError("备份条目重复、过多或解压后超过限制")
                if "manifest.json" not in names or archive.getinfo("manifest.json").file_size > 4 * 1024 * 1024:
                    raise AppError("备份清单缺失或过大")
                manifest = json.loads(archive.read("manifest.json"), parse_constant=strict_json_constant, object_pairs_hook=unique_json_object)
                if manifest.get("format") != "health-journal" or type(manifest.get("version")) is not int or manifest["version"] not in (1, 2, 3, 4):
                    raise AppError("不支持的备份格式或版本")
                if manifest["version"] >= 2 and "analyses" not in manifest:
                    raise AppError("v2 备份缺少分析草稿清单，拒绝不完整恢复")
                demo = boolean(manifest.get("demo", False), "演示标记")
                profile = validate_profile(manifest["profile"])
                docs = manifest["documents"]
                records = manifest["records"]
                plans = manifest["meal_plans"]
                analyses = manifest.get("analyses", [])
                if not isinstance(analyses, list) or len(analyses) > 2000:
                    raise AppError("分析草稿格式或数量无效")
                if not all(isinstance(items, list) for items in (docs, records, plans)) or len(docs) > 500 or len(records) > 10000 or len(plans) > 3660:
                    raise AppError("备份数据数量或结构无效")
                approved_docs, approved_records, approved_plans = [], [], []
                ids, digests, record_ids, plan_dates = set(), set(), set(), set()
                approved_routes, approved_analyses = {}, []
                approved_food, food_ids = [], set()
                food_entries = manifest.get("food_entries", [])
                if manifest["version"] == 4 and "food_entries" not in manifest or manifest["version"] < 4 and "food_entries" in manifest or not isinstance(food_entries, list) or len(food_entries) > 10000:
                    raise AppError("饮食日记备份清单缺失、数量过多或版本不兼容")
                for item in docs:
                    if manifest["version"] >= 2 and ("routing" not in item or "routing_version" not in item):
                        raise AppError("v2 备份缺少科室关联信息")
                    document_id = identifier(item["id"])
                    digest = item["sha256"]
                    if not isinstance(digest, str) or not re.fullmatch("[a-f0-9]{64}", digest) or document_id in ids or digest in digests:
                        raise AppError("备份附件标识重复或无效")
                    file_content = archive.read("attachments/" + digest)
                    filename, mime = check_document(item["filename"], file_content)
                    if hashlib.sha256(file_content).hexdigest() != digest or type(item["size"]) is not int or item["size"] != len(file_content) or item["mime"] != mime:
                        raise AppError("备份附件校验失败，未恢复任何数据")
                    ids.add(document_id)
                    digests.add(digest)
                    approved_docs.append(({"id": document_id, "filename": filename, "mime": mime, "sha256": digest, "size": len(file_content), "created_at": timestamp_value(item["created_at"])}, file_content))
                    routing = validate_routing(item["routing"]) if "routing" in item else suggest_departments(filename, file_content.decode("utf-8-sig", errors="replace") if mime == "text/plain" else "")
                    route_version = item.get("routing_version", 1)
                    if type(route_version) is not int or not 1 <= route_version <= 1000000000:
                        raise AppError("科室分类版本无效")
                    approved_routes[document_id] = (routing, route_version)
                has_wearables = manifest["version"] == 3 or manifest["version"] == 4 and "wearable" in manifest
                if set(names) != {"manifest.json"} | {"attachments/" + digest for digest in digests} | ({"wearable.jsonl"} if has_wearables else set()):
                    raise AppError("备份包含不允许的路径或额外文件")
                for item in records:
                    clean = validate_record(item)
                    record_id = identifier(item["id"])
                    if record_id in record_ids or clean["document_id"] and clean["document_id"] not in ids:
                        raise AppError("记录标识重复或引用了缺失附件")
                    if type(item.get("version")) is not int or not 1 <= item["version"] <= 1000000000:
                        raise AppError("记录版本无效")
                    created = timestamp_value(item["created_at"])
                    updated = timestamp_value(item["updated_at"])
                    if datetime.datetime.fromisoformat(updated) < datetime.datetime.fromisoformat(created):
                        raise AppError("修改时间不能早于创建时间")
                    clean.update(id=record_id, version=item["version"], created_at=created, updated_at=updated)
                    record_ids.add(record_id)
                    approved_records.append(clean)
                for plan in plans:
                    clean = validate_plan(plan)
                    if clean["date"] in plan_dates:
                        raise AppError("餐单日期重复")
                    plan_dates.add(clean["date"])
                    approved_plans.append(clean)
                analysis_ids = set()
                for item in analyses:
                    clean = validate_analysis(item)
                    if clean["id"] in analysis_ids or clean["document_id"] and clean["document_id"] not in ids:
                        raise AppError("分析草稿标识重复或缺少原件")
                    if clean["document_id"]:
                        original = next(doc for doc, content in approved_docs if doc["id"] == clean["document_id"])
                        if any(clean["provenance"]["source"][field] != original[field] for field in ("sha256", "filename", "mime", "size")):
                            raise AppError("分析草稿来源与原件不匹配")
                    analysis_ids.add(clean["id"])
                    approved_analyses.append(clean)
                for item in food_entries:
                    clean = validate_food(item, saved=True)
                    if clean["id"] in food_ids or clean["document_id"] and clean["document_id"] not in ids:
                        raise AppError("饮食日记标识重复或缺少关联原件")
                    food_ids.add(clean["id"])
                    approved_food.append(clean)
                if has_wearables:
                    metadata = manifest["wearable"]
                    if not isinstance(metadata, dict) or set(metadata) != {"path", "sha256"} or metadata["path"] != "wearable.jsonl" or archive.getinfo("wearable.jsonl").file_size > 40 * 1024 * 1024:
                        raise AppError("健康样本备份清单无效")
                    wearable_bytes = archive.read("wearable.jsonl")
                    if hashlib.sha256(wearable_bytes).hexdigest() != metadata["sha256"]:
                        raise AppError("健康样本备份校验失败")
                    wearable_database = validate_wearable_backup(wearable_bytes)
        except AppError:
            raise
        except (zipfile.BadZipFile, zlib.error, KeyError, ValueError, TypeError, AttributeError, RuntimeError, NotImplementedError, EOFError, RecursionError):
            raise AppError("备份文件无效或已损坏，未恢复任何数据")
        written_paths = []
        with self.lock:
            try:
                with self.connection() as database:
                    occupied = any(database.execute("SELECT COUNT(*) FROM " + table).fetchone()[0] for table in ("records", "documents", "meal_plans", "analyses", "wearable_samples", "wearable_batches", "food_entries"))
                    existing_profile = json.loads(database.execute("SELECT value FROM settings WHERE key='profile'").fetchone()[0])
                    if occupied or existing_profile != DEFAULT_PROFILE:
                        raise AppError("为避免覆盖资料，只能恢复到全新空档案。请以新的 --data-dir 启动后恢复", 409)
                    for item, file_content in approved_docs:
                        path = self.files / item["sha256"]
                        self.write_attachment(path, file_content)
                        written_paths.append(path)
                        database.execute("INSERT INTO documents VALUES (?,?,?,?,?,?)", tuple(item.values()))
                        routing, route_version = approved_routes[item["id"]]
                        database.execute("INSERT INTO document_routes VALUES (?,?,?)", (item["id"], encode(routing), route_version))
                    for item in approved_records:
                        self.insert_record(database, item)
                    for plan in approved_plans:
                        database.execute("INSERT INTO meal_plans VALUES (?,?,?)", (plan["date"], encode(plan), timestamp()))
                    for item in approved_analyses:
                        self.insert_analysis(database, item)
                    for item in approved_food:
                        FoodJournal.insert(database, item)
                    if wearable_database:
                        for table, columns in (("wearable_batches", 6), ("wearable_samples", 16), ("wearable_members", 2)):
                            database.executemany("INSERT INTO " + table + " VALUES (" + ",".join("?" for column in range(columns)) + ")", wearable_database.execute("SELECT * FROM " + table))
                    database.execute("UPDATE settings SET value=? WHERE key='profile'", (encode(profile),))
                    database.execute("INSERT OR REPLACE INTO settings VALUES ('demo',?)", (encode(demo),))
                    self.audit(database, "restore", "backup", "validated")
            except Exception:
                for path in written_paths:
                    with contextlib.suppress(FileNotFoundError):
                        path.unlink()
                raise
            finally:
                if wearable_database:
                    wearable_database.close()
        return {"records": len(approved_records), "documents": len(approved_docs), "meal_plans": len(approved_plans), "analyses": len(approved_analyses), "food_entries": len(approved_food)}
