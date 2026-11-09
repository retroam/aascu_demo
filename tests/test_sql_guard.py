"""Public SQL boundary regressions against normalized synthetic data, never writes it."""
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

import analytics
import sql_guard as guard

N = "COUNT(DISTINCT student_id) AS n"
BASE = f"SELECT {N} FROM cohort_records"


class SQLGuardTests(unittest.TestCase):
    """Exercise valid analytics, scope enforcement and adversarial SQL."""

    def test_shared_model_terms_and_housing_obey_scope_and_grain(self):
        catalog = guard.schema_catalog()
        self.assertEqual(len(catalog["normalized_model"]["tables"]), 10)
        course = catalog["views"]["course_records"]["columns"]
        self.assertEqual(course["academic_year"]["origin"], {"table": "term", "column": "academic_year"})
        self.assertIn("attribute_records", catalog["views"])
        for population in ("all", "pell"):
            filters = {"cohort": "2023-24", "population": population}
            result = guard.execute_sql(f"SELECT {N}, attribute_value, COUNT(*) AS records FROM attribute_records WHERE attribute_key = 'uses_on_campus_housing' GROUP BY attribute_value ORDER BY attribute_value", filters)
            with closing(sqlite3.connect(f"{guard.DATABASE.as_uri()}?mode=ro", uri=True)) as db:
                expected = db.execute("""SELECT COUNT(DISTINCT sa.student_id), sa.attribute_value, COUNT(*)
                    FROM student_attribute sa JOIN cohort_membership cm ON cm.student_id = sa.student_id
                    WHERE cm.cohort = '2023-24' AND sa.attribute_key = 'uses_on_campus_housing'
                    AND (? = 'all' OR cm.pell_status_first_year = 'Y')
                    GROUP BY sa.attribute_value HAVING COUNT(DISTINCT sa.student_id) >= 20 ORDER BY sa.attribute_value""", (population,)).fetchall()
            self.assertEqual([tuple(r.values()) for r in result["rows"]], expected)
            self.assertTrue(result["rows"])
        result = guard.execute_sql(f"SELECT {N}, academic_year, COUNT(*) AS attempts FROM course_records GROUP BY academic_year ORDER BY academic_year")
        with closing(sqlite3.connect(f"{guard.DATABASE.as_uri()}?mode=ro", uri=True)) as db:
            expected = db.execute("""SELECT COUNT(DISTINCT ce.student_id), t.academic_year, COUNT(*)
                FROM course_enrollment ce LEFT JOIN term t USING(term_id)
                GROUP BY t.academic_year HAVING COUNT(DISTINCT ce.student_id) >= 20 ORDER BY t.academic_year""").fetchall()
        self.assertEqual([tuple(r.values()) for r in result["rows"]], expected)
        self.reject(f"SELECT {N}, retention FROM attribute_records GROUP BY retention")
        self.reject(f"SELECT {N} FROM attribute_records WHERE attribute_key = 'invented'")
        self.reject(f"SELECT {N} FROM student_attribute")

    def test_sql_results_cache_revalidates_and_isolates_mutations(self):
        guard.RESULT_CACHE.clear()
        sql = "SELECT student_id FROM cohort_records ORDER BY student_id LIMIT 3"
        first = guard.execute_sql(sql, rows=True)
        expected = first["rows"].copy()
        first["rows"].clear()
        with patch.object(guard, "_connection", side_effect=AssertionError("Cached result should not reread rows")):
            self.assertEqual(guard.execute_sql(sql, rows=True)["rows"], expected)
            with self.assertRaises(guard.SQLValidationError):
                guard.execute_sql(sql, rows=False)

    def test_synthetic_rows_are_scoped_bounded_and_read_only(self):
        sql = "SELECT student_id, cohort, retention FROM cohort_records ORDER BY student_id"
        result = guard.execute_sql(sql, {"cohort": "2023-24"}, rows=True)
        self.assertEqual(len(result["rows"]), 200)
        self.assertTrue(result["truncated"])
        self.assertTrue(all(r["cohort"] == "2023-24" for r in result["rows"]))
        with self.assertRaises(guard.SQLValidationError):
            guard.validate_sql(sql)
        for bad in ("DELETE FROM cohort_records", "SELECT * FROM student",
                    "SELECT student_id FROM cohort_records; SELECT student_id FROM cohort_records",
                    "SELECT COUNT(*) AS total FROM cohort_records",
                    "SELECT student_id FROM cohort_records LIMIT 201"):
            with self.subTest(sql=bad), self.assertRaises(guard.SQLValidationError):
                guard.execute_sql(bad, rows=True)

    def reject(self, sql):
        """Both public entry points must reject before any proposed SQL executes."""
        for call in (guard.validate_sql, guard.execute_sql):
            with self.subTest(api=call.__name__, sql=sql), self.assertRaises(guard.SQLValidationError):
                call(sql)

    def test_catalog_has_normalized_domains_and_no_ids(self):
        catalog = guard.schema_catalog({"population": "adult"})
        json.dumps(catalog, allow_nan=False)
        self.assertEqual(catalog["filters"]["population"], "adult")
        cols = catalog["views"]["cohort_records"]["columns"]
        self.assertEqual(cols["retention"]["range"], [0, 1])
        self.assertNotIn("allowed_values", cols["student_id"])
        self.assertNotIn("program_of_study_term_1", cols)
        self.assertIn("UNKNOWN", cols["enrollment_intensity_first_term"]["allowed_values"])
        self.assertNotIn("Unknown", cols["enrollment_intensity_first_term"]["allowed_values"])
        self.assertIn("Nonresident Alien", cols["race"]["dictionary_values"])
        self.assertIn("Nonresident alien", cols["race"]["observed_values"])
        self.assertNotIn("range", cols["number_of_credits_earned_yr_1"])

    def test_known_retention_and_grain(self):
        sql = f"SELECT {N}, SUM(retention) AS retained, COUNT(retention) AS eligible, 100.0 * AVG(retention) AS rate FROM cohort_records"
        self.assertEqual(guard.validate_sql(sql), sql)
        row = guard.execute_sql(sql)["rows"][0]
        self.assertEqual((row["n"], row["retained"], row["eligible"]), (10311, 5114, 10313))
        self.assertAlmostEqual(row["rate"], 100 * 5114 / 10313)

    def test_new_formula_case_aliases_and_having(self):
        sql = f"""SELECT {N}, CASE WHEN race IN ('Asian', 'White') THEN 'selected' ELSE 'other' END AS category,
            ROUND(100.0 * SUM(CASE WHEN retention = 1 THEN 1 ELSE 0 END) / NULLIF(COUNT(retention), 0), 2) AS custom_rate
            FROM cohort_records WHERE number_of_credits_earned_yr_1 BETWEEN 0 AND 200
            GROUP BY category HAVING n >= 20 ORDER BY custom_rate DESC"""
        result = guard.execute_sql(sql)
        self.assertEqual(len(result["rows"]), 2)
        self.assertEqual({row["category"] for row in result["rows"]}, {"selected", "other"})

    def test_every_selected_scope_matches_dashboard(self):
        for population in analytics.POPULATIONS:
            for cohort in ("all", "2021-22", "2024-25"):
                f = {"cohort": cohort, "population": population}
                with self.subTest(filters=f):
                    result = guard.execute_sql(BASE + " WHERE 1 = 1 OR retention = 0", f)
                    expected = analytics.filter_data(f).Student_GUID.nunique()
                    self.assertEqual(result["rows"][0]["n"], expected)
        empty = guard.execute_sql(BASE + " WHERE cohort = '2022-23'", {"cohort": "2021-22"})
        self.assertEqual(empty["rows"], [])
        self.assertEqual(empty["suppressed_rows"], 1)

    def test_course_join_uses_both_keys_and_respects_scope(self):
        f = {"cohort": "2021-22", "population": "pell"}
        sql = f"SELECT {N}, COUNT(*) AS attempts, SUM(number_of_credits_earned) AS credits FROM course_records"
        actual = guard.execute_sql(sql, f)["rows"][0]
        with closing(sqlite3.connect(f"{guard.DATABASE.as_uri()}?mode=ro", uri=True)) as db:
            expected = db.execute("""SELECT COUNT(DISTINCT ce.student_id), COUNT(*), SUM(ce.number_of_credits_earned)
                FROM course_enrollment ce JOIN cohort_membership cm
                ON ce.student_id=cm.student_id AND ce.cohort=cm.cohort
                JOIN student s ON s.student_id=cm.student_id LEFT JOIN course c ON c.course_id=ce.course_id
                WHERE cm.cohort='2021-22' AND cm.pell_status_first_year='Y'""").fetchone()
        self.assertEqual(tuple(actual.values()), expected)
        all_courses = guard.execute_sql(sql)["rows"][0]
        self.assertEqual((all_courses["n"], all_courses["attempts"]), (10311, 100951))

    def test_domain_errors_in_all_predicate_positions(self):
        for condition in ("retention = 'Yes'", "retention = 2", "retention = 0.5", "cohort = '2099-00'",
                          "race IN ('White', 'Martian')", "'Martian' = race", "gender BETWEEN 'A' AND 'Z'",
                          "gpa_group_year_1 > 4.1", "race = 1", "retention IN ('0', '1')"):
            self.reject(BASE + " WHERE " + condition)
            self.reject(f"SELECT {N}, SUM(CASE WHEN {condition} THEN 1 ELSE 0 END) AS hits FROM cohort_records")
        self.reject(f"SELECT {N}, race AS r FROM cohort_records GROUP BY r HAVING r = 'Martian'")
        self.reject(f"SELECT {N}, MAX(race) AS r FROM cohort_records HAVING r = 'Martian'")
        # A declared dictionary code is valid even when it is not observed; not a typo.
        self.assertTrue(guard.validate_sql(BASE + " WHERE race = 'Nonresident Alien'"))
        self.assertTrue(guard.validate_sql(BASE + " WHERE number_of_credits_earned_yr_1 > 5000"))

    def test_no_domain_bypass_with_transforms(self):
        for expression in ("LOWER(race) = 'white'", "CAST(retention AS TEXT) = 'Yes'",
                           "COALESCE(race, 'missing') = 'Martian'", "retention + 0 = 2",
                           "CASE WHEN race = 'White' THEN race ELSE race END = 'Martian'",
                           "race LIKE 'Mart%'", "race = gender", "gpa_group_year_1 + 0 > 5", "race"):
            self.reject(BASE + " WHERE " + expression)
        self.reject(f"SELECT {N}, COUNT(NULLIF(race, 'Martian')) AS bad FROM cohort_records")
        self.reject(f"SELECT {N}, SUM(DISTINCT race) AS bad FROM cohort_records")
        self.reject(f"SELECT {N}, 2 AS retention FROM cohort_records GROUP BY retention")

    def test_identifier_and_forged_n_attacks(self):
        for sql in ("SELECT 100 AS n FROM cohort_records", "SELECT COUNT(*) AS n FROM cohort_records",
                    "SELECT COUNT(DISTINCT student_id) AS N FROM cohort_records",
                    f"SELECT {N}, 87.5 AS invented_rate FROM cohort_records",
                    f"SELECT {N}, SUM(87.5) AS invented_total FROM cohort_records",
                    "SELECT COUNT(DISTINCT student_id) + 100 AS n FROM cohort_records",
                    f"SELECT {N}, student_id FROM cohort_records GROUP BY student_id",
                    f"SELECT {N}, MIN(student_id) AS leaked FROM cohort_records",
                    f"SELECT {N}, COUNT(DISTINCT COALESCE(student_id, 'x')) AS leaked FROM cohort_records",
                    BASE + " WHERE student_id = 'secret'", BASE + " GROUP BY student_id",
                    f"SELECT {N}, SUM(student_id + 1) AS leaked FROM cohort_records"):
            self.reject(sql)

    def test_reject_nonaggregate_columns_and_scalar_minmax(self):
        for expression in ("race AS label", "COALESCE(race, 'missing') AS label",
                           "CASE WHEN retention=1 THEN race ELSE 'other' END AS label",
                           "MIN(retention, persistence) AS value", "MAX(retention, persistence) AS value",
                           "MIN(DISTINCT gpa_group_year_1, 9999) AS value", "MAX(DISTINCT race, 'zzzz') AS value",
                           "SUM(race) AS value", "SUM(SUM(retention)) AS value"):
            self.reject(f"SELECT {N}, {expression} FROM cohort_records")
        self.reject(BASE + " ORDER BY race")
        self.reject(BASE + " WHERE SUM(retention) > 0")

    def test_commands_functions_crossproducts_and_unknown_names(self):
        for sql in ("DELETE FROM student", "PRAGMA table_info(student)", "ATTACH DATABASE ':memory:' AS x",
                    BASE + "; SELECT 1", BASE + " UNION ALL " + BASE,
                    f"SELECT {N}, load_extension('/tmp/x') AS x FROM cohort_records",
                    f"SELECT {N}, readfile('/etc/passwd') AS x FROM cohort_records",
                    f"SELECT {N}, randomblob(1000000000) AS x FROM cohort_records",
                    f"SELECT {N}, * FROM cohort_records", BASE.replace("cohort_records", "student"),
                    BASE.replace("cohort_records", "main.cohort_records"),
                    f"SELECT {N} FROM cohort_records a, cohort_records b",
                    f"SELECT {N} FROM cohort_records JOIN course_records USING(student_id)",
                    f"WITH RECURSIVE x AS ({BASE}) SELECT * FROM x",
                    f"SELECT {N}, (SELECT 1) AS x FROM cohort_records",
                    f"SELECT {N}, SUM(invented) AS x FROM cohort_records",
                    f"SELECT {N}, SUM(retention) OVER () AS x FROM cohort_records"):
            self.reject(sql)

    def test_sqlite_authorizer_independent_of_ast(self):
        with guard._connection(None) as db:
            guard._lockdown(db, "cohort_records")
            for sql in ("SELECT student_id FROM student", "SELECT * FROM sqlite_master", "PRAGMA table_info(student)",
                        "ATTACH ':memory:' AS x", "DELETE FROM student", "SELECT randomblob(5)", "SELECT * FROM course_records"):
                with self.subTest(sql=sql), self.assertRaises(sqlite3.DatabaseError):
                    db.execute(sql)
            self.assertEqual(db.execute(BASE).fetchone(), (10311,))

    def test_size_complexity_deadline_and_finite_numbers(self):
        self.reject(BASE + " " * guard.MAX_SQL)
        self.reject(BASE + " WHERE " + " AND ".join(["retention = 1"] * 200))
        self.reject(f"SELECT {N}, " + ", ".join(f"SUM(retention) AS r{i}" for i in range(16)) + " FROM cohort_records")
        self.reject(BASE + " LIMIT 201")
        self.reject(BASE + " LIMIT -1")
        with patch.object(guard, "INSTRUCTION_BUDGET", 0):
            with self.assertRaisesRegex(guard.SQLValidationError, "budget"):
                guard.execute_sql(BASE)
        with patch.object(guard, "TIMEOUT_SECONDS", -1):
            with self.assertRaisesRegex(guard.SQLValidationError, "budget"):
                guard.execute_sql(BASE)
        with self.assertRaisesRegex(guard.SQLValidationError, "non-finite"):
            guard.execute_sql(f"SELECT {N}, COUNT(*) * 1e308 AS huge FROM cohort_records")
        self.reject(f"SELECT {N}, -1e999 AS huge FROM cohort_records")
        safe = guard.execute_sql(f"SELECT {N}, MAX(retention) * 9007199254740991 AS large FROM cohort_records")
        self.assertEqual(safe["rows"][0]["large"], 9007199254740991)
        for factor in (9007199254740992, -9007199254740992):
            with self.assertRaisesRegex(guard.SQLValidationError, "exact numeric range"):
                guard.execute_sql(f"SELECT {N}, MAX(retention) * {factor} AS large FROM cohort_records")

    def test_suppression_cap_strings_and_nulls_with_disposable_database(self):
        # Reuse only the real table definitions; never copy or mutate shared rows.
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "fixture.sqlite"
            with closing(sqlite3.connect(f"{guard.DATABASE.as_uri()}?mode=ro", uri=True)) as source:
                ddl = [r[0] for r in source.execute("SELECT sql FROM sqlite_master WHERE name IN ('student','cohort_membership','course_enrollment','course','term','student_attribute')")]
            with closing(sqlite3.connect(path)) as db:
                for statement in ddl:
                    db.execute(statement)
                for i in range(4021):
                    sid = f"{i:032x}"
                    db.execute("INSERT INTO student(student_id,institution_id,race) VALUES (?,1,NULL)", (sid,))
                    db.execute("INSERT INTO cohort_membership(student_id,cohort,provider_id,cohort_term,number_of_credits_earned_yr_1) VALUES (?,'2021-22',1,'Fall',?)", (sid, i // 20))
                db.commit()
            with patch.object(guard, "DATABASE", path):
                result = guard.execute_sql(f"SELECT {N}, number_of_credits_earned_yr_1 AS credits FROM cohort_records GROUP BY credits ORDER BY credits")
                self.assertEqual(len(result["rows"]), 200)
                self.assertTrue(result["truncated"])
                self.assertTrue(all(r["n"] == 20 for r in result["rows"]))
                small = guard.execute_sql(BASE + " WHERE number_of_credits_earned_yr_1 = 201")
                self.assertEqual(small["rows"], [])
                self.assertEqual(small["suppressed_rows"], 1)
                long = guard.execute_sql(f"SELECT {N}, COALESCE(MIN(race), '{'x' * 600}') AS label, MIN(retention) AS missing FROM cohort_records")
                self.assertEqual(len(long["rows"][0]["label"]), 200)
                self.assertIsNone(long["rows"][0]["missing"])


if __name__ == "__main__":
    unittest.main()
