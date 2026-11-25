import copy
import datetime
import hashlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock
import uuid
import zipfile

from health_journal.assistant import NoRedirect, active_medication, grounded_answer, model_answer, observation_flag
from health_journal.demo import seed_demo
from health_journal.nutrition import BY_ID, MEALS, RECIPES, make_plan, restrictions, validate_plan
from health_journal.store import DEFAULT_PROFILE, Store
from health_journal.validation import AppError, date_value, number, safe_filename, timestamp_value, validate_profile, validate_record
from health_journal.vault_lock import vault_lock


TODAY = datetime.date.today().isoformat()


def record(kind="visit", **changes):
    payloads = {
        "visit": {"hospital": "合成测试机构", "conclusion": "仅用于软件测试"},
        "observation": {"value": 3.2, "unit": "mmol/L", "reference_low": 1, "reference_high": 4},
        "medication": {"dose": "原处方测试剂量", "frequency": "原处方测试频次", "prescriber": "合成处方", "start_date": TODAY},
        "symptom": {"severity": 3},
        "condition": {"status": "suspected"},
        "reminder": {"done": False},
    }
    return {"kind": kind, "title": "合成测试记录", "date": TODAY, "data": payloads[kind], **changes}


def adult(**changes):
    return validate_profile({"name": "合成成年人", "birth_date": "1990-01-01", "diet": "balanced", "diet_acknowledged": True, **changes})


def alter_backup(content, edit_manifest=None, extra=None, replace=None):
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        entries = {name: archive.read(name) for name in archive.namelist()}
    if edit_manifest:
        manifest = json.loads(entries["manifest.json"])
        edit_manifest(manifest)
        entries["manifest.json"] = json.dumps(manifest, ensure_ascii=False).encode()
    entries.update(extra or {})
    entries.update(replace or {})
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, value in entries.items():
            archive.writestr(name, value)
    return output.getvalue()


class ValidationTests(unittest.TestCase):
    def test_blank_profile_does_not_invent_personal_information(self):
        profile = validate_profile({})
        for key in ("name", "birth_date", "emergency_contact", "notes", "diet_notes"):
            self.assertEqual(profile[key], "")
        self.assertEqual(profile["allergies"], [])
        self.assertEqual(profile["sex"], "unspecified")
        self.assertEqual(profile["diet"], "unspecified")
        self.assertFalse(profile["diet_acknowledged"])
        self.assertEqual(validate_profile({"name": "  "})["name"], "")
        for value in (None, [], 1, "x" * 41):
            with self.subTest(value=value), self.assertRaises(AppError):
                validate_profile({"name": value})

    def test_timestamps_reject_non_browser_iso_separators(self):
        for value in ("2026-11-13x12:00:00+00:00", "2026-11-13 12:00:00+00:00", "2026-11-13T12:00:00+00:00:30"):
            with self.subTest(value=value), self.assertRaises(AppError):
                timestamp_value(value)
        self.assertEqual(timestamp_value("2026-11-13T12:00:00.123456+00:00"), "2026-11-13T12:00:00.123456+00:00")
        self.assertEqual(timestamp_value("2026-11-13T12:00:00Z"), "2026-11-13T12:00:00+00:00")

    def test_all_record_kinds(self):
        for kind in ("visit", "observation", "medication", "symptom", "condition", "reminder"):
            with self.subTest(kind=kind):
                self.assertEqual(validate_record(record(kind))["kind"], kind)

    def test_nonfinite_and_invalid_numbers(self):
        for value in (float("nan"), float("inf"), "-Infinity", "NaN", "x", True, [], {}):
            with self.subTest(value=value), self.assertRaises(AppError):
                number(value, "数值")

    def test_optional_zero_is_not_missing(self):
        self.assertEqual(number(0, "数值", optional=True), 0)
        self.assertIsNone(number("", "数值", optional=True))

    def test_future_and_malformed_dates(self):
        tomorrow = (datetime.date.today() + datetime.timedelta(days=1)).isoformat()
        for value in ("2024-02-30", "1899-12-31", "2024-1-1", None, tomorrow):
            with self.subTest(value=value), self.assertRaises(AppError):
                date_value(value, "日期", True, False)
        self.assertEqual(validate_record(record("reminder", date=tomorrow))["date"], tomorrow)

    def test_severity_requires_integer(self):
        for value in (0.5, 10.1, -1, True):
            with self.subTest(value=value), self.assertRaises(AppError):
                validate_record(record("symptom", data={"severity": value}))

    def test_reference_bounds(self):
        with self.assertRaises(AppError):
            validate_record(record("observation", data={"value": 3, "unit": "g/L", "reference_low": 4, "reference_high": 2}))

    def test_confirmed_requires_document(self):
        with self.assertRaises(AppError):
            validate_record(record("condition", data={"status": "confirmed"}))
        self.assertEqual(validate_record(record("condition"))["data"]["status"], "suspected")

    def test_medication_dates_and_source_required(self):
        for payload in ({"dose": "1", "frequency": "1", "prescriber": ""}, {"dose": "1", "frequency": "1", "prescriber": "合成", "start_date": "2024-01-02", "end_date": "2024-01-01"}):
            with self.subTest(payload=payload), self.assertRaises(AppError):
                validate_record(record("medication", data=payload))

    def test_wrong_types_and_lengths(self):
        for change in ({"title": []}, {"title": " "}, {"title": "字" * 121}, {"data": []}, {"kind": {}}, {"document_id": "../../x"}, {"notes": "a\x00b"}):
            with self.subTest(change=change), self.assertRaises(AppError):
                validate_record({**record(), **change})
        for change in ({"allergies": "牛奶"}, {"clinical_diet": "false"}, {"allergies": [""]}):
            with self.subTest(change=change), self.assertRaises(AppError):
                validate_profile(change)

    def test_safe_filenames(self):
        for filename in ("../secret.txt", "x\\file.txt", ".env", "a\r\nb.txt", ""):
            with self.subTest(filename=filename), self.assertRaises(AppError):
                safe_filename(filename)
        self.assertEqual(safe_filename("报告:合成.txt"), "报告_合成.txt")


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="health-journal-test-")
        self.addCleanup(self.temp.cleanup)
        self.store = Store(Path(self.temp.name) / "original")

    def empty_store(self):
        return Store(Path(self.temp.name) / str(uuid.uuid4()))

    def seed(self):
        seed_demo(self.store)
        return self.store.backup()

    def test_new_store_remains_empty_on_restart(self):
        for store in (self.store, Store(self.store.directory)):
            self.assertEqual(store.profile(), DEFAULT_PROFILE)
            self.assertEqual(store.profile()["name"], "")
            self.assertEqual(store.profile()["diet"], "unspecified")
            for collection in (store.records, store.documents, store.plans, store.analyses, store.audits):
                self.assertEqual(collection(), [])
            self.assertFalse(store.setting("demo"))
            self.assertEqual(list(store.files.iterdir()), [])

    def test_empty_backup_roundtrip_preserves_unknown_profile(self):
        restored = self.empty_store()
        restored.restore(self.store.backup())
        self.assertEqual(restored.profile(), DEFAULT_PROFILE)
        self.assertEqual(restored.records(), [])
        self.assertEqual(restored.plans(), [])
        self.assertFalse(restored.setting("demo"))

    def test_existing_profile_is_not_cleared_on_restart(self):
        profile = self.store.profile(adult(name="合成已保存称呼", notes="保留合成备注"))
        saved = self.store.save_record(record())
        reopened = Store(self.store.directory)
        self.assertEqual(reopened.profile(), profile)
        self.assertEqual(reopened.records(), [saved])

    def test_unspecified_diet_cannot_generate_plan_even_after_acknowledgment(self):
        profile = adult(diet="unspecified")
        with self.assertRaisesRegex(AppError, "选择饮食偏好"):
            make_plan(TODAY, profile, [])
        self.assertEqual(self.store.plans(), [])

    def test_create_update_delete_and_version(self):
        saved = self.store.save_record(record())
        updated = self.store.save_record({**saved, "title": "合成修订"}, saved["id"])
        self.assertEqual(updated["version"], 2)
        self.assertEqual(updated["created_at"], saved["created_at"])
        with self.assertRaises(AppError) as error:
            self.store.save_record(saved, saved["id"])
        self.assertEqual(error.exception.status, 409)
        with self.assertRaises(AppError):
            self.store.delete_record(saved["id"], 1)
        self.store.delete_record(saved["id"], 2)
        self.assertEqual(self.store.records(), [])

    def test_profile_conflict(self):
        version = self.store.profile_version()
        self.store.profile(adult(), expected=version)
        with self.assertRaises(AppError) as error:
            self.store.profile(adult(allergies=["牛奶"]), expected=version)
        self.assertEqual(error.exception.status, 409)
        self.assertEqual(self.store.profile()["allergies"], [])

    def test_persistence(self):
        saved = self.store.save_record(record())
        reopened = Store(self.store.directory)
        self.assertEqual(reopened.get_record(saved["id"]), saved)

    def test_document_roundtrip_dedup_and_link_protection(self):
        content = "纯合成报告".encode()
        document = self.store.add_document("合成.txt", content)
        duplicate = self.store.add_document("合成副本.txt", content)
        self.assertTrue(duplicate["duplicate"])
        self.assertEqual(document["id"], duplicate["id"])
        self.assertEqual(self.store.get_document(document["id"])[1], content)
        saved = self.store.save_record(record(document_id=document["id"]))
        self.assertEqual(self.store.documents()[0]["links"], 1)
        with self.assertRaises(AppError):
            self.store.delete_document(document["id"])
        self.store.delete_record(saved["id"], saved["version"])
        self.store.delete_document(document["id"])
        self.assertEqual(list(self.store.files.iterdir()), [])

    def test_missing_reference(self):
        with self.assertRaises(AppError):
            self.store.save_record(record(document_id=str(uuid.uuid4())))
        self.assertEqual(self.store.records(), [])

    def test_file_signature_size_and_utf8(self):
        for name, content in (("a.pdf", b"not a pdf"), ("a.txt", b"\xff"), ("a.txt", b"a\x00b"), ("a.html", b"<p>no</p>"), ("a.txt", b"")):
            with self.subTest(name=name, content=content), self.assertRaises(AppError):
                self.store.add_document(name, content)
        with mock.patch("health_journal.store.MAX_FILE", 3), self.assertRaises(AppError):
            self.store.add_document("a.txt", b"1234")

    def test_corrupt_attachment_never_exported_or_deduplicated(self):
        doc = self.store.add_document("a.txt", b"original")
        (self.store.files / doc["sha256"]).write_bytes(b"damaged")
        for callback in (lambda: self.store.get_document(doc["id"]), self.store.backup, lambda: self.store.add_document("a.txt", b"original")):
            with self.subTest(callback=callback), self.assertRaises(AppError):
                callback()

    def test_add_document_cleans_new_file_on_database_insert_failure(self):
        with mock.patch("health_journal.store.suggest_departments", side_effect=RuntimeError("synthetic failure")):
            with self.assertRaises(RuntimeError):
                self.store.add_document("orphan.txt", b"must-not-remain")
        self.assertEqual(self.store.documents(), [])
        self.assertEqual(list(self.store.files.iterdir()), [])

    def test_audit_has_no_clinical_text(self):
        self.store.save_record(record(title="合成隐私标记", notes="不应进入日志"))
        encoded = json.dumps(self.store.audits(), ensure_ascii=False)
        self.assertNotIn("合成隐私标记", encoded)
        self.assertNotIn("不应进入日志", encoded)

    def test_backup_roundtrip_preserves_every_record_and_attachment(self):
        self.seed()
        item = self.store.records()[0]
        self.store.save_record({**item, "notes": "合成修订"}, item["id"])
        self.store.set_setting("model", "never-export-me")
        backup = self.store.backup()
        restored = self.empty_store()
        result = restored.restore(backup)
        self.assertEqual(result["records"], len(self.store.records()))
        self.assertEqual(restored.records(), self.store.records())
        self.assertEqual(restored.documents(), self.store.documents())
        self.assertEqual(restored.profile(), self.store.profile())
        self.assertEqual(restored.plans(), self.store.plans())
        self.assertTrue(restored.setting("demo"))
        self.assertEqual(restored.setting("model"), "")
        for doc in self.store.documents():
            self.assertEqual(restored.get_document(doc["id"])[1], self.store.get_document(doc["id"])[1])

    def test_restore_refuses_occupied_or_modified_profile(self):
        backup = self.seed()
        with self.assertRaises(AppError):
            self.store.restore(backup)
        restored = self.empty_store()
        restored.profile(adult())
        with self.assertRaises(AppError):
            restored.restore(backup)

    def test_restore_rejects_path_traversal_and_unknown_entries(self):
        backup = self.seed()
        for name in ("../outside", "/absolute", "attachments/../outside", "unlisted.txt"):
            target = self.empty_store()
            with self.subTest(name=name), self.assertRaises(AppError):
                target.restore(alter_backup(backup, extra={name: b"no"}))
            self.assertEqual(target.records(), [])
            self.assertEqual(list(target.files.iterdir()), [])

    def test_restore_rejects_duplicate_ids_missing_refs_and_bad_timestamps(self):
        backup = self.seed()
        edits = [
            lambda data: data["records"].append(data["records"][0]),
            lambda data: data["documents"].append(data["documents"][0]),
            lambda data: data["meal_plans"].append(data["meal_plans"][0]),
            lambda data: data["records"][0].update(document_id=str(uuid.uuid4())),
            lambda data: data["records"][0].update(version=True),
            lambda data: data["records"][0].update(created_at="2020-01-01"),
            lambda data: data.update(version=True),
            lambda data: data.update(profile=[]),
            lambda data: data["documents"][0].update(size=999),
            lambda data: data["meal_plans"][0]["meals"]["breakfast"].update(recipe_id="missing"),
        ]
        for index, edit in enumerate(edits):
            target = self.empty_store()
            with self.subTest(index=index), self.assertRaises(AppError):
                target.restore(alter_backup(backup, edit))
            self.assertEqual(target.profile(), DEFAULT_PROFILE)
            self.assertEqual(target.records(), [])
            self.assertEqual(list(target.files.iterdir()), [])

    def test_restore_rejects_hash_damage(self):
        backup = self.seed()
        name = "attachments/" + self.store.documents()[0]["sha256"]
        target = self.empty_store()
        with self.assertRaises(AppError):
            target.restore(alter_backup(backup, replace={name: b"tampered"}))

    def test_restore_replaces_unreferenced_corrupt_orphan(self):
        backup = self.seed()
        target = self.empty_store()
        doc = self.store.documents()[0]
        (target.files / doc["sha256"]).write_bytes(b"old orphan")
        target.restore(backup)
        self.assertEqual(hashlib.sha256(target.get_document(doc["id"])[1]).hexdigest(), doc["sha256"])

    def test_restore_limits_and_malformed_archive(self):
        backup = self.seed()
        target = self.empty_store()
        for content in (b"bad", b"PK\x03\x04bad"):
            with self.subTest(content=content), self.assertRaises(AppError):
                target.restore(content)
        with mock.patch("health_journal.store.MAX_EXPANDED", 1), self.assertRaises(AppError):
            target.restore(backup)
        with mock.patch("health_journal.store.MAX_BACKUP", 1), self.assertRaises(AppError):
            target.restore(backup)

    def test_export_never_emits_unrestorable_oversize_archive(self):
        self.seed()
        with mock.patch("health_journal.store.MAX_EXPANDED", 1), self.assertRaises(AppError) as error:
            self.store.backup()
        self.assertEqual(error.exception.status, 413)

    def test_restore_write_failure_rolls_back(self):
        backup = self.seed()
        target = self.empty_store()
        with mock.patch.object(target, "insert_record", side_effect=OSError("synthetic disk failure")), self.assertRaises(OSError):
            target.restore(backup)
        self.assertEqual(target.documents(), [])
        self.assertEqual(target.records(), [])
        self.assertEqual(list(target.files.iterdir()), [])
        self.assertEqual(target.profile(), DEFAULT_PROFILE)

    def test_demo_cannot_mix_with_personal_records(self):
        self.store.save_record(record())
        with self.assertRaises(AppError):
            seed_demo(self.store)

    def test_demo_refuses_private_profile_with_default_name(self):
        profile = self.store.profile({**DEFAULT_PROFILE, "notes": "合成私密信息", "allergies": ["牛奶"]})
        with self.assertRaises(AppError):
            seed_demo(self.store)
        self.assertEqual(self.store.profile(), profile)
        self.assertEqual(self.store.records(), [])

    def test_attachment_size_mismatch_is_rejected(self):
        doc = self.store.add_document("synthetic.txt", b"synthetic")
        with self.store.connection() as database:
            database.execute("UPDATE documents SET size = size + 1 WHERE id = ?", (doc["id"],))
        with self.assertRaises(AppError):
            self.store.get_document(doc["id"])

    def test_v2_backup_requires_complete_collections_and_routing(self):
        backup = self.seed()
        for mutation in (lambda data: data.pop("analyses"), lambda data: data["documents"][0].pop("routing"), lambda data: data["documents"][0].pop("routing_version")):
            target = self.empty_store()
            with self.subTest(mutation=mutation), self.assertRaises(AppError):
                target.restore(alter_backup(backup, mutation))
            self.assertEqual(target.records(), [])
            self.assertEqual(target.documents(), [])

    def test_backup_rejects_duplicate_json_keys(self):
        backup = self.seed()
        with self.assertRaises(AppError):
            self.empty_store().restore(alter_backup(backup, replace={"manifest.json": b'{"version":2,"version":1}'}))

    def test_demo_is_idempotent(self):
        seed_demo(self.store)
        original = self.store.records()
        seed_demo(self.store)
        self.assertEqual(self.store.records(), original)

    @unittest.skipIf(os.name == "nt", "POSIX same-process flock test")
    def test_single_instance_lock(self):
        with vault_lock(self.store.directory):
            with self.assertRaises(AppError):
                with vault_lock(self.store.directory):
                    self.fail("second instance acquired lock")
        with vault_lock(self.store.directory):
            pass


class NutritionTests(unittest.TestCase):
    def test_deterministic_and_all_three_meals(self):
        plan = make_plan(TODAY, adult(), [])
        self.assertEqual(plan, make_plan(TODAY, adult(), []))
        self.assertEqual(set(plan["meals"]), set(MEALS))
        self.assertEqual(validate_plan(plan), plan)

    def test_allergen_exclusion_across_revisions(self):
        profile = adult(allergies=["鸡蛋", "牛奶", "小麦", "大豆", "鱼", "甲壳类", "坚果", "花生", "芝麻"])
        for revision in range(40):
            plan = make_plan(TODAY, profile, [], revision)
            for entry in plan["meals"].values():
                self.assertFalse(set(BY_ID[entry["recipe_id"]]["allergens"]) & set(profile["allergies"]))

    def test_vegetarian_respected(self):
        for revision in range(20):
            for entry in make_plan(TODAY, adult(diet="vegetarian"), [], revision)["meals"].values():
                self.assertTrue(BY_ID[entry["recipe_id"]]["vegetarian"])

    def test_uncertainty_and_special_diets_block(self):
        for changes in ({"allergies": ["芹菜"]}, {"clinical_diet": True}, {"diet_notes": "合成医生医嘱"}, {"diet_acknowledged": False}, {"birth_date": TODAY}):
            with self.subTest(changes=changes), self.assertRaises(AppError):
                make_plan(TODAY, adult(**changes), [])

    def test_confirmed_sensitive_condition_blocks_but_not_suspected_diagnosis(self):
        item = validate_record(record("condition", title="合成糖尿病", document_id=str(uuid.uuid4()), data={"status": "confirmed"}))
        self.assertTrue(restrictions(adult(), [item]))
        item["data"]["status"] = "suspected"
        self.assertEqual(restrictions(adult(), [item]), [])

    def test_invalid_plan_types(self):
        plan = make_plan(TODAY, adult(), [])
        for field, value in (("revision", True), ("revision", -1), ("date", "bad"), ("meals", [])):
            with self.subTest(field=field, value=value), self.assertRaises(AppError):
                validate_plan({**plan, field: value})
        plan["meals"]["breakfast"]["recipe_id"] = "l1"
        with self.assertRaises(AppError):
            validate_plan(plan)

    def test_recipe_identifiers_unique(self):
        self.assertEqual(len(BY_ID), len(RECIPES))


class AssistantTests(unittest.TestCase):
    def stored(self, kind="visit", **changes):
        return {**validate_record(record(kind, **changes)), "id": str(uuid.uuid4()), "created_at": "2024-01-01T00:00:00+00:00"}

    def test_current_medication_date_and_status(self):
        item = self.stored("medication")
        self.assertTrue(active_medication(item, TODAY))
        for changes in ({"status": "stopped"}, {"status": "planned"}, {"start_date": "9999-01-01"}, {"end_date": "1900-01-01"}):
            modified = {**item, "data": {**item["data"], **changes}}
            with self.subTest(changes=changes):
                self.assertFalse(active_medication(modified, TODAY))

    def test_current_medication_query_excludes_old_records(self):
        current = self.stored("medication", title="合成当前药物")
        stopped = copy.deepcopy(current)
        stopped["id"] = str(uuid.uuid4())
        stopped["data"]["status"] = "stopped"
        answer = grounded_answer("我目前记录了哪些用药？", [current, stopped])
        self.assertEqual([item["id"] for item in answer["sources"]], [current["id"]])

    def test_observation_pending_nonexact_and_reference(self):
        item = self.stored("observation")
        self.assertEqual(observation_flag(item), "待核对")
        item["verification"] = "verified"
        item["data"].update(comparator=">", value=999)
        self.assertEqual(observation_flag(item), "非精确值")
        item["data"]["comparator"] = "="
        self.assertEqual(observation_flag(item), "高于报告参考范围")
        item["data"]["value"] = 0
        self.assertEqual(observation_flag(item), "低于报告参考范围")
        item["data"].update(reference_low=None, reference_high=None)
        self.assertEqual(observation_flag(item), "未提供参考范围")

    def test_suspected_never_becomes_confirmed(self):
        item = self.stored("condition")
        before = copy.deepcopy(item)
        answer = grounded_answer("可能得了什么病？", [item])
        self.assertIn("不是确诊", answer["sections"][0]["text"])
        self.assertIn("不根据零散症状推断疾病", answer["sections"][1]["text"])
        self.assertEqual(item, before)

    def test_empty_records_not_false_reassurance(self):
        answer = grounded_answer("有危险吗", [])
        self.assertEqual(answer["sources"], [])
        self.assertIn("不代表不存在", answer["sections"][0]["text"])
        self.assertIn("120", answer["safety"])

    def test_result_limit_discloses_incomplete_excerpt(self):
        answer = grounded_answer("整理记录", [self.stored() for index in range(15)])
        self.assertEqual(len(answer["sources"]), 12)
        self.assertIn("匹配 15 条", answer["sections"][0]["text"])
        self.assertIn("不要将本回答视为全部病史", answer["sections"][0]["text"])

    def test_ongoing_redflag_signaled(self):
        item = self.stored("symptom", data={"severity": 7, "red_flags": True})
        self.assertTrue(grounded_answer("整理记录", [item])["urgent"])
        item["data"]["status"] = "resolved"
        self.assertFalse(grounded_answer("整理记录", [item])["urgent"])

    def test_redflag_does_not_wait_for_model(self):
        item = self.stored("symptom", data={"severity": 8, "red_flags": True})
        with mock.patch("health_journal.assistant.ollama_request") as request:
            answer = model_answer("整理症状", [item], "local-model")
        request.assert_not_called()
        self.assertTrue(answer["urgent"])
        self.assertIn("立即", answer["sections"][0]["heading"])

    def test_upcoming_reminders_exclude_completed(self):
        incomplete = self.stored("reminder", title="合成待办")
        completed = self.stored("reminder", title="合成完成", data={"done": True})
        answer = grounded_answer("接下来有哪些随访", [completed, incomplete])
        self.assertEqual([item["id"] for item in answer["sources"]], [incomplete["id"]])

    def test_cloud_model_blocked_before_sending(self):
        with mock.patch("health_journal.assistant.ollama_request") as request:
            with self.assertRaises(AppError):
                model_answer("整理", [], "some:cloud")
            request.assert_not_called()

    def test_remote_or_unknown_model_metadata_blocked(self):
        for metadata in ({"remote_host": "example.com"}, {}, {"remote_model": "cloud", "model_info": {"x": 1}}):
            with self.subTest(metadata=metadata), mock.patch("health_journal.assistant.ollama_request", return_value=metadata) as request:
                with self.assertRaises(AppError):
                    model_answer("整理", [], "local-name")
                self.assertEqual(request.call_count, 1)
                self.assertEqual(request.call_args.args[0], "show")

    def test_model_draft_is_separate_and_readonly(self):
        items = [self.stored()]
        original = copy.deepcopy(items)
        with mock.patch("health_journal.assistant.ollama_request", side_effect=[{"model_info": {"architecture": "test"}}, {"message": {"content": "合成测试草稿"}}]):
            result = model_answer("整理", items, "local-model")
        self.assertEqual(items, original)
        self.assertEqual(result["mode"], "ollama")
        self.assertIn("草稿", result["model_notice"])

    def test_malformed_local_model_messages_are_controlled_errors(self):
        for message in (None, 2, [], {"content": []}, {"content": "\ud800"}, {"content": "bad\x00text"}):
            with self.subTest(message=message), mock.patch("health_journal.assistant.ollama_request", side_effect=[{"model_info": {"architecture": "test"}}, {"message": message}]):
                with self.assertRaises(AppError) as error:
                    model_answer("合成问题", [], "local-model")
                self.assertEqual(error.exception.status, 502)

    def test_redirect_denied(self):
        with self.assertRaises(AppError):
            NoRedirect().redirect_request(None, None, 302, "Found", {}, "https://example.com")


if __name__ == "__main__":
    unittest.main()
