
import argparse
import csv
import json
import sqlite3
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from src.services.evaluation_metrics import calculate_metrics


PROJECT_ROOT = Path(__file__).resolve().parents[2]

DEFAULT_DB = (
    PROJECT_ROOT
    / "data"
    / "generated"
    / "reverse_logistics_step16_test.db"
)

DEFAULT_LABELS = (
    PROJECT_ROOT
    / "data"
    / "evaluation"
    / "generated_ground_truth.csv"
)

DEFAULT_OUTPUT = (
    PROJECT_ROOT
    / "reports"
    / "ground_truth_evaluation.json"
)


def read_ground_truth(csv_path: Path) -> list[dict]:
    """Read and validate generated ground-truth labels."""
    if not csv_path.is_file():
        raise FileNotFoundError(
            f"Ground-truth CSV not found: {csv_path}"
        )

    records = []
    seen = set()

    with csv_path.open(
        "r",
        newline="",
        encoding="utf-8-sig",
    ) as file:
        reader = csv.DictReader(
            line for line in file if line.strip()
        )

        required = {"rule_name", "record_id", "actual_label"}

        if not reader.fieldnames:
            raise ValueError("Ground-truth CSV has no header.")

        reader.fieldnames = [
            field.strip() if field else ""
            for field in reader.fieldnames
        ]

        missing = required - set(reader.fieldnames)

        if missing:
            raise ValueError(
                f"Missing CSV columns: {sorted(missing)}"
            )

        for line_number, row in enumerate(reader, start=2):
            rule_name = (row.get("rule_name") or "").strip()
            record_id = (row.get("record_id") or "").strip()

            if not rule_name or not record_id:
                raise ValueError(
                    f"Missing rule or record ID near line {line_number}."
                )

            key = (rule_name, record_id)

            if key in seen:
                raise ValueError(f"Duplicate label: {key}")

            seen.add(key)

            try:
                label = int(row["actual_label"])
            except (TypeError, ValueError):
                raise ValueError(
                    f"Invalid actual_label near line {line_number}."
                ) from None

            if label not in (0, 1):
                raise ValueError(
                    f"Labels must be 0 or 1 near line {line_number}."
                )

            records.append({
                "rule_name": rule_name,
                "record_id": record_id,
                "actual_label": label,
            })

    if not records:
        raise ValueError("Ground-truth CSV contains no records.")

    return records


def load_predictions(connection: sqlite3.Connection) -> dict:
    """Run deterministic detectors against the source database."""

    predictions = {}

    # Detector 1: Shipment status explicitly marked Exception.
    for row in connection.execute(
        """
        SELECT shipment_id, shipment_status
        FROM shipments
        """
    ):
        predictions[("shipment_exception", row["shipment_id"])] = int(
            row["shipment_status"] == "Exception"
        )

    # Detector 2: Lost, damaged, or unusable assets.
    for row in connection.execute(
        """
        SELECT asset_id, asset_status, condition_status
        FROM reusable_assets
        """
    ):
        is_exception = (
            row["asset_status"] == "Lost"
            or row["condition_status"] in ("Damaged", "Unusable")
        )

        predictions[("asset_condition", row["asset_id"])] = int(
            is_exception
        )

    # Detector 3: Custody events without an assigned actor.
    for row in connection.execute(
        """
        SELECT custody_event_id, actor_id
        FROM custody_events
        """
    ):
        predictions[("custody_missing_actor", row["custody_event_id"])] = int(
            row["actor_id"] is None
        )

    return predictions


def evaluate_labels(
    labels: list[dict],
    predictions: dict,
) -> dict:
    """Compare ground-truth labels with matching detector predictions."""

    grouped = defaultdict(list)
    missing_predictions = []

    for label in labels:
        key = (label["rule_name"], label["record_id"])

        if key not in predictions:
            missing_predictions.append({
                "rule_name": label["rule_name"],
                "record_id": label["record_id"],
            })
            continue

        grouped[label["rule_name"]].append({
            "record_id": label["record_id"],
            "actual": label["actual_label"],
            "predicted": predictions[key],
        })

    if missing_predictions:
        examples = missing_predictions[:10]
        raise ValueError(
            f"{len(missing_predictions)} labeled records have no "
            f"matching database prediction. Examples: {examples}"
        )

    if not grouped:
        raise ValueError("No matching labels and predictions were found.")

    all_records = [
        record
        for rule_records in grouped.values()
        for record in rule_records
    ]

    overall = calculate_metrics(
        [record["actual"] for record in all_records],
        [record["predicted"] for record in all_records],
    )

    per_rule = {}

    for rule_name, rule_records in sorted(grouped.items()):
        per_rule[rule_name] = calculate_metrics(
            [record["actual"] for record in rule_records],
            [record["predicted"] for record in rule_records],
        )

    return {
        "records_evaluated": len(all_records),
        "overall": overall,
        "per_rule": per_rule,
    }


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Evaluate deterministic logistics detectors "
            "against generated ground-truth labels."
        )
    )

    parser.add_argument(
        "--db",
        default=str(DEFAULT_DB),
        help="Path to the generated SQLite database.",
    )

    parser.add_argument(
        "--labels",
        default=str(DEFAULT_LABELS),
        help="Path to the ground-truth CSV.",
    )

    parser.add_argument(
        "--output",
        default=str(DEFAULT_OUTPUT),
        help="Path to the JSON report.",
    )

    args = parser.parse_args()

    db_path = Path(args.db).expanduser().resolve()
    labels_path = Path(args.labels).expanduser().resolve()
    output_path = Path(args.output).expanduser().resolve()

    if not db_path.is_file():
        raise FileNotFoundError(f"Database not found: {db_path}")

    labels = read_ground_truth(labels_path)

    # Open source data read-only. No database changes are made.
    db_uri = db_path.as_uri() + "?mode=ro"

    with sqlite3.connect(db_uri, uri=True) as connection:
        connection.row_factory = sqlite3.Row
        predictions = load_predictions(connection)

    evaluation = evaluate_labels(labels, predictions)

    report = {
        "generated_at_utc": datetime.now(
            timezone.utc
        ).isoformat(),
        "database_path": str(db_path),
        "ground_truth_path": str(labels_path),
        "evaluation_scope": (
            "Synthetic records evaluated against documented "
            "deterministic business rules."
        ),
        "independence_warning": (
            "The generated labels and predictions use the same "
            "business-rule definitions. Perfect scores demonstrate "
            "implementation consistency, not independent real-world "
            "detection accuracy."
        ),
        **evaluation,
    }

    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    output_path.write_text(
        json.dumps(report, indent=2),
        encoding="utf-8",
    )

    print("\nGround-truth evaluation completed.")
    print(f"Database: {db_path}")
    print(f"Labels: {labels_path}")
    print(f"Report: {output_path}")
    print(f"Records evaluated: {report['records_evaluated']}")

    print("\nOverall metrics:")
    for name, value in report["overall"].items():
        print(f"- {name}: {value}")

    print("\nPer-rule metrics:")
    for rule_name, metrics in report["per_rule"].items():
        print(f"\n{rule_name}")
        for name, value in metrics.items():
            print(f"  {name}: {value}")


if __name__ == "__main__":
    main()
