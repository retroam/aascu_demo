"""Coordinate verified, local Workbench snapshots and dashboard dataset generations."""
from contextlib import contextmanager, closing
from functools import wraps
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import tempfile
import threading
import time
from urllib.parse import unquote, urlsplit
from urllib.request import urlopen

import foundations

WORKBENCH = Path(__file__).resolve().parents[1] / ".data/workbench/pdp.sqlite"
CONDITION = threading.Condition()
SYNC = threading.Lock()
_readers = 0
_writing = False


class SyncError(ValueError):
    """A refused sync with an actionable HTTP status."""
    def __init__(self, message, status=409):
        super().__init__(message)
        self.status = status


@contextmanager
def reading():
    """Keep every query in an HTTP response on one dataset generation."""
    global _readers
    with CONDITION:
        CONDITION.wait_for(lambda: not _writing)
        _readers += 1
    try:
        yield
    finally:
        with CONDITION:
            _readers -= 1
            CONDITION.notify_all()


@contextmanager
def writing(timeout=20):
    """Wait for existing analyses and prevent new readers during a replacement."""
    global _writing
    with CONDITION:
        _writing = True
        if not CONDITION.wait_for(lambda: _readers == 0, timeout):
            _writing = False
            CONDITION.notify_all()
            raise SyncError("Analyses are still running. Wait for them to finish, then retry sync.")
    try:
        yield
    finally:
        with CONDITION:
            _writing = False
            CONDITION.notify_all()


def guard_request(method):
    """Guard data requests, leaving sync and Workbench probes outside the read lock."""
    @wraps(method)
    def guarded(handler):
        """Version each response and refuse requests carrying an obsolete browser context."""
        handler.dataset_generation = None
        path = unquote(urlsplit(handler.path).path)
        if path.startswith("/api/") and not path.startswith("/api/workbench"):
            with reading():
                value = identity()
                handler.dataset_generation = f"{value['origin']}:{value['run_id']}"
                expected = handler.headers.get("X-PDP-Dataset")
                if expected and expected != handler.dataset_generation:
                    return handler._json({"error": "The dataset changed. Reload the workspace."}, 409)
                return method(handler)
        return method(handler)
    return guarded


def describe(path):
    """Read one committed load's identity, counts, cohorts, and sanitized provenance."""
    if not path.exists():
        return {"available": False}
    with closing(sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True, timeout=2)) as db:
        db.row_factory = sqlite3.Row
        db.execute("BEGIN")
        tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if "load_run" not in tables:
            return {"available": False}
        runs = db.execute("SELECT run_id, finished_at FROM load_run").fetchall()
        if len(runs) != 1 or not runs[0]["finished_at"]:
            raise SyncError("The dataset does not contain one completed load.", 422)
        sources = [{"file": Path(r["source_file"]).name, "rows": r["row_count"], "sha256": r["file_sha256"]}
                   for r in db.execute("SELECT * FROM data_provider ORDER BY provider_id")]
        result = {"available": True, **dict(runs[0]), "origin": "starter", "sources": sources,
                  "cohorts": [r[0] for r in db.execute("SELECT DISTINCT cohort FROM cohort_membership ORDER BY cohort")],
                  "students": db.execute("SELECT COUNT(*) FROM student").fetchone()[0],
                  "cohort_rows": db.execute("SELECT COUNT(*) FROM cohort_membership").fetchone()[0],
                  "course_rows": db.execute("SELECT COUNT(*) FROM course_enrollment").fetchone()[0]}
        if "demo_dataset" in tables:
            result.update(dict(db.execute("SELECT origin, synced_at FROM demo_dataset").fetchone()))
        return result


def identity():
    """Identify the dashboard's current committed dataset."""
    return describe(foundations.DATABASE)


def workbench_status():
    """Require the isolated API to report whether its loader is active."""
    try:
        with urlopen("http://127.0.0.1:8100/health", timeout=2) as response:
            value = json.load(response)
        if value.get("service") != "demo-workbench":
            raise ValueError("Wrong service")
        return value
    except (OSError, ValueError) as exc:
        raise SyncError("Workbench is unavailable. Restart the main app and check its service logs.", 503) from exc


def preview():
    """Show exactly which completed Workbench load would replace the dashboard."""
    status = workbench_status()
    with reading():
        current = identity()
    return {"current": current, "workbench": describe(WORKBENCH), "busy": bool(status.get("active_run"))}


def invalidate():
    """Clear all process-local values derived from dashboard records."""
    import analytics
    import modeling
    import sql_guard
    import llm_chat
    for function in (foundations.cohort_frame, foundations.documentation, analytics.load_data,
                     analytics.provenance, analytics.cohorts, modeling._raw_data,
                     modeling._model_bundle, modeling._association_cached, sql_guard._metadata):
        function.cache_clear()
    for cache in (sql_guard.RESULT_CACHE, llm_chat.RESPONSE_CACHE, llm_chat.PLAN_CACHE, llm_chat.SEMANTICS_CACHE):
        cache.clear()


def sync(workbench_run_id, current_run_id):
    """Validate and atomically replace all dashboard tables, restoring the old file on failure."""
    if not SYNC.acquire(blocking=False):
        raise SyncError("Another sync is already running.")
    staged = None
    try:
        if workbench_status().get("active_run"):
            raise SyncError("Workbench is loading. Wait for it to finish, then refresh the preview.")
        target = foundations.DATABASE
        fd, name = tempfile.mkstemp(prefix="pdp-sync-", suffix=".sqlite", dir=target.parent)
        os.close(fd)
        staged = Path(name)
        deadline = time.monotonic() + 10

        def progress(_status, _remaining, _total):
            """Bound SQLite backup retries when another process holds a write lock."""
            if time.monotonic() > deadline:
                raise SyncError("Workbench database is busy. Retry after the load finishes.")

        with closing(sqlite3.connect(f"{WORKBENCH.resolve().as_uri()}?mode=ro", uri=True, timeout=2)) as source:
            with closing(sqlite3.connect(staged)) as copy:
                source.backup(copy, pages=256, progress=progress, sleep=.05)
                if copy.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                    raise SyncError("Workbench database integrity check failed.", 422)
                for table, columns in foundations.model_metadata().schema.items():
                    actual = {r[1] for r in copy.execute(f'PRAGMA table_info("{table}")')}
                    if not set(columns).issubset(actual):
                        raise SyncError(f"Workbench is missing required columns in {table}.", 422)
                if copy.execute("PRAGMA foreign_key_check").fetchone():
                    raise SyncError("Workbench contains broken table relationships.", 422)
        info = describe(staged)
        if not info["available"] or info["run_id"] != workbench_run_id:
            raise SyncError("Workbench data changed. Close this confirmation and preview it again.")
        if not info["cohort_rows"] or not info["students"] or len(info["sources"]) < 2:
            raise SyncError("Load a nonempty cohort and course dataset before syncing.", 422)
        if any(not re.fullmatch(r"[0-9]{4}-[0-9]{2}", year) for year in info["cohorts"]):
            raise SyncError("Every cohort must use the YYYY-YY format.", 422)
        with closing(sqlite3.connect(staged)) as copy:
            copy.execute("DROP TABLE IF EXISTS demo_dataset")
            copy.execute("CREATE TABLE demo_dataset(origin TEXT, synced_at TEXT)")
            copy.execute("INSERT INTO demo_dataset VALUES ('workbench', strftime('%Y-%m-%dT%H:%M:%SZ','now'))")
            copy.commit()
        with writing():
            if identity().get("run_id") != current_run_id:
                raise SyncError("Dashboard data changed. Close this confirmation and preview it again.")
            if workbench_status().get("active_run"):
                raise SyncError("Workbench started another load. Wait for it to finish.")
            backup = target.with_name("pdp.previous.sqlite")
            shutil.copy2(target, backup)
            with staged.open("rb") as stream:
                os.fsync(stream.fileno())
            os.replace(staged, target)
            try:
                invalidate()
                import analytics
                analytics.get_dashboard()
                analytics.get_shared_measures()
            except Exception:
                os.replace(backup, target)
                invalidate()
                raise SyncError("The new data could not be analyzed. The previous dashboard was restored.", 422)
            return identity()
    except sqlite3.Error as exc:
        raise SyncError("Workbench database is unavailable or incompatible. Finish a valid load, then retry.", 422) from exc
    finally:
        if staged is not None:
            staged.unlink(missing_ok=True)
        SYNC.release()
