"""Shared helpers for the population enrichment generators: read the raw files, order terms, write rows.

Standard library only. Paths default to the starter's raw files, found from this file's location,
so a generator runs the same from any folder.
"""

import csv
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
RAW_DIR = HERE.parent.parent / "pdp-datathon-starter" / "data" / "raw"
COHORT_PATH = RAW_DIR / "pdp_cohort_data.csv"
COURSE_PATH = RAW_DIR / "pdp_course_data.csv"
DATA_DIR = HERE / "data"
SEED = 2026

TERMS = ("FALL", "WINTER", "SPRING", "SUMMER")  # dictionary order within an academic year
_NEXT_MAIN_TERM = {"FALL": "SPRING", "WINTER": "SPRING", "SPRING": "FALL", "SUMMER": "FALL"}


def read_students(cohort_path=COHORT_PATH):
    """One cohort-file row (a dict) per student. A student with two cohort rows keeps the earlier one."""
    students = {}
    with open(cohort_path, newline="", encoding="utf-8-sig") as f:
        for line, row in enumerate(csv.DictReader(f), start=2):
            if not re.fullmatch(r"[0-9]{4}-[0-9]{2}", row["Cohort"]):
                raise ValueError(f"{cohort_path} line {line}: Cohort {row['Cohort']!r} is not a YYYY-YY academic year")
            row["Cohort_Term"] = row["Cohort_Term"].upper()
            guid = row["Student_GUID"]
            if guid not in students or _cohort_key(row) < _cohort_key(students[guid]):
                students[guid] = row
    return students


def _cohort_key(row):
    """Sort key for a cohort row: its cohort year, then its term in academic-year order."""
    return term_key((row["Cohort"], row["Cohort_Term"]))


def term_key(entry):
    """Sort key for (academic_year, term): years in order, then terms in TERMS order, not alphabetical."""
    year, term = entry
    return year, TERMS.index(term) if term in TERMS else len(TERMS)


def read_course_terms(course_path=COURSE_PATH):
    """{student: {(academic_year, term): [(grade, delivery_method), ...]}} for rows with a year and a term."""
    terms = {}
    with open(course_path, newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            year, term = row["Academic_Year"].strip(), row["Academic_Term"].strip().upper()
            if not year or not term:
                continue  # the 456 rows with no year or term belong to no term
            courses = terms.setdefault(row["Student_GUID"], {}).setdefault((year, term), [])
            courses.append((row["Grade"].strip(), row["Delivery_Method"].strip()))
    return terms


def next_academic_year(academic_year):
    """'2021-22' -> '2022-23'."""
    start = int(academic_year[:4]) + 1
    return f"{start}-{str(start + 1)[-2:]}"


def next_main_term(year, term):
    """The next fall or spring term after (year, term): fall -> spring, spring or summer -> next fall."""
    nxt = _NEXT_MAIN_TERM[term]
    return (year, nxt) if nxt == "SPRING" else (next_academic_year(year), nxt)


def enrolled_next_term(student_terms, year, term, last_term):
    """True if the student has course rows after (year, term), up to the next main term; None if the data ends first."""
    target = next_main_term(year, term)
    if term_key(target) > term_key(last_term):
        return None  # the next main term is past the end of the course file, so it can't be seen
    now = term_key((year, term))
    return any(now < term_key(t) <= term_key(target) for t in student_terms)


def last_term_in(course_terms):
    """The latest (academic_year, term) any student has course rows in."""
    return max((t for terms in course_terms.values() for t in terms), key=term_key)


def write_rows(rows, output_path, columns):
    """Write rows (dicts) to a CSV with the given columns, creating the folder."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)
