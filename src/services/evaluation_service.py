
from pathlib import Path
import argparse
import json
import sqlite3
from datetime import datetime, timezone

import pandas as pd

from src.services.dashboard_service import (
    find_delayed_shipments,
    find_exception_shipments,
    find_asset_exceptions,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]

DEFAULT_DB = (
    PROJECT_ROOT
    / "data"
    / "generated"
    / "reverse_logistics_step16_test.db"
)

DEFAULT_REPORT = (
    PROJECT_ROOT
    / "reports"
    / "exception_evaluation.json"
)


def read_query(
    connection: sqlite3.Connection,
    query: str,
    params: tuple = (),
) -> pd.DataFrame:
    """Load a query result into a DataFrame."""
    return pd.read_sql_query(query, connection, params=params)


def evaluate_database(
    connection: sqlite3.Connection,
    delay_days: int,
) -> dict:
    """Calculate deterministic operational exception metrics."""

    if delay_days < 0:
        raise ValueError("delay_days cannot be negative.")

    shipment_details = read_query(
        connection,
        """
        SELECT
            shipment_id,
            shipment_status,
            dispatched_at,
            delivered_at,
            ROUND(
                julianday('now') - julianday(dispatched_at),
                1
            ) AS days_since_dispatch
        FROM shipments
        ORDER BY shipment_id
        """,
    )

    asset_details = read_query(
        connection,
        """
        SELECT
            asset_id,
            asset_status,
            condition_status
        FROM reusable_assets
        ORDER BY asset_id
        """,
    )

    missing_actor_events = read_query(
        connection,
        """
        SELECT custody_event_id
        FROM custody_events
        WHERE actor_id IS NULL
        """,
    )

    conflicting_custody = read_query(
        connection,
        """
        SELECT asset_id, occurred_at
        FROM custody_events
        GROUP BY asset_id, occurred_at
        HAVING COUNT(DISTINCT to_location_id) > 1
        """,
    )

    shipment_exception_count = len(
        find_exception_shipments(shipment_details)
    )

    delayed_shipment_count = len(
        find_delayed_shipments(
            shipment_details,
            delay_days,
        )
    )

    asset_exception_count = len(
        find_asset_exceptions(asset_details)
    )

    status_counts = (
        shipment_details["shipment_status"]
        .value_counts(dropna=False)
        .to_dict()
    )

    asset_status_counts = (
        asset_details["asset_status"]
        .value_counts(dropna=False)
        .to_dict()
    )

    condition_counts = (
        asset_details["condition_status"]
        .value_counts(dropna=False)
        .to_dict()
    )

    return {
        "generated_at_utc": datetime.now(
            timezone.utc
        ).isoformat(),
        "database": "SQLite",
        "delay_threshold_days": delay_days,
        "scope": {
            "total_shipments": int(len(shipment_details)),
            "total_assets": int(len(asset_details)),
            "total_custody_events": int(
                connection.execute(
                    "SELECT COUNT(*) FROM custody_events"
                ).fetchone()[0]
            ),
        },
        "shipment_status_counts": {
            str(key): int(value)
            for key, value in status_counts.items()
        },
        "asset_status_counts": {
            str(key): int(value)
            for key, value in asset_status_counts.items()
        },
        "asset_condition_counts": {
            str(key): int(value)
            for key, value in condition_counts.items()
        },
        "exception_metrics": {
            "exception_status_shipments": int(
                shipment_exception_count
            ),
            "potentially_delayed_shipments": int(
                delayed_shipment_count
            ),
            "lost_or_damaged_assets": int(
                asset_exception_count
            ),
            "custody_events_missing_actor": int(
                len(missing_actor_events)
            ),
            "potentially_conflicting_custody_groups": int(
                len(conflicting_custody)
            ),
        },
        "evaluation_note": (
            "These are deterministic rule-triggered counts, "
            "not precision, recall, or proven detection accuracy. "
            "Potential delays use current age since dispatch, "
            "not a promised delivery deadline. "
            "Asset exceptions include lost assets and assets "
            "marked Damaged or Unusable."
        ),
    }


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Evaluate operational exception counts "
            "in a reverse-logistics SQLite database."
        )
    )

    parser.add_argument(
        "--db",
        default=str(DEFAULT_DB),
        help="Path to the generated SQLite database.",
    )

    parser.add_argument(
        "--delay-days",
        type=int,
        default=3,
        help="Flag active shipments older than this many days.",
    )

    parser.add_argument(
        "--output",
        default=str(DEFAULT_REPORT),
        help="Path for the JSON evaluation report.",
    )

    args = parser.parse_args()

    db_path = Path(args.db).expanduser().resolve()
    output_path = Path(args.output).expanduser().resolve()

    if not db_path.is_file():
        raise FileNotFoundError(
            f"Database not found: {db_path}"
        )

    if args.delay_days < 0:
        parser.error("--delay-days cannot be negative.")

    # Open the database in read-only mode.
    database_uri = db_path.as_uri() + "?mode=ro"

    with sqlite3.connect(
        database_uri,
        uri=True,
    ) as connection:
        report = evaluate_database(
            connection,
            args.delay_days,
        )

    report["database_path"] = str(db_path)

    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    output_path.write_text(
        json.dumps(report, indent=2),
        encoding="utf-8",
    )

    print("\nReverse Logistics Exception Evaluation")
    print("=" * 42)
    print(f"Database: {db_path}")
    print(f"Report:   {output_path}")
    print(
        f"Shipments: "
        f"{report['scope']['total_shipments']}"
    )
    print(
        f"Assets: "
        f"{report['scope']['total_assets']}"
    )
    print(
        f"Custody events: "
        f"{report['scope']['total_custody_events']}"
    )

    print("\nException metrics:")

    for name, count in report["exception_metrics"].items():
        print(f"- {name}: {count}")

    print("\nEvaluation report created successfully.")


if __name__ == "__main__":
    main()
