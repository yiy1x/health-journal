import datetime
import hashlib
from pathlib import Path
import tempfile
import uuid

from health_journal.demo import seed_demo
from health_journal.server import create_server
from tests.test_wearables import attrs, export_xml, record_xml


def main():
    with tempfile.TemporaryDirectory(prefix='health-daily-browser-') as directory:
        server = create_server(directory,8767)
        seed_demo(server.store)
        yesterday = datetime.date.today() - datetime.timedelta(days=1)
        samples = []
        for offset, steps in enumerate((4600, 5800, 3700, 6200, 8100, 5300, 6840)):
            day = (yesterday - datetime.timedelta(days=6-offset)).isoformat()
            common = {'startDate':day+' 08:00:00 +0800','endDate':day+' 08:30:00 +0800'}
            samples.append(record_xml(attrs(value=str(steps),**common)))
            samples.append(record_xml(attrs('HeartRate',unit='count/min',value=str(63+offset%5),**common)))
            samples.append(record_xml(attrs('DistanceWalkingRunning',unit='km',value=str(round(steps*0.0007,2)),**common)))
            samples.append(record_xml(attrs(type='HKCategoryTypeIdentifierSleepAnalysis',value='HKCategoryValueSleepAnalysisAsleepCore',startDate=day+' 00:00:00 +0800',endDate=day+' 07:20:00 +0800')))
        content = export_xml(*samples)
        job = server.wearables.reserve('合成日常验收.xml')
        path = Path(job['temporary'].name)/'input'
        path.write_bytes(content)
        server.wearables.launch(job,path,hashlib.sha256(content).hexdigest()); job['worker'].join(timeout=5)
        server.wearables.commit({'id':job['id'],'metrics':['steps','heart_rate','distance','sleep'],'from':(yesterday-datetime.timedelta(days=6)).isoformat(),'to':yesterday.isoformat(),'confirm':True})
        server.wearables.cancel(job['id'])
        for meal,clock,note in [('breakfast','08:15','【合成演示】燕麦一碗、鸡蛋一个，豆浆未加糖。'),('lunch','12:30','【合成演示】米饭、清炒西兰花、鸡肉。份量按自己的记忆记录。')]:
            server.food.save({'id':str(uuid.uuid4()),'date':yesterday.isoformat(),'time':clock,'meal':meal,'note':note})
        print('http://127.0.0.1:8767/#wearables?date='+yesterday.isoformat()+' — 独立合成日常手记，不连接模型或 Apple',flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            server.server_close()


if __name__ == '__main__':
    main()
