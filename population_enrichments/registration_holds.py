"""Generate the synthetic registration holds enrichment file (rows per student, term and hold type).

Generalizes the draft in pdp-datathon-starter/normalized-data-model/sources/registration_holds/
to every student. A hold is a flag the SIS places that blocks registration until it's resolved.

Every effect below is PLANTED by this script. None is a finding about real students.

Terms: only terms in which the student has course-file rows (Academic_Year and Academic_Term
non-blank). In each such term, each hold type is drawn on its own, so a student can have more
than one type in a term. The chance of a hold type in a term is
    base_rate[type]
    x pell_factor          (financial only, when Pell_Status_First_Year = Y; default 2.0)
    x not_enrolled_factor  (every type, when the student has no course rows after this term up to
                            the next fall or spring term; default 1.6)
Base rates: financial 0.06, advising 0.05, sap 0.03, immunization 0.015, disciplinary 0.005.
When the next fall or spring term is past the end of the course file (the last term at least
100 students are enrolled in), next-term enrollment can't be seen and not_enrolled_factor isn't
applied.

The extra columns are made up with no planted effect: Hold_Status (resolved, waived or active;
holds in the course file's last academic year are active half the time), Placed_Date (in the
first 90 days of the term), Resolved_Date (1-60 days later, blank when active). Dates are YYYYMMDD.
Fixed seed: same seed, same file.

Run:
    python population_enrichments/registration_holds.py
"""

import argparse
import datetime
import random

import _common

__all__ = ["generate_registration_holds"]

HOLD_TYPES = ("financial", "advising", "immunization", "disciplinary", "sap")
BASE_RATES = {"financial": 0.06, "advising": 0.05, "immunization": 0.015, "disciplinary": 0.005, "sap": 0.03}
_SOURCE = "synthetic: population_enrichments/registration_holds.py, seed {seed}, planted effects"
_OUTPUT_COLUMNS = ["Student_GUID", "Academic_Year", "Academic_Term", "Hold_Type", "Hold_Status",
                   "Placed_Date", "Resolved_Date", "Source"]
_TERM_START = {"FALL": (0, 8, 25), "WINTER": (1, 1, 3), "SPRING": (1, 1, 20), "SUMMER": (1, 5, 27)}  # (years after the academic year's start, month, day)
_MIN_STUDENTS_IN_LAST_TERM = 100


def generate_registration_holds(
    cohort_path=_common.COHORT_PATH,
    course_path=_common.COURSE_PATH,
    output_path=_common.DATA_DIR / "registration_holds.csv",
    pell_factor=2.0,
    not_enrolled_factor=1.6,
    seed=_common.SEED,
):
    """Write the registration holds file and return its rows."""
    students = _common.read_students(cohort_path)
    course_terms = _common.read_course_terms(course_path)
    rows = _generate(students, course_terms, pell_factor, not_enrolled_factor, seed)
    _common.write_rows(rows, output_path, _OUTPUT_COLUMNS)
    return rows


def last_observed_term(course_terms, min_students=_MIN_STUDENTS_IN_LAST_TERM):
    """The latest term at least min_students have course rows in; a few stray later rows don't count."""
    counts = {}
    for terms in course_terms.values():
        for term in terms:
            counts[term] = counts.get(term, 0) + 1
    busy = [term for term, n in counts.items() if n >= min_students] or list(counts)
    return max(busy, key=_common.term_key)


def hold_chance(hold_type, pell, enrolled_next, pell_factor, not_enrolled_factor):
    """The chance of one hold type in one term, with the planted effects."""
    chance = BASE_RATES[hold_type]
    if hold_type == "financial" and pell == "Y":
        chance *= pell_factor
    if enrolled_next is False:
        chance *= not_enrolled_factor
    return min(chance, 1.0)


def _term_start(year, term):
    """A made-up first day for (academic_year, term)."""
    offset, month, day = _TERM_START[term]
    return datetime.date(int(year[:4]) + offset, month, day)


def _status_and_dates(year, term, final_year, rng):
    """Made-up hold_status, placed_date and resolved_date for one hold."""
    placed = _term_start(year, term) + datetime.timedelta(days=rng.randrange(90))
    if year >= final_year:
        status = "active" if rng.random() < 0.5 else "resolved"
    else:
        status = rng.choices(["resolved", "waived", "active"], weights=[0.85, 0.10, 0.05])[0]
    resolved = "" if status == "active" else (placed + datetime.timedelta(days=rng.randint(1, 60))).strftime("%Y%m%d")
    return status, placed.strftime("%Y%m%d"), resolved


def _generate(students, course_terms, pell_factor, not_enrolled_factor, seed):
    """All hold rows, as dicts with _OUTPUT_COLUMNS. Same seed, same rows."""
    rng = random.Random(seed)
    last_term = last_observed_term(course_terms)
    source = _SOURCE.format(seed=seed)
    rows = []
    for guid in sorted(course_terms):
        pell = students[guid]["Pell_Status_First_Year"] if guid in students else ""
        terms = course_terms[guid]
        for year, term in sorted(terms, key=_common.term_key):
            enrolled_next = _common.enrolled_next_term(terms, year, term, last_term)
            for hold_type in HOLD_TYPES:
                if rng.random() >= hold_chance(hold_type, pell, enrolled_next, pell_factor, not_enrolled_factor):
                    continue
                status, placed, resolved = _status_and_dates(year, term, last_term[0], rng)
                rows.append({"Student_GUID": guid, "Academic_Year": year, "Academic_Term": term,
                             "Hold_Type": hold_type, "Hold_Status": status, "Placed_Date": placed,
                             "Resolved_Date": resolved, "Source": source})
    return rows


def _main(argv=None):
    """Command line: python registration_holds.py [--pell-factor 2.0 ...]."""
    parser = argparse.ArgumentParser(description="Generate the synthetic registration holds enrichment file.")
    parser.add_argument("--cohort", default=str(_common.COHORT_PATH), help="cohort Analysis-Ready File")
    parser.add_argument("--course", default=str(_common.COURSE_PATH), help="course Analysis-Ready File")
    parser.add_argument("--output", default=str(_common.DATA_DIR / "registration_holds.csv"))
    parser.add_argument("--pell-factor", type=float, default=2.0, help="financial-hold multiplier for Pell = Y")
    parser.add_argument("--not-enrolled-factor", type=float, default=1.6,
                        help="hold multiplier in a term with no enrollment by the next fall or spring")
    parser.add_argument("--seed", type=int, default=_common.SEED)
    args = parser.parse_args(argv)

    rows = generate_registration_holds(args.cohort, args.course, args.output, args.pell_factor,
                                       args.not_enrolled_factor, args.seed)
    students = len({row["Student_GUID"] for row in rows})
    print(f"{len(rows)} holds for {students} students written to {args.output}")


if __name__ == "__main__":
    _main()
