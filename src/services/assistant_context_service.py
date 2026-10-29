
"""Read-only operational context for the local Qwen RAG assistant."""

import sqlite3
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]

DEFAULT_DB = (
    PROJECT_ROOT
    / "data"
    / "generated"
    / "custody_consistent_100k.db"
)

SHIPMENT_DELAY_THRESHOLD_DAYS = 3


def _read_query(connection, query, params=()):
    """Run a SELECT query and return dictionaries."""
    cursor = connection.execute(query, params)
    columns = [column[0] for column in cursor.description]
    return [
        dict(zip(columns, row))
        for row in cursor.fetchall()
    ]


def build_operational_context(db_path=None):
    """Build a bounded, read-only snapshot of operational facts."""

    database = Path(db_path) if db_path else DEFAULT_DB

    if not database.is_file():
        raise FileNotFoundError(
            "Operational database not found: {}".format(database)
        )

    uri = database.resolve().as_uri() + "?mode=ro"

    with sqlite3.connect(uri, uri=True, timeout=5) as connection:
        connection.row_factory = sqlite3.Row

        asset_status_counts = _read_query(
            connection,
            """
            SELECT asset_status, condition_status, COUNT(*) AS total
            FROM reusable_assets
            GROUP BY asset_status, condition_status
            ORDER BY total DESC
            """,
        )

        shipment_status_counts = _read_query(
            connection,
            """
            SELECT shipment_status, COUNT(*) AS total
            FROM shipments
            GROUP BY shipment_status
            ORDER BY total DESC
            """,
        )

        asset_exceptions = _read_query(
            connection,
            """
            SELECT
                a.asset_id,
                t.type_name AS asset_type,
                a.asset_status,
                a.condition_status,
                l.location_name AS current_location,
                o.owner_name AS owner
            FROM reusable_assets a
            JOIN asset_types t
                ON t.asset_type_id = a.asset_type_id
            JOIN owners o
                ON o.owner_id = a.owner_id
            LEFT JOIN locations l
                ON l.location_id = a.current_location_id
            WHERE LOWER(TRIM(a.asset_status)) = 'lost'
               OR LOWER(TRIM(a.condition_status))
                    IN ('damaged', 'unusable')
            ORDER BY a.asset_id
            LIMIT 20
            """,
        )

        shipment_exceptions = _read_query(
            connection,
            """
            SELECT
                s.shipment_id,
                s.shipment_status,
                origin.location_name AS origin,
                destination.location_name AS destination,
                s.dispatched_at,
                s.delivered_at
            FROM shipments s
            JOIN locations origin
                ON origin.location_id = s.origin_location_id
            JOIN locations destination
                ON destination.location_id = s.destination_location_id
            WHERE LOWER(TRIM(s.shipment_status)) = 'exception'
            ORDER BY s.created_at DESC
            LIMIT 20
            """,
        )

        potentially_delayed_shipments = _read_query(
            connection,
            """
            SELECT
                s.shipment_id,
                s.shipment_status,
                origin.location_name AS origin,
                destination.location_name AS destination,
                s.dispatched_at,
                s.delivered_at,
                ROUND(
                    julianday('now') - julianday(s.dispatched_at),
                    1
                ) AS days_since_dispatch
            FROM shipments s
            JOIN locations origin
                ON origin.location_id = s.origin_location_id
            JOIN locations destination
                ON destination.location_id = s.destination_location_id
            WHERE LOWER(TRIM(s.shipment_status))
                    IN ('dispatched', 'in transit')
              AND s.dispatched_at IS NOT NULL
              AND ROUND(
                    julianday('now') - julianday(s.dispatched_at),
                    1
                  ) > ?
            ORDER BY s.dispatched_at ASC, s.shipment_id
            LIMIT 20
            """,
            (SHIPMENT_DELAY_THRESHOLD_DAYS,),
        )

        return_status_counts = _read_query(
            connection,
            """
            SELECT return_status, COUNT(*) AS total
            FROM return_authorizations
            GROUP BY return_status
            ORDER BY total DESC
            """,
        )

        repair_summary = _read_query(
            connection,
            """
            SELECT
                repair_status,
                COUNT(*) AS total,
                COALESCE(SUM(repair_cost), 0) AS repair_cost
            FROM repairs
            GROUP BY repair_status
            ORDER BY total DESC
            """,
        )

        inspection_status_counts = _read_query(
            connection,
            """
            SELECT inspection_status, COUNT(*) AS total
            FROM inspections
            GROUP BY inspection_status
            ORDER BY total DESC
            """,
        )

        missing_actor_events = _read_query(
            connection,
            """
            SELECT
                custody_event_id,
                asset_id,
                shipment_id,
                event_type,
                occurred_at
            FROM custody_events
            WHERE actor_id IS NULL
            ORDER BY occurred_at DESC
            LIMIT 20
            """,
        )

        conflicting_custody = _read_query(
            connection,
            """
            SELECT
                asset_id,
                occurred_at,
                COUNT(*) AS event_count,
                COUNT(DISTINCT to_location_id) AS destination_count
            FROM custody_events
            GROUP BY asset_id, occurred_at
            HAVING COUNT(DISTINCT to_location_id) > 1
            ORDER BY occurred_at DESC
            LIMIT 20
            """,
        )

    return {
        "data_source": database.name,
        "read_only": True,
        "shipment_delay_threshold_days":
            SHIPMENT_DELAY_THRESHOLD_DAYS,
        "asset_status_counts": asset_status_counts,
        "shipment_status_counts": shipment_status_counts,
        "asset_exceptions": asset_exceptions,
        "shipment_exceptions": shipment_exceptions,
        "potentially_delayed_shipments":
            potentially_delayed_shipments,
        "return_status_counts": return_status_counts,
        "repair_summary": repair_summary,
        "inspection_status_counts": inspection_status_counts,
        "custody_events_missing_actor": missing_actor_events,
        "conflicting_custody_destinations": conflicting_custody,
        "limitations": [
            "Exception and investigation record lists are limited to 20 records.",
            "Potentially delayed shipments are limited to 20 records.",
            "Summary counts cover all records in their respective tables.",
            "Potential delay is an age-based indicator, not proof of a missed delivery commitment.",
            "Only the explicitly included data is available to the assistant.",
            "No database changes are performed.",
        ],
    }
