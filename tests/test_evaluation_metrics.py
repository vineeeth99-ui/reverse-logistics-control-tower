
import unittest

from src.services.evaluation_metrics import calculate_metrics


class TestEvaluationMetrics(unittest.TestCase):

    def test_perfect_predictions(self):
        result = calculate_metrics(
            actual_labels=[1, 0, 1, 0],
            predicted_labels=[1, 0, 1, 0],
        )

        self.assertEqual(result["true_positive"], 2)
        self.assertEqual(result["true_negative"], 2)
        self.assertEqual(result["false_positive"], 0)
        self.assertEqual(result["false_negative"], 0)
        self.assertEqual(result["precision"], 1.0)
        self.assertEqual(result["recall"], 1.0)
        self.assertEqual(result["f1_score"], 1.0)
        self.assertEqual(result["accuracy"], 1.0)

    def test_false_positive_and_false_negative(self):
        result = calculate_metrics(
            actual_labels=[1, 1, 0, 0],
            predicted_labels=[1, 0, 1, 0],
        )

        self.assertEqual(result["true_positive"], 1)
        self.assertEqual(result["true_negative"], 1)
        self.assertEqual(result["false_positive"], 1)
        self.assertEqual(result["false_negative"], 1)
        self.assertEqual(result["precision"], 0.5)
        self.assertEqual(result["recall"], 0.5)
        self.assertEqual(result["f1_score"], 0.5)
        self.assertEqual(result["accuracy"], 0.5)

    def test_no_positive_predictions(self):
        result = calculate_metrics(
            actual_labels=[1, 0],
            predicted_labels=[0, 0],
        )

        self.assertEqual(result["precision"], 0.0)
        self.assertEqual(result["recall"], 0.0)
        self.assertEqual(result["f1_score"], 0.0)

    def test_mismatched_lengths_are_rejected(self):
        with self.assertRaises(ValueError):
            calculate_metrics(
                actual_labels=[1, 0],
                predicted_labels=[1],
            )

    def test_invalid_labels_are_rejected(self):
        with self.assertRaises(ValueError):
            calculate_metrics(
                actual_labels=[2, 0],
                predicted_labels=[1, 0],
            )

    def test_empty_input_is_rejected(self):
        with self.assertRaises(ValueError):
            calculate_metrics([], [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
