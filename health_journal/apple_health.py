import collections
import datetime
import hashlib
import json
import math
from pathlib import PurePosixPath
import re
import sqlite3
import time
import xml.parsers.expat
import zipfile
import zlib

from .validation import AppError, text


MAX_UPLOAD = 256 * 1024 * 1024
MAX_XML = 1024 * 1024 * 1024
MAX_SAMPLES = 1000000
MAX_SECONDS = 180
METRICS = {
    "steps": ("步数", "步", "sum", "StepCount", {"count": 1}, 1000000),
    "distance": ("步行与跑步距离", "km", "sum", "DistanceWalkingRunning", {"km": 1, "m": 0.001, "mi": 1.609344}, 1000),
    "heart_rate": ("心率", "次/分", "mean", "HeartRate", {"count/min": 1}, 400),
    "resting_heart_rate": ("静息心率", "次/分", "mean", "RestingHeartRate", {"count/min": 1}, 400),
    "walking_heart_rate": ("步行平均心率", "次/分", "mean", "WalkingHeartRateAverage", {"count/min": 1}, 400),
    "hrv": ("心率变异性（SDNN）", "ms", "mean", "HeartRateVariabilitySDNN", {"ms": 1, "s": 1000}, 5000),
    "active_energy": ("活动能量", "kcal", "sum", "ActiveEnergyBurned", {"kcal": 1, "kJ": 1 / 4.184, "Cal": 1}, 100000),
    "basal_energy": ("静息能量", "kcal", "sum", "BasalEnergyBurned", {"kcal": 1, "kJ": 1 / 4.184, "Cal": 1}, 100000),
    "exercise": ("锻炼时间", "分钟", "sum", "AppleExerciseTime", {"min": 1, "s": 1 / 60}, 1440),
    "flights": ("爬楼层数", "层", "sum", "FlightsClimbed", {"count": 1}, 10000),
    "weight": ("体重", "kg", "last", "BodyMass", {"kg": 1, "lb": 0.45359237}, 1000),
    "body_fat": ("体脂率", "%", "last", "BodyFatPercentage", {"%": 100}, 100),
    "oxygen": ("血氧饱和度", "%", "mean", "OxygenSaturation", {"%": 100}, 100),
    "respiratory_rate": ("呼吸频率", "次/分", "mean", "RespiratoryRate", {"count/min": 1}, 150),
    "dietary_energy": ("已记录摄入能量", "kcal", "sum", "DietaryEnergyConsumed", {"kcal": 1, "kJ": 1 / 4.184, "Cal": 1}, 100000),
    "water": ("已记录饮水", "mL", "sum", "DietaryWater", {"mL": 1, "L": 1000, "fl_oz_us": 29.5735295625}, 100000),
    "sleep": ("睡眠时长", "小时", "sleep", "", {}, 48),
    "workout": ("体能训练", "分钟", "workout", "", {}, 2880),
}
TYPE_MAP = {"HKQuantityTypeIdentifier" + value[3]: key for key, value in METRICS.items() if value[3]}
SLEEP = {"HKCategoryValueSleepAnalysisInBed": "in_bed", "HKCategoryValueSleepAnalysisAwake": "awake", "HKCategoryValueSleepAnalysisAsleep": "asleep", "HKCategoryValueSleepAnalysisAsleepUnspecified": "asleep", "HKCategoryValueSleepAnalysisAsleepCore": "core", "HKCategoryValueSleepAnalysisAsleepDeep": "deep", "HKCategoryValueSleepAnalysisAsleepREM": "rem"}
TABLE_SQL = """
CREATE TABLE IF NOT EXISTS wearable_samples (
    id TEXT PRIMARY KEY, metric TEXT NOT NULL, source TEXT NOT NULL,
    source_name TEXT NOT NULL, device TEXT NOT NULL, source_version TEXT NOT NULL,
    start TEXT NOT NULL, end TEXT NOT NULL, day TEXT NOT NULL,
    value REAL NOT NULL, unit TEXT NOT NULL, category TEXT NOT NULL,
    manual INTEGER NOT NULL, cross_day INTEGER NOT NULL,
    original_value TEXT NOT NULL, original_unit TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS wearable_metric_day ON wearable_samples(metric, day, source);
"""
FIELDS = ("id", "metric", "source", "source_name", "device", "source_version", "start", "end", "day", "value", "unit", "category", "manual", "cross_day", "original_value", "original_unit")
INSERT_SQL = "INSERT OR IGNORE INTO wearable_samples VALUES (" + ",".join("?" for field in FIELDS) + ")"


def catalog():
    return [{"id": key, "name": row[0], "unit": row[1], "method": row[2]} for key, row in METRICS.items()]


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()


def apple_date(value):
    value = text(value, "健康时间", 80, True)
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}(?:\.\d{1,6})? ?(?:Z|[+-]\d{2}:?\d{2})", value):
        raise AppError("健康样本缺少有效日期或时区")
    offset = re.search(r"[+-](\d{2}):?(\d{2})$", value)
    if offset and int(offset.group(2)) >= 60:
        raise AppError("健康样本时区分钟无效")
    try:
        canonical = value.replace("Z", "+00:00").replace(" +", "+").replace(" -", "-")
        canonical = re.sub(r"([+-]\d{2})(\d{2})$", r"\1:\2", canonical)
        parsed = datetime.datetime.fromisoformat(canonical)
        if not 1900 <= parsed.year <= 2100 or abs(parsed.utcoffset().total_seconds()) > 14 * 3600:
            raise ValueError()
        return parsed
    except ValueError:
        raise AppError("健康样本日期或时区无效")


def finite(value, maximum):
    if isinstance(value, bool):
        raise AppError("样本数值不能是布尔值")
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError):
        raise AppError("样本数值无效")
    if not math.isfinite(result) or not 0 <= result <= maximum:
        raise AppError("样本数值超出导入边界，不代表医学判断")
    return result


def normalized(attributes, tag, manual=False):
    metric = TYPE_MAP.get(attributes.get("type")) if tag == "Record" else "workout"
    if tag == "Record" and attributes.get("type") == "HKCategoryTypeIdentifierSleepAnalysis":
        metric = "sleep"
    if not metric:
        return None
    start, end = apple_date(attributes.get("startDate")), apple_date(attributes.get("endDate"))
    seconds = (end - start).total_seconds()
    if not 0 <= seconds <= 48 * 3600 or end > datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(minutes=5):
        raise AppError("样本日期倒置、跨度超过 48 小时或位于未来")
    name = text(attributes.get("sourceName", "未提供来源"), "来源名称", 240, True)
    device = text(attributes.get("device", ""), "设备信息", 2000)
    version = text(attributes.get("sourceVersion", ""), "来源版本", 120)
    category = ""
    if metric == "sleep":
        category = SLEEP.get(attributes.get("value"))
        if not category or seconds <= 0:
            raise AppError("不支持的睡眠类别或空区间")
        value = seconds / 3600
    elif metric == "workout":
        category = text(attributes.get("workoutActivityType", "未提供训练类型"), "训练类型", 160, True)
        factor = {"min": 1, "s": 1 / 60, "hr": 60}.get(attributes.get("durationUnit", "min"))
        if factor is None:
            raise AppError("训练时长单位不支持")
        value = finite(attributes.get("duration"), 172800) * factor
        if value > seconds / 60 + 1 or value > 2880:
            raise AppError("训练时长超过起止区间")
    else:
        factor = METRICS[metric][4].get(attributes.get("unit"))
        if factor is None:
            raise AppError("不支持的数值单位")
        value = finite(attributes.get("value"), 100000000) * factor
        finite(value, METRICS[metric][5])
        if metric in ("heart_rate", "resting_heart_rate", "walking_heart_rate", "weight") and value == 0:
            raise AppError("此指标的零值不能当作有效测量")
    source = digest([name, re.sub(r'(<HKDevice: )0x[0-9a-fA-F]+', r'\1', device)])
    start_text, end_text = start.isoformat(), end.isoformat()
    sample_id = digest([metric, source, start.astimezone(datetime.timezone.utc).isoformat(), end.astimezone(datetime.timezone.utc).isoformat(), value, category, bool(manual)])
    original_value = text(attributes.get("duration" if metric == "workout" else "value", ""), "原始值", 240)
    original_unit = text(attributes.get("durationUnit" if metric == "workout" else "unit", "min" if metric == "workout" else ""), "原始单位", 80)
    return dict(zip(FIELDS, (sample_id, metric, source, name, device, version, start_text, end_text, end.date().isoformat(), value, METRICS[metric][1], category, int(manual), int(start.date() != end.date()), original_value, original_unit)))


class AppleParser:
    def __init__(self, database, cancelled, progress):
        self.database, self.cancelled, self.progress = database, cancelled, progress
        self.seen = 0
        self.accepted = 0
        self.duplicate = 0
        self.skipped = collections.Counter()
        self.invalid = collections.Counter()
        self.stack = []
        self.current = None
        self.manual = False
        self.root = None
        self.started = time.monotonic()
        self.bytes_read = 0
        self.buffer = []
        self.parser = xml.parsers.expat.ParserCreate()
        self.parser.StartElementHandler = self.start
        self.parser.EndElementHandler = self.end
        self.parser.EntityDeclHandler = self.forbidden
        self.parser.ExternalEntityRefHandler = self.forbidden
        self.parser.StartDoctypeDeclHandler = self.doctype
        self.parser.SetParamEntityParsing(xml.parsers.expat.XML_PARAM_ENTITY_PARSING_NEVER)

    def forbidden(self, *arguments):
        raise AppError("拒绝 XML 实体、外部文件或网络引用")

    def doctype(self, name, system_id, public_id, internal):
        if name != "HealthData" or system_id or public_id:
            self.forbidden()

    def check(self):
        if self.cancelled.is_set():
            raise AppError("导入已取消，未保存健康样本", 409)
        if time.monotonic() - self.started > MAX_SECONDS:
            raise AppError("解析超过 180 秒；请使用较小文件，没有保存部分结果", 413)

    def start(self, tag, attributes):
        if not self.stack:
            self.root = tag
            if tag != "HealthData":
                raise AppError("不是 Apple HealthData 主 XML；不能使用 ClinicalDocument/export_cda.xml")
        self.stack.append(tag)
        if len(self.stack) > 32 or len(attributes) > 100 or any(len(value) > 8192 for value in attributes.values()):
            raise AppError("XML 嵌套或属性超过安全限制")
        if len(self.stack) == 2:
            self.check()
            self.seen += 1
            if self.seen > 5000000:
                raise AppError("XML 条目过多", 413)
            if tag in ("Record", "Workout"):
                self.current = (tag, attributes)
                self.manual = False
            elif tag not in ("Me", "ExportDate"):
                self.skipped[tag[:160]] += 1
        elif tag == "MetadataEntry" and len(self.stack) == 3 and self.current:
            if attributes.get("key") == "HKWasUserEntered" and attributes.get("value", "").lower() in ("1", "true", "yes"):
                self.manual = True

    def end(self, tag):
        if len(self.stack) == 2 and self.current:
            source_tag, attributes = self.current
            try:
                sample = normalized(attributes, source_tag, self.manual)
                if sample:
                    self.buffer.append(tuple(sample[field] for field in FIELDS))
                    if len(self.buffer) >= 1000:
                        self.flush()
                else:
                    key = text(attributes.get("type", "未提供类型"), "类型", 240)
                    if len(self.skipped) < 100 or key in self.skipped:
                        self.skipped[key] += 1
                    else:
                        self.skipped["其他不支持类型"] += 1
            except AppError as error:
                if error.status == 413:
                    raise
                self.invalid[error.message] += 1
            self.current = None
        self.stack.pop()

    def flush(self):
        before = self.database.total_changes
        self.database.executemany(INSERT_SQL, self.buffer)
        added = self.database.total_changes - before
        self.accepted += added
        self.duplicate += len(self.buffer) - added
        self.buffer.clear()
        if self.accepted > MAX_SAMPLES:
            raise AppError("最多导入 100 万条有效样本，请缩小范围", 413)
        self.progress({"records_seen": self.seen, "samples": self.accepted, "bytes_read": self.bytes_read})

    def parse(self, stream):
        while True:
            self.check()
            chunk = stream.read(64 * 1024)
            if not chunk:
                break
            self.bytes_read += len(chunk)
            if self.bytes_read > MAX_XML:
                raise AppError("主 XML 展开后超过 1 GiB", 413)
            self.parser.Parse(chunk, False)
        self.parser.Parse(b"", True)
        self.flush()
        if not self.accepted:
            raise AppError("没有可导入的有效支持样本；请核对主 XML、日期、单位和支持范围", 422)
        return {"records_seen": self.seen, "samples": self.accepted, "file_duplicates": self.duplicate, "unsupported": dict(self.skipped), "invalid": dict(self.invalid), "ignored_profile": True}


def parse_export(path, database, cancelled, progress):
    database.executescript(TABLE_SQL)
    try:
        if not zipfile.is_zipfile(path):
            with open(path, "rb") as stream:
                return AppleParser(database, cancelled, progress).parse(stream)
        with zipfile.ZipFile(path) as archive:
            infos = archive.infolist()
            if len(infos) > 20000:
                raise AppError("ZIP 条目超过 20000，拒绝解析", 413)
            candidates = []
            xml_count = 0
            paths = set()
            for entry in infos:
                parts = PurePosixPath(entry.filename).parts
                if entry.filename in paths or entry.filename.startswith("/") or re.match(r"^[A-Za-z]:", entry.filename) or ".." in parts or "\\" in entry.filename or (entry.external_attr >> 16) & 0o170000 == 0o120000:
                    raise AppError("ZIP 有重复、穿越路径或符号链接")
                paths.add(entry.filename)
                if entry.flag_bits & 1:
                    raise AppError("不支持加密 ZIP，请先在自己的设备解密")
                if entry.is_dir() or not entry.filename.lower().endswith(".xml") or entry.filename.startswith("__MACOSX/"):
                    continue
                xml_count += 1
                if entry.file_size > MAX_XML:
                    raise AppError("ZIP 中 XML 超过 1 GiB", 413)
                if xml_count > 20:
                    raise AppError("ZIP 中 XML 过多，请单独选择主 XML")
                with archive.open(entry) as probe:
                    prefix = probe.read(128 * 1024)
                if re.search(br"<HealthData(?:\s|>)", prefix):
                    candidates.append(entry)
            if len(candidates) != 1:
                raise AppError("ZIP 必须包含一份 HealthData 主 XML；支持中文文件名，不能有多份主导出")
            with archive.open(candidates[0]) as stream:
                return AppleParser(database, cancelled, progress).parse(stream)
    except AppError:
        raise
    except (xml.parsers.expat.ExpatError, zipfile.BadZipFile, zlib.error, RuntimeError, NotImplementedError, UnicodeError, ValueError, OSError):
        raise AppError("Apple 健康导出格式损坏或不支持；未保存任何样本") from None
