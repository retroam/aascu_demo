"""Bounded process-local JSON caches. No prompts, credentials or results written to disk."""
from collections import OrderedDict
import hashlib
import json
from pathlib import Path
import threading
import time


def key(*parts):
    return hashlib.sha256(json.dumps(parts, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def file_revision(path):
    path = Path(path)
    try:
        st = path.stat()
        return [str(path.resolve()), st.st_ino, st.st_size, st.st_mtime_ns, st.st_ctime_ns]
    except FileNotFoundError:
        return [str(path), None]


def data_revision(database=None):
    import foundations
    db = foundations.DATABASE if database is None else database
    return [file_revision(db), file_revision(str(db) + '-wal')]


def definition_revision():
    import foundations
    config = foundations.MODEL / "config"
    calculations = foundations.STARTER / "measures/calculations"
    return [file_revision(config / name) for name in
            ("destination_schema.yaml", "column_dictionary.yaml", "cohort_mapping.yaml")] + [
            file_revision(path) for path in sorted(calculations.glob("*.py"))]


class TTLCache:
    def __init__(self, capacity=128, ttl=300, max_bytes=8_000_000):
        self.capacity, self.ttl, self.max_bytes = capacity, ttl, max_bytes
        self.items = OrderedDict()
        self.size = 0
        self.lock = threading.Lock()

    def get(self, cache_key):
        with self.lock:
            entry = self.items.get(cache_key)
            if entry is None:
                return None
            until, blob = entry
            if time.monotonic() >= until:
                self.items.pop(cache_key)
                self.size -= len(blob)
                return None
            self.items.move_to_end(cache_key)
            return json.loads(blob)

    def put(self, cache_key, value):
        blob = json.dumps(value, allow_nan=False).encode()
        if len(blob) > self.max_bytes:
            return
        with self.lock:
            old = self.items.pop(cache_key, None)
            if old:
                self.size -= len(old[1])
            self.items[cache_key] = (time.monotonic() + self.ttl, blob)
            self.size += len(blob)
            while len(self.items) > self.capacity or self.size > self.max_bytes:
                _, (_, evicted) = self.items.popitem(last=False)
                self.size -= len(evicted)

    def clear(self):
        with self.lock:
            self.items.clear()
            self.size = 0
