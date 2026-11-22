import concurrent.futures
import datetime
import http.client
import json
import tempfile
import threading
import unittest
from unittest import mock
from urllib.parse import quote

from health_journal.server import JournalServer, create_server
from tests.test_core import TODAY, adult, record
from tests.test_cloud import FAKE_KEY, FOOD, REPORT


class HTTPTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="health-journal-http-")
        self.server = create_server(self.temp.name, 0)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.port = self.server.server_address[1]

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.temp.cleanup()

    def request(self, method, path, data=None, body=None, headers=None, token=True):
        headers = dict(headers or {})
        if token:
            headers.setdefault("X-Journal-Token", self.server.token)
        if data is not None:
            body = json.dumps(data, ensure_ascii=False).encode()
            headers.setdefault("Content-Type", "application/json")
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        connection.request(method, path, body=body, headers=headers)
        response = connection.getresponse()
        status, metadata, content = response.status, dict(response.getheaders()), response.read()
        connection.close()
        if metadata.get("Content-Type", "").startswith("application/json"):
            content = json.loads(content)
        return status, metadata, content

    def test_home_assets_and_security_headers(self):
        for path in ("/", "/app.js", "/style.css", "/favicon.svg"):
            status, headers, content = self.request("GET", path, token=False)
            self.assertEqual(status, 200)
            self.assertEqual(headers["Cache-Control"], "no-store")
            self.assertEqual(headers["X-Frame-Options"], "DENY")
            self.assertIn("script-src 'self'", headers["Content-Security-Policy"])
            self.assertNotIn("Access-Control-Allow-Origin", headers)
            if path == "/":
                self.assertNotIn(b"__LOCAL_TOKEN__", content)
                self.assertIn(self.server.token.encode(), content)

    def test_personal_first_start_has_no_demo_or_prepopulated_content(self):
        status, _, snapshot = self.request("GET", "/api/state")
        self.assertEqual(status, 200)
        self.assertFalse(snapshot["demo"])
        for key in ("records", "documents", "plans", "analyses", "audits"):
            self.assertEqual(snapshot[key], [])
        self.assertEqual(snapshot["profile"]["name"], "")
        self.assertEqual(snapshot["profile"]["diet"], "unspecified")
        self.assertFalse(snapshot["cloud"]["has_key"])
        self.assertFalse(snapshot["codex"]["connected"])
        self.assertTrue(snapshot["departments"])
        self.assertEqual(self.request("PUT", "/api/profile", data={**snapshot["profile"], "_version": snapshot["profile_version"]})[0], 200)
        self.assertEqual(self.request("POST", "/api/plans", data={"date": snapshot["today"]})[0], 422)
        self.assertEqual(self.request("GET", "/api/state")[2]["plans"], [])

    def test_phone_static_assets_and_scope_are_allowlisted(self):
        for path in ("/phone/", "/phone/index.html", "/phone/phone.js", "/phone/core.js", "/phone/db.js", "/phone/phone.css", "/phone/sw.js", "/phone/manifest.webmanifest", "/phone/icon.svg", "/phone/catalog.json"):
            status, headers, content = self.request("GET", path, token=False)
            self.assertEqual(status, 200, path)
            self.assertNotIn("Service-Worker-Allowed", headers)
            self.assertNotIn(self.server.token, str(content))
        self.assertEqual(self.request("GET", "/phone/../../journal.sqlite3", token=False)[0], 404)
        self.assertEqual(self.request("GET", "/phone/unknown.js", token=False)[0], 404)

    def test_phone_transfer_requires_session_and_explicit_confirmation(self):
        from tests.test_transfer import transfer
        body = transfer(("synthetic.txt", b"synthetic"))
        self.assertEqual(self.request("GET", "/api/transfer", token=False)[0], 401)
        self.assertEqual(self.request("POST", "/api/transfer", body=body)[0], 400)
        self.assertEqual(self.request("POST", "/api/transfer", body=body, headers={"X-Confirm-Transfer": "append-originals"})[0], 415)
        status, headers, result = self.request("POST", "/api/transfer", body=body, headers={"X-Confirm-Transfer": "append-originals", "Content-Type": "application/json"})
        self.assertEqual(status, 200)
        self.assertEqual(result, {"imported": 1, "duplicates": 0})
        status, headers, content = self.request("GET", "/api/transfer")
        self.assertEqual(status, 200)
        self.assertIn("attachment", headers["Content-Disposition"])
        self.assertEqual(json.loads(content)["documents"][0]["filename"], "synthetic.txt")

    def test_token_host_origin_and_cross_site(self):
        self.assertEqual(self.request("GET", "/api/state", token=False)[0], 401)
        for headers in ({"Host": "evil.example"}, {"Origin": "https://evil.example"}, {"Origin": "null"}, {"Sec-Fetch-Site": "cross-site"}, {"Sec-Fetch-Site": "same-site"}):
            with self.subTest(headers=headers):
                self.assertEqual(self.request("GET", "/api/state", headers=headers)[0], 403)
        self.assertEqual(self.request("GET", "/api/state", headers={"Origin": "http://127.0.0.1:" + str(self.port), "Sec-Fetch-Site": "same-origin"})[0], 200)

    def configure_cloud(self):
        config = self.request("GET", "/api/state")[2]["cloud"]
        status, _, saved = self.request("PUT", "/api/ai/config", data={"provider": "openai", "model": "synthetic-model", "vision": True, "api_key": FAKE_KEY, "revision": config["revision"]})
        self.assertEqual(status, 200)
        self.assertNotIn(FAKE_KEY, json.dumps(saved))

    def test_codex_http_lifecycle_and_single_use_consent(self):
        from tests.test_codex import FakeRPC, login
        self.server.codex.rpc_factory = FakeRPC
        self.assertEqual(self.request("POST", "/api/codex/connect", data={})[0], 400)
        self.assertEqual(self.request("POST", "/api/codex/connect", data={"confirm": True})[0], 200)
        login(self.server.codex)
        config = self.request("GET", "/api/state")[2]["codex"]
        self.assertEqual(self.request("PUT", "/api/codex/config", data={"model": "synthetic-vision", "vision": True, "revision": config["revision"]})[0], 200)
        status, _, consent = self.request("POST", "/api/codex/prepare", data={"task": "breakfast", "text": "HTTP 合成早餐"})
        self.assertEqual(status, 200)
        self.assertEqual(self.request("POST", "/api/codex/run", data={"approval_id": consent["approval_id"]})[0], 400)
        payload = {"approval_id": consent["approval_id"], "confirm": True}
        status, _, draft = self.request("POST", "/api/codex/run", data=payload)
        self.assertEqual(status, 200)
        self.assertEqual(draft["provenance"]["provider"], "codex")
        self.assertEqual(self.request("POST", "/api/codex/run", data=payload)[0], 409)
        self.assertEqual(self.request("POST", "/api/codex/logout", data={"confirm": True})[0], 200)
        self.assertEqual(self.request("POST", "/api/codex/disconnect", data={"confirm": True})[0], 200)

    def test_codex_endpoints_reject_remote_and_unauthorized_requests(self):
        from tests.test_codex import FakeRPC
        self.server.codex.rpc_factory = FakeRPC
        for path in ("connect", "login", "refresh", "cancel-login", "logout", "disconnect", "prepare", "run", "cancel", "config"):
            method = "PUT" if path == "config" else "POST"
            endpoint = "/api/codex/" + path
            with self.subTest(path=path):
                self.assertEqual(self.request(method, endpoint, data={}, token=False)[0], 401)
                self.assertEqual(self.request(method, endpoint, data={}, headers={"Origin": "https://evil.invalid"})[0], 403)
                self.assertEqual(self.request(method, endpoint, data={}, headers={"Host": "192.168.1.5"})[0], 403)
        self.assertIsNone(self.server.codex.rpc)
        self.assertEqual(self.request("POST", "/api/codex/rpc", data={"method": "turn/start"})[0], 404)
        self.assertEqual(self.request("GET", "/.codex-connection/auth/auth.json")[0], 404)

    def test_cloud_api_consent_draft_intake_and_deletion(self):
        self.configure_cloud()
        with mock.patch("health_journal.cloud.request_completion", return_value=json.dumps(FOOD)) as completion:
            status, _, consent = self.request("POST", "/api/ai/prepare", data={"task": "breakfast", "text": "合成早餐描述"})
            self.assertEqual(status, 200)
            completion.assert_not_called()
            self.assertEqual(self.request("POST", "/api/ai/run", data={"approval_id": consent["approval_id"]})[0], 400)
            status, _, draft = self.request("POST", "/api/ai/run", data={"approval_id": consent["approval_id"], "confirm": True})
            self.assertEqual(status, 200)
            self.assertEqual(completion.call_count, 1)
            self.assertEqual(self.request("POST", "/api/ai/run", data={"approval_id": consent["approval_id"], "confirm": True})[0], 409)
        snapshot = self.request("GET", "/api/state")[2]
        self.assertEqual(snapshot["records"], [])
        self.assertEqual(snapshot["analyses"], [draft])
        self.assertNotIn(FAKE_KEY, json.dumps(snapshot))
        endpoint = "/api/analyses/" + draft["id"]
        payload = {"version": 1, "date": TODAY, "meal": "breakfast", "note": "合成：用户核对鸡蛋一枚"}
        self.assertEqual(self.request("PUT", endpoint, data=payload)[0], 200)
        self.assertEqual(self.request("PUT", endpoint, data=payload)[0], 409)
        self.assertEqual(self.request("DELETE", endpoint, data={"version": 1})[0], 409)
        self.assertEqual(self.request("DELETE", endpoint, data={"version": 2})[0], 200)
        self.assertEqual(self.request("DELETE", "/api/ai/key")[0], 200)
        self.assertFalse(self.request("GET", "/api/state")[2]["cloud"]["has_key"])

    def test_cloud_report_routing_stays_user_confirmed(self):
        self.configure_cloud()
        doc = self.request("POST", "/api/documents", body="合成血糖报告".encode(), headers={"X-Filename": quote("合成.txt")})[2]
        consent = self.request("POST", "/api/ai/prepare", data={"task": "document", "document_id": doc["id"]})[2]
        with mock.patch("health_journal.cloud.request_completion", return_value=json.dumps(REPORT)):
            self.assertEqual(self.request("POST", "/api/ai/run", data={"approval_id": consent["approval_id"], "confirm": True})[0], 200)
        snapshot = self.request("GET", "/api/state")[2]
        self.assertEqual(snapshot["records"], [])
        self.assertEqual(snapshot["documents"][0]["routing"]["status"], "pending")
        endpoint = "/api/documents/" + doc["id"]
        self.assertEqual(self.request("DELETE", endpoint)[0], 409)
        payload = {"version": 1, "status": "confirmed", "method": "ai-reviewed", "links": [{"name": "内分泌科", "evidence": "合成人工确认"}]}
        self.assertEqual(self.request("PUT", endpoint + "/routing", data=payload)[0], 200)
        self.assertEqual(self.request("PUT", endpoint + "/routing", data=payload)[0], 409)
        self.assertEqual(self.request("GET", "/api/state")[2]["documents"][0]["routing"]["status"], "confirmed")

    def test_cloud_endpoints_require_local_session_and_explicit_options(self):
        for path in ("/api/ai/config", "/api/ai/prepare", "/api/ai/run"):
            self.assertEqual(self.request("POST", path, data={}, token=False)[0], 401)
        self.configure_cloud()
        for option in ("include_records", "include_profile"):
            self.assertEqual(self.request("POST", "/api/ai/prepare", data={"task": "chat", "text": "合成测试", option: "true"})[0], 400)

    def test_path_traversal_and_method_denied(self):
        for path in ("/../health_journal/store.py", "/%2e%2e/secret", "/journal.sqlite3", "/api/missing"):
            with self.subTest(path=path):
                self.assertEqual(self.request("GET", path)[0], 404)
        self.assertEqual(self.request("POST", "/")[0], 405)

    def test_only_loopback_bind(self):
        with self.assertRaises(ValueError):
            JournalServer(("0.0.0.0", 0), self.server.store)

    def test_json_invalid_type_nonfinite_and_content_type(self):
        for body in (b"[]", b"{", b'{"optional":NaN}', b'{"optional":Infinity}', b'{"optional":-Infinity}', b"\xff"):
            with self.subTest(body=body):
                self.assertEqual(self.request("POST", "/api/records", body=body, headers={"Content-Type": "application/json"})[0], 400)
        self.assertEqual(self.request("POST", "/api/records", body=b"{}")[0], 415)

    def test_record_api_lifecycle(self):
        status, headers, saved = self.request("POST", "/api/records", data=record())
        self.assertEqual(status, 201)
        endpoint = "/api/records/" + saved["id"]
        changed = {**saved, "title": "合成已修改"}
        self.assertEqual(self.request("PUT", endpoint, data=changed)[0], 200)
        self.assertEqual(self.request("PUT", endpoint, data=changed)[0], 409)
        self.assertEqual(self.request("DELETE", endpoint, data={"version": 1})[0], 409)
        self.assertEqual(self.request("DELETE", endpoint, data={"version": 2})[0], 200)
        self.assertEqual(self.request("GET", "/api/state")[2]["records"], [])

    def test_simultaneous_update_only_one_wins(self):
        saved = self.request("POST", "/api/records", data=record())[2]
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(self.request, "PUT", "/api/records/" + saved["id"], data={**saved, "title": "合成修改" + str(index)}) for index in range(2)]
            statuses = sorted(future.result()[0] for future in futures)
        self.assertEqual(statuses, [200, 409])

    def test_profile_requires_version_and_rejects_stale_write(self):
        self.assertEqual(self.request("PUT", "/api/profile", data=adult())[0], 400)
        version = self.request("GET", "/api/state")[2]["profile_version"]
        self.assertEqual(self.request("PUT", "/api/profile", data={**adult(), "_version": version})[0], 200)
        self.assertEqual(self.request("PUT", "/api/profile", data={**adult(allergies=["牛奶"]), "_version": version})[0], 409)

    def test_document_download_and_link_delete_protection(self):
        content = "仅合成报告".encode()
        status, headers, doc = self.request("POST", "/api/documents", body=content, headers={"X-Filename": quote("合成.txt")})
        self.assertEqual(status, 201)
        endpoint = "/api/documents/" + doc["id"]
        status, headers, downloaded = self.request("GET", endpoint)
        self.assertEqual(status, 200)
        self.assertEqual(downloaded, content)
        self.assertIn("attachment", headers["Content-Disposition"])
        self.request("POST", "/api/records", data=record(document_id=doc["id"]))
        self.assertEqual(self.request("DELETE", endpoint)[0], 409)

    def test_backup_restore_http_confirmation(self):
        saved = self.request("POST", "/api/records", data=record())[2]
        status, headers, backup = self.request("GET", "/api/backup")
        self.assertEqual(status, 200)
        self.assertEqual(headers["Content-Type"], "application/zip")
        self.assertEqual(self.request("POST", "/api/restore", body=backup)[0], 400)
        self.assertEqual(self.request("POST", "/api/restore", body=backup, headers={"X-Confirm-Restore": "empty-vault"})[0], 409)
        self.request("DELETE", "/api/records/" + saved["id"], data={"version": saved["version"]})
        self.assertEqual(self.request("POST", "/api/restore", body=backup, headers={"X-Confirm-Restore": "empty-vault"})[0], 200)
        self.assertEqual(self.request("GET", "/api/state")[2]["records"], [saved])

    def test_meal_log_protects_against_regeneration_and_swap(self):
        self.server.store.profile(adult())
        status, headers, plan = self.request("POST", "/api/plans", data={"date": TODAY})
        self.assertEqual(status, 200)
        endpoint = "/api/plans/" + TODAY
        status, headers, saved = self.request("PUT", endpoint, data={"meal": "breakfast", "revision": plan["revision"], "eaten": True, "note": "合成实际餐食"})
        self.assertEqual(status, 200)
        self.assertEqual(self.request("POST", "/api/plans", data={"date": TODAY})[0], 409)
        self.assertEqual(self.request("PUT", endpoint, data={"meal": "breakfast", "revision": saved["revision"], "swap": True})[0], 409)
        self.assertEqual(self.request("PUT", endpoint, data={"meal": "lunch", "revision": 0, "swap": True})[0], 409)
        self.assertEqual(self.request("PUT", endpoint, data={"meal": "lunch", "revision": saved["revision"], "swap": True})[0], 200)

    def test_new_restrictions_block_swap_but_allow_historical_logging(self):
        self.server.store.profile(adult())
        plan = self.request("POST", "/api/plans", data={"date": TODAY})[2]
        self.server.store.profile(adult(birth_date=TODAY))
        state = self.request("GET", "/api/state")[2]
        self.assertTrue(state["nutrition_restrictions"])
        endpoint = "/api/plans/" + TODAY
        self.assertEqual(self.request("PUT", endpoint, data={"meal": "lunch", "revision": plan["revision"], "swap": True})[0], 422)
        self.assertEqual(self.request("PUT", endpoint, data={"meal": "lunch", "revision": plan["revision"], "eaten": True, "note": "记录实际已发生事实"})[0], 200)

    def test_assistant_does_not_write_records(self):
        saved = self.request("POST", "/api/records", data=record("condition"))[2]
        status, headers, answer = self.request("POST", "/api/assistant", data={"question": "我可能得了什么病"})
        self.assertEqual(status, 200)
        self.assertEqual(answer["mode"], "local-rules")
        self.assertEqual(self.request("GET", "/api/state")[2]["records"], [saved])

    def test_model_requires_explicit_boolean_opt_in(self):
        self.assertEqual(self.request("POST", "/api/assistant", data={"question": "合成测试", "use_model": "false"})[0], 400)

    def test_oversized_and_duplicate_length_denied(self):
        self.assertEqual(self.request("POST", "/api/documents", body=b"", headers={"Content-Length": "999999999", "X-Filename": "a.txt"})[0], 413)
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        connection.putrequest("POST", "/api/documents")
        connection.putheader("X-Journal-Token", self.server.token)
        connection.putheader("X-Filename", "a.txt")
        connection.putheader("Content-Length", "0")
        connection.putheader("Content-Length", "0")
        connection.endheaders()
        response = connection.getresponse()
        self.assertEqual(response.status, 400)
        response.read()
        connection.close()

    def test_ambiguous_headers_denied_and_responses_close_connection(self):
        for header, value in (("Host", "127.0.0.1:" + str(self.port)), ("X-Journal-Token", self.server.token), ("Origin", "http://127.0.0.1:" + str(self.port))):
            connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
            connection.putrequest("GET", "/api/state", skip_host=True)
            connection.putheader("Host", "127.0.0.1:" + str(self.port))
            connection.putheader("X-Journal-Token", self.server.token)
            connection.putheader(header, value)
            if header == "Origin":
                connection.putheader(header, value)
            connection.endheaders()
            response = connection.getresponse()
            with self.subTest(header=header):
                self.assertEqual(response.status, 400)
                self.assertEqual(response.getheader("Connection"), "close")
            response.read()
            connection.close()
        self.assertEqual(self.request("GET", "/api/state")[1]["Connection"], "close")

    def test_non_ascii_token_is_unauthorized_not_internal_error(self):
        self.assertEqual(self.request("GET", "/api/state", headers={"X-Journal-Token": "caf\u00e9"})[0], 401)

    def test_malformed_ollama_list_is_controlled_error(self):
        with mock.patch("health_journal.server.ollama_request", return_value={"models": 2}):
            self.assertEqual(self.request("GET", "/api/models")[0], 502)

    def test_server_restart_retains_local_data_but_not_ram_key(self):
        self.configure_cloud()
        self.server.store.profile(adult())
        self.request("POST", "/api/plans", data={"date": TODAY})
        doc = self.request("POST", "/api/documents", body=b"synthetic restart source", headers={"X-Filename": "synthetic.txt"})[2]
        self.request("POST", "/api/records", data=record(document_id=doc["id"]))
        consent = self.request("POST", "/api/ai/prepare", data={"task": "breakfast", "text": "合成重启测试", "document_id": doc["id"]})[2]
        with mock.patch("health_journal.cloud.request_completion", return_value=json.dumps(FOOD)):
            status, headers, draft = self.request("POST", "/api/ai/run", data={"approval_id": consent["approval_id"], "confirm": True})
        self.assertEqual(status, 200)
        self.request("PUT", "/api/analyses/" + draft["id"], data={"date": TODAY, "meal": "breakfast", "note": "合成已核对实际饮食", "version": draft["version"]})
        previous = self.request("GET", "/api/state")[2]
        previous_token = self.server.token
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.server = create_server(self.temp.name, 0)
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        current = self.request("GET", "/api/state")[2]
        for field in ("profile", "profile_version", "records", "documents", "plans", "analyses", "audits"):
            self.assertEqual(current[field], previous[field], field)
        self.assertFalse(current["cloud"]["has_key"])
        self.assertEqual(current["cloud"]["model"], previous["cloud"]["model"])
        self.assertNotEqual(self.server.token, previous_token)
        self.assertEqual(self.request("GET", "/api/documents/" + doc["id"])[2], b"synthetic restart source")

    def test_duplicate_json_and_unpaired_unicode_rejected(self):
        for content in (b'{"kind":"visit","kind":"symptom"}', json.dumps(record(title="\ud800")).encode()):
            with self.subTest(content=content):
                self.assertEqual(self.request("POST", "/api/records", body=content, headers={"Content-Type": "application/json"})[0], 400)
        self.assertEqual(self.server.store.records(), [])

    def test_future_plans_are_not_actual_intake(self):
        self.server.store.profile(adult())
        tomorrow = (datetime.date.today() + datetime.timedelta(days=1)).isoformat()
        status, headers, plan = self.request("POST", "/api/plans", data={"date": tomorrow})
        self.assertEqual(status, 200)
        for changes in ({"eaten": True}, {"note": "合成未来实际饮食"}):
            self.assertEqual(self.request("PUT", "/api/plans/" + tomorrow, data={"meal": "breakfast", "revision": plan["revision"], **changes})[0], 400)
        self.assertEqual(self.server.store.plans()[0]["revision"], plan["revision"])


if __name__ == "__main__":
    unittest.main()
