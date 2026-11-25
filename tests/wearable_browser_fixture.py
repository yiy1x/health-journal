import datetime
import hashlib
from pathlib import Path
import tempfile

from health_journal.demo import seed_demo
from health_journal.nutrition import make_plan
from health_journal.server import create_server
from tests.test_wearables import attrs, export_xml, record_xml, zipped


def main():
    with tempfile.TemporaryDirectory(prefix="health-apple-browser-") as directory:
        server = create_server(directory, 8767)
        seed_demo(server.store)
        samples = []
        today = datetime.date.today()
        for index in range(14):
            day = (today - datetime.timedelta(days=14 - index)).isoformat()
            common = {"startDate": day + " 08:00:00 +0800", "endDate": day + " 08:30:00 +0800"}
            samples.append(record_xml(attrs(value=str(2400 + index * 330), **common)))
            if index > 5:
                samples.append(record_xml(attrs(value=str(1200 + index * 230), sourceName="合成 iPhone", device="Synthetic iPhone", **common)))
            for metric, unit, value in (("HeartRate", "count/min", 64 + index % 6), ("RestingHeartRate", "count/min", 58 + index % 4), ("HeartRateVariabilitySDNN", "ms", 38 + index), ("ActiveEnergyBurned", "kcal", 100 + index * 15), ("BodyMass", "kg", 66 + index % 4 / 10)):
                samples.append(record_xml(attrs(metric, unit=unit, value=str(value), **common)))
            samples.append(record_xml(attrs(type="HKCategoryTypeIdentifierSleepAnalysis", value="HKCategoryValueSleepAnalysisAsleepCore", startDate=day + " 00:00:00 +0800", endDate=day + " 07:30:00 +0800")))
            if index % 3 == 0:
                plan = make_plan(day, server.store.profile(), [])
                plan["meals"]["breakfast"].update(eaten=True, note="【合成验收】鸡蛋、燕麦与无糖豆浆，非真实饮食")
                server.store.save_plan(plan)
        content = zipped({"apple_health_export/导出.xml": export_xml(*samples)})
        job = server.wearables.reserve("合成验收_Apple健康.zip")
        path = Path(job["temporary"].name) / "input"
        path.write_bytes(content)
        server.wearables.launch(job, path, hashlib.sha256(content).hexdigest())
        job["worker"].join(timeout=5)
        if server.wearables.status()["state"] != "ready":
            raise RuntimeError("Synthetic preview failed")
        print("http://127.0.0.1:8767/#wearables — 合成健康预览；未登录 Apple、未读取真实资料", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            server.server_close()


if __name__ == "__main__":
    main()
