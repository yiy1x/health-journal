import datetime
import math
import re
import uuid


class AppError(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.message = message
        self.status = status


KINDS = ("visit", "observation", "medication", "symptom", "condition", "reminder")
UNITS = ("mmol/L", "mg/dL", "μmol/L", "U/L", "g/L", "10^9/L", "%", "mmHg", "kg", "次/分", "℃", "其他")
ALLERGENS = ("鸡蛋", "牛奶", "大豆", "小麦", "花生", "坚果", "鱼", "甲壳类", "芝麻")


def text(value, label, maximum=2000, required=False):
    if not isinstance(value, str):
        raise AppError(label + "必须为文字")
    value = value.strip()
    if required and not value:
        raise AppError("请填写" + label)
    if len(value) > maximum or "\x00" in value:
        raise AppError(label + "过长或含无效字符")
    try:
        value.encode("utf-8")
    except UnicodeEncodeError:
        raise AppError(label + "含无效 Unicode 字符")
    return value


def choice(value, allowed, label):
    if value not in allowed:
        raise AppError(label + "选项无效")
    return value


def date_value(value, label, required=False, allow_future=True):
    value = text(value, label, 10, required)
    if not value:
        return ""
    try:
        parsed = datetime.date.fromisoformat(value)
    except ValueError:
        raise AppError(label + "须为 YYYY-MM-DD 格式")
    if parsed.isoformat() != value or parsed.year < 1900:
        raise AppError(label + "格式或年份无效")
    if not allow_future and parsed > datetime.date.today():
        raise AppError(label + "不能晚于今天")
    return value


def identifier(value):
    if not isinstance(value, str):
        raise AppError("记录标识无效")
    try:
        if str(uuid.UUID(value)) != value:
            raise ValueError()
    except (ValueError, AttributeError):
        raise AppError("记录标识无效")
    return value


def number(value, label, minimum=None, maximum=None, optional=False):
    if optional and (value is None or value == ""):
        return None
    if isinstance(value, bool):
        raise AppError(label + "必须为有效数字")
    try:
        result = float(value)
    except (ValueError, TypeError, OverflowError):
        raise AppError(label + "必须为有效数字")
    if not math.isfinite(result):
        raise AppError(label + "必须为有限数字")
    if minimum is not None and result < minimum:
        raise AppError(label + "不能小于 " + str(minimum))
    if maximum is not None and result > maximum:
        raise AppError(label + "不能大于 " + str(maximum))
    return result


def boolean(value, label):
    if not isinstance(value, bool):
        raise AppError(label + "必须为是或否")
    return value


def strict_json_constant(value):
    raise ValueError("Non-finite JSON number: " + value)


def unique_json_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON field")
        result[key] = value
    return result


def timestamp_value(value):
    value = text(value, "保存时间", 40, True)
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2})", value):
        raise AppError("保存时间须为带时区的标准 ISO 时间")
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    try:
        parsed = datetime.datetime.fromisoformat(value)
    except ValueError:
        raise AppError("保存时间格式无效")
    if parsed.tzinfo is None or parsed.year < 1900:
        raise AppError("保存时间必须包含时区且年份有效")
    return value


def validate_record(raw):
    if not isinstance(raw, dict):
        raise AppError("记录格式无效")
    kind = choice(raw.get("kind"), KINDS, "记录类型")
    payload = raw.get("data", {})
    if not isinstance(payload, dict):
        raise AppError("记录内容无效")
    record = {
        "kind": kind,
        "title": text(raw.get("title", ""), "标题", 120, True),
        "date": date_value(raw.get("date", ""), "记录日期", True, kind == "reminder"),
        "department": text(raw.get("department", ""), "科室", 80),
        "topic": text(raw.get("topic", ""), "健康主题", 100),
        "notes": text(raw.get("notes", ""), "备注", 8000),
        "source_label": text(raw.get("source_label", ""), "来源说明", 240),
        "document_id": identifier(raw["document_id"]) if raw.get("document_id") else None,
        "verification": choice(raw.get("verification", "pending"), ("pending", "verified"), "核对状态"),
        "data": {},
    }
    data = record["data"]
    if kind == "visit":
        data["hospital"] = text(payload.get("hospital", ""), "医院", 120)
        data["doctor"] = text(payload.get("doctor", ""), "医生", 80)
        data["reason"] = text(payload.get("reason", ""), "主诉", 2000)
        data["conclusion"] = text(payload.get("conclusion", ""), "报告或医嘱摘录", 4000)
    elif kind == "observation":
        data["value"] = number(payload.get("value"), "检验值")
        data["comparator"] = choice(payload.get("comparator", "="), ("=", "<", ">", "≤", "≥"), "比较符")
        data["unit"] = text(payload.get("unit", ""), "单位", 32, True)
        data["reference_low"] = number(payload.get("reference_low"), "参考下限", optional=True)
        data["reference_high"] = number(payload.get("reference_high"), "参考上限", optional=True)
        if data["reference_low"] is not None and data["reference_high"] is not None:
            if data["reference_low"] > data["reference_high"]:
                raise AppError("参考下限不能大于参考上限")
        data["lab"] = text(payload.get("lab", ""), "检测机构/方法", 160)
    elif kind == "medication":
        data["dose"] = text(payload.get("dose", ""), "剂量（含单位）", 120, True)
        data["frequency"] = text(payload.get("frequency", ""), "频次", 120, True)
        data["start_date"] = date_value(payload.get("start_date", record["date"]), "开始日期", True)
        data["end_date"] = date_value(payload.get("end_date", ""), "结束日期")
        if data["end_date"] and data["end_date"] < data["start_date"]:
            raise AppError("结束日期不能早于开始日期")
        data["status"] = choice(payload.get("status", "active"), ("active", "stopped", "planned"), "用药状态")
        data["prescriber"] = text(payload.get("prescriber", ""), "处方来源", 240, True)
    elif kind == "symptom":
        severity = number(payload.get("severity", 3), "程度", 0, 10)
        if not severity.is_integer():
            raise AppError("程度须为 0–10 的整数")
        data["severity"] = int(severity)
        data["status"] = choice(payload.get("status", "ongoing"), ("ongoing", "resolved"), "症状状态")
        data["duration"] = text(payload.get("duration", ""), "持续情况", 160)
        data["triggers"] = text(payload.get("triggers", ""), "诱因或缓解因素", 1000)
        data["red_flags"] = boolean(payload.get("red_flags", False), "危险症状标记")
    elif kind == "condition":
        data["status"] = choice(payload.get("status", "suspected"), ("suspected", "confirmed", "ruled_out", "resolved"), "问题状态")
        if data["status"] == "confirmed" and not record["document_id"]:
            raise AppError("记录“报告记载已诊断”时，请关联相应原始文件；没有原件请使用“待查/个人转述”")
    elif kind == "reminder":
        data["done"] = boolean(payload.get("done", False), "完成状态")
        data["category"] = choice(payload.get("category", "followup"), ("followup", "check", "other"), "提醒类型")
    return record


def validate_profile(raw):
    if not isinstance(raw, dict):
        raise AppError("档案格式无效")
    allergies = raw.get("allergies", [])
    if not isinstance(allergies, list) or len(allergies) > 20:
        raise AppError("过敏信息无效")
    return {
        "name": text(raw.get("name", ""), "称呼", 40),
        "birth_date": date_value(raw.get("birth_date", ""), "出生日期", allow_future=False),
        "sex": choice(raw.get("sex", "unspecified"), ("unspecified", "female", "male", "other"), "性别"),
        "allergies": sorted(set(text(item, "过敏原", 40, True) for item in allergies)),
        "diet": choice(raw.get("diet", "unspecified"), ("unspecified", "balanced", "vegetarian"), "饮食偏好"),
        "clinical_diet": boolean(raw.get("clinical_diet", False), "医学饮食限制"),
        "diet_acknowledged": boolean(raw.get("diet_acknowledged", False), "一般膳食适用确认"),
        "diet_notes": text(raw.get("diet_notes", ""), "饮食医嘱", 2000),
        "emergency_contact": text(raw.get("emergency_contact", ""), "紧急联系人", 160),
        "notes": text(raw.get("notes", ""), "补充说明", 4000),
    }


def safe_filename(value):
    value = text(value, "文件名", 180, True)
    if any(character in value for character in ("/", "\\", "\r", "\n")) or value.startswith("."):
        raise AppError("文件名无效")
    return re.sub(r'[<>:"|?*]', "_", value)
