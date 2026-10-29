
from pathlib import Path
import sqlite3

from database.connection import PROJECT_ROOT, get_connection


def validate_database(connection: sqlite3.Connection) -> dict:
    """Run database integrity and logistics business-rule checks."""

    issues = []

    def check(name, sql):
        count = connection.execute(sql).fetchone()[0]
        if count:
            issues.append({"check": name, "count": count})

    # 1. Foreign-key integrity
    foreign_key_errors = connection.execute(
        "PRAGMA foreign_key_check"
    ).fetchall()

    if foreign_key_errors:
        issues.append({
            "check": "foreign_key_violations",
            "count": len(foreign_key_errors),
        })

    # 2. Invalid shipment chronology
    check(
        "delivery_before_dispatch",
        """
        SELECT COUNT(*)
        FROM shipments
        WHERE dispatched_at IS NOT NULL
          AND delivered_at IS NOT NULL
          AND delivered_at < dispatched_at
        """,
    )

    # 3. Custody events without an actor
    check(
        "custody_event_missing_actor",
        """
        SELECT COUNT(*)
        FROM custody_events
        WHERE actor_id IS NULL
        """,
    )

    # 4. Repairs completed without a linked inspection
    check(
        "completed_repair_without_inspection",
        """
        SELECT COUNT(*)
        FROM repairs
        WHERE repair_status = 'Completed'
          AND inspection_id IS NULL
        """,
    )

    # 5. Repeated refunds for the same asset and return authorization
    check(
        "possible_duplicate_refunds",
        """
        SELECT COUNT(*)
        FROM (
            SELECT asset_id, rma_id
            FROM deposit_ledger
            WHERE transaction_type = 'Refund'
              AND rma_id IS NOT NULL
            GROUP BY asset_id, rma_id
            HAVING COUNT(*) > 1
        )
        """,
    )

    # 6. Shipment-asset bridge records with no matching asset
    check(
        "shipment_link_missing_asset",
        """
        SELECT COUNT(*)
        FROM shipment_assets sa
        LEFT JOIN reusable_assets a ON a.asset_id = sa.asset_id
        WHERE a.asset_id IS NULL
        """,
    )

    # 7. Custody events recorded in reverse chronological order
    # This checks adjacent event records within each asset's history.
    check(
        "custody_time_moves_backward",
        """
        SELECT COUNT(*)
        FROM (
            SELECT occurred_at,
                   LAG(occurred_at) OVER (
                       PARTITION BY asset_id
                       ORDER BY occurred_at, custody_event_id
                   ) AS previous_time
            FROM custody_events
        )
        WHERE previous_time IS NOT NULL
          AND occurred_at < previous_time
        """,
    )

    # 8. Assets with multiple different destinations at the same timestamp.
    # This is a candidate conflict, not definitive proof of a bad location.
    check(
        "possible_conflicting_custody_locations",
        """
        SELECT COUNT(*)
        FROM (
            SELECT asset_id, occurred_at
            FROM custody_events
            GROUP BY asset_id, occurred_at
            HAVING COUNT(DISTINCT to_location_id) > 1
        )
        """,
    )

    return {
        "passed": len(issues) == 0,
        "issue_count": len(issues),
        "issues": issues,
    }


def main():
    # Validate the permanent development database by default.
    # Optionally pass a generated database path.
    import argparse

    parser = argparse.ArgumentParser(
        description="Validate a reverse-logistics SQLite database."
    )
    parser.add_argument(
        "--db",
        default=str(PROJECT_ROOT / "data" / "reverse_logistics.db"),
        help="Path to the SQLite database to validate.",
    )
    args = parser.parse_args()

    database_path = Path(args.db).expanduser().resolve()

    if not database_path.exists():
        raise FileNotFoundError(
            f"Database not found: {database_path}"
        )

    connection = sqlite3.connect(database_path)
    connection.row_factory = sqlite3.Row

    try:
        connection.execute("PRAGMA foreign_keys = ON")
        result = validate_database(connection)

        print(f"Database: {database_path}")
        print(f"Checks passed: {result['passed']}")
        print(f"Issue categories found: {result['issue_count']}")

        if result["issues"]:
            for issue in result["issues"]:
                print(
                    f"- {issue['check']}: {issue['count']} record group(s)"
                )
        else:
            print("All validation checks passed.")

    finally:
        connection.close()


if __name__ == "__main__":
    main()
