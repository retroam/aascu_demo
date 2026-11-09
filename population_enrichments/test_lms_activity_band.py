"""LMS activity band generator: repeatable, valid values, enrolled terms only, planted effect."""
import unittest

import _common
import lms_activity_band as lms


class LmsActivityBandTests(unittest.TestCase):
    def test_is_dfw_reads_the_grade_codes(self):
        for grade, expected in [("F", True), ("W", True), ("UW", True), ("0", True), ("1.7", True),
                                ("2", False), ("4", False), ("P", False), ("I", None), ("M", None), ("", None)]:
            self.assertEqual(lms.is_dfw(grade), expected, grade)

    def test_dfw_share(self):
        self.assertEqual(lms.dfw_share([("F", "O"), ("4", "F"), ("I", "F"), ("W", "")]), 2 / 3)
        self.assertIsNone(lms.dfw_share([("", "F"), ("M", "O")]))

    def test_one_row_per_enrolled_term_and_repeatable(self):
        terms = {"A": {("2022-23", "FALL"): [("4", "F")], ("2022-23", "SPRING"): [("F", "O")]},
                 "B": {("2023-24", "SUMMER"): [("", "")]}}
        rows = lms._generate(terms, 1.5, -0.6, 0.6, 1)
        self.assertEqual(sorted((r["Student_GUID"], r["Academic_Year"], r["Academic_Term"]) for r in rows),
                         [("A", "2022-23", "FALL"), ("A", "2022-23", "SPRING"), ("B", "2023-24", "SUMMER")])
        self.assertLessEqual({r["LMS_Activity_Band"] for r in rows}, set(lms.BANDS))
        self.assertEqual(rows, lms._generate(terms, 1.5, -0.6, 0.6, 1))

    def test_dfw_terms_get_lower_bands(self):
        terms = {f"S{i}": {("2022-23", "FALL"): [("F", "F")] if i % 2 else [("4", "F")]} for i in range(4000)}
        rows = lms._generate(terms, 1.5, -0.6, 0.6, 2)
        low_share = {}
        for failed in (True, False):
            bands = [r["LMS_Activity_Band"] for r in rows if (int(r["Student_GUID"][1:]) % 2 == 1) == failed]
            low_share[failed] = bands.count("low") / len(bands)
        self.assertGreater(low_share[True], low_share[False] + 0.3)


@unittest.skipUnless(_common.COURSE_PATH.exists(), "needs the starter's raw course file")
class LmsActivityBandOnMockDataTests(unittest.TestCase):
    def test_mean_dfw_share_falls_from_low_to_high(self):
        terms = _common.read_course_terms()
        rows = lms._generate(terms, 1.5, -0.6, 0.6, _common.SEED)
        self.assertEqual(len(rows), sum(len(t) for t in terms.values()))
        shares = {band: [] for band in lms.BANDS}
        for r in rows:
            share = lms.dfw_share(terms[r["Student_GUID"]][(r["Academic_Year"], r["Academic_Term"])])
            if share is not None:
                shares[r["LMS_Activity_Band"]].append(share)
        mean = {band: sum(v) / len(v) for band, v in shares.items()}
        self.assertGreater(mean["low"], mean["medium"] + 0.1)
        self.assertGreater(mean["medium"], mean["high"] + 0.05)


if __name__ == "__main__":
    unittest.main()
