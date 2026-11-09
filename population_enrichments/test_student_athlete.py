"""Student-athlete generator: repeatable, valid values, target share, planted effects."""
import csv
import tempfile
import unittest
from pathlib import Path

import _common
import student_athlete as sa

WEIGHTS = {"ftft": 0.6, "young": 0.5, "older": -0.8, "retained": 0.2}


def fake_students(n):
    """n made-up cohort rows that vary every column the model reads."""
    ages = ["20 and younger", ">20 - 24", "Older than 24"]
    return {f"S{i:05d}": {"Student_GUID": f"S{i:05d}", "Cohort": ["2022-23", "2023-24"][i % 2], "Cohort_Term": "FALL",
                          "Student_Age": ages[i % 3], "Enrollment_Type": ["First-Time", "Transfer-In"][i % 5 == 0],
                          "Enrollment_Intensity_First_Term": ["Full-Time", "Part-Time"][i % 4 == 0],
                          "Retention": str(i % 7 % 2), "Gender": ["M", "F"][i % 11 % 2]}
            for i in range(n)}


def athletes(rows):
    """{student: True/False} from the is_student_athlete rows."""
    return {r["Student_GUID"]: r["Attribute_Value"] == "true" for r in rows if r["Attribute_Key"] == "is_student_athlete"}


class StudentAthleteTests(unittest.TestCase):
    def test_same_seed_same_rows(self):
        students = fake_students(500)
        self.assertEqual(sa._generate(students, 0.45, WEIGHTS, "2023-24", 3.0, 5),
                         sa._generate(students, 0.45, WEIGHTS, "2023-24", 3.0, 5))
        self.assertNotEqual(sa._generate(students, 0.45, WEIGHTS, "2023-24", 3.0, 5),
                            sa._generate(students, 0.45, WEIGHTS, "2023-24", 3.0, 6))

    def test_values_and_one_flag_per_student(self):
        students = fake_students(800)
        rows = sa._generate(students, 0.45, WEIGHTS, "2023-24", 3.0, 1)
        flags = athletes(rows)
        self.assertEqual(set(flags), set(students))
        sports = {r["Student_GUID"]: r["Attribute_Value"] for r in rows if r["Attribute_Key"] == "athlete_sport"}
        self.assertEqual(set(sports), {g for g, a in flags.items() if a})
        self.assertLessEqual(set(sports.values()), set(sa.SPORTS))
        self.assertFalse({"football", "wrestling"} & {s for g, s in sports.items() if students[g]["Gender"] != "M"})

    def test_intercept_hits_the_share(self):
        scores = [sa._score(row, WEIGHTS) for row in fake_students(900).values()]
        intercept = sa._solve_intercept(scores, 0.45)
        self.assertAlmostEqual(sum(sa._sigmoid(intercept + s) for s in scores) / len(scores), 0.45, places=6)

    def test_writes_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            cohort = Path(tmp) / "cohort.csv"
            students = fake_students(50)
            with open(cohort, "w", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=list(next(iter(students.values()))))
                writer.writeheader()
                writer.writerows(students.values())
            output = Path(tmp) / "out" / "athlete.csv"
            sa._main(["--cohort", str(cohort), "--output", str(output), "--seed", "9"])
            with open(output, newline="") as f:
                rows = list(csv.DictReader(f))
            self.assertEqual(len(athletes(rows)), 50)
            self.assertTrue(all(r["Source"].endswith("seed 9, planted effects") for r in rows))


@unittest.skipUnless(_common.COHORT_PATH.exists(), "needs the starter's raw cohort file")
class StudentAthleteOnMockDataTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.students = _common.read_students()
        cls.rows = sa._generate(cls.students, 0.45, WEIGHTS, "2023-24", 3.0, _common.SEED)
        cls.flags = athletes(cls.rows)

    def retention(self, guids):
        guids = list(guids)
        return sum(self.students[g]["Retention"] == "1" for g in guids) / len(guids)

    def test_share_is_near_target(self):
        self.assertAlmostEqual(sum(self.flags.values()) / len(self.flags), 0.45, delta=0.02)

    def test_athletes_retain_8_to_12_points_better(self):
        gap = self.retention(g for g, a in self.flags.items() if a) - self.retention(g for g, a in self.flags.items() if not a)
        self.assertTrue(0.08 <= gap <= 0.12, gap)

    def test_skewed_to_young_students(self):
        young = [a for g, a in self.flags.items() if self.students[g]["Student_Age"] == "20 and younger"]
        older = [a for g, a in self.flags.items() if self.students[g]["Student_Age"] == "Older than 24"]
        self.assertGreater(sum(young) / len(young), sum(older) / len(older) + 0.2)

    def test_coach_change_cohort_football_retains_worse(self):
        sports = {r["Student_GUID"]: r["Attribute_Value"] for r in self.rows if r["Attribute_Key"] == "athlete_sport"}
        in_cohort = [g for g in sports if self.students[g]["Cohort"] == "2023-24"]
        football = self.retention(g for g in in_cohort if sports[g] == "football")
        others = self.retention(g for g in in_cohort if sports[g] != "football")
        self.assertLess(football, others - 0.08)


if __name__ == "__main__":
    unittest.main()
