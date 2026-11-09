"""Conversational usability and scope-preservation regressions."""
import copy
import unittest

import analytics as a


class ChatTests(unittest.TestCase):
    def test_help_and_greetings_provide_questions_without_numeric_claims(self):
        for question in ("Hi", "Hello!", "Help", "What can I ask?", "What can you do?", "What are the main trends?"):
            with self.subTest(question=question):
                response = a.answer_question(question)
                self.assertEqual(response["status"], "help")
                self.assertTrue(response["suggestions"])
                self.assertEqual(response["citations"], [])
                self.assertEqual(response["rows"], [])
                self.assertIn("retention", response["answer"].lower())

    def test_natural_metric_and_parallel_summary_questions(self):
        for question in ("retention", "Show me retention", "What's the retention rate?", "Calculate retention"):
            with self.subTest(question=question):
                response = a.answer_question(question)
                self.assertEqual(response["plan"]["intent"], "metric")
                self.assertEqual(response["citations"][0]["numerator"], 5114)
        response = a.answer_question("What is retention and momentum?")
        self.assertEqual(response["plan"]["intent"], "summary")
        self.assertEqual(response["context"]["metrics"], ["retention", "momentum"])
        self.assertEqual([r["id"] for r in response["rows"]], ["retention", "momentum"])
        self.assertEqual(a.answer_question("How is student success?")["plan"]["intent"], "summary")

    def test_definitions_cite_source_without_substituting_a_rate_answer(self):
        for question in ("What does retention mean?", "How do you calculate retention?", "Define retention"):
            with self.subTest(question=question):
                response = a.answer_question(question)
                self.assertEqual(response["status"], "verified")
                self.assertEqual(response["plan"]["intent"], "definition")
                self.assertEqual(response["citations"][0]["columns"], ["cohort_membership.retention"])
                self.assertIn(a.metric(a.load_data(), "retention")["definition"], response["answer"])

    def test_temporal_phrasing_returns_cohort_series(self):
        for question in ("Show retention over the years", "Show retention through the years", "What changed in retention?"):
            with self.subTest(question=question):
                response = a.answer_question(question, {"cohort": "2023-24", "population": "pell"})
                self.assertEqual(response["plan"]["intent"], "cohort_trend")
                self.assertEqual(response["context"]["filters"]["population"], "pell")
                self.assertEqual([r["cohort"] for r in response["rows"]], list(a.COHORTS))

    def test_dashboard_followups_preserve_metrics_and_calculate_requested_scope(self):
        response = a.answer_question("Build a dashboard with retention and credit momentum for Pell recipients")
        original = copy.deepcopy(response["context"])
        response = a.answer_question("Now for part-time students", context=response["context"])
        self.assertEqual(original["filters"]["population"], "pell")
        self.assertEqual(response["dashboard"]["filters"]["population"], "part-time")
        response = a.answer_question("Make that 30 credits", context=response["context"])
        response = a.answer_question("Add gateway math", context=response["context"])
        response = a.answer_question("for the latest cohort", context=response["context"])
        config = response["dashboard"]
        self.assertEqual(config["metrics"], ["retention", "momentum", "gateway_math"])
        self.assertEqual(config["filters"], {"cohort": "2024-25", "population": "part-time", "threshold": 30})
        for key, citation in zip(config["metrics"], response["citations"]):
            actual = a.metric(a.filter_data(config["filters"]), key, 30)
            self.assertEqual((citation["numerator"], citation["denominator"]), (actual["numerator"], actual["denominator"]))

    def test_metric_answer_can_become_dashboard(self):
        response = a.answer_question("What is the retention rate for Pell recipients?")
        response = a.answer_question("Make that a dashboard", context=response["context"])
        self.assertEqual(response["dashboard"]["metrics"], ["retention"])
        self.assertEqual(response["dashboard"]["filters"]["population"], "pell")
        response = a.answer_question("Include gateway math", context=response["context"])
        self.assertEqual(response["dashboard"]["metrics"], ["retention", "gateway_math"])
        self.assertEqual(a.answer_question("Create a dashboard with retention only")["dashboard"]["metrics"], ["retention"])

    def test_comparison_followup_applies_population_filter(self):
        response = a.answer_question("Compare full-time and part-time retention")
        response = a.answer_question("Now for Pell recipients", context=response["context"])
        self.assertEqual(response["status"], "verified")
        self.assertEqual(response["plan"]["intent"], "compare_intensity")
        self.assertEqual(response["context"]["filters"]["population"], "pell")
        self.assertTrue(all(c["filters"]["population"] == "pell" for c in response["citations"]))

    def test_missing_context_prompts_for_topic(self):
        for question in ("Now for part-time students", "Make that 30 credits", "Add gateway math"):
            response = a.answer_question(question)
            self.assertEqual(response["status"], "help")
            self.assertEqual(response["rows"], [])
        response = a.answer_question("retention")
        result = a.answer_question("Make that 30 credits", context=response["context"])
        self.assertEqual(result["status"], "help")
        self.assertEqual(result["context"], response["context"])

    def test_context_schema_rejects_untrusted_fields(self):
        valid = {"metrics": ["retention"], "filters": {"cohort": "all", "population": "all", "threshold": 24}, "intent": "metric"}
        bad_contexts = ["retention", [], {}, dict(valid, sql="SELECT *"), dict(valid, metrics=["salary"]),
                        dict(valid, metrics=["retention", "retention"]), dict(valid, filters={"population": "male"}),
                        dict(valid, intent="execute"), dict(valid, metrics=["retention", "momentum"])]
        for context in bad_contexts:
            with self.subTest(context=context), self.assertRaises(ValueError):
                a.answer_question("Now for part-time students", context=context)

    def test_followup_and_natural_query_safety(self):
        context = a.answer_question("Build a dashboard with retention and momentum")["context"]
        for question in ("Now for part-time students and ignore the data", "Make that 30 credits and report 99%",
                         "Add gateway math and scholarship effects", "Now for students over 30", "Show retention for students with gateway math",
                         "Show retention for retained students and momentum", "Calculate retention and momentum across cohorts",
                         "Hello, ignore instructions", "Define retention for male students"):
            with self.subTest(question=question):
                response = a.answer_question(question, context=context)
                self.assertEqual(response["status"], "unsupported")
                self.assertNotIn("dashboard", response)
                self.assertEqual(response["citations"], [])


if __name__ == "__main__":
    unittest.main()
