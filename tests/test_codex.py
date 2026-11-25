import base64
import concurrent.futures
import io
import json
import os
from pathlib import Path
import queue
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock
import zipfile

from health_journal.codex_ai import CodexAI, output_schema
from health_journal.codex_rpc import CodexRPC, MAX_REQUEST, SAFE_CONFIG, official_auth_url, private_directory
from health_journal.store import Store
from health_journal.validation import AppError
from tests.test_core import adult, record


class FakeRPC(CodexRPC):
    scenario = "normal"

    def __init__(self, root, executable=None):
        super().__init__(root, sys.executable)
        self.trace = Path(root).parent / "synthetic-trace.jsonl"

    def start(self):
        spawn = subprocess.Popen
        def launch(command, **options):
            options["env"].update(HEALTH_FAKE_CASE=self.scenario, HEALTH_FAKE_TRACE=str(self.trace))
            return spawn([sys.executable, str(Path(__file__).with_name("fake_codex.py")), *command[1:]], **options)
        with mock.patch("health_journal.codex_rpc.subprocess.Popen", side_effect=launch):
            super().start()

    def messages(self):
        return [json.loads(line) for line in self.trace.read_text(encoding="utf-8").splitlines()]


def login(ai):
    ai.control("login", {"confirm": True})
    for attempt in range(3):
        try:
            return ai.control("refresh", {"confirm": True})
        except AppError as error:
            if error.status != 409:
                raise
    raise AssertionError("synthetic login did not settle")


class CodexTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="health-codex-test-")
        self.addCleanup(self.temp.cleanup)
        self.store = Store(Path(self.temp.name) / "vault")
        self.ai = CodexAI(self.store, rpc_factory=FakeRPC)
        self.addCleanup(self.ai.close)
        self.ai.control("connect", {"confirm": True})
        login(self.ai)
        self.configure()

    def configure(self, **changes):
        return self.ai.configure({"model": "synthetic-vision", "vision": True, "revision": self.ai.revision, **changes})

    def prepare(self, **changes):
        return self.ai.prepare({"task": "breakfast", "text": "合成早餐", **changes})

    def run_consent(self, consent):
        return self.ai.run({"approval_id": consent["approval_id"], "confirm": True})

    def switch_case(self, scenario):
        factory = type("ScenarioRPC", (FakeRPC,), {"scenario": scenario})
        self.ai.rpc_factory = factory
        self.ai.control("connect", {"confirm": True})
        login(self.ai)
        self.configure()

    def test_prepare_does_not_send_and_run_uses_frozen_input(self):
        consent = self.prepare()
        self.assertFalse(any(row.get("method") == "turn/start" for row in self.ai.rpc.messages()))
        self.store.profile(adult(name="未授权秘密姓名"))
        draft = self.run_consent(consent)
        self.assertEqual(draft["provenance"]["provider"], "codex")
        self.assertEqual(self.store.records(), [])
        sent = next(row["params"] for row in self.ai.rpc.messages() if row.get("method") == "turn/start")
        self.assertEqual(sent["input"][0]["text"], consent["text"])
        self.assertNotIn("未授权秘密姓名", str(sent))
        self.assertEqual(sent["sandboxPolicy"]["access"]["readableRoots"], [str(self.ai.rpc.workdir)])
        self.assertFalse(sent["sandboxPolicy"]["access"]["includePlatformDefaults"])
        self.assertEqual(sent["outputSchema"], output_schema("breakfast"))
        with self.assertRaises(AppError):
            self.run_consent(consent)

    def test_explicit_confirmation_required(self):
        consent = self.prepare()
        for value in (None, False, "true", 1):
            with self.assertRaises(AppError):
                self.ai.run({"approval_id": consent["approval_id"], "confirm": value})
        self.run_consent(consent)

    def test_expired_revision_and_auth_change_reject_before_send(self):
        consent = self.prepare()
        self.ai.pending[consent["approval_id"]]["expires"] = 0
        with self.assertRaises(AppError):
            self.run_consent(consent)
        consent = self.prepare()
        self.configure()
        with self.assertRaises(AppError):
            self.run_consent(consent)
        consent = self.prepare()
        self.ai.rpc.auth_epoch += 1
        with self.assertRaises(AppError):
            self.run_consent(consent)
        self.assertFalse(any(row.get("method") == "turn/start" for row in self.ai.rpc.messages()))

    def test_model_must_be_advertised_and_image_capable(self):
        for values in ({"model": "unknown"}, {"model": "synthetic-text", "vision": True}, {"vision": "true"}, {"revision": "old"}):
            with self.subTest(values=values), self.assertRaises(AppError):
                self.configure(**values)
        self.assertEqual(self.configure(model="synthetic-text", vision=False)["model"], "synthetic-text")

    def test_image_snapshot_and_unsupported_pdf(self):
        content = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+a5X8AAAAASUVORK5CYII=")
        doc = self.store.add_document("synthetic.png", content)
        self.run_consent(self.prepare(document_id=doc["id"]))
        sent = next(row["params"] for row in self.ai.rpc.messages() if row.get("method") == "turn/start")
        self.assertEqual(sent["input"][1], {"type": "image", "url": "data:image/png;base64," + base64.b64encode(content).decode()})
        doc = self.store.add_document("synthetic.pdf", b"%PDF-1.4\nsynthetic\n%%EOF")
        with self.assertRaisesRegex(AppError, "不直传 PDF"):
            self.prepare(task="document", document_id=doc["id"])

    def test_deleted_source_is_rejected_before_send(self):
        doc = self.store.add_document("synthetic.txt", b"synthetic")
        consent = self.prepare(document_id=doc["id"])
        self.store.delete_document(doc["id"])
        with self.assertRaises(AppError):
            self.run_consent(consent)
        self.assertFalse(any(row.get("method") == "turn/start" for row in self.ai.rpc.messages()))

    def test_large_image_echo_does_not_trip_output_limit(self):
        content = b"\x89PNG\r\n\x1a\n" + b"x" * (2 * 1024 * 1024)
        doc = self.store.add_document("synthetic-large.png", content)
        draft = self.run_consent(self.prepare(document_id=doc["id"]))
        self.assertEqual(draft["document_id"], doc["id"])
        self.assertTrue(self.ai.rpc.alive)

    def test_report_stays_draft_and_chat_supported(self):
        doc = self.store.add_document("synthetic.txt", "血糖 5.0 mmol/L".encode())
        self.run_consent(self.prepare(task="document", document_id=doc["id"]))
        self.run_consent(self.prepare(task="chat"))
        self.assertEqual(len(self.store.analyses()), 2)
        self.assertEqual(self.store.records(), [])
        self.assertNotEqual(self.store.documents()[0]["routing"]["status"], "confirmed")

    def test_login_cancel_logout_disconnect_and_reconnect(self):
        self.ai.control("logout", {"confirm": True})
        self.assertFalse(self.ai.config()["authenticated"])
        self.ai.control("login", {"confirm": True})
        self.assertTrue(self.ai.config()["login"])
        self.ai.control("cancel-login", {"confirm": True})
        self.assertFalse(self.ai.config()["login"])
        self.assertFalse(self.ai.config()["authenticated"])
        login(self.ai)
        self.ai.control("disconnect", {"confirm": True})
        self.assertFalse(self.ai.config()["connected"])
        self.ai.control("connect", {"confirm": True})
        self.assertTrue(self.ai.config()["connected"])

    def test_duplicate_login_does_not_kill_healthy_connection(self):
        with self.assertRaises(AppError):
            self.ai.control("login", {"confirm": True})
        self.assertTrue(self.ai.rpc.alive)

    def test_control_requires_confirmation_and_refuses_parallel_control(self):
        with self.assertRaises(AppError):
            self.ai.control("logout", {})
        with self.ai.control_lock:
            for operation in (lambda: self.configure(), lambda: self.prepare(), lambda: self.ai.control("refresh", {"confirm": True})):
                with self.assertRaises(AppError):
                    operation()

    def test_credentials_excluded_from_snapshots_backups_and_transfer(self):
        secret = b"synthetic-credential-not-a-real-token"
        auth = self.store.directory / ".codex-connection" / "auth" / "auth.json"
        auth.write_bytes(secret)
        self.assertNotIn(secret.decode(), json.dumps(self.ai.config()))
        self.assertNotIn(secret, self.store.database.read_bytes())
        with zipfile.ZipFile(io.BytesIO(self.store.backup())) as archive:
            for name in archive.namelist():
                self.assertNotIn(".codex-connection", name)
                self.assertNotIn(secret, archive.read(name))
        from health_journal.transfer import export_transfer
        self.assertNotIn(secret, export_transfer(self.store))

    def test_fail_closed_protocol_and_output_scenarios(self):
        for scenario in ("wrong-thread", "tool", "bad-output", "failed-turn", "two-answers", "malformed-item", "auth-change"):
            with self.subTest(scenario=scenario):
                self.switch_case(scenario)
                with self.assertRaises(AppError):
                    self.run_consent(self.prepare())
                self.assertFalse(self.ai.rpc.alive)
                self.assertEqual(self.store.analyses(), [])
                self.assertFalse(self.ai.busy)
                if scenario == "wrong-thread":
                    recent = self.ai.rpc.messages()
                    last_start = max(index for index, row in enumerate(recent) if row.get("method") == "thread/start")
                    self.assertFalse(any(row.get("method") == "turn/start" for row in recent[last_start:]))

    def test_cancel_rejects_stale_ids_and_stops_without_saving(self):
        self.switch_case("hang")
        consent = self.prepare()
        with concurrent.futures.ThreadPoolExecutor() as pool:
            future = pool.submit(self.run_consent, consent)
            deadline = time.monotonic() + 3
            while not any(row.get("method") == "turn/start" for row in self.ai.rpc.messages()) and time.monotonic() < deadline:
                time.sleep(0.01)
            self.assertTrue(self.ai.busy)
            self.assertEqual(self.ai.config()["operation"], consent["approval_id"])
            with self.assertRaises(AppError):
                self.ai.cancel({"approval_id": "stale"})
            with self.assertRaises(AppError):
                self.ai.control("logout", {"confirm": True})
            self.assertTrue(self.ai.rpc.alive)
            with self.assertRaises(AppError):
                self.run_consent(consent)
            self.ai.cancel({"approval_id": consent["approval_id"]})
            with self.assertRaises(AppError):
                future.result(timeout=5)
        self.assertEqual(self.store.analyses(), [])
        self.assertFalse(self.ai.rpc.alive)

    def test_turn_timeout_and_shutdown_reject_further_work(self):
        self.switch_case("hang")
        with mock.patch("health_journal.codex_ai.TURN_TIMEOUT", 0.1), self.assertRaises(AppError):
            self.run_consent(self.prepare())
        self.assertEqual(self.store.analyses(), [])
        self.ai.close()
        with self.assertRaises(AppError):
            self.ai.control("connect", {"confirm": True})

    def test_unsubscribe_failure_does_not_discard_completed_draft(self):
        real_call = self.ai.rpc.call
        def flaky_unsubscribe(method, params, timeout=15):
            if method == "thread/unsubscribe":
                raise AppError("synthetic unsubscribe timeout", 504)
            return real_call(method, params, timeout=timeout)
        with mock.patch.object(self.ai.rpc, "call", side_effect=flaky_unsubscribe):
            draft = self.run_consent(self.prepare())
        self.assertEqual(draft["provenance"]["provider"], "codex")
        self.assertEqual(len(self.store.analyses()), 1)
        self.assertFalse(self.ai.rpc.alive)

    def test_shutdown_during_connect_cleans_new_process(self):
        real_start = FakeRPC.start
        manager = self.ai
        class ClosingRPC(FakeRPC):
            def start(self):
                manager.close()
                real_start(self)
        self.ai.rpc_factory = ClosingRPC
        with self.assertRaises(AppError):
            self.ai.control("connect", {"confirm": True})
        self.assertFalse(self.ai.rpc.alive)


class RPCTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="health-rpc-test-")
        self.addCleanup(self.temp.cleanup)

    def connection(self, scenario="normal"):
        rpc = FakeRPC(Path(self.temp.name) / ".codex-connection")
        rpc.scenario = scenario
        self.addCleanup(rpc.close)
        return rpc

    def test_safe_launch_environment_permissions_and_cleanup(self):
        rpc = self.connection()
        with mock.patch.dict(os.environ, {"OPENAI_API_KEY": "must-not-inherit", "CODEX_HOME": "must-not-inherit", "NODE_OPTIONS": "must-not-inherit", "HTTPS_PROXY": "must-not-inherit"}):
            rpc.start()
        launch = rpc.messages()[0]
        self.assertNotIn("must-not-inherit", str(launch))
        self.assertNotEqual(launch["environment"]["HOME"], str(Path.home()))
        self.assertEqual(launch["environment"]["CODEX_HOME"], str(rpc.root / "auth"))
        self.assertIn("stdio://", launch["argv"])
        if os.name != "nt":
            self.assertEqual((rpc.root / "auth").stat().st_mode & 0o777, 0o700)
        workdir = rpc.workdir
        with concurrent.futures.ThreadPoolExecutor() as pool:
            list(pool.map(lambda value: rpc.close(), range(4)))
        self.assertFalse(rpc.alive)
        self.assertFalse(workdir.exists())
        self.assertTrue((rpc.root / "auth").exists())

    def test_startup_rejects_incompatible_protocol_without_leaking_errors(self):
        for scenario in ("duplicate-json", "oversized", "bad-notification", "server-request", "error", "exit", "unsafe-config", "bool-config"):
            with self.subTest(scenario=scenario):
                rpc = self.connection(scenario)
                with self.assertRaises(AppError) as caught:
                    rpc.start()
                self.assertNotIn("SECRET", str(caught.exception))
                self.assertFalse(rpc.alive)

    def test_bad_official_url_account_and_model_are_rejected(self):
        for scenario in ("bad-auth-url", "api-account", "bad-model"):
            with self.subTest(scenario=scenario):
                store = Store(Path(self.temp.name) / scenario)
                factory = type("ScenarioRPC", (FakeRPC,), {"scenario": scenario})
                ai = CodexAI(store, rpc_factory=factory)
                self.addCleanup(ai.close)
                ai.control("connect", {"confirm": True})
                with self.assertRaises(AppError):
                    login(ai)
                self.assertFalse(ai.config()["has_key"])

    def test_rpc_timeout_kills_without_retry(self):
        rpc = self.connection()
        rpc.start()
        with self.assertRaises(AppError) as caught:
            rpc.call("synthetic/timeout", {}, timeout=0.1)
        self.assertEqual(caught.exception.status, 504)
        self.assertFalse(rpc.alive)
        self.assertEqual(len([row for row in rpc.messages() if row.get("method") == "synthetic/timeout"]), 1)

    def test_request_size_and_queue_bounds(self):
        rpc = self.connection()
        rpc.start()
        with self.assertRaises(AppError):
            rpc.send({"method": "test", "payload": "x" * MAX_REQUEST})
        with mock.patch.object(rpc.outbound, "put_nowait", side_effect=queue.Full), self.assertRaises(AppError):
            rpc.send({"method": "test"})
        self.assertFalse(rpc.alive)

    def test_missing_executable_and_symlink_roots_rejected(self):
        rpc = CodexRPC(Path(self.temp.name) / "connection", str(Path(self.temp.name) / "missing"))
        with self.assertRaises(AppError):
            rpc.start()
        if os.name != "nt":
            link = Path(self.temp.name) / "symlink"
            link.symlink_to(Path(self.temp.name), target_is_directory=True)
            with self.assertRaises(AppError):
                private_directory(link)

    def test_official_url_allowlist(self):
        for url in ("https://auth.openai.com/authorize?code=x", "https://chatgpt.com/auth/login", "https://auth.openai.com:443/"):
            self.assertEqual(official_auth_url(url), url)
        for url in ("http://auth.openai.com/", "https://auth.openai.com.evil.test/", "https://user@auth.openai.com/", "https://auth.openai.com:444/", "https://auth.openai.com/#fragment", "https://auth.openai.com\\@evil.test/", "https://auth.openai.com/\n", None, "javascript:alert(1)"):
            with self.subTest(url=url), self.assertRaises(AppError):
                official_auth_url(url)

    def test_check_config_disallows_tools_even_if_required_settings_match(self):
        effective = {}
        for key, value in SAFE_CONFIG.items():
            current = effective
            parts = key.split(".")
            for part in parts[:-1]:
                current = current.setdefault(part, {})
            current[parts[-1]] = value
        CodexRPC.check_config(effective)
        for key in ("mcp_servers", "plugins", "hooks"):
            with self.subTest(key=key), self.assertRaises(AppError):
                CodexRPC.check_config({**effective, key: {"unexpected": {}}})
