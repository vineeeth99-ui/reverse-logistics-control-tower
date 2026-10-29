
import argparse
import csv
import sqlite3
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]

DEFAULT_DB = (
    PROJECT_ROOT
    / "data"
    / "generated"
    / "reverse_logistics_step16_test.db"
)

DEFAULT_OUTPUT = (
    PROJECT_ROOT
    / "data"
    / "evaluation"
    / "generated_ground_truth.csv"
)


def generate_labels(connection: sqlite3.Connection) -> list[dict]:
    """
    Create rule-based labels from documented synthetic-data rules.

    Important:
    These labels are trustworthy only for rules explicitly encoded
    here. They do not establish general real-world exception accuracy.
    """
    labels = []

    # Rule 1: Shipment status explicitly marked Exception.
    shipments = connection.execute(
        """
        SELECT shipment_id, shipment_status
        FROM shipments
        ORDER BY shipment_id
        """
    ).fetchall()

    for row in shipments:
        labels.append({
            "rule_name": "shipment_exception",
            "record_id": row["shipment_id"],
            "actual_label": int(
                row["shipment_status"] == "Exception"
            ),
        })

    # Rule 2: Assets considered exceptions if lost, damaged, or unusable.
    assets = connection.execute(
        """
        SELECT asset_id, asset_status, condition_status
        FROM reusable_assets
        ORDER BY asset_id
        """
    ).fetchall()

    for row in assets:
        is_exception = (
            row["asset_status"] == "Lost"
            or row["condition_status"] in ("Damaged", "Unusable")
        )

        labels.append({
            "rule_name": "asset_condition",
            "record_id": row["asset_id"],
            "actual_label": int(is_exception),
        })

    # Rule 3: Custody events missing an assigned actor.
    custody_events = connection.execute(
        """
        SELECT custody_event_id, actor_id
        FROM custody_events
        ORDER BY custody_event_id
        """
    ).fetchall()

    for row in custody_events:
        labels.append({
            "rule_name": "custody_missing_actor",
            "record_id": row["custody_event_id"],
            "actual_label": int(row["actor_id"] is None),
        })

    return labels


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Generate documented ground-truth labels from "
            "synthetic logistics database records."
        )
    )

    parser.add_argument(
        "--db",
        default=str(DEFAULT_DB),
        help="Path to the generated SQLite database.",
    )

    parser.add_argument(
        "--output",
        default=str(DEFAULT_OUTPUT),
        help="Path for the new labeled CSV file.",
    )

    args = parser.parse_args()

    db_path = Path(args.db).expanduser().resolve()
    output_path = Path(args.output).expanduser().resolve()

    if not db_path.is_file():
        raise FileNotFoundError(
            f"Database not found: {db_path}"
        )

    # Do not overwrite an existing file.
    if output_path.exists():
        raise FileExistsError(
            f"Output already exists: {output_path}\n"
            "Choose a different --output path to preserve existing data."
        )

    database_uri = db_path.as_uri() + "?mode=ro"

    with sqlite3.connect(
        database_uri,
        uri=True,
    ) as connection:
        connection.row_factory = sqlite3.Row
        labels = generate_labels(connection)

    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with output_path.open(
        "w",
        newline="",
        encoding="utf-8",
    ) as file:
        writer = csv.DictWriter(
            file,
            fieldnames=[
                "rule_name",
                "record_id",
                "actual_label",
            ],
        )
        writer.writeheader()
        writer.writerows(labels)

    print("Ground-truth label generation completed.")
    print(f"Source database: {db_path}")
    print(f"Output CSV: {output_path}")
    print(f"Total labeled records: {len(labels)}")

    counts = {}

    for row in labels:
        rule = row["rule_name"]
        counts[rule] = counts.get(rule, 0) + 1

    print("\nRecords per rule:")
    for rule, count in sorted(counts.items()):
        print(f"- {rule}: {count}")


if __name__ == "__main__":
    main()
