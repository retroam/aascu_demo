"""Registration holds generator: repeatable, valid values, enrolled terms only, planted effects."""
import unittest

import _common
import registration_holds as rh


def fake_inputs(n):
    """n made-up students, half Pell, each enrolled in a few terms with gaps."""
    students = {f"S{i:04d}": {"Pell_Status_First_Year": "Y" if i % 2 else "N"} for i in range(n)}
    grid = [("2022-23", "FALL"), ("2022-23", "SPRING"), ("2023-24", "FALL"), ("2023-24", "SPRING"), ("2024-25", "FALL")]
    course_terms = {g: {t: [("4", "F")] for k, t in enumerate(grid) if (i + k) % 3} for i, g in enumerate(students)}
    return students, course_terms


class RegistrationHoldsTests(unittest.TestCase):
    def test_same_seed_same_rows(self):
        students, terms = fake_inputs(300)
        self.assertEqual(rh._generate(students, terms, 2.0, 1.6, 3), rh._generate(students, terms, 2.0, 1.6, 3))
        self.assertNotEqual(rh._generate(students, terms, 2.0, 1.6, 3), rh._generate(students, terms, 2.0, 1.6, 4))

    def test_values_and_enrolled_terms_only(self):
        students, terms = fake_inputs(500)
        rows = rh._generate(students, terms, 2.0, 1.6, 1)
        self.assertTrue(rows)
        self.assertLessEqual({r["Hold_Type"] for r in rows}, set(rh.HOLD_TYPES))
        self.assertLessEqual({r["Hold_Status"] for r in rows}, {"active", "resolved", "waived"})
        for r in rows:
            self.assertIn((r["Academic_Year"], r["Academic_Term"]), terms[r["Student_GUID"]])
            self.assertEqual(r["Resolved_Date"] == "", r["Hold_Status"] == "active")
        keys = [(r["Student_GUID"], r["Academic_Year"], r["Academic_Term"], r["Hold_Type"]) for r in rows]
        self.assertEqual(len(keys), len(set(keys)))

    def test_hold_chance(self):
        self.assertAlmostEqual(rh.hold_chance("financial", "Y", True, 2.0, 1.6), 0.12)
        self.assertAlmostEqual(rh.hold_chance("advising", "Y", False, 2.0, 1.6), 0.08)
        self.assertAlmostEqual(rh.hold_chance("sap", "N", None, 2.0, 1.6), 0.03)

    def test_last_observed_term_ignores_stray_rows(self):
        terms = {f"S{i}": {("2024-25", "SPRING"): []} for i in range(5)}
        terms["S0"][("2026-27", "FALL")] = []
        self.assertEqual(rh.last_observed_term(terms, min_students=2), ("2024-25", "SPRING"))


@unittest.skipUnless(_common.COURSE_PATH.exists(), "needs the starter's raw files")
class RegistrationHoldsOnMockDataTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.students = _common.read_students()
        cls.terms = _common.read_course_terms()
        cls.rows = rh._generate(cls.students, cls.terms, 2.0, 1.6, _common.SEED)

    def test_financial_holds_more_likely_for_pell(self):
        financial = {(r["Student_GUID"], r["Academic_Year"], r["Academic_Term"]) for r in self.rows if r["Hold_Type"] == "financial"}
        rate = {}
        for pell in ("Y", "N"):
            enrolled = [(g, *t) for g, ts in self.terms.items() for t in ts
                        if self.students[g]["Pell_Status_First_Year"] == pell]
            rate[pell] = sum(e in financial for e in enrolled) / len(enrolled)
        self.assertGreater(rate["Y"], rate["N"] * 1.6)

    def test_hold_terms_less_often_followed_by_enrollment(self):
        held = {(r["Student_GUID"], r["Academic_Year"], r["Academic_Term"]) for r in self.rows}
        last = rh.last_observed_term(self.terms)
        outcomes = {True: [], False: []}
        for g, ts in self.terms.items():
            for year, term in ts:
                nxt = _common.enrolled_next_term(ts, year, term, last)
                if nxt is not None:
                    outcomes[(g, year, term) in held].append(nxt)
        with_hold = sum(outcomes[True]) / len(outcomes[True])
        without = sum(outcomes[False]) / len(outcomes[False])
        self.assertTrue(0.03 < without - with_hold < 0.25, (with_hold, without))


if __name__ == "__main__":
    unittest.main()
