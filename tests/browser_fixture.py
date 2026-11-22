import json
import os
import tempfile
import time
from unittest import mock

from health_journal.demo import seed_demo
from health_journal.server import create_server
from tests.test_cloud import FAKE_KEY, FOOD, REPORT
from tests.test_codex import FakeRPC


def synthetic_completion(config, key, messages):
    time.sleep(min(30, max(0, float(os.environ.get("HEALTH_FIXTURE_DELAY", "0")))))
    task = json.loads(messages[1]["content"][0]["text"])["task"]
    result = dict(REPORT if task == "document" else FOOD if task == "breakfast" else {"summary": "合成档案问答", "suggestions": [], "uncertainties": [], "questions": []})
    result["summary"] = "【离线合成验收，非真实模型输出】" + result["summary"]
    return json.dumps(result, ensure_ascii=False)


def main():
    with tempfile.TemporaryDirectory(prefix="health-browser-fixture-") as directory:
        server = create_server(directory, 8767)
        server.codex.rpc_factory = type("BrowserRPC", (FakeRPC,), {"scenario": "delay"})
        seed_demo(server.store)
        server.cloud.configure({"provider": "openai", "model": "synthetic-offline-fixture", "vision": True, "api_key": FAKE_KEY, "revision": server.cloud.revision})
        print("http://127.0.0.1:8767 — 离线合成浏览器夹具，不连接任何模型服务", flush=True)
        try:
            with mock.patch("health_journal.cloud.request_completion", side_effect=synthetic_completion):
                server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            server.server_close()


if __name__ == "__main__":
    main()
