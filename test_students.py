"""Student detail scope, data fidelity, pagination and HTTP routing checks."""
import io
import json
import sqlite3
import unittest
from unittest.mock import patch

import foundations
import students
from server import Handler


class StudentRecordsTests(unittest.TestCase):
    def test_default_and_pagination(self):
        first = students.get_students({"page_size": 7})
        second = students.get_students({"page_size": 7, "page": 2})
        self.assertEqual(first["total"], 10313)
        self.assertEqual(len(first["rows"]), 7)
        self.assertFalse({(r["student_id"], r["cohort"]) for r in first["rows"]} &
                         {(r["student_id"], r["cohort"]) for r in second["rows"]})
        with foundations.connection() as db:
            expected = db.execute("SELECT student_id, cohort FROM cohort_membership ORDER BY cohort DESC, student_id LIMIT 14").fetchall()
        self.assertEqual([(r["student_id"], r["cohort"]) for r in first["rows"] + second["rows"]], expected)
        self.assertEqual(students.get_students({"page": 100000})["rows"], [])
        self.assertIsNone(first["freshness"]["extracted_at"])

    def test_scope_and_review_filter_match_database(self):
        filters = {"cohort": "2024-25", "population": "part-time", "threshold": 30, "review": "low-credits"}
        result = students.get_students(filters)
        with foundations.connection() as db:
            expected = db.execute("SELECT COUNT(*) FROM cohort_membership WHERE cohort='2024-25' "
                                  "AND enrollment_intensity_first_term='Part-Time' "
                                  "AND number_of_credits_earned_yr_1 >= 0 AND number_of_credits_earned_yr_1 < 30").fetchone()[0]
        self.assertEqual(result["total"], expected)
        for row in result["rows"]:
            self.assertEqual(row["cohort"], "2024-25")
            self.assertEqual(row["enrollment_intensity"], "Part-Time")
            self.assertLess(row["credits_earned"], 30)
            self.assertIn("low-credits", [r["id"] for r in row["review_reasons"]])

    def test_missing_values_never_become_adverse_observations(self):
        with foundations.connection() as db:
            db.row_factory = sqlite3.Row
            row = dict(db.execute("SELECT * FROM cohort_membership LIMIT 1").fetchone())
        row.update(number_of_credits_earned_yr_1=None, gpa_group_term_1=None,
                   gateway_math_status="R", completed_gateway_math_year1="UNKNOWN",
                   gateway_english_status="N", completed_gateway_english_year1="D", retention=None)
        summary = students._summary(row, 24)
        self.assertIsNone(summary["credits_earned"])
        self.assertIsNone(summary["gpa"])
        self.assertIsNone(summary["retention"])
        self.assertEqual(summary["gateway_math"], "Unknown")
        self.assertEqual(summary["gateway_english"], "Not required")
        self.assertEqual(summary["review_reasons"], [])
        row.update(number_of_credits_earned_yr_1=0, gpa_group_term_1=0,
                   completed_gateway_math_year1="D")
        summary = students._summary(row, 24)
        self.assertEqual({r["id"] for r in summary["review_reasons"]}, {"low-credits", "gateway-math", "low-gpa"})
        row.update(gateway_math_status="UNKNOWN", completed_gateway_math_year1="C")
        summary = students._summary(row, 24)
        self.assertEqual(summary["gateway_math"], "Completed")
        self.assertEqual(summary["gateway_math_requirement"], "Unknown")
        self.assertNotIn("gateway-math", [r["id"] for r in summary["review_reasons"]])

    def test_entry_type_only_narrows_selected_population(self):
        result = students.get_students({"population": "part-time", "entry_type": "transfer"})
        with foundations.connection() as db:
            expected = db.execute("SELECT COUNT(*) FROM cohort_membership WHERE enrollment_type='Transfer-In' "
                                  "AND enrollment_intensity_first_term='Part-Time'").fetchone()[0]
        self.assertEqual(result["total"], expected)
        self.assertEqual(result["entry_type"], "transfer")
        self.assertTrue(all(r["enrollment_type"] == "Transfer-In" for r in result["rows"]))
        with self.assertRaises(LookupError):
            students.get_student({"id": result["rows"][0]["student_id"], "cohort": result["rows"][0]["cohort"], "entry_type": "first-time"})

    def test_repeated_student_courses_join_on_both_keys(self):
        with foundations.connection() as db:
            student_id = db.execute("SELECT student_id FROM cohort_membership GROUP BY student_id HAVING COUNT(*) > 1 LIMIT 1").fetchone()[0]
            cohorts = [r[0] for r in db.execute("SELECT cohort FROM cohort_membership WHERE student_id=? ORDER BY cohort", (student_id,))]
            expected = db.execute("SELECT COUNT(*) FROM course_enrollment WHERE student_id=? AND cohort=?", (student_id, cohorts[0])).fetchone()[0]
        detail = students.get_student({"id": student_id.lower(), "cohort": cohorts[0]})
        self.assertEqual([c["cohort"] for c in detail["cohorts"]], [cohorts[0]])
        self.assertEqual(detail["course_count"], expected)
        self.assertTrue(all(c["cohort"] == cohorts[0] for c in detail["courses"]))
        full_detail = students.get_student({"id": student_id})
        self.assertEqual([c["cohort"] for c in full_detail["cohorts"]], cohorts)
        json.dumps(full_detail, allow_nan=False)

    def test_prefix_search_and_scope_mismatch(self):
        selected = students.get_students({"population": "part-time", "cohort": "2024-25", "page_size": 1})["rows"][0]
        result = students.get_students({"search": selected["student_id"].lower()[:12]})
        self.assertTrue(result["rows"])
        self.assertTrue(all(r["student_id"].startswith(selected["student_id"][:12]) for r in result["rows"]))
        with self.assertRaises(LookupError):
            students.get_student({"id": selected["student_id"], "cohort": "2024-25", "population": "full-time"})

    def test_validation(self):
        for query in ({"page": 0}, {"page_size": 51}, {"page": "1.0"}, {"page": True},
                      {"review": "race"}, {"search": "%' OR 1=1--"}, {"search": None}, {"sort": "risk"}, {"entry_type": "unknown"}):
            with self.subTest(query=query), self.assertRaises(ValueError):
                students.get_students(query)
        for value in (None, "", "a", "../student", "0" * 31 + "'", []):
            with self.subTest(value=value), self.assertRaises(ValueError):
                students.get_student({"id": value})
        with self.assertRaises(LookupError):
            students.get_student({"id": "0" * 32})


class StudentRoutesTests(unittest.TestCase):
    def request(self, path):
        # Exercise real dispatch and JSON encoding without binding a network port.
        handler = object.__new__(Handler)
        handler.path, handler.command, handler.wfile = path, "GET", io.BytesIO()
        handler.headers = {}
        with patch.object(handler, "_local_host", return_value=True), \
             patch.object(handler, "send_response") as status, \
             patch.object(handler, "send_header"), patch.object(handler, "end_headers"):
            handler.do_GET()
        return status.call_args.args[0], json.loads(handler.wfile.getvalue())

    def test_roster_and_detail_routes(self):
        status, roster = self.request("/api/students?page_size=1&population=part-time")
        self.assertEqual(status, 200)
        status, detail = self.request("/api/student?id=" + roster["rows"][0]["student_id"])
        self.assertEqual(status, 200)
        self.assertTrue(detail["synthetic"])

    def test_route_errors(self):
        for path, expected in [("/api/student?id=bad", 400), ("/api/student?id=" + "0" * 32, 404),
                               ("/api/students?page_size=1000000", 400), ("/api/student?id=a&id=b", 400)]:
            status, result = self.request(path)
            self.assertEqual(status, expected)
            self.assertIn("error", result)


if __name__ == "__main__":
    unittest.main()
