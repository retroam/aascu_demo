"""Generate the synthetic LMS activity band enrichment file (one row per student per enrolled term).

Models IU's use of Canvas activity scores for real-time outreach: each term a student is enrolled,
their LMS activity is low, medium or high.

Every effect below is PLANTED by this script. None is a finding about real students.

Terms: only terms in which the student has course-file rows (Academic_Year and Academic_Term
non-blank). The band follows that term's D/F/W share: of the student's courses that term with a
gradeable Grade (a number 0-4, P, F, W or UW), the share with a number below 2.0 (D or F), F, W
or UW. I, M, A, O, OTH and blanks don't count either way; with none gradeable the share is unknown.
    score = gauss(0, 1) - dfw_weight * (dfw_share - 0.25)     (default dfw_weight 1.5; unknown share: no shift)
    low if score < low_cut (default -0.6), high if score > high_cut (default 0.6), else medium
So a term with every course D/F/W is far more likely to be low, and a term with none to be high.
Fixed seed: same seed, same file.

Run:
    python population_enrichments/lms_activity_band.py
"""

import argparse
import random

import _common

__all__ = ["generate_lms_activity_band"]

BANDS = ("low", "medium", "high")
_SOURCE = "synthetic: population_enrichments/lms_activity_band.py, seed {seed}, planted effects"
_OUTPUT_COLUMNS = ["Student_GUID", "Academic_Year", "Academic_Term", "LMS_Activity_Band", "Source"]
_DFW_LETTERS = {"F", "W", "UW"}
_CENTER = 0.25  # about the mock data's overall D/F/W share, so the cuts give similar band sizes either way


def generate_lms_activity_band(
    course_path=_common.COURSE_PATH,
    output_path=_common.DATA_DIR / "lms_activity_band.csv",
    dfw_weight=1.5,
    low_cut=-0.6,
    high_cut=0.6,
    seed=_common.SEED,
):
    """Write the LMS activity band file and return its rows."""
    course_terms = _common.read_course_terms(course_path)
    rows = _generate(course_terms, dfw_weight, low_cut, high_cut, seed)
    _common.write_rows(rows, output_path, _OUTPUT_COLUMNS)
    return rows


def is_dfw(grade):
    """True for D/F/W, False for another gradeable grade, None when the grade doesn't count."""
    if grade in _DFW_LETTERS:
        return True
    if grade == "P":
        return False
    try:
        return float(grade) < 2.0
    except ValueError:
        return None  # blank, I, M, A, O, OTH and other codes


def dfw_share(courses):
    """The share of gradeable courses graded D, F or W; None when none is gradeable."""
    flags = [flag for flag in (is_dfw(grade) for grade, _ in courses) if flag is not None]
    return sum(flags) / len(flags) if flags else None


def band_for(score, low_cut, high_cut):
    """low, medium or high for a score."""
    if score < low_cut:
        return "low"
    if score > high_cut:
        return "high"
    return "medium"


def _generate(course_terms, dfw_weight, low_cut, high_cut, seed):
    """All rows, as dicts with _OUTPUT_COLUMNS. Same seed, same rows."""
    rng = random.Random(seed)
    source = _SOURCE.format(seed=seed)
    rows = []
    for guid in sorted(course_terms):
        for year, term in sorted(course_terms[guid], key=_common.term_key):
            share = dfw_share(course_terms[guid][(year, term)])
            shift = 0.0 if share is None else -dfw_weight * (share - _CENTER)
            score = rng.gauss(0, 1) + shift
            rows.append({"Student_GUID": guid, "Academic_Year": year, "Academic_Term": term,
                         "LMS_Activity_Band": band_for(score, low_cut, high_cut), "Source": source})
    return rows


def _main(argv=None):
    """Command line: python lms_activity_band.py [--dfw-weight 1.5 ...]."""
    parser = argparse.ArgumentParser(description="Generate the synthetic LMS activity band enrichment file.")
    parser.add_argument("--course", default=str(_common.COURSE_PATH), help="course Analysis-Ready File")
    parser.add_argument("--output", default=str(_common.DATA_DIR / "lms_activity_band.csv"))
    parser.add_argument("--dfw-weight", type=float, default=1.5, help="how strongly D/F/W share lowers the band")
    parser.add_argument("--low-cut", type=float, default=-0.6, help="scores below this are low")
    parser.add_argument("--high-cut", type=float, default=0.6, help="scores above this are high")
    parser.add_argument("--seed", type=int, default=_common.SEED)
    args = parser.parse_args(argv)

    rows = generate_lms_activity_band(args.course, args.output, args.dfw_weight, args.low_cut, args.high_cut, args.seed)
    print(f"{len(rows)} student-terms written to {args.output}")


if __name__ == "__main__":
    _main()
