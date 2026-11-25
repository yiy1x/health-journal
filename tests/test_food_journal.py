import concurrent.futures
import datetime
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock
import uuid
import zipfile

from health_journal.cloud import CloudAI
from health_journal.demo import seed_demo
from health_journal.food_journal import FoodJournal, validate_food
from health_journal.store import Store
from health_journal.validation import AppError
from health_journal.wearables import Wearables
from tests.test_core import TODAY, adult, alter_backup


def food(**changes):
    return {"id": str(uuid.uuid4()), "date": TODAY, "time": "08:30", "meal": "breakfast", "note": "合成：燕麦一碗、鸡蛋一个", "document_id": None, **changes}


class FoodJournalTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="health-food-test-")
        self.addCleanup(self.temporary.cleanup)
        self.store = Store(Path(self.temporary.name) / 'original')
        self.food = FoodJournal(self.store)

    def test_create_without_model_or_diet_plan_and_restart(self):
        saved = self.food.save(food())
        self.assertEqual(FoodJournal(Store(self.store.directory)).entries(TODAY, TODAY), [saved])
        self.assertEqual(self.store.plans(), [])
        self.assertEqual(self.store.analyses(), [])
        self.assertFalse(self.store.profile()['diet_acknowledged'])
        self.assertEqual(saved['version'], 1)

    def test_idempotent_create_prevents_lost_response_duplicates(self):
        raw = food()
        first = self.food.save(raw)
        self.assertEqual(self.food.save(raw), first)
        self.assertEqual(len(self.food.entries()), 1)
        with self.assertRaises(AppError):
            self.food.save({**raw, 'note': '合成变化'})

    def test_repeat_identical_meals_with_new_ids_are_not_deduplicated(self):
        self.food.save(food())
        self.food.save(food())
        self.assertEqual(len(self.food.entries()), 2)

    def test_edit_delete_versions_and_audit_no_contents(self):
        first = self.food.save(food(note='synthetic-private-unique-food'))
        saved = self.food.save({**first, 'note': 'synthetic-private-edited'}, update=True)
        self.assertEqual(saved['version'], 2)
        self.assertEqual(saved['created_at'], first['created_at'])
        with self.assertRaises(AppError):
            self.food.save(first, update=True)
        with self.assertRaises(AppError):
            self.food.delete({'id': first['id'], 'version': 1, 'confirm': True})
        with self.assertRaises(AppError):
            self.food.delete({'id': first['id'], 'version': 2})
        self.food.delete({'id': first['id'], 'version': 2, 'confirm': True})
        self.assertEqual(self.food.entries(), [])
        self.assertNotIn('synthetic-private', json.dumps(self.store.audits()))

    def test_concurrent_edits_only_one_wins(self):
        saved = self.food.save(food())
        def update(note):
            try:
                self.food.save({**saved, 'note': note}, update=True)
                return 200
            except AppError as error:
                return error.status
        with concurrent.futures.ThreadPoolExecutor() as pool:
            self.assertEqual(sorted(pool.map(update, ('one', 'two'))), [200, 409])

    def test_invalid_fields_and_future_records_rejected(self):
        tomorrow = (datetime.date.today() + datetime.timedelta(days=1)).isoformat()
        for changes in ({'id':'bad'}, {'note':''}, {'note':'x'*2001}, {'note':[]}, {'date':tomorrow}, {'date':'2026-02-30'}, {'time':'24:00'}, {'time':'9:30'}, {'time':'00:60'}, {'meal':'unknown'}, {'meal':[]}, {'document_id':'../../bad'}):
            with self.subTest(changes=changes), self.assertRaises(AppError):
                self.food.save(food(**changes))
        self.assertEqual(self.food.entries(), [])
        self.assertEqual(self.food.save(food(time=''))['time'], '')

    def test_attachment_reference_protects_source_and_delete_keeps_original(self):
        doc = self.store.add_document('synthetic.txt', b'synthetic evidence')
        saved = self.food.save(food(document_id=doc['id']))
        with self.assertRaises(AppError) as caught:
            self.store.delete_document(doc['id'])
        self.assertEqual(caught.exception.status, 409)
        self.food.delete({'id':saved['id'],'version':1,'confirm':True})
        self.assertEqual(self.store.get_document(doc['id'])[1], b'synthetic evidence')

    def test_missing_corrupt_attachment_does_not_write(self):
        with self.assertRaises(AppError):
            self.food.save(food(document_id=str(uuid.uuid4())))
        doc = self.store.add_document('synthetic.txt', b'evidence')
        (self.store.files / doc['sha256']).write_bytes(b'corrupt')
        with self.assertRaises(AppError):
            self.food.save(food(document_id=doc['id']))
        self.assertEqual(self.food.entries(), [])

    def test_sql_injection_is_inert_text(self):
        saved = self.food.save(food(note="'; DROP TABLE records; -- <script>alert(1)</script>"))
        self.assertEqual(self.food.entries()[0], saved)
        self.assertEqual(self.store.records(), [])

    def test_empty_and_range_query(self):
        self.assertEqual(self.food.entries(TODAY, TODAY), [])
        self.food.save(food())
        self.assertEqual(self.food.entries('2020-01-01','2020-01-02'), [])
        for first,last in (('2020-01-01',TODAY), (TODAY,'2020-01-01'), ('bad',TODAY)):
            with self.assertRaises(AppError):
                self.food.entries(first,last)

    def test_food_backup_v4_roundtrip_and_old_versions(self):
        doc = self.store.add_document('synthetic.png', b'\x89PNG\r\n\x1a\nsynthetic')
        saved = self.food.save(food(document_id=doc['id']))
        backup = self.store.backup()
        with zipfile.ZipFile(io.BytesIO(backup)) as archive:
            manifest = json.loads(archive.read('manifest.json'))
        self.assertEqual(manifest['version'], 4)
        self.assertEqual(manifest['food_entries'], [saved])
        target = Store(Path(self.temporary.name)/'restored')
        target.restore(backup)
        self.assertEqual(FoodJournal(target).entries(), [saved])
        self.assertEqual(target.get_document(doc['id'])[1], self.store.get_document(doc['id'])[1])
        with self.assertRaises(AppError):
            target.restore(backup)

    def test_malformed_backup_never_partially_restores(self):
        self.food.save(food())
        backup = self.store.backup()
        mutations = [lambda data:data.pop('food_entries'), lambda data:data['food_entries'].append(data['food_entries'][0]), lambda data:data['food_entries'][0].update(version=True), lambda data:data['food_entries'][0].update(document_id=str(uuid.uuid4())), lambda data:data.update(version=2), lambda data:data['food_entries'][0].update(updated_at='1900-01-01T00:00:00Z')]
        for index, mutation in enumerate(mutations):
            target = Store(Path(self.temporary.name)/str(index))
            with self.assertRaises(AppError):
                target.restore(alter_backup(backup, mutation))
            self.assertEqual(FoodJournal(target).entries(), [])
            self.assertEqual(target.documents(), [])

    def test_food_prevents_restore_or_demo_overwrite(self):
        empty = Store(Path(self.temporary.name)/'blank')
        backup = empty.backup()
        self.food.save(food())
        with self.assertRaises(AppError):
            self.store.restore(backup)
        with self.assertRaises(AppError):
            seed_demo(self.store)

    def test_food_is_not_implicitly_sent_to_cloud(self):
        self.food.save(food(note='synthetic-secret-food'))
        cloud = CloudAI(self.store)
        cloud.configure({'provider':'openai','model':'synthetic','api_key':'synthetic','revision':cloud.revision})
        consent = cloud.prepare({'task':'chat','text':'synthetic','include_records':True,'include_profile':True})
        self.assertNotIn('synthetic-secret-food', json.dumps(consent))

    def test_day_overview_contains_food_without_device_data(self):
        saved = self.food.save(food())
        overview = Wearables(self.store).overview(TODAY, TODAY)
        self.assertEqual(overview['meals'][0]['id'], saved['id'])
        self.assertEqual(overview['meals'][0]['origin'], 'journal')
        self.assertIsNone(overview['daily'][0]['value'])
        day = Wearables(self.store).day(TODAY, {})
        for metric in day['metrics'].values():
            self.assertIsNone(metric['value'])

    def test_limit_stops_new_entries_but_allows_edits(self):
        saved = self.food.save(food())
        with mock.patch('health_journal.food_journal.LIMIT', 1):
            with self.assertRaises(AppError):
                self.food.save(food())
            self.food.save({**saved, 'note':'edited'}, update=True)
        self.assertEqual(len(self.food.entries()), 1)

    def test_v3_database_upgrade_does_not_change_profile_or_plans(self):
        self.store.profile(adult(notes='synthetic prior profile'))
        original = self.store.profile()
        with self.store.connection() as database:
            database.executescript('DROP TABLE food_entries; PRAGMA user_version=3;')
        restored = Store(self.store.directory)
        self.assertEqual(restored.profile(), original)
        self.assertEqual(FoodJournal(restored).entries(), [])
        with restored.connection() as database:
            self.assertEqual(database.execute('PRAGMA user_version').fetchone()[0],4)

    def test_device_and_food_joint_backup_and_independent_sources(self):
        import hashlib
        from tests.test_wearables import attrs, export_xml, record_xml, DAY
        manager = Wearables(self.store)
        self.addCleanup(manager.close)
        job = manager.reserve('synthetic.xml')
        path = Path(job['temporary'].name)/'input'
        payload = export_xml(record_xml(attrs(sourceName='watch')), record_xml(attrs(sourceName='phone',value='80')))
        path.write_bytes(payload)
        manager.launch(job,path,hashlib.sha256(payload).hexdigest())
        job['worker'].join(timeout=5)
        manager.commit({'id':job['id'],'metrics':['steps'],'from':DAY,'to':DAY,'confirm':True})
        saved = self.food.save(food(date=DAY))
        day = manager.day(DAY,{})
        self.assertTrue(day['metrics']['steps']['conflict'])
        chosen = day['metrics']['steps']['sources'][0]['source']
        chosen_result = manager.day(DAY,{'steps':chosen})
        self.assertIsNotNone(chosen_result['metrics']['steps']['value'])
        target = Store(Path(self.temporary.name)/'joint-restored')
        target.restore(self.store.backup())
        self.assertEqual(FoodJournal(target).entries(),[saved])
        self.assertEqual(Wearables(target).day(DAY,{})['metrics']['steps'],day['metrics']['steps'])

    def test_invalid_day_metric_selection_refused(self):
        manager = Wearables(self.store)
        for choices in ({'unknown':''},{'steps':'../path'}, {'steps':True}):
            with self.subTest(choices=choices),self.assertRaises(AppError):
                manager.day(TODAY,choices)
