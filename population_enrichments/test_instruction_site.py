"""Instruction site generator: repeatable, valid values, small CDOC group, online tilt."""
import unittest

import _common
import instruction_site as site


class InstructionSiteTests(unittest.TestCase):
    def test_online_share_ignores_blank_delivery(self):
        terms = {("2022-23", "FALL"): [("4", "O"), ("4", "F"), ("4", "")], ("2022-23", "SPRING"): [("4", "O")]}
        self.assertEqual(site.online_share(terms), 2 / 3)
        self.assertIsNone(site.online_share({("2022-23", "FALL"): [("4", "")]}))

    def test_online_chance_by_share(self):
        self.assertEqual(site.online_chance(1.0), 0.70)
        self.assertEqual(site.online_chance(0.6), 0.40)
        self.assertEqual(site.online_chance(0.3), 0.15)
        self.assertEqual(site.online_chance(0.0), 0.03)
        self.assertEqual(site.online_chance(None), site.NO_DELIVERY_ONLINE_RATE)

    def test_one_row_per_student_and_repeatable(self):
        students = {f"S{i}": {"Student_Age": "Older than 24"} for i in range(200)}
        rows = site._generate(students, {}, 1.0, 4)
        self.assertEqual([r["Student_GUID"] for r in rows], sorted(students))
        self.assertLessEqual({r["Instruction_Site"] for r in rows}, set(site.SITES))
        self.assertEqual(rows, site._generate(students, {}, 1.0, 4))


@unittest.skipUnless(_common.COURSE_PATH.exists(), "needs the starter's raw files")
class InstructionSiteOnMockDataTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.students = _common.read_students()
        cls.terms = _common.read_course_terms()
        cls.sites = {r["Student_GUID"]: r["Instruction_Site"] for r in site._generate(cls.students, cls.terms, 1.0, _common.SEED)}

    def test_cdoc_is_small_and_older(self):
        cdoc = [g for g, s in self.sites.items() if s == "cdoc_facility"]
        self.assertTrue(40 <= len(cdoc) <= 80, len(cdoc))
        older = sum(self.students[g]["Student_Age"] == "Older than 24" for g in cdoc)
        self.assertGreater(older / len(cdoc), 0.5)

    def test_online_students_take_mostly_online_courses(self):
        mean = {}
        for kind in ("online", "on_campus"):
            shares = [site.online_share(self.terms.get(g, {})) for g, s in self.sites.items() if s == kind]
            shares = [x for x in shares if x is not None]
            mean[kind] = sum(shares) / len(shares)
        self.assertGreater(mean["online"], mean["on_campus"] + 0.3)


if __name__ == "__main__":
    unittest.main()
