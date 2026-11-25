import copy
import datetime
import hashlib
import io
import json
from pathlib import Path
import sqlite3
import tempfile
import threading
import time
import unittest
from unittest import mock
import zipfile
from xml.sax.saxutils import quoteattr

from health_journal.apple_health import AppleParser, FIELDS, METRICS, TABLE_SQL, apple_date, normalized, parse_export
from health_journal.demo import seed_demo
from health_journal.store import Store
from health_journal.validation import AppError
from health_journal.wearables import Wearables, aggregate, export_backup, summary, validate_backup
from tests.test_core import adult, alter_backup
from tests.test_cloud import FOOD


DAY = "2026-01-02"


def attrs(metric="StepCount", **changes):
    return {"type": "HKQuantityTypeIdentifier" + metric, "sourceName": "合成手表", "sourceVersion": "1", "device": "Synthetic Watch", "unit": "count", "value": "100", "startDate": DAY + " 10:00:00 +0800", "endDate": DAY + " 10:10:00 +0800", **changes}


def record_xml(attributes=None, children="", tag="Record"):
    attributes = attributes or attrs()
    return "<" + tag + " " + " ".join(key + "=" + quoteattr(str(value)) for key, value in attributes.items()) + ">" + children + "</" + tag + ">"


def export_xml(*records, prefix=""):
    return ('<?xml version="1.0" encoding="UTF-8"?>' + prefix + '<HealthData locale="zh_CN"><Me HKCharacteristicTypeIdentifierDateOfBirth="1900-01-01"/>' + ''.join(records or [record_xml()]) + '</HealthData>').encode()


def zipped(entries):
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, content in entries.items():
            archive.writestr(name, content)
    return output.getvalue()


class ParserTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "input"

    def parse(self, payload):
        self.path.write_bytes(payload)
        with sqlite3.connect(":memory:") as database:
            database.row_factory = sqlite3.Row
            result = parse_export(self.path, database, threading.Event(), lambda value: None)
            return result, [dict(row) for row in database.execute("SELECT * FROM wearable_samples ORDER BY day,id")]

    def test_official_dtd_and_unicode_xml_names(self):
        body = export_xml(prefix='<!DOCTYPE HealthData [<!ELEMENT HealthData ANY><!ELEMENT Record ANY><!ATTLIST HealthData locale CDATA #IMPLIED>]>')
        result, rows = self.parse(zipped({"apple_health_export/导出.xml": body, "apple_health_export/export_cda.xml": b"<ClinicalDocument/>", "workout-routes/route.gpx": b"private-not-read"}))
        self.assertEqual(result["samples"], 1)
        self.assertTrue(result["ignored_profile"])
        self.assertEqual(rows[0]["metric"], "steps")
        self.assertEqual(rows[0]["day"], DAY)

    def test_units_and_percentage_fractions(self):
        cases = [("BodyMass", "lb", "100", "weight", 45.359237), ("DistanceWalkingRunning", "mi", "1", "distance", 1.609344), ("HeartRateVariabilitySDNN", "s", "0.05", "hrv", 50), ("OxygenSaturation", "%", "0.98", "oxygen", 98), ("BodyFatPercentage", "%", "0.2", "body_fat", 20), ("DietaryWater", "L", "0.5", "water", 500), ("ActiveEnergyBurned", "kJ", "4.184", "active_energy", 1)]
        for kind, unit, value, metric, expected in cases:
            with self.subTest(metric=metric):
                result, rows = self.parse(export_xml(record_xml(attrs(kind, unit=unit, value=value))))
                self.assertEqual(rows[0]["metric"], metric)
                self.assertAlmostEqual(rows[0]["value"], expected)
                self.assertEqual(rows[0]["original_value"], value)
                self.assertEqual(rows[0]["original_unit"], unit)

    def test_all_metrics_have_a_supported_representation(self):
        for metric, definition in METRICS.items():
            if not definition[3]:
                continue
            unit = next(iter(definition[4]))
            value = "0.5" if metric in ("oxygen", "body_fat") else "1"
            with self.subTest(metric=metric):
                result, rows = self.parse(export_xml(record_xml(attrs(definition[3], value=value, unit=unit))))
                self.assertEqual(rows[0]["metric"], metric)

    def test_invalid_values_and_unsupported_types_reported_not_silently_saved(self):
        records = [record_xml()]
        for change in ({"value": "NaN"}, {"value": "inf"}, {"value": "-1"}, {"unit": "wrong"}, {"startDate": "bad"}, {"endDate": DAY + " 09:00:00 +0800"}, {"endDate": "2099-01-01 00:00:00 +0800"}):
            records.append(record_xml(attrs(**change)))
        records.append(record_xml(attrs("Unknown")))
        report, rows = self.parse(export_xml(*records))
        self.assertEqual(len(rows), 1)
        self.assertEqual(sum(report["invalid"].values()), 7)
        self.assertEqual(sum(report["unsupported"].values()), 1)

    def test_percent_98_does_not_become_9800(self):
        with self.assertRaises(AppError):
            self.parse(export_xml(record_xml(attrs("OxygenSaturation", value="98", unit="%"))))

    def test_entity_dtd_external_and_deep_documents_rejected(self):
        cases = [export_xml(prefix='<!DOCTYPE HealthData SYSTEM "file:///etc/passwd">'), export_xml(prefix='<!DOCTYPE HealthData [<!ENTITY secret SYSTEM "file:///etc/passwd">]>'), export_xml(prefix='<!DOCTYPE HealthData [<!ENTITY a "123">]>'), b"<HealthData>" + b"<a>" * 40 + b"</a>" * 40 + b"</HealthData>", b"<ClinicalDocument/>", b"<HealthData><Record", b"<HealthData/>"]
        for payload in cases:
            with self.subTest(payload=payload[:60]), self.assertRaises(AppError):
                self.parse(payload)

    def test_unsafe_zip_paths_multiple_or_absent_main_rejected(self):
        for entries in ({"../export.xml": export_xml()}, {"/export.xml": export_xml()}, {"a.xml": export_xml(), "b.xml": export_xml()}, {"export_cda.xml": b"<ClinicalDocument/>"}, {"export.xml": b"bad"}):
            with self.subTest(entries=list(entries)), self.assertRaises(AppError):
                self.parse(zipped(entries))

    def test_zip_duplicate_names_and_symlinks_rejected(self):
        output = io.BytesIO()
        with zipfile.ZipFile(output, "w") as archive:
            entry = zipfile.ZipInfo("export.xml")
            entry.external_attr = 0o120777 << 16
            archive.writestr(entry, export_xml())
        with self.assertRaises(AppError):
            self.parse(output.getvalue())

    def test_caps_and_cancel_fail_without_partial_output(self):
        self.path.write_bytes(export_xml())
        cancelled = threading.Event()
        cancelled.set()
        with sqlite3.connect(":memory:") as database, self.assertRaises(AppError):
            parse_export(self.path, database, cancelled, lambda value: None)
        for target, value in (("MAX_XML", 10), ("MAX_SAMPLES", 0), ("MAX_SECONDS", -1)):
            with mock.patch("health_journal.apple_health." + target, value), self.assertRaises(AppError):
                self.parse(export_xml())

    def test_source_pointer_and_version_do_not_duplicate_reexports(self):
        first = record_xml(attrs(device="<HKDevice: 0xabc>, name: Watch", sourceVersion="1"))
        second = record_xml(attrs(device="<HKDevice: 0xdef>, name: Watch", sourceVersion="2"))
        report, rows = self.parse(export_xml(first, second))
        self.assertEqual(len(rows), 1)
        self.assertEqual(report["file_duplicates"], 1)

    def test_manual_metadata_retained(self):
        report, rows = self.parse(export_xml(record_xml(children='<MetadataEntry key="HKWasUserEntered" value="1"/>')))
        self.assertEqual(rows[0]["manual"], 1)

    def test_sleep_dst_duration_and_end_day(self):
        data = attrs(type="HKCategoryTypeIdentifierSleepAnalysis", value="HKCategoryValueSleepAnalysisAsleepCore", startDate="2025-11-02 01:30:00 -0400", endDate="2025-11-02 02:30:00 -0500")
        report, rows = self.parse(export_xml(record_xml(data)))
        self.assertEqual(rows[0]["value"], 2)
        self.assertEqual(rows[0]["day"], "2025-11-02")

    def test_workout_uses_reported_duration_not_full_span(self):
        data = attrs(workoutActivityType="HKWorkoutActivityTypeWalking", duration="8", durationUnit="min")
        report, rows = self.parse(export_xml(record_xml(data, tag="Workout")))
        self.assertEqual(rows[0]["metric"], "workout")
        self.assertEqual(rows[0]["value"], 8)
        with self.assertRaises(AppError):
            self.parse(export_xml(record_xml({**data, "duration": "120"}, tag="Workout")))

    def test_date_requires_zone(self):
        for value in (DAY + " 12:00:00", DAY + "T12:00:00+1500", DAY + "x12:00:00+0800", DAY + "T12:00:00+0860"):
            with self.subTest(value=value), self.assertRaises(AppError):
                apple_date(value)

    def test_cross_midnight_keeps_original_offsets_and_end_date(self):
        data = attrs(startDate="2026-01-01 23:55:00 +0800", endDate="2026-01-02 00:05:00 +0800")
        report, rows = self.parse(export_xml(record_xml(data)))
        self.assertEqual(rows[0]["cross_day"], 1)
        self.assertEqual(rows[0]["day"], "2026-01-02")
        self.assertTrue(rows[0]["start"].endswith('+08:00'))
        self.assertIn('结束日', aggregate(rows, 'steps')["warning"])

    def test_truncated_zip_crc_and_large_attributes_fail(self):
        content = zipped({"export.xml": export_xml()})
        with self.assertRaises(AppError):
            self.parse(content[:-30])
        with self.assertRaises(AppError):
            self.parse(export_xml(record_xml(attrs(device="x" * 9000))))


class AggregateTests(unittest.TestCase):
    def sample(self, **changes):
        return normalized(attrs(**changes), "Record")

    def test_missing_is_not_zero_and_real_zero_remains_zero(self):
        self.assertIsNone(aggregate([], "steps")["value"])
        self.assertEqual(aggregate([self.sample(value="0")], "steps")["value"], 0)

    def test_multiple_sources_require_explicit_selection(self):
        watch, phone = self.sample(), self.sample(sourceName="合成手机", value="80")
        self.assertTrue(aggregate([watch, phone], "steps")["conflict"])
        self.assertIsNone(aggregate([watch, phone], "steps")["value"])
        self.assertEqual(aggregate([watch, phone], "steps", phone["source"])["value"], 80)

    def test_same_source_overlap_not_double_counted(self):
        first = self.sample()
        overlap = self.sample(startDate=DAY + " 10:05:00 +0800", endDate=DAY + " 10:15:00 +0800", value="50")
        self.assertIsNone(aggregate([first, overlap], "steps")["value"])
        adjacent = self.sample(startDate=DAY + " 10:10:00 +0800", endDate=DAY + " 10:15:00 +0800", value="50")
        self.assertEqual(aggregate([first, adjacent], "steps")["value"], 150)

    def test_heart_rate_mean_and_last_weight_timezone(self):
        rows = [self.sample(type="HKQuantityTypeIdentifierHeartRate", unit="count/min", value=str(value)) for value in (60, 80)]
        self.assertEqual(aggregate(rows, "heart_rate")["value"], 70)
        self.assertIn("算术均值", aggregate(rows, "heart_rate")["warning"])
        weights = [self.sample(type="HKQuantityTypeIdentifierBodyMass", unit="kg", value="60"), self.sample(type="HKQuantityTypeIdentifierBodyMass", unit="kg", value="61", startDate=DAY + " 08:00:00 -0800", endDate=DAY + " 08:00:00 -0800")]
        self.assertEqual(aggregate(weights, "weight")["value"], 61)

    def test_sleep_union_excludes_awake_and_inbed(self):
        rows = []
        for category, start, end in (("Asleep", "00:00:00", "08:00:00"), ("AsleepCore", "00:00:00", "06:00:00"), ("AsleepREM", "06:00:00", "08:00:00"), ("InBed", "00:00:00", "09:00:00")):
            rows.append(self.sample(type="HKCategoryTypeIdentifierSleepAnalysis", value="HKCategoryValueSleepAnalysis" + category, startDate=DAY + " " + start + " +0800", endDate=DAY + " " + end + " +0800"))
        result = aggregate(rows, "sleep")
        self.assertEqual(result["value"], 8)
        self.assertEqual(result["stages"]["in_bed"], 9)
        self.assertIsNone(aggregate([rows[-1]], "sleep")["value"])


class WearableStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = Store(Path(self.temp.name) / "vault")
        self.manager = Wearables(self.store)
        self.addCleanup(self.manager.close)

    def preview(self, payload=None):
        previous = self.manager.status()
        if previous["state"] != "idle":
            self.manager.cancel(previous["id"])
        job = self.manager.reserve("合成健康.xml")
        path = Path(job["temporary"].name) / "input"
        content = payload or export_xml()
        path.write_bytes(content)
        self.manager.launch(job, path, hashlib.sha256(content).hexdigest())
        job["worker"].join(timeout=5)
        self.assertEqual(self.manager.status()["state"], "ready", self.manager.status())
        self.assertFalse(path.exists())
        return job

    def commit(self, **changes):
        return self.manager.commit({"id": self.manager.job["id"], "metrics": ["steps"], "from": DAY, "to": DAY, "confirm": True, **changes})

    def test_preview_requires_confirmation_and_frozen_selection(self):
        job = self.preview()
        with self.store.connection() as database:
            self.assertEqual(summary(database)["samples"], 0)
        with self.assertRaises(AppError):
            self.commit(confirm=False)
        result = self.commit()
        self.assertEqual(result["imported"], 1)
        self.assertFalse(Path(job["temporary"].name).exists())
        with self.assertRaises(AppError):
            self.commit()
        self.assertEqual(self.store.records(), [])
        self.assertEqual(self.store.profile()["birth_date"], "")

    def test_preview_and_commit_close_temporary_database_connections(self):
        real_connect = sqlite3.connect
        connections = []
        def tracked_connect(*arguments, **options):
            connection = real_connect(*arguments, **options)
            if str(arguments[0]).endswith('preview.sqlite3'):
                connections.append(connection)
            return connection
        with mock.patch('health_journal.wearables.sqlite3.connect', side_effect=tracked_connect):
            self.preview()
            self.commit()
        self.assertEqual(len(connections), 2)
        for connection in connections:
            with self.assertRaises(sqlite3.ProgrammingError):
                connection.execute('SELECT 1')

    def test_reimport_idempotence_and_batch_deletion_preserves_shared_samples(self):
        self.preview()
        first = self.commit()
        self.preview()
        self.assertTrue(self.commit()["already_imported"])
        self.preview(export_xml(record_xml(), '<ExportDate value="changed"/>'))
        second = self.commit()
        self.assertEqual(second["duplicates"], 1)
        self.manager.delete({"id": first["batch_id"], "confirm": True})
        self.assertEqual(self.manager.overview(DAY, DAY)["samples"], 1)
        self.manager.delete({"id": second["batch_id"], "confirm": True})
        self.assertEqual(self.manager.overview(DAY, DAY)["samples"], 0)

    def test_metric_and_date_selection_only_saves_requested_samples(self):
        self.preview(export_xml(record_xml(), record_xml(attrs("HeartRate", unit="count/min", value="65")), record_xml(attrs(startDate="2026-01-03 00:00:00 +0800", endDate="2026-01-03 00:10:00 +0800"))))
        self.assertEqual(self.commit()["imported"], 1)
        self.assertEqual(self.manager.overview(DAY, DAY)["samples"], 1)

    def test_end_day_selection_does_not_use_computer_timezone_future_cutoff(self):
        from health_journal.validation import date_value
        self.preview()
        with mock.patch('health_journal.wearables.date_value', wraps=date_value) as check:
            self.commit()
        self.assertTrue(all(len(call.args) < 4 or call.args[3] is True for call in check.call_args_list))

    def test_invalid_selection_empty_range_and_limits_rollback(self):
        self.preview()
        for change in ({"metrics": []}, {"metrics": ["__proto__"]}, {"metrics": [["steps"]]}, {"metrics": ["steps", "steps"]}, {"from": "2026-01-03"}, {"to": "2025-12-30"}, {"from": "2026-01-04", "to": "2026-01-04"}):
            with self.subTest(change=change), self.assertRaises(AppError):
                self.commit(**change)
        with mock.patch("health_journal.wearables.MAX_SAMPLES", 0), self.assertRaises(AppError):
            self.commit()
        self.assertEqual(self.manager.overview(DAY, DAY)["samples"], 0)
        self.assertEqual(self.manager.overview(DAY, DAY)["batches"], [])

    def test_preview_expiry_cancel_and_shutdown_cleanup(self):
        job = self.preview()
        self.manager.cancel(job["id"])
        self.assertEqual(self.manager.status()["state"], "idle")
        self.assertFalse(Path(job["temporary"].name).exists())
        job = self.preview()
        job["expires"] = 0
        self.assertEqual(self.manager.status()["state"], "idle")
        job = self.preview()
        self.manager.close()
        self.assertFalse(Path(job["temporary"].name).exists())
        with self.assertRaises(AppError):
            self.manager.reserve("new.xml")

    def test_single_import_and_wrong_cancel_id_rejected(self):
        self.preview()
        with self.assertRaises(AppError):
            self.manager.reserve("new.xml")
        with self.assertRaises(AppError):
            self.manager.cancel("not-owner")
        self.assertEqual(self.manager.status()["state"], "ready")

    def test_backup_restore_v3_and_tamper_rejection(self):
        self.preview(); self.commit()
        backup = self.store.backup()
        with zipfile.ZipFile(io.BytesIO(backup)) as archive:
            manifest = json.loads(archive.read("manifest.json"))
            self.assertEqual(manifest["version"], 3)
            self.assertIn("wearable.jsonl", archive.namelist())
        target = Store(Path(self.temp.name) / "restored")
        target.restore(backup)
        manager = Wearables(target)
        self.assertEqual(manager.overview(DAY, DAY)["daily"], self.manager.overview(DAY, DAY)["daily"])
        with self.assertRaises(AppError):
            self.store.restore(backup)
        empty = Store(Path(self.temp.name) / "invalid")
        with self.assertRaises(AppError):
            empty.restore(alter_backup(backup, replace={"wearable.jsonl": b"tampered"}))
        self.assertEqual(Wearables(empty).overview(DAY, DAY)["samples"], 0)

    def test_backup_structure_reference_and_value_validation(self):
        self.preview(); self.commit()
        with self.store.connection() as database:
            content = export_backup(database)
        rows = [json.loads(line) for line in content.splitlines()]
        variants = [rows[:-1], rows + [rows[1]], [{"kind": "surprise", "data": {}}]]
        bad = copy.deepcopy(rows)
        next(row for row in bad if row["kind"] == "sample")["data"]["value"] = float("nan")
        variants.append(bad)
        for variant in variants:
            with self.subTest(variant=str(variant)[:70]), self.assertRaises(AppError):
                validate_backup('\n'.join(json.dumps(row) for row in variant).encode())

    def test_daily_meals_include_only_real_intake_not_plans_or_ai_foods(self):
        from health_journal.nutrition import make_plan
        self.store.profile(adult())
        plan = make_plan(DAY, self.store.profile(), [])
        self.store.save_plan(plan)
        self.preview(); self.commit()
        self.assertEqual(self.manager.overview(DAY, DAY)["meals"], [])
        plan["meals"]["breakfast"].update(eaten=True, note="合成实际鸡蛋")
        self.store.save_plan(plan)
        draft = self.store.save_analysis("breakfast", FOOD, {"provider": "synthetic", "model": "synthetic", "endpoint": "none", "source": None, "submitted_text": "synthetic"})
        self.assertEqual(len(self.manager.overview(DAY, DAY)["meals"]), 1)
        self.store.update_intake(draft["id"], {"date": DAY, "meal": "lunch", "note": "合成实际午餐", "version": 1})
        self.assertEqual(len(self.manager.overview(DAY, DAY)["meals"]), 2)

    def test_restart_pagination_and_date_limits(self):
        self.preview(); self.commit()
        restarted = Wearables(Store(self.store.directory))
        result = restarted.details(DAY, "steps", "", 0)
        self.assertEqual(result["total"], 1)
        self.assertEqual(restarted.details(DAY, "steps", "", 50)["items"], [])
        for args in (("2020-01-01", DAY), (DAY, "2025-01-01"), (DAY, DAY, "bad")):
            with self.assertRaises(AppError):
                restarted.overview(*args)
        with self.assertRaises(AppError):
            restarted.details(DAY, "steps", "bad", 0)

    def test_wearables_not_implicitly_included_in_ai_or_original_transfer(self):
        from health_journal.cloud import CloudAI
        from health_journal.transfer import export_transfer
        self.preview(export_xml(record_xml(attrs(sourceName="SECRET-SYNTHETIC-WATCH")))); self.commit()
        cloud = CloudAI(self.store)
        cloud.configure({"provider": "openai", "model": "synthetic", "api_key": "synthetic-key", "revision": cloud.revision})
        consent = cloud.prepare({"task": "chat", "text": "合成问题", "include_records": True})
        self.assertNotIn("SECRET-SYNTHETIC-WATCH", json.dumps(consent))
        self.assertNotIn(b"SECRET-SYNTHETIC-WATCH", export_transfer(self.store))
        with self.assertRaises(AppError):
            seed_demo(self.store)

    def test_malformed_file_background_error_and_removal(self):
        job = self.manager.reserve("bad.xml")
        path = Path(job["temporary"].name) / "input"
        path.write_bytes(b"<bad>")
        self.manager.launch(job, path, hashlib.sha256(b"<bad>").hexdigest())
        job["worker"].join(timeout=5)
        self.assertEqual(self.manager.status()["state"], "error")
        self.assertFalse(Path(job["temporary"].name).exists())
        self.assertEqual(self.manager.overview(DAY, DAY)["samples"], 0)

    def test_schema_v2_upgrade_preserves_prior_profile(self):
        profile = self.store.profile(adult(notes="合成既有备注"))
        with self.store.connection() as database:
            database.executescript("DROP TABLE wearable_members; DROP TABLE wearable_batches; DROP TABLE wearable_samples; PRAGMA user_version = 2;")
        upgraded = Store(self.store.directory)
        self.assertEqual(upgraded.profile(), profile)
        with upgraded.connection() as database:
            self.assertEqual(database.execute('PRAGMA user_version').fetchone()[0], 4)
            self.assertEqual(summary(database)["samples"], 0)

    def test_cancel_during_parse_and_close_do_not_commit(self):
        started, release = threading.Event(), threading.Event()
        def slow_parser(path, database, cancelled, progress):
            started.set()
            release.wait(2)
            if cancelled.is_set():
                raise AppError('已取消')
            raise AssertionError('Expected cancellation')
        with mock.patch('health_journal.wearables.parse_export', side_effect=slow_parser):
            job = self.manager.reserve('synthetic.xml')
            path = Path(job['temporary'].name) / 'input'
            path.write_bytes(export_xml())
            self.manager.launch(job, path, 'a' * 64)
            self.assertTrue(started.wait(1))
            self.manager.cancel(job['id'])
            release.set()
            job['worker'].join(timeout=3)
        self.assertEqual(self.manager.status()['state'], 'cancelled')
        self.assertFalse(Path(job['temporary'].name).exists())
        self.assertEqual(self.manager.overview(DAY, DAY)['samples'], 0)

    def test_reference_range_and_original_unit_tampering_rejected(self):
        self.preview(); self.commit()
        with self.store.connection() as database:
            rows = [json.loads(line) for line in export_backup(database).splitlines()]
        for change in ('range', 'unit', 'boolean'):
            modified = copy.deepcopy(rows)
            if change == 'range':
                batch = next(row['data'] for row in modified if row['kind'] == 'batch')
                batch['selection'] = json.dumps({'metrics':['steps'], 'from':'2026-01-03', 'to':'2026-01-03'})
            else:
                sample = next(row['data'] for row in modified if row['kind'] == 'sample')
                if change == 'unit':
                    sample['original_unit'] = 'kg'
                else:
                    sample['value'] = True
            with self.subTest(change=change), self.assertRaises(AppError):
                validate_backup('\n'.join(json.dumps(row) for row in modified).encode())

    def test_backup_size_guard_preserves_source_data(self):
        self.preview(); self.commit()
        with mock.patch('health_journal.wearables.BACKUP_LIMIT', 10), self.assertRaises(AppError):
            self.store.backup()
        self.assertEqual(self.manager.overview(DAY, DAY)['samples'], 1)

    def test_health_backups_with_every_supported_metric_roundtrip(self):
        records = []
        for metric, definition in METRICS.items():
            if definition[3]:
                records.append(record_xml(attrs(definition[3], unit=next(iter(definition[4])), value='0.5' if metric in ('oxygen','body_fat') else '1')))
        records.append(record_xml(attrs(type='HKCategoryTypeIdentifierSleepAnalysis', value='HKCategoryValueSleepAnalysisAsleepCore')))
        records.append(record_xml(attrs(workoutActivityType='HKWorkoutActivityTypeWalking', duration='8', durationUnit='min'), tag='Workout'))
        self.preview(export_xml(*records)); self.commit(metrics=list(METRICS))
        target = Store(Path(self.temp.name) / 'all-restored')
        target.restore(self.store.backup())
        with target.connection() as database:
            self.assertEqual(summary(database)['samples'], len(METRICS))
