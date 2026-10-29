
import unittest

from src.services.ground_truth_evaluation import evaluate_labels


class TestGroundTruthEvaluation(unittest.TestCase):

    def test_perfect_detector_predictions(self):
        labels = [
            {
                "rule_name": "shipment_exception",
                "record_id": "SHP-001",
                "actual_label": 1,
            },
            {
                "rule_name": "shipment_exception",
                "record_id": "SHP-002",
                "actual_label": 0,
            },
        ]

        predictions = {
            ("shipment_exception", "SHP-001"): 1,
            ("shipment_exception", "SHP-002"): 0,
        }

        result = evaluate_labels(labels, predictions)

        self.assertEqual(result["records_evaluated"], 2)
        self.assertEqual(result["overall"]["precision"], 1.0)
        self.assertEqual(result["overall"]["recall"], 1.0)
        self.assertEqual(result["overall"]["f1_score"], 1.0)

    def test_incorrect_prediction_is_counted(self):
        labels = [
            {
                "rule_name": "asset_condition",
                "record_id": "ASSET-001",
                "actual_label": 1,
            },
            {
                "rule_name": "asset_condition",
                "record_id": "ASSET-002",
                "actual_label": 0,
            },
        ]

        predictions = {
            ("asset_condition", "ASSET-001"): 0,
            ("asset_condition", "ASSET-002"): 1,
        }

        result = evaluate_labels(labels, predictions)

        self.assertEqual(result["overall"]["false_positive"], 1)
        self.assertEqual(result["overall"]["false_negative"], 1)
        self.assertEqual(result["overall"]["f1_score"], 0.0)

    def test_metrics_are_grouped_by_rule(self):
        labels = [
            {
                "rule_name": "shipment_exception",
                "record_id": "SHP-001",
                "actual_label": 1,
            },
            {
                "rule_name": "asset_condition",
                "record_id": "ASSET-001",
                "actual_label": 0,
            },
        ]

        predictions = {
            ("shipment_exception", "SHP-001"): 1,
            ("asset_condition", "ASSET-001"): 0,
        }

        result = evaluate_labels(labels, predictions)

        self.assertIn("shipment_exception", result["per_rule"])
        self.assertIn("asset_condition", result["per_rule"])
        self.assertEqual(len(result["per_rule"]), 2)

    def test_missing_prediction_is_rejected(self):
        labels = [
            {
                "rule_name": "shipment_exception",
                "record_id": "SHP-MISSING",
                "actual_label": 1,
            }
        ]

        with self.assertRaisesRegex(ValueError, "no matching"):
            evaluate_labels(labels, {})


if __name__ == "__main__":
    unittest.main(verbosity=2)
