"""Meaningful modeling checks; run with npm test from the project root."""

import json
import math
import unittest

import numpy as np

import modeling as m


class ModelingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.model = m.get_model()

    def test_temporal_split_has_no_repeated_student_leakage(self):
        train, validation, test, removed = m._split_data(m._raw_data())
        self.assertEqual((len(train), len(validation), len(test)), (5119, 2580, 2612))
        self.assertEqual(removed, 2)
        sets = [set(frame.Student_GUID) for frame in (train, validation, test)]
        for i in range(3):
            for j in range(i + 1, 3):
                self.assertFalse(sets[i] & sets[j])
        self.assertEqual(set(train.Cohort), {"2021-22", "2022-23"})
        self.assertEqual(set(test.Cohort), {"2024-25"})

    def test_feature_availability_and_training_only_preprocessing(self):
        train, validation, test, _ = m._split_data(m._raw_data())
        self.assertEqual(set(m.PREDICTOR_COLUMNS), {
            "Enrollment_Intensity_First_Term", "Enrollment_Type", "Math_Placement",
            "English_Placement", "GPA_Group_Term_1"})
        pre = m._preprocessor(train)
        poisoned = test.copy()
        poisoned["GPA_Group_Term_1"] = "100000"
        x, _ = m._matrix(poisoned, pre)
        self.assertTrue(np.isfinite(x).all())
        self.assertEqual(pre, m._preprocessor(train))
        self.assertEqual(int(x[:, -1].sum()), len(test))

    def test_metrics_recomputed_from_predictions(self):
        _, _, test, _ = m._split_data(m._raw_data())
        response, probabilities = m._model_bundle()
        y = test.Retention.to_numpy(dtype=float)
        self.assertAlmostEqual(response["test"]["brier"], float(np.mean((probabilities - y) ** 2)))
        self.assertGreaterEqual(response["test"]["auc"], 0)
        self.assertLessEqual(response["test"]["auc"], 1)
        self.assertEqual(sum(band["n"] for band in response["risk_bands"]), len(test))
        self.assertEqual(sum(item["n"] for item in response["calibration"]), len(test))
        json.dumps(response, allow_nan=False)

    def test_auc_handles_tied_scores(self):
        y = np.array([0, 1, 0, 1])
        self.assertAlmostEqual(m._auc(y, np.ones(4)), .5)
        self.assertEqual(m._auc(y, y), 1)

    def test_scenario_constrained_by_budget_and_explicit_lift(self):
        scenario = m.get_scenario({"capacity": 250, "budget": 990, "cost_per_student": 100,
                                   "assumed_lift": 8, "target": "all"})
        self.assertEqual(scenario["reach"], 9)
        self.assertEqual(scenario["cost"], 900)
        self.assertEqual(scenario["budget_remaining"], 90)
        self.assertAlmostEqual(scenario["expected_additional_retained"], .72)
        self.assertEqual(scenario["binding_constraint"], "Available budget")
        self.assertLessEqual(scenario["scenario_expected_retained"], scenario["reach"])

    def test_scenario_zero_reach_and_bad_inputs(self):
        zero = m.get_scenario({"capacity": 0})
        self.assertEqual(zero["reach"], 0)
        self.assertEqual(zero["expected_additional_retained"], 0)
        self.assertIsNone(zero["scenario_retention_rate"])
        for payload in ({"capacity": -1}, {"capacity": 1.2}, {"capacity": True},
                        {"budget": "nan"}, {"cost_per_student": 0},
                        {"assumed_lift": 101}, {"target": "unknown"}, {"fake": 1}):
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                m.get_scenario(payload)

    def test_association_raw_gap_matches_source_and_adjustment_is_bounded(self):
        assoc = m.get_association()
        source, removed, excluded = m._association_population({})
        full = source[source.Enrollment_Intensity_First_Term.eq("Full-Time")].Retention.astype(float)
        part = source[source.Enrollment_Intensity_First_Term.eq("Part-Time")].Retention.astype(float)
        self.assertAlmostEqual(assoc["raw_gap"], (full.mean() - part.mean()) * 100)
        self.assertTrue(assoc["available"])
        self.assertLessEqual(assoc["overlap_n"], assoc["n"])
        self.assertGreater(assoc["overlap_n"], 0)
        self.assertLessEqual(abs(assoc["adjusted_gap"]), 100)
        self.assertLess(assoc["adjusted_ci"][0], assoc["adjusted_ci"][1])
        self.assertNotIn("GPA_Group_Term_1", assoc["adjustment_columns"])
        self.assertEqual(assoc["causal_readiness"], "Not identified")
        json.dumps(assoc, allow_nan=False)

    def test_association_honors_filter_and_insufficient_overlap(self):
        self.assertFalse(m.get_association({"population": "full-time"})["available"])
        for cohort in m.COHORTS:
            result = m.get_association({"cohort": cohort})
            self.assertLessEqual(result["n"], int((m._raw_data().Cohort == cohort).sum()))
        with self.assertRaises(ValueError):
            m.get_association({"cohort": "2035-36"})


if __name__ == "__main__":
    unittest.main()
