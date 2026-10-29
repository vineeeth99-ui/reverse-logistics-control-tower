
def calculate_metrics(
    actual_labels: list[int],
    predicted_labels: list[int],
) -> dict:
    """
    Calculate binary classification metrics.

    Label convention:
        1 = exception
        0 = normal

    Ground-truth labels must come from documented rules or
    independently verified records, not from model predictions.
    """
    if len(actual_labels) != len(predicted_labels):
        raise ValueError(
            "Actual and predicted labels must have equal lengths."
        )

    if not actual_labels:
        raise ValueError("At least one labeled record is required.")

    valid_labels = {0, 1}

    if not set(actual_labels).issubset(valid_labels):
        raise ValueError("Actual labels must contain only 0 or 1.")

    if not set(predicted_labels).issubset(valid_labels):
        raise ValueError("Predicted labels must contain only 0 or 1.")

    true_positive = sum(
        actual == 1 and predicted == 1
        for actual, predicted in zip(
            actual_labels,
            predicted_labels,
        )
    )

    true_negative = sum(
        actual == 0 and predicted == 0
        for actual, predicted in zip(
            actual_labels,
            predicted_labels,
        )
    )

    false_positive = sum(
        actual == 0 and predicted == 1
        for actual, predicted in zip(
            actual_labels,
            predicted_labels,
        )
    )

    false_negative = sum(
        actual == 1 and predicted == 0
        for actual, predicted in zip(
            actual_labels,
            predicted_labels,
        )
    )

    precision_denominator = true_positive + false_positive
    recall_denominator = true_positive + false_negative

    precision = (
        true_positive / precision_denominator
        if precision_denominator
        else 0.0
    )

    recall = (
        true_positive / recall_denominator
        if recall_denominator
        else 0.0
    )

    f1_score = (
        2 * precision * recall / (precision + recall)
        if precision + recall
        else 0.0
    )

    total = len(actual_labels)
    accuracy = (true_positive + true_negative) / total

    return {
        "records_evaluated": total,
        "true_positive": true_positive,
        "true_negative": true_negative,
        "false_positive": false_positive,
        "false_negative": false_negative,
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1_score": round(f1_score, 4),
        "accuracy": round(accuracy, 4),
    }
