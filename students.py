"""Read-only individual records for the explicitly synthetic local demonstration.

This bounded interface leaves the aggregate assistant's identifier guard intact.
Records are historical observations, not live alerts or model-derived risk scores.
"""
from __future__ import annotations

import math
import re
import sqlite3

import analytics
import foundations

NOTICE = ("Synthetic student records only. Historical observations are not live alerts. "
          "Verify current circumstances before planning support; no intervention or contact history is supplied.")
REVIEW_OPTIONS = {"all", "low-credits", "gateway-math", "gateway-english", "low-gpa"}
ENTRY_TYPES = {"all": None, "transfer": "Transfer-In", "first-time": "First-Time", "readmit": "Re-admit", "continuing": "Continuing"}
MAX_COURSES = 250


def _integer(value, name, minimum, maximum):
    if isinstance(value, bool) or not re.fullmatch(r"[0-9]+", str(value)):
        raise ValueError(f"{name} must be a whole number.")
    value = int(value)
    if not minimum <= value <= maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}.")
    return value


def _identifier(value, *, prefix=False):
    """Validate an ID without changing the case preserved by the shared loader."""
    pattern = r"[A-Fa-f0-9]{1,32}" if prefix else r"[A-Fa-f0-9]{32}"
    if not isinstance(value, str) or not re.fullmatch(pattern, value):
        raise ValueError("Use a synthetic student ID" + (" or its hexadecimal prefix." if prefix else " of 32 hexadecimal characters."))
    return value


def _number(value, maximum=None):
    try:
        n = float(value)
    except (ValueError, TypeError):
        return None
    return n if math.isfinite(n) and n >= 0 and (maximum is None or n <= maximum) else None


def _outcome(value):
    return bool(value) if value in (0, 1) and value is not None else None


def _gateway(row, subject):
    requirement = row[f"gateway_{subject}_status"]
    completion = row[f"completed_gateway_{subject}_year1"]
    if requirement == "N":
        return "Not required"
    if completion in ("C", "D"):
        return "Completed" if completion == "C" else "Not completed"
    return "Unknown"


def _summary(row, threshold):
    earned = _number(row["number_of_credits_earned_yr_1"])
    gpa = _number(row["gpa_group_term_1"], 4)
    math_status, english_status = _gateway(row, "math"), _gateway(row, "english")
    reasons = []
    if earned is not None and earned < threshold:
        reasons.append({"id": "low-credits", "label": f"Year-one earned credits below {threshold}"})
    if math_status == "Not completed" and row["gateway_math_status"] == "R":
        reasons.append({"id": "gateway-math", "label": "Required gateway math not completed in year one"})
    if english_status == "Not completed" and row["gateway_english_status"] == "R":
        reasons.append({"id": "gateway-english", "label": "Required gateway English not completed in year one"})
    if gpa is not None and gpa < 2:
        reasons.append({"id": "low-gpa", "label": "First-term GPA below 2.0"})
    return {"student_id": row["student_id"], "cohort": row["cohort"],
            "enrollment_intensity": row["enrollment_intensity_first_term"],
            "enrollment_type": row["enrollment_type"],
            "credits_attempted": _number(row["number_of_credits_attempted_yr_1"]),
            "credits_earned": earned, "gpa": gpa,
            "retention": _outcome(row["retention"]), "persistence": _outcome(row["persistence"]),
            "gateway_math": math_status, "gateway_english": english_status,
            "gateway_math_requirement": {"R": "Required", "N": "Not required"}.get(row["gateway_math_status"], "Unknown"),
            "gateway_english_requirement": {"R": "Required", "N": "Not required"}.get(row["gateway_english_status"], "Unknown"),
            "review_reasons": reasons}


def _freshness(db):
    row = db.execute("SELECT finished_at FROM load_run ORDER BY finished_at DESC LIMIT 1").fetchone()
    return {"extracted_at": None, "normalized_loaded_at": row[0] if row else None,
            "detail": "Source extraction date and follow-up completeness are unavailable. Normalization time is not data freshness."}


def _query(query, extra):
    if query is None:
        query = {}
    if not isinstance(query, dict):
        raise ValueError("Query must be an object.")
    if set(query) - {"cohort", "population", "threshold", "entry_type", *extra}:
        raise ValueError("Unsupported student query parameter.")
    filters = analytics.normalize_filters({k: v for k, v in query.items() if k in ("cohort", "population", "threshold")})
    return dict(query), filters


def _scope(query, filters):
    entry_type = query.get("entry_type", "all")
    if not isinstance(entry_type, str) or entry_type not in ENTRY_TYPES:
        raise ValueError("Choose an available entry type.")
    frame = analytics.filter_data(filters)
    if entry_type != "all":
        frame = frame.loc[frame.Enrollment_Type.eq(ENTRY_TYPES[entry_type])]
    return frame, entry_type


def get_students(query=None):
    """Return a deterministic page at student × entry-cohort grain."""
    query, filters = _query(query, {"page", "page_size", "search", "review"})
    page = _integer(query.get("page", 1), "Page", 1, 100000)
    page_size = _integer(query.get("page_size", 25), "Page size", 1, 50)
    search = query.get("search", "")
    if search:
        search = _identifier(search, prefix=True)
    elif not isinstance(search, str):
        raise ValueError("Search must be a synthetic ID prefix.")
    review = query.get("review", "all")
    if not isinstance(review, str) or review not in REVIEW_OPTIONS:
        raise ValueError("Choose an available historical observation filter.")
    frame, entry_type = _scope(query, filters)
    with foundations.scoped_connection(frame) as db:
        db.row_factory = sqlite3.Row
        rows = db.execute("SELECT * FROM cohort_membership WHERE substr(student_id, 1, ?) = ? COLLATE NOCASE "
                          "ORDER BY cohort DESC, student_id", (len(search), search)).fetchall()
        summaries = [_summary(row, filters["threshold"]) for row in rows]
        if review != "all":
            summaries = [row for row in summaries if any(r["id"] == review for r in row["review_reasons"])]
        total = len(summaries)
        start = (page - 1) * page_size
        return {"filters": filters, "entry_type": entry_type, "page": page, "page_size": page_size,
                "search": search, "review": review, "total": total,
                "total_pages": math.ceil(total / page_size), "rows": summaries[start:start + page_size],
                "grain": "student × entry cohort", "synthetic": True, "notice": NOTICE,
                "freshness": _freshness(db)}


def get_student(query=None):
    """Return only cohort and course history allowed by the selected UI scope."""
    query, filters = _query(query, {"id"})
    student_id = _identifier(query.get("id"))
    frame, entry_type = _scope(query, filters)
    # Preserve exact IDs; case-insensitive convenience must never merge distinct students.
    if not frame.Student_GUID.eq(student_id).any():
        all_ids = analytics.load_data().Student_GUID
        matches = all_ids.loc[all_ids.str.casefold().eq(student_id.casefold())].unique()
        if len(matches) == 1:
            student_id = matches[0]
    frame = frame.loc[frame.Student_GUID.eq(student_id)]
    if frame.empty:
        raise LookupError("Student not found in the selected cohort and population. Broaden the filters to view other cohort records.")
    with foundations.scoped_connection(frame) as db:
        db.row_factory = sqlite3.Row
        records = db.execute("SELECT * FROM cohort_membership WHERE student_id = ? ORDER BY cohort", (student_id,)).fetchall()
        cohorts = []
        for row in records:
            summary = _summary(row, filters["threshold"])
            summary["credit_history"] = [{"year": year,
                                          "attempted": _number(row[f"number_of_credits_attempted_yr_{year}"]),
                                          "earned": _number(row[f"number_of_credits_earned_yr_{year}"])}
                                         for year in range(1, 5)]
            cohorts.append(summary)
        course_from = (" FROM course_enrollment ce JOIN selected s ON ce.student_id = s.student_id AND ce.cohort = s.cohort "
                       "JOIN term t ON t.term_id = ce.term_id ")
        count = db.execute("SELECT COUNT(*)" + course_from).fetchone()[0]
        course_rows = db.execute("SELECT ce.*, t.academic_year, t.academic_term" + course_from +
                                 " ORDER BY ce.cohort, t.sort_order, ce.course_begin_date, ce.enrollment_id LIMIT ?", (MAX_COURSES,)).fetchall()
        courses = [{"cohort": row["cohort"], "term": ("Term unavailable" if row["academic_year"] == "UNKNOWN" else f'{row["academic_year"]} {row["academic_term"].title()}'),
                    "course_name": row["course_name"] or "Course name unavailable", "grade": row["grade"],
                    "credits_attempted": _number(row["number_of_credits_attempted"]),
                    "credits_earned": _number(row["number_of_credits_earned"]),
                    "begin_date": row["course_begin_date"], "end_date": row["course_end_date"],
                    "gateway": row["math_or_english_gateway"]} for row in course_rows]
        return {"student_id": student_id, "filters": filters, "entry_type": entry_type, "cohorts": cohorts, "courses": courses,
                "course_count": count, "courses_truncated": count > MAX_COURSES,
                "history_scope": "Only entry-cohort records matching the selected cohort and population are shown. Course history is joined on student ID and entry cohort.",
                "synthetic": True, "notice": NOTICE, "freshness": _freshness(db)}
