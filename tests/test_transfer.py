import base64
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from health_journal.export_phone import ASSETS, export_phone
from health_journal.store import Store
from health_journal.transfer import export_transfer, read_transfer
from health_journal.validation import AppError


def transfer(*files):
    return json.dumps({"format": "health-journal-transfer", "version": 1, "documents": [{"filename": name, "mime": "text/plain", "sha256": hashlib.sha256(content).hexdigest(), "content": base64.b64encode(content).decode()} for name, content in files]}, ensure_ascii=False).encode()


class TransferTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.temporary.name) / "vault")

    def tearDown(self):
        self.temporary.cleanup()

    def test_roundtrip_is_append_only_and_idempotent(self):
        self.store.add_document("电脑原件.txt", b"desktop")
        entries = read_transfer(transfer(("手机随记.txt", "合成早餐记录".encode())))
        self.assertEqual(self.store.merge_documents(entries), {"imported": 1, "duplicates": 0})
        original = self.store.documents()
        self.assertEqual(self.store.merge_documents(entries), {"imported": 0, "duplicates": 1})
        self.assertEqual(self.store.documents(), original)
        destination = Store(Path(self.temporary.name) / "other")
        self.assertEqual(destination.merge_documents(read_transfer(export_transfer(self.store)))["imported"], 2)
        self.assertEqual(self.store.records(), [])
        self.assertEqual(self.store.plans(), [])
        self.assertEqual(self.store.analyses(), [])

    def test_same_content_keeps_existing_filename_and_routing(self):
        item = self.store.add_document("全科.txt", b"unchanged")
        self.store.route_document(item["id"], {"links": [{"name": "全科", "evidence": "synthetic"}], "version": 1})
        before = self.store.documents()
        result = self.store.merge_documents(read_transfer(transfer(("other.txt", b"unchanged"))))
        self.assertEqual(result["duplicates"], 1)
        self.assertEqual(self.store.documents(), before)

    def test_same_name_different_content_both_survive(self):
        self.store.merge_documents(read_transfer(transfer(("record.txt", b"one"), ("record.txt", b"two"))))
        self.assertEqual(len(self.store.documents()), 2)

    def test_invalid_entry_does_not_partially_import(self):
        raw = json.loads(transfer(("good.txt", b"good"), ("bad.txt", b"bad")))
        raw["documents"][1]["sha256"] = "0" * 64
        with self.assertRaises(AppError):
            self.store.merge_documents(read_transfer(json.dumps(raw).encode()))
        self.assertEqual(self.store.documents(), [])

    def test_write_failure_rolls_back_database_and_new_files(self):
        self.store.add_document("old.txt", b"keep")
        original = self.store.documents()
        write = self.store.write_attachment
        count = 0

        def fail_second(path, content):
            nonlocal count
            count += 1
            if count == 2:
                raise OSError("synthetic disk failure")
            write(path, content)

        with patch.object(self.store, "write_attachment", side_effect=fail_second):
            with self.assertRaises(OSError):
                self.store.merge_documents(read_transfer(transfer(("one.txt", b"one"), ("two.txt", b"two"))))
        self.assertEqual(self.store.documents(), original)
        self.assertEqual(len(list(self.store.files.iterdir())), 1)

    def test_corrupt_existing_duplicate_rolls_back_new_documents(self):
        item = self.store.add_document("old.txt", b"original")
        (self.store.files / item["sha256"]).write_bytes(b"corrupt")
        with self.assertRaises(AppError):
            self.store.merge_documents(read_transfer(transfer(("new.txt", b"new"), ("old.txt", b"original"))))
        self.assertEqual(len(self.store.documents()), 1)

    def test_rejects_ambiguous_and_unknown_format(self):
        for content in [b'{"format":"health-journal-transfer","version":1,"version":1,"documents":[]}', b'[]', b'{"format":"health-journal-transfer","version":true,"documents":[]}', b'null']:
            with self.subTest(content=content), self.assertRaises(AppError):
                read_transfer(content)

    def test_rejects_invalid_encoding_mime_path_and_extra_fields(self):
        original = json.loads(transfer(("note.txt", b"test")))
        for field, value in [("content", "dGVzdA==\n"), ("mime", "text/html"), ("filename", "../note.txt"), ("extra", "unsafe")]:
            raw = json.loads(json.dumps(original))
            raw["documents"][0][field] = value
            with self.subTest(field=field), self.assertRaises(AppError):
                read_transfer(json.dumps(raw).encode())

    def test_duplicate_hash_rejected_in_single_package(self):
        with self.assertRaises(AppError):
            read_transfer(transfer(("one.txt", b"same"), ("two.txt", b"same")))

    def test_control_character_names_are_not_accepted_by_transfer(self):
        for character in ("\t", "\x01", "\x7f", "\x85", "\ufeff"):
            with self.subTest(character=repr(character)), self.assertRaises(AppError):
                read_transfer(transfer(("note" + character + ".txt", b"test")))

    def test_legacy_export_sanitizes_filename_without_changing_original(self):
        item = self.store.add_document("note.txt", b"synthetic")
        with self.store.connection() as database:
            database.execute("UPDATE documents SET filename=? WHERE id=?", ("legacy\t.txt", item["id"]))
        entries = read_transfer(export_transfer(self.store))
        self.assertEqual(entries, [("legacy_.txt", b"synthetic")])
        self.assertEqual(self.store.documents()[0]["filename"], "legacy\t.txt")

    def test_phone_export_sanitizes_control_characters_without_changing_zip_compatibility(self):
        self.store.add_document("note\t\x01\x7f.txt", b"synthetic")
        self.assertEqual(read_transfer(export_transfer(self.store)), [("note___.txt", b"synthetic")])
        self.assertEqual(self.store.documents()[0]["filename"], "note\t\x01\x7f.txt")

    def test_limits_enforced_before_import(self):
        with patch("health_journal.transfer.MAX_TOTAL", 3), self.assertRaises(AppError):
            read_transfer(transfer(("note.txt", b"four")))
        self.store.add_document("note.txt", b"four")
        with patch("health_journal.transfer.MAX_TOTAL", 3), self.assertRaises(AppError):
            export_transfer(self.store)

    def test_export_contains_no_profile_key_or_records(self):
        self.store.add_document("note.txt", b"test")
        raw = json.loads(export_transfer(self.store))
        self.assertEqual(set(raw), {"format", "version", "documents"})
        self.assertEqual(set(raw["documents"][0]), {"filename", "mime", "sha256", "content"})

    def test_phone_export_is_static_and_does_not_overwrite(self):
        destination = Path(self.temporary.name) / "phone"
        export_phone(destination)
        self.assertEqual(set(path.name for path in destination.iterdir()), set(ASSETS) | {"catalog.json"})
        self.assertEqual(len(json.loads((destination / "catalog.json").read_text(encoding="utf-8"))), 55)
        self.assertEqual((destination / "LICENSE.txt").read_bytes(), (Path(__file__).parents[1] / "LICENSE").read_bytes())
        with self.assertRaises(FileExistsError):
            export_phone(destination)
