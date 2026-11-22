import base64
import binascii
import hashlib
import json
import re

from .store import check_document, encode
from .validation import AppError, safe_filename, strict_json_constant, unique_json_object


MAX_TRANSFER = 58 * 1024 * 1024
MAX_TOTAL = 40 * 1024 * 1024
MAX_ITEMS = 500


def transfer_filename(value):
    return re.sub(r"[\x00-\x1f\x7f-\x9f\ufeff]", "_", safe_filename(value))


def read_transfer(content):
    if len(content) > MAX_TRANSFER:
        raise AppError("资料互传文件超过 58 MB", 413)
    try:
        raw = json.loads(content, parse_constant=strict_json_constant, object_pairs_hook=unique_json_object)
        if not isinstance(raw, dict) or set(raw) != {"format", "version", "documents"} or raw["format"] != "health-journal-transfer" or type(raw["version"]) is not int or raw["version"] != 1:
            raise ValueError()
        if not isinstance(raw["documents"], list) or len(raw["documents"]) > MAX_ITEMS:
            raise ValueError()
        approved, total, digests = [], 0, set()
        for item in raw["documents"]:
            if not isinstance(item, dict) or set(item) != {"filename", "mime", "sha256", "content"} or not isinstance(item["content"], str):
                raise ValueError()
            data = base64.b64decode(item["content"], validate=True)
            if base64.b64encode(data).decode("ascii") != item["content"]:
                raise ValueError()
            filename, mime = check_document(transfer_filename(item["filename"]), data)
            digest = hashlib.sha256(data).hexdigest()
            if filename != item["filename"] or mime != item["mime"] or digest != item["sha256"] or digest in digests:
                raise ValueError()
            digests.add(digest)
            total += len(data)
            if total > MAX_TOTAL:
                raise AppError("互传原件总量超过 40 MB", 413)
            approved.append((filename, data))
        return approved
    except (ValueError, TypeError, KeyError, UnicodeError, binascii.Error, RecursionError):
        raise AppError("互传文件结构、编码或原件校验失败；未导入任何资料")


def export_transfer(store):
    with store.lock:
        documents = store.documents()
        if len(documents) > MAX_ITEMS or sum(item["size"] for item in documents) > MAX_TOTAL:
            raise AppError("互传仅支持最多 500 份、原件合计 40 MB；请单独下载所需原件", 413)
        entries = []
        for document in documents:
            item, content = store.get_document(document["id"])
            entries.append({"filename": transfer_filename(item["filename"]), "mime": item["mime"], "sha256": item["sha256"], "content": base64.b64encode(content).decode("ascii")})
        return encode({"format": "health-journal-transfer", "version": 1, "documents": entries}).encode("utf-8")
