import datetime
import re

from .validation import AppError, choice, date_value, identifier, text, timestamp_value


LIMIT = 10000
MEALS = ("breakfast", "lunch", "dinner", "snack")
FIELDS = ("id", "date", "time", "meal", "note", "document_id", "version", "created_at", "updated_at")
SCHEMA = """
CREATE TABLE IF NOT EXISTS food_entries (
    id TEXT PRIMARY KEY, date TEXT NOT NULL, time TEXT NOT NULL,
    meal TEXT NOT NULL, note TEXT NOT NULL,
    document_id TEXT REFERENCES documents(id) ON DELETE RESTRICT,
    version INTEGER NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS food_date ON food_entries(date, time, id);
"""


def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


def validate_food(raw, saved=False):
    if not isinstance(raw, dict):
        raise AppError("实际饮食格式无效")
    clock = text(raw.get("time", ""), "用餐时间", 5)
    if clock and not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", clock):
        raise AppError("用餐时间须为 HH:MM，也可以留空")
    item = {"id": identifier(raw.get("id")), "date": date_value(raw.get("date", ""), "实际用餐日期", True, False), "time": clock,
            "meal": choice(raw.get("meal"), MEALS, "餐次"), "note": text(raw.get("note", ""), "实际吃了什么", 2000, True),
            "document_id": identifier(raw["document_id"]) if raw.get("document_id") else None}
    if saved:
        if type(raw.get("version")) is not int or not 1 <= raw["version"] <= 1000000000:
            raise AppError("饮食记录版本无效")
        created, updated = timestamp_value(raw.get("created_at")), timestamp_value(raw.get("updated_at"))
        if datetime.datetime.fromisoformat(updated) < datetime.datetime.fromisoformat(created):
            raise AppError("饮食记录修改时间早于创建时间")
        item.update(version=raw["version"], created_at=created, updated_at=updated)
    return item


class FoodJournal:
    def __init__(self, store):
        self.store = store

    def entries(self, first=None, last=None):
        with self.store.lock, self.store.connection() as database:
            if first is None and last is None:
                return [dict(row) for row in database.execute("SELECT * FROM food_entries ORDER BY date,time,id")]
            first, last = date_value(first, "开始日期", True), date_value(last, "结束日期", True)
            if first > last or (datetime.date.fromisoformat(last) - datetime.date.fromisoformat(first)).days > 365:
                raise AppError("日记范围须为 1–366 天")
            return [dict(row) for row in database.execute("SELECT * FROM food_entries WHERE date BETWEEN ? AND ? ORDER BY date,time,id", (first, last))]

    def save(self, raw, update=False):
        item = validate_food(raw)
        with self.store.lock, self.store.connection() as database:
            existing = database.execute("SELECT * FROM food_entries WHERE id=?", (item["id"],)).fetchone()
            if not update and existing:
                if all(existing[key] == value for key, value in item.items()):
                    return dict(existing)
                raise AppError("这条记录已保存且内容有变化，请刷新后编辑，不会重复新增", 409)
            if update and (not existing or type(raw.get("version")) is not int or raw["version"] != existing["version"]):
                raise AppError("记录已被修改或删除，请保留输入并刷新后重试", 409)
            if item["document_id"]:
                if not database.execute("SELECT id FROM documents WHERE id=?", (item["document_id"],)).fetchone():
                    raise AppError("所选原件不存在，请重新选择", 409)
                self.store.get_document(item["document_id"])
            if not update and database.execute("SELECT COUNT(*) FROM food_entries").fetchone()[0] >= LIMIT:
                raise AppError("独立饮食记录最多 10000 条，请先备份并管理资料", 413)
            item.update(version=existing["version"] + 1 if update else 1, created_at=existing["created_at"] if update else now(), updated_at=now())
            if update:
                if item["version"] > 1000000000:
                    raise AppError("记录版本超出限制", 409)
                database.execute("UPDATE food_entries SET date=?,time=?,meal=?,note=?,document_id=?,version=?,updated_at=? WHERE id=?", tuple(item[key] for key in ("date", "time", "meal", "note", "document_id", "version", "updated_at", "id")))
            else:
                self.insert(database, item)
            self.store.audit(database, "update" if update else "create", "food_entry", item["id"])
            return item

    @staticmethod
    def insert(database, item):
        database.execute("INSERT INTO food_entries VALUES (?,?,?,?,?,?,?,?,?)", tuple(item[field] for field in FIELDS))

    def delete(self, raw):
        entry_id = identifier(raw.get("id"))
        if raw.get("confirm") is not True:
            raise AppError("请确认删除这条实际饮食记录")
        with self.store.lock, self.store.connection() as database:
            row = database.execute("SELECT version FROM food_entries WHERE id=?", (entry_id,)).fetchone()
            if not row or type(raw.get("version")) is not int or row["version"] != raw["version"]:
                raise AppError("记录已修改或删除，请刷新", 409)
            database.execute("DELETE FROM food_entries WHERE id=?", (entry_id,))
            self.store.audit(database, "delete", "food_entry", entry_id)
        return {"ok": True}
