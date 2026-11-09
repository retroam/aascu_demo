"""Generate the synthetic student-athlete enrichment file (one row per student, no term).

Models Adams State's description: 45-50% of undergraduates are athletes in a large Division II
program, athletes retain better, and fall-to-spring retention dipped when a new football coach came.

Every effect below is PLANTED by this script. None is a finding about real students.

Who is an athlete: a logistic model on cohort-file columns, with the intercept solved so the
overall share is exactly `share` (default 0.45):
    logit(p) = b0 + ftft_weight    * [Enrollment_Type = First-Time and Enrollment_Intensity_First_Term = Full-Time]
                  + young_weight   * [Student_Age = 20 and younger]
                  + older_weight   * [Student_Age = Older than 24]
                  + retained_weight * [Retention = 1]
Defaults: ftft 0.6, young 0.5, older -0.8, retained 0.2. Younger, full-time first-time students
retain better in the mock data already, so most of the athletes' retention gap (about 10 points)
comes from that skew; retained_weight adds the rest.

Sport (athletes only): football and wrestling go to Gender = M only. Weights for M are football
0.40, track_and_field 0.24, basketball 0.12, soccer 0.12, wrestling 0.12; for everyone else
soccer 0.30, basketball 0.25, track_and_field 0.25, volleyball 0.20.
Coach change: in `coach_change_cohort` (default 2023-24), football's weight is multiplied by
`coach_change_factor` (default 3.0) for students with Retention = 0, so that cohort's football
players retain worse than other athletes. Retention is the ARF's year-2 measure, the closest the
mock data has to fall-to-spring retention.

Writes is_student_athlete (true/false) for every student and athlete_sport for athletes, one
attribute per row (Attribute_Key, Attribute_Value), so one mapping config loads both keys.
A student in two cohorts is modelled on the earlier cohort row. Fixed seed: same seed, same file.

Run:
    python population_enrichments/student_athlete.py
"""

import argparse
import math
import random

import _common

__all__ = ["generate_student_athlete"]

_SOURCE = "synthetic: population_enrichments/student_athlete.py, seed {seed}, planted effects"
_OUTPUT_COLUMNS = ["Student_GUID", "Attribute_Key", "Attribute_Value", "Source"]
_MALE_SPORTS = {"football": 0.40, "track_and_field": 0.24, "basketball": 0.12, "soccer": 0.12, "wrestling": 0.12}
_OTHER_SPORTS = {"soccer": 0.30, "basketball": 0.25, "track_and_field": 0.25, "volleyball": 0.20}
SPORTS = sorted(set(_MALE_SPORTS) | set(_OTHER_SPORTS))


def generate_student_athlete(
    cohort_path=_common.COHORT_PATH,
    output_path=_common.DATA_DIR / "student_athlete.csv",
    share=0.45,
    ftft_weight=0.6,
    young_weight=0.5,
    older_weight=-0.8,
    retained_weight=0.2,
    coach_change_cohort="2023-24",
    coach_change_factor=3.0,
    seed=_common.SEED,
):
    """Write the student-athlete file and return its rows."""
    students = _common.read_students(cohort_path)
    weights = {"ftft": ftft_weight, "young": young_weight, "older": older_weight, "retained": retained_weight}
    rows = _generate(students, share, weights, coach_change_cohort, coach_change_factor, seed)
    _common.write_rows(rows, output_path, _OUTPUT_COLUMNS)
    return rows


def _score(row, weights):
    """The student's logistic score before the intercept."""
    ftft = row["Enrollment_Type"] == "First-Time" and row["Enrollment_Intensity_First_Term"] == "Full-Time"
    return (weights["ftft"] * ftft
            + weights["young"] * (row["Student_Age"] == "20 and younger")
            + weights["older"] * (row["Student_Age"] == "Older than 24")
            + weights["retained"] * (row["Retention"] == "1"))


def _solve_intercept(scores, share):
    """The intercept that makes the mean probability equal share, by bisection."""
    low, high = -20.0, 20.0
    for _ in range(100):
        mid = (low + high) / 2
        mean = sum(_sigmoid(mid + s) for s in scores) / len(scores)
        low, high = (mid, high) if mean < share else (low, mid)
    return (low + high) / 2


def _sigmoid(x):
    """The logistic function."""
    return 1 / (1 + math.exp(-x))


def _pick_sport(row, coach_change_cohort, coach_change_factor, rng):
    """One sport for an athlete, with the coach-change tilt on football."""
    weights = dict(_MALE_SPORTS if row["Gender"] == "M" else _OTHER_SPORTS)
    if "football" in weights and row["Cohort"] == coach_change_cohort and row["Retention"] == "0":
        weights["football"] *= coach_change_factor
    sports = sorted(weights)
    return rng.choices(sports, weights=[weights[s] for s in sports])[0]


def _generate(students, share, weights, coach_change_cohort, coach_change_factor, seed):
    """All rows, as dicts with _OUTPUT_COLUMNS. Same seed, same rows."""
    rng = random.Random(seed)
    guids = sorted(students)
    scores = [_score(students[g], weights) for g in guids]
    intercept = _solve_intercept(scores, share)
    source = _SOURCE.format(seed=seed)
    rows = []
    for guid, score in zip(guids, scores):
        athlete = rng.random() < _sigmoid(intercept + score)
        sport = _pick_sport(students[guid], coach_change_cohort, coach_change_factor, rng) if athlete else ""
        rows.append(_row(guid, "is_student_athlete", "true" if athlete else "false", source))
        if athlete:
            rows.append(_row(guid, "athlete_sport", sport, source))
    return rows


def _row(guid, key, value, source):
    """One output row. The file is long, one attribute per row, so both keys share one mapping."""
    return {"Student_GUID": guid, "Attribute_Key": key, "Attribute_Value": value, "Source": source}


def _main(argv=None):
    """Command line: python student_athlete.py [--share 0.45 ...]."""
    parser = argparse.ArgumentParser(description="Generate the synthetic student-athlete enrichment file.")
    parser.add_argument("--cohort", default=str(_common.COHORT_PATH), help="cohort Analysis-Ready File")
    parser.add_argument("--output", default=str(_common.DATA_DIR / "student_athlete.csv"))
    parser.add_argument("--share", type=float, default=0.45, help="overall share of students who are athletes")
    parser.add_argument("--ftft-weight", type=float, default=0.6, help="log-odds added for first-time full-time")
    parser.add_argument("--young-weight", type=float, default=0.5, help="log-odds added for 20 and younger")
    parser.add_argument("--older-weight", type=float, default=-0.8, help="log-odds added for older than 24")
    parser.add_argument("--retained-weight", type=float, default=0.2, help="log-odds added for Retention = 1")
    parser.add_argument("--coach-change-cohort", default="2023-24", help="cohort whose football players retain worse")
    parser.add_argument("--coach-change-factor", type=float, default=3.0,
                        help="football weight multiplier for non-retained students in that cohort")
    parser.add_argument("--seed", type=int, default=_common.SEED)
    args = parser.parse_args(argv)

    rows = generate_student_athlete(args.cohort, args.output, args.share, args.ftft_weight, args.young_weight,
                                    args.older_weight, args.retained_weight, args.coach_change_cohort,
                                    args.coach_change_factor, args.seed)
    students = sum(row["Attribute_Key"] == "is_student_athlete" for row in rows)
    athletes = sum(row["Attribute_Value"] == "true" for row in rows)
    print(f"{len(rows)} rows: {students} students, {athletes} athletes, written to {args.output}")


if __name__ == "__main__":
    _main()
