"""Read-only integration with the starter's normalized model and shared measures."""
from contextlib import closing, contextmanager
from dataclasses import asdict
from functools import lru_cache
from pathlib import Path
import csv
import hashlib
import os
import sqlite3
import sys

import pandas as pd
import yaml

STARTER = Path(__file__).resolve().parents[1] / "pdp-datathon-starter"
MODEL = STARTER / "normalized-data-model"
DATABASE = Path(os.environ.get("PDP_DEMO_DATABASE", str(Path(__file__).resolve().parent / ".data/pdp.sqlite"))).resolve()
sys.path.insert(0, str(STARTER))
sys.path.insert(0, str(MODEL))
sys.path.insert(0, str(STARTER / "mcp"))

from pdp_model import column_dictionary, schema_field
from pdp_mcp.metadata import Metadata
from measures.models import Cohort, Measure, EVERYONE
from measures.run_measures import run_measure
from measures.calculations import dfw
from gap_finder.find_gaps import find_gaps

MIN_CELL = 20


@contextmanager
def connection():
    """Open the demo's generated database without permission to change it."""
    if not DATABASE.exists():
        raise RuntimeError("Run ../.venv/bin/python prepare_data.py in demo first.")
    db = sqlite3.connect(f"{DATABASE.as_uri()}?mode=ro", uri=True)
    try:
        yield db
    finally:
        db.close()


@lru_cache(maxsize=1)
def mappings():
    """Read the source-to-model names from the shared mapping contract."""
    with (MODEL / "config/cohort_mapping.yaml").open() as stream:
        return yaml.safe_load(stream)


@lru_cache(maxsize=1)
def cohort_frame():
    """Project normalized records into the demo's existing analytical column names."""
    fields = []
    seen = set()
    for entry in mappings():
        if "source" not in entry or entry.get("destination_table") not in ("student", "cohort_membership"):
            continue
        if entry["source"] in seen:
            continue
        seen.add(entry["source"])
        alias = "s" if entry["destination_table"] == "student" else "cm"
        fields.append(f'{alias}."{entry["destination_column"]}" AS "{entry["source"]}"')
    with connection() as db:
        frame = pd.read_sql_query("SELECT " + ", ".join(fields) +
            " FROM cohort_membership cm JOIN student s USING(student_id) ORDER BY cm.cohort, cm.student_id", db)
    for name in frame:
        frame[name] = frame[name].map(lambda value: "" if pd.isna(value) else str(value))
    for name in ("Retention", "Persistence"):
        frame[name] = frame[name].replace({"1.0": "1", "0.0": "0"})
    for name in ("Enrollment_Intensity_First_Term", "Enrollment_Type"):
        frame[name] = frame[name].replace({"UNKNOWN": "Unknown"})
    for name in ("Math_Placement", "English_Placement"):
        frame[name] = frame[name].replace({"UNKNOWN": "UK"})
    return frame


def measure(frame, name):
    """Run shared cohort measures on the exact selected records, including test fixtures."""
    # A small in-memory projection lets the existing planner retain intersections without
    # translating them into a second filter language or changing the shared library.
    cm = pd.DataFrame(index=frame.index)
    student = pd.DataFrame(index=frame.index)
    for entry in mappings():
        table = entry.get("destination_table")
        if table not in ("student", "cohort_membership") or "source" not in entry:
            continue
        target = student if table == "student" else cm
        values = frame.get(entry["source"], pd.Series("", index=frame.index))
        if entry["destination_column"] in ("retention", "persistence"):
            values = values.map({"1": 1, "0": 0})
        elif entry["source"].startswith("Number_of_Credits_"):
            values = pd.to_numeric(values, errors="coerce")
        target[entry["destination_column"]] = values.replace({"": None})
    # A cohort record is the unit of analysis, even when a student enters twice.
    cm["student_id"] = range(len(frame))
    student["student_id"] = range(len(frame))
    if "Cohort" not in frame:
        cm["cohort"] = "fixture"
    years = sorted(cm["cohort"].dropna().unique()) or ["empty"]
    with closing(sqlite3.connect(":memory:")) as db:
        cm.to_sql("cohort_membership", db, index=False)
        student.to_sql("student", db, index=False)
        db.execute("CREATE TABLE data_provider(provider_id, source_file, file_sha256, loaded_at)")
        result = run_measure(Measure(name), [Cohort.of(*years)], database=db)[0]
    return result


def additional_measures(frame, years):
    """Expose the remaining shared measures without treating ratios as binary outcomes."""
    cohort = Cohort.of(*years)
    labels = {"gateway_english": "Gateway English completion", "credit_completion": "Credit completion ratio", "dfw_rate": "D, F or withdrawal rate"}
    rows = []
    with scoped_connection(frame) as db:
        for name, label in labels.items():
            result = run_measure(Measure(name), [cohort], database=db)[0]
            students = dfw.count(db, [cohort], [EVERYONE])[(cohort, EVERYONE)].n_students if name == "dfw_rate" else result.denominator
            hidden = result.suppressed or (students or 0) < MIN_CELL
            rows.append({"id": name, "label": label, "value": None if hidden else round(100 * result.numerator / result.denominator, 2),
                         "numerator": None if hidden else result.numerator, "denominator": None if hidden else result.denominator,
                         "missing": None if hidden else result.n_excluded, "definition": result.note,
                         "status": result.status.value if result.suppressed else "suppressed" if hidden else "ok",
                         "unit": "course enrollments" if name == "dfw_rate" else "student-cohort records"})
    return rows


@contextmanager
def scoped_connection(frame):
    """Restrict shared queries to selected student-cohort keys using a temporary view."""
    with connection() as db:
        db.execute("CREATE TEMP TABLE selected(student_id TEXT, cohort TEXT, PRIMARY KEY(student_id, cohort))")
        db.executemany("INSERT INTO selected VALUES (?, ?)", frame[["Student_GUID", "Cohort"]].itertuples(index=False, name=None))
        db.execute("CREATE TEMP VIEW cohort_membership AS SELECT cm.* FROM main.cohort_membership cm JOIN selected s USING(student_id, cohort)")
        yield db


def equity_gaps(frame, years, measure_name="retention", dimensions=("race",)):
    """Use the gap finder and apply the demo's stricter display suppression to both sides."""
    with scoped_connection(frame) as db:
        rows = find_gaps([measure_name], [years], [list(dimensions)], database=db)
    results = []
    for row in rows:
        item = asdict(row)
        if row.suppressed or (row.denominator or 0) < MIN_CELL or (
            row.comparison_denominator is not None and row.comparison_denominator < MIN_CELL
        ):
            for key, value in item.items():
                if isinstance(value, (int, float)) or key == "likely_noise":
                    item[key] = None
            item.update(status="suppressed", suppressed=True)
        results.append(item)
    return results


@lru_cache(maxsize=1)
def model_metadata():
    """Reuse the starter's definition-only metadata reader, without an MCP server."""
    return Metadata(STARTER)


@lru_cache(maxsize=1)
def normalized_model():
    """Expose the schema behind the shared ER diagram and its exact source fingerprints."""
    metadata = model_metadata()
    problem, sources = metadata.status()
    if problem:
        raise RuntimeError(problem)
    diagram = MODEL / "normalized-data-model.mmd"
    return {"tables": {table["name"]: metadata.describe(table["name"]) for table in metadata.tables()},
            "sources": sources,
            "diagram": {"path": "normalized-data-model/normalized-data-model.mmd",
                        "sha256": hashlib.sha256(diagram.read_bytes()).hexdigest()},
            "contract": "destination_schema.yaml is authoritative; normalized-data-model.mmd is its tested ER diagram. Tables listed here are definitions, not SQL permissions. Use only the approved scoped views for queries."}


@lru_cache(maxsize=1)
def documentation():
    """Return shared dictionary entries and the dataset-wide quality issue inventory."""
    dictionary = {(entry["table"], entry["column"]): entry for entry in column_dictionary()}
    entries = []
    metadata = model_metadata()
    for table, columns in metadata.schema.items():
        for column in columns:
            definition = metadata.normalized_column(table, column)
            entry = dictionary.get((table, column), {"table": table, "column": column,
                "description": definition["description"] or f"{column} in {table}; see the table keys and stored rules.",
                "sources": definition["sources"], "dictionary_values": []})
            entries.append({**entry, "stored": schema_field(table, column), "rules": definition["rules"]})
    with (STARTER / "data/quality/findings.csv").open(newline="", encoding="utf-8-sig") as stream:
        findings = list(csv.DictReader(stream))
    with connection() as db:
        db.row_factory = sqlite3.Row
        run = dict(db.execute("SELECT * FROM load_run LIMIT 1").fetchone())
        uploaded = db.execute("SELECT 1 FROM sqlite_master WHERE name='demo_dataset'").fetchone() is not None
    if uploaded:
        findings = []
    return {"dictionary": entries, "findings": findings, "load": run,
            "model": normalized_model(), "diagram_source": (MODEL / "normalized-data-model.mmd").read_text(),
            "quality_scope": ("This dataset was synced from Workbench. Published starter-file findings do not describe these uploads; review their validation results in Workbench." if uploaded else "Published raw-file findings for the entire dataset, not the selected filters. The normalized loader applies documented corrections; this is not a count of remaining errors."),
            "source": "synthetic"}
