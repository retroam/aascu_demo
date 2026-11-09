"""Dataset replacement contracts, using disposable files and the public HTTP boundary."""
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from http.server import ThreadingHTTPServer

import analytics
import dataset
import foundations
import modeling
import pdp_model
import server
import sql_guard
import students
import yaml


class SyncTests(unittest.TestCase):
    """A sync changes every consumer or leaves the old dataset intact."""
    @classmethod
    def setUpClass(cls):
        """Build the ten-student fixture with different entry cohorts once."""
        cls.fixture_dir = tempfile.TemporaryDirectory()
        root = Path(cls.fixture_dir.name)
        cls.sample = root / "sample.sqlite"
        original = pdp_model.PIPELINE_CONFIG
        config = yaml.safe_load(original.read_text())
        config.update(logs_dir=str(root / "logs"), staging_dir=str(root / "staging"))
        local = root / "pipeline.yaml"
        local.write_text(yaml.safe_dump(config))
        sample = foundations.MODEL / "data/input/sample"
        with patch.object(pdp_model, "PIPELINE_CONFIG", local):
            pdp_model.run_load(f"sqlite:///{cls.sample}", "sync-contract-fixture", cohort=str(sample / "pdp_cohort_data.csv"),
                               course=str(sample / "pdp_course_data.csv"), tables_dir=root / "tables")
        with closing(sqlite3.connect(cls.sample)) as db:
            years = [r[0] for r in db.execute("SELECT DISTINCT cohort FROM cohort_membership")]
            cls.years = sorted(f"{int(year[:4])-5}-{int(year[-2:])-5:02}" for year in years)
            for year in years:
                new = f"{int(year[:4])-5}-{int(year[-2:])-5:02}"
                for table in ("cohort_membership", "course_enrollment"):
                    db.execute(f"UPDATE {table} SET cohort=? WHERE cohort=?", (new, year))
            old_id = db.execute("SELECT student_id FROM student ORDER BY student_id LIMIT 1").fetchone()[0]
            cls.lower_id = old_id.lower()
            for table in ("student", "cohort_membership", "course_enrollment", "student_attribute"):
                db.execute(f"UPDATE {table} SET student_id=? WHERE student_id=?", (cls.lower_id, old_id))
            db.commit()

    @classmethod
    def tearDownClass(cls):
        """Remove generated fixture files."""
        cls.fixture_dir.cleanup()

    def setUp(self):
        """Redirect all consumers to one disposable dashboard and Workbench pair."""
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.target, self.source = root / "pdp.sqlite", root / "workbench.sqlite"
        shutil.copy2(foundations.DATABASE, self.target)
        shutil.copy2(self.sample, self.source)
        self.patches = [patch.object(foundations, "DATABASE", self.target), patch.object(sql_guard, "DATABASE", self.target),
                        patch.object(dataset, "WORKBENCH", self.source), patch.object(dataset, "workbench_status", return_value={"active_run": None})]
        for item in self.patches:
            item.start()
        dataset.invalidate()
        self.before = self.target.read_bytes()
        self.current = dataset.identity()["run_id"]

    def tearDown(self):
        """Restore consumer paths and clear data cached from the test."""
        for item in reversed(self.patches):
            item.stop()
        dataset.invalidate()
        self.temp.cleanup()

    def test_sync_replaces_all_consumers_and_preserves_backup(self):
        """Different cohort years and row counts expose stale metadata or cached frames."""
        analytics.get_dashboard()
        foundations.documentation()
        sql_guard.schema_catalog()
        result = dataset.sync("sync-contract-fixture", self.current)
        dashboard = analytics.get_dashboard()
        self.assertEqual((result["students"], result["cohort_rows"], result["course_rows"]), (10, 11, 52))
        self.assertEqual(dashboard["meta"]["cohorts"], self.years)
        self.assertEqual(dashboard["meta"]["cohort_rows"], 11)
        self.assertEqual(dashboard["meta"]["dataset"]["origin"], "workbench")
        self.assertEqual(self.target.with_name("pdp.previous.sqlite").read_bytes(), self.before)
        self.assertFalse(modeling.get_model()["available"])
        self.assertFalse(modeling.get_scenario({})["available"])
        self.assertEqual(foundations.documentation()["findings"], [])
        self.assertTrue(all("/" not in source["file"] for source in analytics.provenance()))
        self.assertEqual(students.get_student({"id": self.lower_id})["student_id"], self.lower_id)
        self.assertEqual(students.get_students({"search": self.lower_id[:12]})["rows"][0]["student_id"], self.lower_id)
        with sql_guard._connection({"cohort": self.years[0]}) as db:
            self.assertEqual(db.execute("SELECT COUNT(DISTINCT cohort) FROM cohort_records").fetchone()[0], 1)
        for year in self.years:
            analytics.get_trends({"cohort": year})
            analytics.get_shared_measures({"cohort": year})
        with self.assertRaises(ValueError):
            analytics.normalize_filters({"cohort": "2019-20' OR 1=1 --"})

    def test_busy_stale_and_invalid_snapshots_leave_dashboard_unchanged(self):
        """Every refusal occurs before the dashboard file is replaced."""
        with patch.object(dataset, "workbench_status", return_value={"active_run": "busy"}):
            with self.assertRaises(dataset.SyncError):
                dataset.sync("sync-contract-fixture", self.current)
        for source, current in (("stale", self.current), ("sync-contract-fixture", "stale")):
            with self.assertRaises(dataset.SyncError):
                dataset.sync(source, current)
        with closing(sqlite3.connect(self.source)) as db:
            db.execute("ALTER TABLE student DROP COLUMN gender")
        with self.assertRaises(dataset.SyncError):
            dataset.sync("sync-contract-fixture", self.current)
        self.assertEqual(self.target.read_bytes(), self.before)
        self.assertEqual(list(self.target.parent.glob("pdp-sync-*")), [])

    def test_analysis_failure_restores_exact_previous_database(self):
        """A valid schema is insufficient if the dashboard cannot analyze the new records."""
        with patch.object(analytics, "get_shared_measures", side_effect=ValueError("bad data")):
            with self.assertRaisesRegex(dataset.SyncError, "restored"):
                dataset.sync("sync-contract-fixture", self.current)
        self.assertEqual(self.target.read_bytes(), self.before)
        self.assertEqual(dataset.identity()["run_id"], self.current)

    def test_writer_waits_for_readers_and_second_sync_is_refused(self):
        """No active response can observe a replaced database halfway through its queries."""
        entered, release, finished = threading.Event(), threading.Event(), threading.Event()
        errors = []
        def reader():
            """Hold a complete old-generation analysis open."""
            with dataset.reading():
                entered.set()
                release.wait(10)
                self.assertEqual(self.target.read_bytes(), self.before)
        def writer():
            """Attempt the replacement while the reader is active."""
            try:
                dataset.sync("sync-contract-fixture", self.current)
            except Exception as error:
                errors.append(error)
            finally:
                finished.set()
        read_thread = threading.Thread(target=reader)
        read_thread.start()
        self.assertTrue(entered.wait(5))
        write_thread = threading.Thread(target=writer)
        write_thread.start()
        try:
            with dataset.CONDITION:
                self.assertTrue(dataset.CONDITION.wait_for(lambda: dataset._writing, timeout=5))
            self.assertFalse(finished.is_set())
            with self.assertRaisesRegex(dataset.SyncError, "already running"):
                dataset.sync("sync-contract-fixture", self.current)
        finally:
            release.set()
            read_thread.join(10)
            write_thread.join(30)
        self.assertTrue(finished.is_set())
        self.assertEqual(errors, [])

    def test_http_sync_requires_local_confirmation_and_attestation(self):
        """Cross-origin, unauthenticated form, and unconfirmed writes cannot replace data."""
        httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        base = f"http://127.0.0.1:{httpd.server_port}"
        payload = {"confirm": "REPLACE ALL DASHBOARD DATA", "synthetic": True,
                   "workbench_run_id": "sync-contract-fixture", "current_run_id": self.current}
        headers = {"Content-Type": "application/json", "Origin": base, "X-PDP-Action": "replace-dashboard"}
        try:
            for change in ({"Origin": "http://evil.test"}, {"Origin": "null"}, {"Origin": ""},
                           {"X-PDP-Action": ""}, {"Content-Type": "text/plain"}, {"Sec-Fetch-Site": "cross-site"}):
                request = Request(base + "/api/workbench/sync", data=json.dumps(payload).encode(), headers={**headers, **change})
                with self.assertRaises(HTTPError) as caught:
                    urlopen(request)
                self.assertEqual(caught.exception.code, 403)
                self.assertEqual(self.target.read_bytes(), self.before)
            bad = Request(base + "/api/workbench/sync", data=json.dumps({**payload, "synthetic": False}).encode(), headers=headers)
            with self.assertRaises(HTTPError) as caught:
                urlopen(bad)
            self.assertEqual(caught.exception.code, 400)
            with urlopen(Request(base + "/api/workbench/sync", data=json.dumps(payload).encode(), headers=headers)) as response:
                self.assertEqual(json.load(response)["dataset"]["cohort_rows"], 11)
            with urlopen(base + "/api/dashboard") as response:
                self.assertEqual(json.load(response)["meta"]["course_rows"], 52)
                self.assertEqual(response.headers["X-PDP-Dataset"], "workbench:sync-contract-fixture")
            for path in ("/api/measures", "/api/report?format=csv"):
                with self.assertRaises(HTTPError) as caught:
                    urlopen(Request(base + path, headers={"X-PDP-Dataset": f"starter:{self.current}"}))
                self.assertEqual(caught.exception.code, 409)
                self.assertEqual(caught.exception.headers["X-PDP-Dataset"], "workbench:sync-contract-fixture")
        finally:
            httpd.shutdown()
            httpd.server_close()
            thread.join()


class HostedWorkbenchTests(unittest.TestCase):
    """Public-host requests stay protected even behind a loopback reverse proxy."""
    def test_remote_session_protects_preview_upload_and_sync(self):
        """A valid HTTPS login permits access; missing, forged and rotated sessions do not."""
        httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        base = f"http://127.0.0.1:{httpd.server_port}"
        headers = {"Host": "demo.example", "Origin": "https://demo.example", "Content-Type": "application/json"}
        token = "test-only-random-credential-not-for-deployment"

        def request(path, body=None, extra=None):
            """Read the real HTTP boundary without treating an expected refusal as an exception."""
            req = Request(base + path, data=None if body is None else json.dumps(body).encode(), headers={**headers, **(extra or {})})
            try:
                response = urlopen(req, timeout=10)
            except HTTPError as error:
                response = error
            with response:
                return response.status, response.headers, json.load(response)

        try:
            with patch.dict(os.environ, {"SANDBOX_PUBLIC_HOST": "demo.example", "WORKBENCH_ADMIN_TOKEN": token}):
                for path, body in (("/api/workbench/dataset", None), ("/api/workbench/sync", {}),
                                   ("/api/workbench-proxy/api/v1/sandbox/pipeline/uploads", {}), ("/workbench-ui/workbench", None),
                                   ("/workbench-ui", None)):
                    self.assertEqual(request(path, body)[0], 401)
                self.assertEqual(request("/api/workbench/login", {"token": "wrong"})[0], 401)
                self.assertEqual(request("/api/workbench/login", {"token": token}, {"Origin": "http://demo.example"})[0], 403)
                status, response_headers, value = request("/api/workbench/login", {"token": token})
                self.assertEqual((status, value), (200, {"ok": True}))
                cookie = response_headers["Set-Cookie"]
                for flag in ("HttpOnly", "Secure", "SameSite=Strict", "Path=/"):
                    self.assertIn(flag, cookie)
                session = {"Cookie": cookie.split(";")[0]}
                with patch.object(dataset, "preview", return_value={"workbench": {"cohort_rows": 11}}):
                    self.assertEqual(request("/api/workbench/dataset", extra=session)[2], {"workbench": {"cohort_rows": 11}})
                    self.assertEqual(request("/api/workbench/dataset", extra={"Cookie": session["Cookie"] + "x"})[0], 401)
                self.assertEqual(request("/api/workbench/sync", {}, session)[0], 403)
                self.assertEqual(request("/api/workbench-proxy/api/v1/sandbox/pipeline/uploads", {},
                                         {**session, "Origin": "https://evil.example"})[0], 403)
                with patch.dict(os.environ, {"WORKBENCH_ADMIN_TOKEN": token + "rotated"}):
                    self.assertEqual(request("/api/workbench/dataset", extra=session)[0], 401)
                with patch.dict(os.environ, {"WORKBENCH_ADMIN_TOKEN": ""}):
                    self.assertEqual(request("/api/workbench/login", {"token": token})[0], 503)
        finally:
            httpd.shutdown()
            httpd.server_close()
            thread.join()
