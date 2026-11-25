import collections
import contextlib
import datetime
import hashlib
import io
import itertools
import json
import re
import secrets
import sqlite3
import tempfile
import threading
import time
import uuid

from .apple_health import FIELDS, INSERT_SQL, MAX_SAMPLES, METRICS, TABLE_SQL, apple_date, catalog, digest, finite, normalized, parse_export
from .validation import AppError, date_value, identifier, strict_json_constant, text, timestamp_value, unique_json_object
from .food_journal import FoodJournal


BACKUP_LIMIT = 40 * 1024 * 1024
BATCH_FIELDS = ("id", "filename", "sha256", "created_at", "selection", "samples")
SCHEMA = TABLE_SQL + """
CREATE TABLE IF NOT EXISTS wearable_batches (
    id TEXT PRIMARY KEY, filename TEXT NOT NULL, sha256 TEXT NOT NULL,
    created_at TEXT NOT NULL, selection TEXT NOT NULL, samples INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS wearable_members (
    batch_id TEXT REFERENCES wearable_batches(id) ON DELETE CASCADE,
    sample_id TEXT REFERENCES wearable_samples(id) ON DELETE CASCADE,
    PRIMARY KEY(batch_id, sample_id)
);
"""


def stamp():
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


def summary(database):
    rows = database.execute("SELECT metric,COUNT(*) AS count,MIN(day) AS first,MAX(day) AS last FROM wearable_samples GROUP BY metric").fetchall()
    return {"metrics": [dict(row) for row in rows], "samples": sum(row["count"] for row in rows), "latest": max((row["last"] for row in rows), default=""), "catalog": catalog()}


def union_seconds(rows):
    return span_seconds((apple_date(row["start"]).timestamp(), apple_date(row["end"]).timestamp()) for row in rows)


def span_seconds(spans):
    spans = sorted(spans)
    total, finish = 0, None
    for start, end in spans:
        total += max(0, end - max(start, finish if finish is not None else start))
        finish = max(end, finish if finish is not None else end)
    return total


def aggregate(rows, metric, selected=""):
    method = METRICS[metric][2]
    choices, seen_instants = set(), set()
    count, total, minimum, maximum = 0, 0, None, None
    manual, cross_day, duplicate_instant = False, False, False
    spans, stage_spans = [], collections.defaultdict(list)
    latest, last_values = None, set()
    for row in rows:
        if selected and row["source"] != selected:
            continue
        choices.add(row["source"])
        count += 1
        total += row["value"]
        minimum = min(minimum, row["value"]) if minimum is not None else row["value"]
        maximum = max(maximum, row["value"]) if maximum is not None else row["value"]
        manual = manual or row["manual"]
        cross_day = cross_day or row["cross_day"]
        if method in ("sum", "workout", "sleep"):
            span = (apple_date(row["start"]).timestamp(), apple_date(row["end"]).timestamp())
            if method == "sleep":
                stage_spans[row["category"]].append(span)
                if row["category"] in ("asleep", "core", "deep", "rem"):
                    spans.append(span)
            else:
                spans.append(span)
                if span[0] == span[1]:
                    duplicate_instant = duplicate_instant or span in seen_instants
                    seen_instants.add(span)
        elif method == "last":
            end = apple_date(row["end"]).timestamp()
            if latest is None or end > latest:
                latest, last_values = end, {row["value"]}
            elif end == latest:
                last_values.add(row["value"])
    if not selected and len(choices) > 1:
        return {"value": None, "count": count, "conflict": True, "warning": "多来源未合并，请明确选择设备/来源"}
    if not count:
        return {"value": None, "count": 0, "conflict": False, "warning": "未记录"}
    warning = []
    if manual:
        warning.append("含手工录入")
    if cross_day:
        warning.append("跨日样本整体计入结束日")
    stages = {}
    if method == "sleep":
        value = span_seconds(spans) / 3600 if spans else None
        for stage in ("core", "deep", "rem", "asleep", "awake", "in_bed"):
            stages[stage] = span_seconds(stage_spans[stage]) / 3600 if stage_spans[stage] else None
        warning.append("睡眠区间取并集；在床/清醒不当作睡着，各分期可能重叠，不相加")
    elif method in ("sum", "workout"):
        overlaps = sum(end - start for start, end in spans) > span_seconds(spans) + 0.001 or duplicate_instant
        value = None if overlaps else total
        if overlaps:
            warning.append("同来源有重叠记录，未计算总量；请查看明细，不猜测去重优先级")
    elif method == "last":
        value = next(iter(last_values)) if len(last_values) == 1 else None
        if value is None:
            warning.append("末次时刻存在冲突数值")
    else:
        value = total / count
        warning.append("样本算术均值，不是全天连续测量或时间加权平均")
    return {"value": round(value, 3) if value is not None else None, "count": count, "min": minimum, "max": maximum, "conflict": False, "warning": "；".join(warning), "stages": stages}


class Wearables:
    def __init__(self, store):
        self.store = store
        self.lock = threading.RLock()
        self.job = None
        self.closed = False

    def reserve(self, filename):
        filename = text(filename, "文件名", 180, True)
        if not filename.lower().endswith((".xml", ".zip")) or any(char in filename for char in ("/", "\\", "\x00")):
            raise AppError("请选择 Apple 健康导出的 ZIP 或主 XML")
        with self.lock:
            self.expire()
            if self.closed or self.job:
                raise AppError("已有待处理导入，请完成或取消后再导入", 409)
            temporary = tempfile.TemporaryDirectory(prefix=".health-import-", dir=self.store.directory)
            job = {"id": secrets.token_urlsafe(24), "state": "uploading", "filename": filename, "temporary": temporary, "cancelled": threading.Event(), "expires": time.monotonic() + 1800, "progress": {}}
            self.job = job
            job["timer"] = threading.Timer(1801, self.cleanup_expired)
            job["timer"].daemon = True
            job["timer"].start()
            return job

    def cleanup_expired(self):
        with self.lock:
            self.expire()

    def launch(self, job, path, file_hash):
        with self.lock:
            if self.closed or self.job is not job or job["cancelled"].is_set():
                raise AppError("导入已取消", 409)
            job.update(state="parsing", sha256=file_hash, path=path)
            job["worker"] = threading.Thread(target=self.parse, args=(job,), daemon=True)
            job["worker"].start()
            return self.status()

    def parse(self, job):
        from pathlib import Path
        try:
            database_path = Path(job["temporary"].name) / "preview.sqlite3"
            with contextlib.closing(sqlite3.connect(database_path)) as database:
                database.row_factory = sqlite3.Row
                report = parse_export(job["path"], database, job["cancelled"], lambda progress: self.progress(job, progress))
                report.update(summary(database))
                sources = database.execute("SELECT source,source_name,device,COUNT(*) AS count FROM wearable_samples GROUP BY source ORDER BY source_name LIMIT 201").fetchall()
                if len(sources) > 200:
                    raise AppError("来源超过 200 个，请使用单个人的导出档案", 413)
                report["sources"] = [dict(row) for row in sources]
                database.commit()
            with self.lock:
                if self.closed or job["cancelled"].is_set():
                    job["state"] = "cancelled"
                else:
                    job.update(state="ready", report=report, database=database_path)
        except AppError as error:
            with self.lock:
                job.update(state="cancelled" if job["cancelled"].is_set() else "error", error=error.message)
        except Exception:
            with self.lock:
                job.update(state="error", error="解析失败，请检查空间和文件；未保存部分样本")
        finally:
            with self.lock:
                job["path"].unlink(missing_ok=True)
                if self.closed or job["state"] != "ready":
                    job["temporary"].cleanup()

    def progress(self, job, progress):
        with self.lock:
            job["progress"] = progress

    def expire(self):
        if self.job and self.job["expires"] < time.monotonic() and self.job["state"] in ("ready", "error", "cancelled", "completed"):
            self.job["timer"].cancel()
            self.job["temporary"].cleanup()
            self.job = None

    def status(self):
        with self.lock:
            self.expire()
            if not self.job:
                return {"state": "idle"}
            return {key: self.job[key] for key in ("id", "state", "filename", "progress", "report", "error", "result") if key in self.job}

    def cancel(self, job_id):
        with self.lock:
            job = self.job
            if not job or job["id"] != job_id:
                raise AppError("导入已失效，请刷新", 409)
            job["cancelled"].set()
            if job["state"] in ("ready", "error", "cancelled", "completed"):
                job["timer"].cancel()
                job["temporary"].cleanup()
                self.job = None
            return {"ok": True}

    def upload_failed(self, job):
        with self.lock:
            job["cancelled"].set()
            job["timer"].cancel()
            job["temporary"].cleanup()
            if self.job is job:
                self.job = None

    def commit(self, raw):
        with self.lock:
            self.expire()
            job = self.job
            if not job or job["id"] != raw.get("id") or job["state"] != "ready" or job["cancelled"].is_set() or self.closed:
                raise AppError("预览不存在、已使用或已过期，请重新导入", 409)
            if raw.get("confirm") is not True:
                raise AppError("须确认本人资料和本次保存范围")
            metrics = raw.get("metrics")
            if not isinstance(metrics, list) or not metrics or len(metrics) > len(METRICS) or any(not isinstance(metric, str) or metric not in METRICS for metric in metrics) or len(set(metrics)) != len(metrics):
                raise AppError("请选择要保存的有效指标")
            first, last = date_value(raw.get("from", ""), "起始日期", True), date_value(raw.get("to", ""), "结束日期", True)
            if first > last:
                raise AppError("起始日期不能晚于结束日期")
            selection = json.dumps({"metrics": sorted(metrics), "from": first, "to": last}, ensure_ascii=False, separators=(",", ":"))
            batch_id = str(uuid.uuid4())
            with self.store.lock, self.store.connection() as target, contextlib.closing(sqlite3.connect(job["database"])) as source:
                count_before = target.execute("SELECT COUNT(*) FROM wearable_samples").fetchone()[0]
                if target.execute("SELECT COUNT(*) FROM wearable_batches").fetchone()[0] >= 200:
                    raise AppError("最多保留 200 个导入批次，请备份后管理旧批次", 413)
                existing = target.execute("SELECT id FROM wearable_batches WHERE sha256=? AND selection=?", (job["sha256"], selection)).fetchone()
                if existing:
                    result = {"imported": 0, "already_imported": True, "batch_id": existing["id"]}
                else:
                    target.execute("INSERT INTO wearable_batches VALUES (?,?,?,?,?,0)", (batch_id, job["filename"], job["sha256"], stamp(), selection))
                    query = "SELECT * FROM wearable_samples WHERE day BETWEEN ? AND ? AND metric IN (" + ",".join("?" for metric in metrics) + ")"
                    cursor = source.execute(query, [first, last] + metrics)
                    total = 0
                    references = target.execute("SELECT COUNT(*) FROM wearable_members").fetchone()[0]
                    while True:
                        rows = cursor.fetchmany(1000)
                        if not rows:
                            break
                        total += len(rows)
                        if references + total > 2000000:
                            raise AppError("批次引用超过 200 万条，请先备份并管理旧批次", 413)
                        target.executemany(INSERT_SQL, rows)
                        target.executemany("INSERT INTO wearable_members VALUES (?,?)", [(batch_id, row[0]) for row in rows])
                    count_after = target.execute("SELECT COUNT(*) FROM wearable_samples").fetchone()[0]
                    if not total or count_after > MAX_SAMPLES:
                        raise AppError("范围内没有样本或档案超过 100 万条上限，未保存", 413)
                    target.execute("UPDATE wearable_batches SET samples=? WHERE id=?", (total, batch_id))
                    self.store.audit(target, "import", "wearable", batch_id)
                    result = {"imported": count_after - count_before, "duplicates": total - (count_after - count_before), "batch_id": batch_id}
            job.update(state="completed", result=result)
            job["timer"].cancel()
            job["temporary"].cleanup()
            return result

    def delete(self, raw):
        batch_id = identifier(raw.get("id"))
        if raw.get("confirm") is not True:
            raise AppError("须确认删除此导入批次")
        with self.store.lock, self.store.connection() as database:
            if not database.execute("SELECT id FROM wearable_batches WHERE id=?", (batch_id,)).fetchone():
                raise AppError("批次已移除", 409)
            database.execute("DELETE FROM wearable_batches WHERE id=?", (batch_id,))
            database.execute("DELETE FROM wearable_samples WHERE NOT EXISTS (SELECT 1 FROM wearable_members WHERE sample_id=wearable_samples.id)")
            self.store.audit(database, "delete", "wearable", batch_id)
        return {"ok": True}

    def overview(self, first, last, metric="steps", source=""):
        first, last = date_value(first, "起始日期", True), date_value(last, "结束日期", True)
        start_day, end_day = datetime.date.fromisoformat(first), datetime.date.fromisoformat(last)
        if metric not in METRICS or not 0 <= (end_day - start_day).days <= 365 or source and (not isinstance(source, str) or not re_hash(source)):
            raise AppError("指标、来源或日期范围无效，最多查看 366 天")
        with self.store.lock, self.store.connection() as database:
            snapshot = summary(database)
            sources = [dict(row) for row in database.execute("SELECT source,source_name,device,COUNT(*) AS count FROM wearable_samples WHERE metric=? AND day BETWEEN ? AND ? GROUP BY source ORDER BY source_name", (metric, first, last))]
            rows = database.execute("SELECT * FROM wearable_samples WHERE metric=? AND day BETWEEN ? AND ? ORDER BY day,start", (metric, first, last))
            grouped = {day: aggregate(group, metric, source) for day, group in itertools.groupby(rows, key=lambda row: row["day"])}
            daily = []
            for offset in range((end_day - start_day).days + 1):
                day = (start_day + datetime.timedelta(days=offset)).isoformat()
                daily.append({"day": day, **grouped.get(day, {"value": None, "count": 0, "conflict": False, "warning": "未记录"})})
            meals = [{**entry, "day": entry["date"], "origin": "journal", "source": "本人实际饮食"} for entry in FoodJournal(self.store).entries(first, last)]
            for plan in self.store.plans():
                if first <= plan["date"] <= last:
                    for kind, entry in plan["meals"].items():
                        if entry["eaten"] or entry["note"]:
                            meals.append({"day": plan["date"], "meal": kind, "note": entry["note"] or "已记录用餐，未填写具体内容", "source": "餐单中的实际饮食", "origin": "plan", "time": ""})
            for analysis in self.store.analyses():
                intake = analysis["intake"]
                if intake and first <= intake["date"] <= last:
                    meals.append({"day": intake["date"], "meal": intake["meal"], "note": intake["note"], "source": "人工核对的饮食备注", "origin": "analysis", "id": analysis["id"], "time": ""})
            batches = [dict(row) for row in database.execute("SELECT * FROM wearable_batches ORDER BY created_at DESC,id")]
        return {**snapshot, "from": first, "to": last, "metric": metric, "source": source, "sources": sources, "daily": daily, "meals": meals, "batches": batches, "notice": "消费级设备记录不是诊断；缺失不按零计算；日期按样本结束时间原时区归属。不会与 Apple 健康的来源优先级合并结果完全一致。饮食同日出现不是因果关系，不据此补偿热量、限食、调药或判断疾病。"}

    def day(self, day, choices):
        day = date_value(day, "日记日期", True)
        metrics = ("steps", "sleep", "heart_rate", "distance")
        if set(choices) - set(metrics) or any(value and not re_hash(value) for value in choices.values()):
            raise AppError("日概览来源无效")
        with self.store.lock, self.store.connection() as database:
            result = {}
            for metric in metrics:
                sources = [dict(row) for row in database.execute("SELECT source,source_name,device,COUNT(*) AS count FROM wearable_samples WHERE metric=? AND day=? GROUP BY source ORDER BY source_name,source", (metric, day))]
                choice = choices.get(metric, "")
                rows = database.execute("SELECT * FROM wearable_samples WHERE metric=? AND day=?", (metric, day))
                result[metric] = {**aggregate(rows, metric, choice), "source": choice, "sources": sources, "unit": METRICS[metric][1], "name": METRICS[metric][0]}
            return {"day": day, "metrics": result}

    def details(self, day, metric, source, offset):
        day = date_value(day, "日期", True)
        if metric not in METRICS or source and not re_hash(source) or type(offset) is not int or not 0 <= offset <= MAX_SAMPLES:
            raise AppError("明细查询无效")
        query = " FROM wearable_samples WHERE day=? AND metric=?" + (" AND source=?" if source else "")
        arguments = [day, metric] + ([source] if source else [])
        with self.store.lock, self.store.connection() as database:
            count = database.execute("SELECT COUNT(*)" + query, arguments).fetchone()[0]
            rows = database.execute("SELECT *" + query + " ORDER BY start,id LIMIT 50 OFFSET ?", arguments + [offset])
            return {"total": count, "offset": offset, "items": [dict(row) for row in rows]}

    def close(self):
        with self.lock:
            self.closed = True
            job = self.job
            if job:
                job["cancelled"].set()
                job["timer"].cancel()
        if job and job.get("worker"):
            job["worker"].join(timeout=5)
        if job and job["state"] != "uploading" and (not job.get("worker") or not job["worker"].is_alive()):
            job["temporary"].cleanup()


def re_hash(value):
    import re
    return isinstance(value, str) and re.fullmatch("[a-f0-9]{64}", value) is not None


def export_backup(database):
    output = io.BytesIO()
    for table, kind in (("wearable_batches", "batch"), ("wearable_samples", "sample"), ("wearable_members", "member")):
        for row in database.execute("SELECT * FROM " + table + " ORDER BY 1,2"):
            output.write((json.dumps({"kind": kind, "data": dict(row)}, ensure_ascii=False, separators=(",", ":")) + "\n").encode())
            if output.tell() > BACKUP_LIMIT:
                raise AppError("健康样本备份超过 40 MiB；请停服完整复制私有资料目录，不要删除唯一数据", 413)
    return output.getvalue()


def validate_backup(content):
    if len(content) > BACKUP_LIMIT:
        raise AppError("健康样本备份过大", 413)
    connection = sqlite3.connect(":memory:")
    connection.executescript(SCHEMA)
    connection.execute("PRAGMA foreign_keys = ON")
    try:
        for line in content.splitlines():
            raw = json.loads(line, parse_constant=strict_json_constant, object_pairs_hook=unique_json_object)
            if set(raw) != {"kind", "data"} or not isinstance(raw["data"], dict):
                raise ValueError()
            row = raw["data"]
            if raw["kind"] == "sample":
                if set(row) != set(FIELDS) or row["metric"] not in METRICS or not re_hash(row["id"]) or not re_hash(row["source"]):
                    raise ValueError()
                metric = row["metric"]
                start, end = apple_date(row["start"]), apple_date(row["end"])
                value = finite(row["value"], METRICS[metric][5])
                if not 0 <= (end - start).total_seconds() <= 172800 or row["day"] != end.date().isoformat() or row["unit"] != METRICS[metric][1] or type(row["manual"]) is not int or row["manual"] not in (0, 1) or type(row["cross_day"]) is not int or row["cross_day"] != int(start.date() != end.date()):
                    raise ValueError()
                name, device = text(row["source_name"], "来源", 240, True), text(row["device"], "设备", 2000)
                text(row["source_version"], "版本", 120)
                text(row["category"], "类别", 160)
                if row["source"] != digest([name, re.sub(r'(<HKDevice: )0x[0-9a-fA-F]+', r'\1', device)]) or row["id"] != digest([metric, row["source"], start.astimezone(datetime.timezone.utc).isoformat(), end.astimezone(datetime.timezone.utc).isoformat(), value, row["category"], bool(row["manual"])]):
                    raise ValueError()
                if metric == "sleep" and (row["category"] not in ("in_bed", "awake", "asleep", "core", "deep", "rem") or abs(value - (end - start).total_seconds() / 3600) > 1e-6):
                    raise ValueError()
                if metric not in ("sleep", "workout") and row["category"] or metric == "workout" and (not row["category"] or value > (end - start).total_seconds() / 60 + 1) or metric in ("heart_rate", "resting_heart_rate", "walking_heart_rate", "weight") and value == 0:
                    raise ValueError()
                original = {"type": "HKCategoryTypeIdentifierSleepAnalysis" if metric == "sleep" else "HKQuantityTypeIdentifier" + METRICS[metric][3], "sourceName": name, "device": device, "sourceVersion": row["source_version"], "startDate": row["start"], "endDate": row["end"], "value": text(row["original_value"], "原值", 240), "unit": text(row["original_unit"], "原单位", 80)}
                if metric == "workout":
                    original.update(duration=original["value"], durationUnit=original["unit"], workoutActivityType=row["category"])
                canonical = normalized(original, "Workout" if metric == "workout" else "Record", bool(row["manual"]))
                if canonical != row:
                    raise ValueError()
                connection.execute(INSERT_SQL.replace(" OR IGNORE", ""), tuple(row[key] for key in FIELDS))
            elif raw["kind"] == "batch":
                if set(row) != set(BATCH_FIELDS) or not re_hash(row["sha256"]) or type(row["samples"]) is not int or not 1 <= row["samples"] <= MAX_SAMPLES:
                    raise ValueError()
                identifier(row["id"])
                text(row["filename"], "文件名", 180, True)
                timestamp_value(row["created_at"])
                selection = json.loads(text(row["selection"], "范围", 2000), object_pairs_hook=unique_json_object)
                if set(selection) != {"metrics", "from", "to"} or not isinstance(selection["metrics"], list) or not selection["metrics"] or any(metric not in METRICS for metric in selection["metrics"]):
                    raise ValueError()
                if date_value(selection["from"], "开始", True) > date_value(selection["to"], "结束", True):
                    raise ValueError()
                connection.execute("INSERT INTO wearable_batches VALUES (?,?,?,?,?,?)", tuple(row[key] for key in BATCH_FIELDS))
            elif raw["kind"] == "member" and set(row) == {"batch_id", "sample_id"}:
                connection.execute("INSERT INTO wearable_members VALUES (?,?)", (row["batch_id"], row["sample_id"]))
            else:
                raise ValueError()
        if connection.execute("SELECT COUNT(*) FROM wearable_samples").fetchone()[0] > MAX_SAMPLES or connection.execute("SELECT COUNT(*) FROM wearable_batches").fetchone()[0] > 200 or connection.execute("SELECT COUNT(*) FROM wearable_members").fetchone()[0] > 2000000:
            raise ValueError()
        if connection.execute("SELECT 1 FROM wearable_samples WHERE id NOT IN (SELECT sample_id FROM wearable_members) LIMIT 1").fetchone() or connection.execute("SELECT 1 FROM wearable_batches WHERE samples != (SELECT COUNT(*) FROM wearable_members WHERE batch_id=wearable_batches.id) LIMIT 1").fetchone():
            raise ValueError()
        for batch_id, selection_text in connection.execute("SELECT id,selection FROM wearable_batches"):
            selection = json.loads(selection_text)
            metrics = selection["metrics"]
            query = "SELECT 1 FROM wearable_samples JOIN wearable_members ON sample_id=wearable_samples.id WHERE batch_id=? AND (day<? OR day>? OR metric NOT IN (" + ",".join("?" for metric in metrics) + ")) LIMIT 1"
            if connection.execute(query, [batch_id, selection["from"], selection["to"]] + metrics).fetchone():
                raise ValueError()
        return connection
    except Exception:
        connection.close()
        raise AppError("健康样本备份结构、哈希或批次引用无效") from None
