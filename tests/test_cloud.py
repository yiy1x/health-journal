import base64
import io
import json
from pathlib import Path
import socket
import tempfile
import unittest
from unittest import mock
import zipfile

from health_journal.cloud import CloudAI, DEFAULT_CONFIG, endpoint_url, parse_result, public_addresses, request_completion
from health_journal.departments import CATALOG, NAMES, suggest_departments
from health_journal.store import Store
from health_journal.validation import AppError
from tests.test_core import TODAY, adult, alter_backup, record


FAKE_KEY = "synthetic-key-not-valid-for-any-provider"
FOOD = {"summary": "合成测试：可能是鸡蛋与豆浆", "foods": [{"name": "鸡蛋", "portion": "无法确认", "confidence": "low"}], "suggestions": ["核对实际配料"], "uncertainties": ["无法判断加糖量"], "questions": ["豆浆是否加糖？"]}
REPORT = {"summary": "合成血糖报告整理", "departments": [{"name": "内分泌科", "evidence": "原文含血糖"}], "excerpts": [{"title": "血糖", "quote": "血糖 5.0 mmol/L", "location": "第1行", "department": "内分泌科"}], "uncertainties": ["日期需核对"], "questions": []}


class CloudTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="health-cloud-test-")
        self.addCleanup(self.temp.cleanup)
        self.store = Store(Path(self.temp.name) / "vault")
        self.cloud = CloudAI(self.store)
        self.configure()

    def configure(self, **changes):
        raw = {"provider": "openai", "model": "synthetic-vision", "vision": True, "api_key": FAKE_KEY, "revision": self.cloud.revision, **changes}
        return self.cloud.configure(raw)

    def prepare(self, **changes):
        return self.cloud.prepare({"task": "breakfast", "text": "合成测试早餐", **changes})

    def run_food(self, **changes):
        consent = self.prepare(**changes)
        with mock.patch("health_journal.cloud.request_completion", return_value=json.dumps(FOOD)):
            return self.cloud.run({"approval_id": consent["approval_id"], "confirm": True})

    def test_key_memory_only_not_echoed_database_or_backup(self):
        self.assertTrue(self.cloud.config()["has_key"])
        self.assertNotIn(FAKE_KEY, json.dumps(self.cloud.config()))
        self.assertNotIn(FAKE_KEY.encode(), self.store.database.read_bytes())
        with zipfile.ZipFile(io.BytesIO(self.store.backup())) as archive:
            self.assertNotIn(FAKE_KEY.encode(), archive.read("manifest.json"))
        self.assertFalse(CloudAI(self.store).config()["has_key"])

    def test_schema_v1_upgrade_preserves_records_and_initializes_routing(self):
        doc = self.store.add_document("合成血糖.txt", b"synthetic source")
        saved = self.store.save_record(record(document_id=doc["id"]))
        with self.store.connection() as database:
            database.executescript("DROP TABLE analyses; DROP TABLE document_routes; PRAGMA user_version = 1;")
        upgraded = Store(self.store.directory)
        self.assertEqual(upgraded.records(), [saved])
        self.assertEqual(upgraded.get_document(doc["id"])[1], b"synthetic source")
        self.assertEqual(upgraded.documents()[0]["routing"]["links"][0]["name"], "内分泌科")
        self.assertEqual(upgraded.documents()[0]["routing"]["status"], "pending")
        self.assertEqual(upgraded.analyses(), [])
        with upgraded.connection() as database:
            self.assertEqual(database.execute("PRAGMA user_version").fetchone()[0], 4)

    def test_prepare_never_calls_external_api(self):
        with mock.patch("health_journal.cloud.request_completion") as request:
            consent = self.prepare()
        request.assert_not_called()
        self.assertEqual(consent["endpoint"], "https://api.openai.com/v1/chat/completions")
        self.assertIn("合成测试早餐", consent["text"])
        self.assertNotIn(FAKE_KEY, json.dumps(consent))

    def test_default_sends_neither_profile_nor_records(self):
        self.store.profile(adult(name="合成私密姓名", emergency_contact="合成私密电话", diet_notes="合成私密医嘱"))
        self.store.save_record(record(title="合成私密就诊"))
        consent = self.prepare()
        for secret in ("合成私密姓名", "合成私密电话", "合成私密医嘱", "合成私密就诊"):
            self.assertNotIn(secret, consent["text"])

    def test_profile_opt_in_is_minimized_and_does_not_send_conditions(self):
        self.store.profile(adult(name="合成姓名不应发送", emergency_contact="合成电话不应发送", allergies=["牛奶"]))
        doc = self.store.add_document("synthetic.txt", b"synthetic source")
        self.store.save_record(record("condition", title="肾病不应随饮食选项发送", data={"status": "confirmed"}, document_id=doc["id"]))
        consent = self.prepare(include_profile=True)
        self.assertIn("牛奶", consent["text"])
        for value in ("合成姓名不应发送", "合成电话不应发送", "肾病不应随饮食选项发送"):
            self.assertNotIn(value, consent["text"])

    def test_record_opt_in_includes_only_visible_excerpt(self):
        saved = self.store.save_record(record(title="合成被授权记录"))
        consent = self.prepare(include_records=True)
        self.assertIn("合成被授权记录", consent["text"])
        self.assertIn(saved["id"], consent["text"])

    def test_record_opt_in_retains_facts_alongside_emergency_and_long_question(self):
        saved = self.store.save_record(record("symptom", title="合成持续症状", data={"severity": 3, "status": "ongoing", "red_flags": True}))
        consent = self.prepare(text="合成持续症状" + "a" * 1100, include_records=True)
        content = json.loads(consent["text"])
        self.assertIn(saved["title"], content["record_excerpts"])
        self.assertIn("120", content["urgent_notice"])
        self.assertIn("前1000", content["record_retrieval_note"])
        self.assertEqual(len(content["user_text"]), 1106)

    def test_confirmation_required_and_single_use(self):
        consent = self.prepare()
        with mock.patch("health_journal.cloud.request_completion", return_value=json.dumps(FOOD)) as request:
            with self.assertRaises(AppError):
                self.cloud.run({"approval_id": consent["approval_id"], "confirm": "true"})
            request.assert_not_called()
            self.cloud.run({"approval_id": consent["approval_id"], "confirm": True})
            with self.assertRaises(AppError):
                self.cloud.run({"approval_id": consent["approval_id"], "confirm": True})
            self.assertEqual(request.call_count, 1)

    def test_expiry_and_config_change_invalidate_consent(self):
        consent = self.prepare()
        self.cloud.pending[consent["approval_id"]]["expires"] = 0
        with self.assertRaises(AppError):
            self.cloud.run({"approval_id": consent["approval_id"], "confirm": True})
        consent = self.prepare()
        self.configure(model="changed-model")
        with self.assertRaises(AppError):
            self.cloud.run({"approval_id": consent["approval_id"], "confirm": True})

    def test_clear_key_and_provider_change(self):
        self.prepare()
        self.cloud.clear_key()
        self.assertFalse(self.cloud.config()["has_key"])
        self.assertEqual(self.cloud.pending, {})
        self.configure()

    def test_request_completion_falls_back_to_next_verified_public_address_before_send(self):
        attempted = []
        class FakeConnection:
            def __init__(self, host, address):
                self.address = address
            def connect(self):
                attempted.append(self.address)
                if self.address == "2001:db8::1":
                    raise OSError("synthetic ipv6 unreachable")
            def request(self, *arguments, **options):
                pass
            def getresponse(self):
                class Response:
                    status = 200
                    def read(self, limit):
                        return json.dumps({"choices": [{"finish_reason": "stop", "message": {"content": json.dumps(FOOD)}}]}).encode()
                return Response()
            def close(self):
                pass
        with mock.patch("health_journal.cloud.public_addresses", return_value=["2001:db8::1", "93.184.216.34"]), mock.patch("health_journal.cloud.PinnedHTTPS", FakeConnection):
            content = request_completion({"provider": "openai", "base_url": "https://api.openai.com/v1", "model": "synthetic"}, FAKE_KEY, [])
        self.assertEqual(attempted, ["2001:db8::1", "93.184.216.34"])
        self.assertEqual(json.loads(content), FOOD)
        self.configure(provider="custom", base_url="https://example.com/v1", api_key="")
        self.assertFalse(self.cloud.config()["has_key"])

    def test_stale_config_and_header_injection_rejected(self):
        for changes in ({"revision": "stale"}, {"api_key": "a\r\nHeader:value"}):
            with self.subTest(changes=changes), self.assertRaises(AppError):
                self.configure(**changes)

    def test_failed_config_save_cannot_rebind_key_to_previous_provider(self):
        consent = self.prepare()
        original = self.cloud.config()
        with mock.patch.object(self.store, "set_setting", side_effect=OSError("synthetic disk failure")), self.assertRaises(OSError):
            self.configure(provider="dashscope", api_key="different-synthetic-key")
        self.assertEqual(self.cloud.config(), original)
        with mock.patch("health_journal.cloud.request_completion", return_value=json.dumps(FOOD)) as completion:
            self.cloud.run({"approval_id": consent["approval_id"], "confirm": True})
        self.assertEqual(completion.call_args.args[1], FAKE_KEY)

    def test_second_request_during_inflight_analysis_is_blocked(self):
        consent = self.prepare()
        self.cloud.busy = True
        with mock.patch("health_journal.cloud.request_completion") as completion, self.assertRaises(AppError):
            self.cloud.run({"approval_id": consent["approval_id"], "confirm": True})
        completion.assert_not_called()
        self.assertIn(consent["approval_id"], self.cloud.pending)

    def test_restore_checks_source_metadata_and_routing(self):
        doc = self.store.add_document("source.txt", b"synthetic")
        self.run_food(document_id=doc["id"])
        backup = self.store.backup()
        for mutation in (lambda data: data["analyses"][0]["provenance"]["source"].update(filename="wrong.txt"), lambda data: data["documents"][0]["routing"].update(links=[{"name": "不存在科室"}])):
            with self.subTest(mutation=mutation), self.assertRaises(AppError):
                Store(Path(self.temp.name) / "invalid-metadata").restore(alter_backup(backup, mutation))

    def test_unknown_key_blocks_prepare(self):
        self.cloud.clear_key()
        with self.assertRaises(AppError):
            self.prepare()

    def test_image_payload_exact_and_vision_required(self):
        content = b"\x89PNG\r\n\x1a\nsynthetic-test-bytes"
        doc = self.store.add_document("synthetic.png", content)
        consent = self.prepare(document_id=doc["id"])
        self.assertEqual(consent["source"]["sha256"], doc["sha256"])
        with mock.patch("health_journal.cloud.request_completion", return_value=json.dumps(FOOD)) as request:
            self.cloud.run({"approval_id": consent["approval_id"], "confirm": True})
            sent = request.call_args.args[2][1]["content"][1]["image_url"]["url"]
        self.assertEqual(base64.b64decode(sent.split(",")[1]), content)
        self.configure(vision=False)
        with self.assertRaises(AppError):
            self.prepare(document_id=doc["id"])

    def test_pdf_provider_gate_and_payload(self):
        doc = self.store.add_document("test.pdf", b"%PDF-synthetic-test-only")
        consent = self.prepare(task="document", document_id=doc["id"])
        part = self.cloud.pending[consent["approval_id"]]["messages"][1]["content"][1]
        self.assertEqual(part["type"], "file")
        self.assertEqual(part["file"]["filename"], "report.pdf")
        self.configure(provider="dashscope")
        with self.assertRaises(AppError):
            self.prepare(task="document", document_id=doc["id"])

    def test_no_silent_input_truncation(self):
        doc = self.store.add_document("long.txt", ("字" * 60001).encode())
        with self.assertRaises(AppError):
            self.prepare(task="document", document_id=doc["id"])

    def test_deleted_source_blocks_sending(self):
        doc = self.store.add_document("test.txt", b"synthetic")
        consent = self.prepare(document_id=doc["id"])
        self.store.delete_document(doc["id"])
        with mock.patch("health_journal.cloud.request_completion") as request:
            with self.assertRaises(AppError):
                self.cloud.run({"approval_id": consent["approval_id"], "confirm": True})
            request.assert_not_called()

    def test_model_error_not_retried_or_saved(self):
        consent = self.prepare()
        with mock.patch("health_journal.cloud.request_completion", side_effect=AppError("synthetic failure")) as request:
            with self.assertRaises(AppError):
                self.cloud.run({"approval_id": consent["approval_id"], "confirm": True})
        self.assertEqual(request.call_count, 1)
        self.assertEqual(self.store.analyses(), [])
        self.assertFalse(self.cloud.busy)

    def test_model_cannot_write_records_or_confirm_routes(self):
        doc = self.store.add_document("synthetic.txt", "血糖 5.0 mmol/L".encode())
        consent = self.prepare(task="document", document_id=doc["id"])
        with mock.patch("health_journal.cloud.request_completion", return_value=json.dumps(REPORT)):
            saved = self.cloud.run({"approval_id": consent["approval_id"], "confirm": True})
        self.assertEqual(saved["task"], "document")
        self.assertEqual(self.store.records(), [])
        self.assertEqual(self.store.documents()[0]["routing"]["status"], "pending")

    def test_actual_food_separate_and_conflict_protected(self):
        saved = self.run_food()
        self.assertEqual(saved["intake"], {})
        self.store.update_intake(saved["id"], {"date": TODAY, "meal": "breakfast", "note": "合成自述实际内容", "version": 1})
        updated = self.store.analyses()[0]
        self.assertEqual(updated["result"], saved["result"])
        self.assertEqual(updated["intake"]["note"], "合成自述实际内容")
        with self.assertRaises(AppError):
            self.store.update_intake(saved["id"], {"date": TODAY, "meal": "breakfast", "note": "旧版本", "version": 1})

    def test_analysis_roundtrip_and_source_deletion_protected(self):
        doc = self.store.add_document("synthetic.txt", b"synthetic")
        saved = self.run_food(document_id=doc["id"])
        with self.assertRaises(AppError):
            self.store.delete_document(doc["id"])
        self.store.update_intake(saved["id"], {"date": TODAY, "meal": "breakfast", "note": "合成实际", "version": 1})
        restored = Store(Path(self.temp.name) / "restored")
        restored.restore(self.store.backup())
        self.assertEqual(restored.analyses(), self.store.analyses())
        self.assertEqual(restored.documents(), self.store.documents())
        self.assertIsNone(restored.setting("cloud_config"))
        self.store.delete_analysis(saved["id"], 2)
        self.store.delete_document(doc["id"])

    def test_routing_and_old_backup_compatibility(self):
        doc = self.store.add_document("test.txt", "眼科检查与血糖记录".encode())
        names = [link["name"] for link in self.store.documents()[0]["routing"]["links"]]
        self.assertIn("眼科", names)
        self.assertIn("内分泌科", names)
        self.store.route_document(doc["id"], {"links": [{"name": "眼科"}], "version": 1})
        with self.assertRaises(AppError):
            self.store.route_document(doc["id"], {"links": [], "version": 1})
        def downgrade(manifest):
            manifest["version"] = 1
            manifest.pop("analyses")
            for item in manifest["documents"]:
                item.pop("routing")
                item.pop("routing_version")
        restored = Store(Path(self.temp.name) / "oldbackup")
        restored.restore(alter_backup(self.store.backup(), downgrade))
        self.assertEqual(restored.documents()[0]["routing"]["status"], "pending")

    def test_restore_rejects_invalid_analysis_or_route(self):
        self.run_food()
        backup = self.store.backup()
        for mutation in (lambda data: data["analyses"][0].update(version=True), lambda data: data["analyses"].append(data["analyses"][0])):
            with self.subTest(mutation=mutation), self.assertRaises(AppError):
                Store(Path(self.temp.name) / "restore-invalid").restore(alter_backup(backup, mutation))

    def test_demo_refuses_existing_analysis_even_without_records(self):
        from health_journal.demo import seed_demo
        self.run_food()
        with self.assertRaises(AppError):
            seed_demo(self.store)
        self.assertEqual(self.store.records(), [])
        self.assertEqual(len(self.store.analyses()), 1)


class TransportTests(unittest.TestCase):
    def test_endpoint_control_characters_are_not_silently_normalized(self):
        for endpoint in ("https://exa\nmple.com/v1", "https://example.com/\tv1", "\nhttps://example.com/v1", "https://example.com/v1\r"):
            with self.subTest(endpoint=endpoint), self.assertRaises(AppError):
                endpoint_url(endpoint)

    def test_malformed_completion_envelopes_are_controlled_errors(self):
        with mock.patch("health_journal.cloud.public_addresses", return_value=["8.8.8.8"]), mock.patch("health_journal.cloud.PinnedHTTPS") as connection:
            response = connection.return_value.getresponse.return_value
            response.status = 200
            for payload in ({"choices": [None]}, {"choices": ["bad"]}, {"choices": []}, {"choices": [{"message": 2}]}, []):
                response.read.return_value = json.dumps(payload).encode()
                with self.subTest(payload=payload), self.assertRaises(AppError) as error:
                    request_completion({**DEFAULT_CONFIG, "model": "synthetic"}, FAKE_KEY, [])
                self.assertEqual(error.exception.status, 502)

    def test_duplicate_model_fields_and_departments_rejected(self):
        for content in ('{"summary":"first","summary":"second"}', json.dumps({**REPORT, "departments": REPORT["departments"] * 2})):
            with self.subTest(content=content), self.assertRaises(AppError):
                parse_result(content, "document")

    def test_bad_endpoints(self):
        for endpoint in ("http://example.com/v1", "https://localhost/v1", "https://example.com:8080/v1", "https://key@example.com/v1", "https://example.com/v1?token=secret", "https://example.com/../api", "https://foo.internal/v1", "https://example.com/v1/chat/completions"):
            with self.subTest(endpoint=endpoint), self.assertRaises(AppError):
                endpoint_url(endpoint)
        self.assertEqual(endpoint_url("https://example.com/v1/"), "https://example.com/v1")

    def test_private_and_mixed_dns_denied(self):
        for addresses in (["127.0.0.1"], ["10.1.2.3"], ["169.254.169.254"], ["::1"], ["8.8.8.8", "192.168.1.1"]):
            replies = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (address, 443)) for address in addresses]
            with self.subTest(addresses=addresses), mock.patch("socket.getaddrinfo", return_value=replies), self.assertRaises(AppError):
                public_addresses("example.com")

    def test_transport_pins_dns_and_does_not_follow_redirects(self):
        with mock.patch("health_journal.cloud.public_addresses", return_value=["8.8.8.8"]), mock.patch("health_journal.cloud.PinnedHTTPS") as connection:
            connection.return_value.getresponse.return_value.status = 302
            with self.assertRaises(AppError):
                request_completion({**DEFAULT_CONFIG, "model": "synthetic"}, FAKE_KEY, [])
            connection.assert_called_once_with("api.openai.com", "8.8.8.8")
            self.assertEqual(connection.return_value.request.call_count, 1)

    def test_transport_correct_shape_and_sanitized_errors(self):
        with mock.patch("health_journal.cloud.public_addresses", return_value=["8.8.8.8"]), mock.patch("health_journal.cloud.PinnedHTTPS") as connection:
            response = connection.return_value.getresponse.return_value
            response.status = 200
            response.read.return_value = json.dumps({"choices": [{"finish_reason": "stop", "message": {"content": json.dumps(FOOD)}}]}).encode()
            request_completion({**DEFAULT_CONFIG, "model": "synthetic"}, FAKE_KEY, [])
            payload = json.loads(connection.return_value.request.call_args.kwargs["body"])
            self.assertFalse(payload["store"])
            self.assertFalse(payload["stream"])
            self.assertEqual(payload["model"], "synthetic")
            response.status = 401
            response.read.return_value = (FAKE_KEY + " secret response").encode()
            with self.assertRaises(AppError) as error:
                request_completion({**DEFAULT_CONFIG, "model": "synthetic"}, FAKE_KEY, [])
            self.assertNotIn(FAKE_KEY, str(error.exception))

    def test_malformed_model_output_cannot_be_promoted(self):
        for content in ("not json", "[]", '{"summary":"x","foods":["bad"]}', json.dumps({**REPORT, "departments": [{"name": "不存在科室", "evidence": "x"}]})):
            with self.subTest(content=content), self.assertRaises(AppError):
                parse_result(content, "document" if "departments" in content else "breakfast")
        parsed = parse_result("```json\n" + json.dumps(FOOD) + "\n```", "breakfast")
        self.assertEqual(parsed["foods"], FOOD["foods"])

    def test_catalog_unique_and_uncertain_files_stay_unclassified(self):
        self.assertEqual(len(NAMES), len(set(NAMES)))
        self.assertGreaterEqual(len(CATALOG), 50)
        self.assertEqual(suggest_departments("photo.jpg")["links"], [])
        self.assertEqual(suggest_departments("眼科报告.pdf")["status"], "pending")


if __name__ == "__main__":
    unittest.main()
