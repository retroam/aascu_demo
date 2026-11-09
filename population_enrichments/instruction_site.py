"""Generate the synthetic instruction site enrichment file (one row per student, no term).

Models Adams State's three ways of teaching: on-campus undergraduates, online programs, and prison
education in 5 Colorado Department of Corrections facilities.

Every effect below is PLANTED by this script. None is a finding about real students.

Step 1, cdoc_facility: a small group, by Student_Age: Older than 24 at 0.012, >20 - 24 at 0.005,
20 and younger at 0.001 (about 55 students; scale all three with cdoc_scale). The group is small
on purpose: summaries must suppress groups under 10 students.
Step 2, online or on_campus for everyone else, by the student's online share: of their course-file
rows with a Delivery_Method (O online, F face to face, H hybrid; blanks don't count), the share
that are O.
    share >= 0.75: online at 0.70    0.50-0.75: 0.40    0.25-0.50: 0.15    below 0.25: 0.03
    no Delivery_Method at all: 0.15
Fixed seed: same seed, same file. A student in two cohorts is modelled on the earlier cohort row.

Run:
    python population_enrichments/instruction_site.py
"""

import argparse
import random

import _common

__all__ = ["generate_instruction_site"]

SITES = ("on_campus", "online", "cdoc_facility")
CDOC_RATES = {"Older than 24": 0.012, ">20 - 24": 0.005, "20 and younger": 0.001}
ONLINE_RATES = ((0.75, 0.70), (0.50, 0.40), (0.25, 0.15), (0.0, 0.03))  # (lowest online share, chance of online)
NO_DELIVERY_ONLINE_RATE = 0.15
_SOURCE = "synthetic: population_enrichments/instruction_site.py, seed {seed}, planted effects"
_OUTPUT_COLUMNS = ["Student_GUID", "Instruction_Site", "Source"]


def generate_instruction_site(
    cohort_path=_common.COHORT_PATH,
    course_path=_common.COURSE_PATH,
    output_path=_common.DATA_DIR / "instruction_site.csv",
    cdoc_scale=1.0,
    seed=_common.SEED,
):
    """Write the instruction site file and return its rows."""
    students = _common.read_students(cohort_path)
    course_terms = _common.read_course_terms(course_path)
    rows = _generate(students, course_terms, cdoc_scale, seed)
    _common.write_rows(rows, output_path, _OUTPUT_COLUMNS)
    return rows


def online_share(terms):
    """The share of a student's course rows with a Delivery_Method that are O; None if none has one."""
    methods = [method for courses in terms.values() for _, method in courses if method]
    return sum(method == "O" for method in methods) / len(methods) if methods else None


def online_chance(share):
    """The chance a non-CDOC student is online, from their online share."""
    if share is None:
        return NO_DELIVERY_ONLINE_RATE
    for lowest, chance in ONLINE_RATES:
        if share >= lowest:
            return chance
    return ONLINE_RATES[-1][1]


def _generate(students, course_terms, cdoc_scale, seed):
    """All rows, as dicts with _OUTPUT_COLUMNS. Same seed, same rows."""
    rng = random.Random(seed)
    source = _SOURCE.format(seed=seed)
    rows = []
    for guid in sorted(students):
        cdoc_chance = CDOC_RATES.get(students[guid]["Student_Age"], 0.0) * cdoc_scale
        if rng.random() < cdoc_chance:
            site = "cdoc_facility"
        elif rng.random() < online_chance(online_share(course_terms.get(guid, {}))):
            site = "online"
        else:
            site = "on_campus"
        rows.append({"Student_GUID": guid, "Instruction_Site": site, "Source": source})
    return rows


def _main(argv=None):
    """Command line: python instruction_site.py [--cdoc-scale 1.0 ...]."""
    parser = argparse.ArgumentParser(description="Generate the synthetic instruction site enrichment file.")
    parser.add_argument("--cohort", default=str(_common.COHORT_PATH), help="cohort Analysis-Ready File")
    parser.add_argument("--course", default=str(_common.COURSE_PATH), help="course Analysis-Ready File")
    parser.add_argument("--output", default=str(_common.DATA_DIR / "instruction_site.csv"))
    parser.add_argument("--cdoc-scale", type=float, default=1.0, help="multiplies every CDOC rate")
    parser.add_argument("--seed", type=int, default=_common.SEED)
    args = parser.parse_args(argv)

    rows = generate_instruction_site(args.cohort, args.course, args.output, args.cdoc_scale, args.seed)
    counts = {site: sum(row["Instruction_Site"] == site for row in rows) for site in SITES}
    print(f"{len(rows)} students written to {args.output}: {counts}")


if __name__ == "__main__":
    _main()
