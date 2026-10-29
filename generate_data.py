
import argparse
import random
import sqlite3
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

from database.connection import PROJECT_ROOT, SCHEMA_PATH


DEFAULT_SEED = 20261022

TABLES = (
    "asset_types",
    "owners",
    "locations",
    "actors",
    "reusable_assets",
    "shipments",
    "shipment_assets",
    "custody_events",
    "return_authorizations",
    "inspections",
    "repairs",
    "deposit_ledger",
)


def validate_dataset(connection, expected_counts=None):
    """Validate database integrity, business rules and custody history."""
    errors = []
    warnings = []

    foreign_key_errors = connection.execute(
        "PRAGMA foreign_key_check"
    ).fetchall()

    if foreign_key_errors:
        errors.append(
            "Foreign-key violations: {}".format(
                len(foreign_key_errors)
            )
        )

    integrity = connection.execute(
        "PRAGMA integrity_check"
    ).fetchone()[0]

    if integrity != "ok":
        errors.append("SQLite integrity check: {}".format(integrity))

    counts = {}

    for table in TABLES:
        counts[table] = connection.execute(
            "SELECT COUNT(*) FROM {}".format(table)
        ).fetchone()[0]

    for table, expected in (expected_counts or {}).items():
        if counts.get(table) != expected:
            errors.append(
                "{} count: expected {}, got {}".format(
                    table, expected, counts.get(table)
                )
            )

    for table in ("asset_types", "owners", "locations", "actors"):
        if counts[table] == 0:
            errors.append("Required master table is empty: " + table)

    checks = [
        (
            "Delivered shipment timestamps",
            """
            SELECT COUNT(*) FROM shipments
            WHERE shipment_status = 'Delivered'
              AND (dispatched_at IS NULL OR delivered_at IS NULL)
            """,
        ),
        (
            "Invalid delivery timestamp on non-delivered shipment",
            """
            SELECT COUNT(*) FROM shipments
            WHERE shipment_status != 'Delivered'
              AND delivered_at IS NOT NULL
            """,
        ),
        (
            "Created shipment has dispatch timestamp",
            """
            SELECT COUNT(*) FROM shipments
            WHERE shipment_status = 'Created'
              AND dispatched_at IS NOT NULL
            """,
        ),
        (
            "In-transit shipment timestamps",
            """
            SELECT COUNT(*) FROM shipments
            WHERE shipment_status = 'In Transit'
              AND (dispatched_at IS NULL OR delivered_at IS NOT NULL)
            """,
        ),
        (
            "Invalid shipment-asset timestamp order",
            """
            SELECT COUNT(*) FROM shipment_assets
            WHERE loaded_at IS NOT NULL
              AND unloaded_at IS NOT NULL
              AND unloaded_at < loaded_at
            """,
        ),
        (
            "Approved return missing approval time",
            """
            SELECT COUNT(*) FROM return_authorizations
            WHERE return_status IN
                  ('Approved', 'In Transit', 'Received', 'Closed')
              AND approved_at IS NULL
            """,
        ),
        (
            "Received return missing receipt time",
            """
            SELECT COUNT(*) FROM return_authorizations
            WHERE return_status = 'Received'
              AND received_at IS NULL
            """,
        ),
        (
            "Non-received return has receipt time",
            """
            SELECT COUNT(*) FROM return_authorizations
            WHERE return_status != 'Received'
              AND received_at IS NOT NULL
            """,
        ),
        (
            "Inspection status conflicts with condition",
            """
            SELECT COUNT(*) FROM inspections
            WHERE (
                inspection_status = 'Failed'
                AND condition_found NOT IN ('Damaged', 'Unusable')
            ) OR (
                inspection_status = 'Passed'
                AND condition_found IN ('Damaged', 'Unusable')
            )
            """,
        ),
        (
            "Completed repair missing close time",
            """
            SELECT COUNT(*) FROM repairs
            WHERE repair_status = 'Completed'
              AND closed_at IS NULL
            """,
        ),
        (
            "Open repair has close time",
            """
            SELECT COUNT(*) FROM repairs
            WHERE repair_status = 'Open'
              AND closed_at IS NOT NULL
            """,
        ),
        (
            "Custody event linked to unrelated shipment asset",
            """
            SELECT COUNT(*)
            FROM custody_events ce
            WHERE ce.shipment_id IS NOT NULL
              AND NOT EXISTS (
                  SELECT 1 FROM shipment_assets sa
                  WHERE sa.shipment_id = ce.shipment_id
                    AND sa.asset_id = ce.asset_id
              )
            """,
        ),
        (
            "Deposit asset differs from return asset",
            """
            SELECT COUNT(*)
            FROM deposit_ledger dl
            JOIN return_authorizations ra ON ra.rma_id = dl.rma_id
            WHERE dl.asset_id != ra.asset_id
            """,
        ),
        (
            "Refunds exceed deposit charges",
            """
            SELECT COUNT(*) FROM (
                SELECT rma_id,
                    SUM(CASE WHEN transaction_type = 'Charge'
                             THEN amount ELSE 0 END) AS charges,
                    SUM(CASE WHEN transaction_type = 'Refund'
                             THEN amount ELSE 0 END) AS refunds
                FROM deposit_ledger
                WHERE rma_id IS NOT NULL
                GROUP BY rma_id
                HAVING refunds > charges + 0.00001
            )
            """,
        ),
    ]

    for description, sql in checks:
        failures = connection.execute(sql).fetchone()[0]
        if failures:
            errors.append(
                "{}: {} row(s)".format(description, failures)
            )

    assets_without_history = connection.execute(
        """
        SELECT COUNT(*)
        FROM reusable_assets a
        WHERE NOT EXISTS (
            SELECT 1 FROM custody_events ce
            WHERE ce.asset_id = a.asset_id
        )
        """
    ).fetchone()[0]

    location_mismatches = connection.execute(
        """
        SELECT COUNT(*)
        FROM reusable_assets a
        JOIN (
            SELECT asset_id, to_location_id,
                   ROW_NUMBER() OVER (
                       PARTITION BY asset_id
                       ORDER BY occurred_at DESC, custody_event_id DESC
                   ) AS rn
            FROM custody_events
        ) latest
          ON latest.asset_id = a.asset_id AND latest.rn = 1
        WHERE a.current_location_id IS NOT latest.to_location_id
        """
    ).fetchone()[0]

    custody_gaps = connection.execute(
        """
        SELECT COUNT(*) FROM (
            SELECT asset_id, from_location_id,
                   LAG(to_location_id) OVER (
                       PARTITION BY asset_id
                       ORDER BY occurred_at, custody_event_id
                   ) AS previous_to_location_id
            FROM custody_events
        )
        WHERE previous_to_location_id IS NOT NULL
          AND from_location_id IS NOT previous_to_location_id
        """
    ).fetchone()[0]

    if assets_without_history:
        warnings.append(
            "Assets without custody events: {}".format(
                assets_without_history
            )
        )

    if location_mismatches:
        errors.append(
            "Current-location mismatches: {}".format(location_mismatches)
        )

    if custody_gaps:
        errors.append(
            "Custody transition gaps: {}".format(custody_gaps)
        )

    return errors, warnings, counts


def print_validation_report(connection, expected_counts=None):
    errors, warnings, counts = validate_dataset(
        connection, expected_counts
    )

    print("\nValidation report")
    print(
        "Database integrity: {}".format(
            "PASS"
            if connection.execute(
                "PRAGMA integrity_check"
            ).fetchone()[0] == "ok"
            else "FAIL"
        )
    )
    print(
        "Foreign-key validation: {}".format(
            "PASS"
            if not connection.execute(
                "PRAGMA foreign_key_check"
            ).fetchall()
            else "FAIL"
        )
    )

    for warning in warnings:
        print("WARNING: " + warning)

    for error in errors:
        print("ERROR: " + error)

    if errors:
        raise RuntimeError(
            "Synthetic data validation failed. See errors above."
        )

    print("Business lifecycle checks: PASS")
    print("Custody consistency checks: PASS")
    print("Expected record counts: PASS")

    return counts


def generate_dataset(
    output,
    asset_count,
    shipment_count,
    event_count,
    seed,
):
    """Generate deterministic synthetic reverse-logistics data."""

    if min(asset_count, shipment_count, event_count) < 1:
        raise ValueError("All record counts must be at least 1.")

    output = Path(output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)

    if output.exists():
        raise FileExistsError(
            "Output already exists: {}\n"
            "Choose a new --output filename.".format(output)
        )

    rng = random.Random(seed)
    connection = sqlite3.connect(str(output))
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")

    try:
        connection.executescript(
            SCHEMA_PATH.read_text(encoding="utf-8")
        )

        with connection:
            # 1. Master data
            connection.executemany(
                """
                INSERT INTO asset_types (type_name, description)
                VALUES (?, ?)
                """,
                [
                    ("Pallet", "Reusable transport pallet"),
                    ("Container", "Reusable shipping container"),
                    ("Crate", "Reusable transport crate"),
                ],
            )

            connection.executemany(
                """
                INSERT INTO owners (owner_name, owner_type)
                VALUES (?, ?)
                """,
                [
                    ("Supplier A", "Supplier"),
                    ("Supplier B", "Supplier"),
                    ("Example Logistics Ltd", "Company"),
                ],
            )

            connection.executemany(
                """
                INSERT INTO locations
                    (location_name, location_type, city, country)
                VALUES (?, ?, ?, ?)
                """,
                [
                    ("Chennai Warehouse", "Warehouse",
                     "Chennai", "India"),
                    ("Bengaluru Distribution Center",
                     "Distribution Center", "Bengaluru", "India"),
                    ("Hyderabad Warehouse", "Warehouse",
                     "Hyderabad", "India"),
                    ("Supplier Site", "Supplier Site",
                     "Chennai", "India"),
                    ("Repair Center", "Repair Center",
                     "Bengaluru", "India"),
                ],
            )

            connection.executemany(
                """
                INSERT INTO actors (actor_name, role, organization)
                VALUES (?, ?, ?)
                """,
                [
                    ("Supplier Operator", "Supplier", "Supplier A"),
                    ("Sample Planner", "Planner", "Example Logistics Ltd"),
                    ("Carrier Operator", "Carrier Operator", "Carrier Co"),
                    ("Warehouse Operator", "Warehouse Operator",
                     "Example Logistics Ltd"),
                    ("Logistics Analyst", "Logistics Analyst",
                     "Example Logistics Ltd"),
                    ("Operations Manager", "Operations Manager",
                     "Example Logistics Ltd"),
                ],
            )

            type_ids = [
                row[0] for row in connection.execute(
                    "SELECT asset_type_id FROM asset_types ORDER BY 1"
                )
            ]
            owner_ids = [
                row[0] for row in connection.execute(
                    "SELECT owner_id FROM owners ORDER BY 1"
                )
            ]
            location_ids = [
                row[0] for row in connection.execute(
                    "SELECT location_id FROM locations ORDER BY 1"
                )
            ]
            actor_ids = [
                row[0] for row in connection.execute(
                    "SELECT actor_id FROM actors ORDER BY 1"
                )
            ]

            base_time = datetime(2026, 1, 1)

            # 2. Assets: keep each initial location for custody generation.
            asset_ids = [
                "ASSET-{:07d}".format(n)
                for n in range(1, asset_count + 1)
            ]
            initial_location_by_asset = {}
            asset_rows = []

            for asset_id in asset_ids:
                initial_location = rng.choice(location_ids)
                initial_location_by_asset[asset_id] = initial_location

                asset_rows.append(
                    (
                        asset_id,
                        rng.choice(type_ids),
                        rng.choice(owner_ids),
                        initial_location,
                        rng.choice(
                            ["Available", "In Transit", "In Use", "Returned"]
                        ),
                        rng.choice(["New", "Good", "Good", "Damaged"]),
                        "2026-01-01",
                        "2026-01-01T00:00:00",
                    )
                )

            connection.executemany(
                """
                INSERT INTO reusable_assets
                    (asset_id, asset_type_id, owner_id,
                     current_location_id, asset_status,
                     condition_status, acquired_at, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                asset_rows,
            )

            # 3. Shipments: deterministic timestamps, no CURRENT_TIMESTAMP.
            shipment_ids = [
                "SHP-2026-{:06d}".format(n)
                for n in range(1, shipment_count + 1)
            ]
            shipment_rows = []

            for shipment_id in shipment_ids:
                origin, destination = rng.sample(location_ids, 2)
                dispatched = rng.random() < 0.8
                delivered = dispatched and rng.random() < 0.65

                dispatch_time = base_time + timedelta(
                    days=rng.randint(0, 180),
                    hours=rng.randint(0, 23),
                )
                delivery_time = (
                    dispatch_time + timedelta(hours=rng.randint(2, 72))
                    if delivered else None
                )

                status = (
                    "Delivered" if delivered
                    else "In Transit" if dispatched
                    else "Created"
                )

                shipment_rows.append(
                    (
                        shipment_id,
                        origin,
                        destination,
                        status,
                        dispatch_time.isoformat() if dispatched else None,
                        delivery_time.isoformat() if delivered else None,
                        base_time.isoformat(),
                    )
                )

            connection.executemany(
                """
                INSERT INTO shipments
                    (shipment_id, origin_location_id,
                     destination_location_id, shipment_status,
                     dispatched_at, delivered_at, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                shipment_rows,
            )

            # 4. Shipment-asset links.
            linked_pairs = []
            linked_set = set()
            links = []

            for shipment_id in shipment_ids:
                asset_id = rng.choice(asset_ids)
                pair = (shipment_id, asset_id)
                linked_pairs.append(pair)
                linked_set.add(pair)
                links.append((shipment_id, asset_id, 1))

            for _ in range(max(shipment_count, asset_count // 2)):
                pair = (
                    rng.choice(shipment_ids),
                    rng.choice(asset_ids),
                )
                if pair not in linked_set:
                    linked_set.add(pair)
                    linked_pairs.append(pair)
                    links.append((pair[0], pair[1], 1))

            connection.executemany(
                """
                INSERT INTO shipment_assets
                    (shipment_id, asset_id, quantity)
                VALUES (?, ?, ?)
                """,
                links,
            )

            shipments_by_asset = defaultdict(list)
            for shipment_id, asset_id in linked_pairs:
                shipments_by_asset[asset_id].append(shipment_id)

            # 5. Custody events.
            # Assign one event to distinct assets first. With 20,000 assets
            # and 10,000 events, 10,000 assets will have no event.
            assigned_event_assets = asset_ids[
                :min(event_count, asset_count)
            ]

            remaining_events = event_count - len(assigned_event_assets)
            if remaining_events > 0:
                assigned_event_assets.extend(
                    rng.choice(asset_ids)
                    for _ in range(remaining_events)
                )

            asset_event_counts = defaultdict(int)
            asset_last_time = defaultdict(lambda: base_time)
            asset_last_location = {}
            event_rows = []

            for asset_id in assigned_event_assets:
                asset_event_counts[asset_id] += 1
                event_number = asset_event_counts[asset_id]

                event_id = "CUST-{}-{:06d}".format(
                    asset_id, event_number
                )

                occurred_at = asset_last_time[asset_id] + timedelta(
                    minutes=rng.randint(5, 120)
                )
                asset_last_time[asset_id] = occurred_at

                from_location = asset_last_location.get(
                    asset_id,
                    initial_location_by_asset[asset_id],
                )

                possible_destinations = [
                    location_id for location_id in location_ids
                    if location_id != from_location
                ]
                to_location = rng.choice(possible_destinations)
                asset_last_location[asset_id] = to_location

                event_type = rng.choice(
                    ["Created", "Dispatched", "Received", "Transferred"]
                )

                candidates = shipments_by_asset.get(asset_id, [])
                shipment_id = (
                    rng.choice(candidates)
                    if candidates and rng.random() < 0.8
                    else None
                )

                event_rows.append(
                    (
                        event_id,
                        asset_id,
                        shipment_id,
                        rng.choice(actor_ids),
                        from_location,
                        to_location,
                        event_type,
                        occurred_at.isoformat(),
                        (occurred_at + timedelta(minutes=5)).isoformat(),
                        "Synthetic generated event",
                    )
                )

            connection.executemany(
                """
                INSERT INTO custody_events
                    (custody_event_id, asset_id, shipment_id, actor_id,
                     from_location_id, to_location_id, event_type,
                     occurred_at, recorded_at, notes)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                event_rows,
            )

            # Current location matches each asset's latest custody event.
            for asset_id, final_location in asset_last_location.items():
                connection.execute(
                    """
                    UPDATE reusable_assets
                    SET current_location_id = ?
                    WHERE asset_id = ?
                    """,
                    (final_location, asset_id),
                )

            # 6. Return authorizations.
            return_count = min(max(1, asset_count // 3), asset_count)
            return_rows = []
            return_details = {}

            for number, asset_id in enumerate(
                asset_ids[:return_count], start=1
            ):
                requested_at = base_time + timedelta(
                    days=rng.randint(30, 180)
                )
                status = rng.choice(
                    ["Requested", "Approved", "In Transit", "Received"]
                )

                received_at = (
                    requested_at + timedelta(days=rng.randint(1, 10))
                    if status == "Received" else None
                )
                approved_at = (
                    requested_at + timedelta(hours=2)
                    if status != "Requested" else None
                )
                rma_id = "RMA-2026-{:06d}".format(number)

                return_rows.append(
                    (
                        rma_id,
                        asset_id,
                        actor_ids[1],
                        rng.choice(location_ids),
                        status,
                        requested_at.isoformat(),
                        approved_at.isoformat() if approved_at else None,
                        received_at.isoformat() if received_at else None,
                        requested_at.isoformat(),
                    )
                )
                return_details[rma_id] = {
                    "asset_id": asset_id,
                    "status": status,
                    "received_at": received_at,
                }

            connection.executemany(
                """
                INSERT INTO return_authorizations
                    (rma_id, asset_id, requested_by,
                     return_location_id, return_status, requested_at,
                     approved_at, received_at, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                return_rows,
            )

            # 7. Inspections for received returns.
            inspection_rows = []
            inspection_number = 0

            for rma_id, details in return_details.items():
                if details["status"] != "Received":
                    continue

                inspection_number += 1
                inspected_at = details["received_at"] + timedelta(hours=2)
                condition = rng.choice(["Good", "Good", "Damaged"])
                status = "Failed" if condition == "Damaged" else "Passed"

                inspection_rows.append(
                    (
                        "INSP-2026-{:06d}".format(inspection_number),
                        details["asset_id"],
                        rma_id,
                        actor_ids[3],
                        status,
                        condition,
                        inspected_at.isoformat(),
                        "Synthetic inspection record",
                    )
                )

            connection.executemany(
                """
                INSERT INTO inspections
                    (inspection_id, asset_id, rma_id, inspected_by,
                     inspection_status, condition_found, inspected_at, notes)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                inspection_rows,
            )

            # 8. Repairs for failed inspections.
            failed_inspections = connection.execute(
                """
                SELECT inspection_id, asset_id, inspected_at
                FROM inspections
                WHERE inspection_status = 'Failed'
                ORDER BY inspection_id
                """
            ).fetchall()

            repair_rows = []

            for number, inspection in enumerate(
                failed_inspections, start=1
            ):
                opened_at = datetime.fromisoformat(
                    inspection["inspected_at"]
                )
                completed = rng.random() < 0.7
                closed_at = (
                    opened_at + timedelta(days=rng.randint(1, 5))
                    if completed else None
                )

                repair_rows.append(
                    (
                        "REP-2026-{:06d}".format(number),
                        inspection["asset_id"],
                        inspection["inspection_id"],
                        "Completed" if completed else "Open",
                        round(rng.uniform(100, 1500), 2),
                        opened_at.isoformat(),
                        closed_at.isoformat() if closed_at else None,
                        "Synthetic repair record",
                    )
                )

            connection.executemany(
                """
                INSERT INTO repairs
                    (repair_id, asset_id, inspection_id,
                     repair_status, repair_cost, opened_at,
                     closed_at, repair_notes)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                repair_rows,
            )

            # 9. Deposit charges and refunds.
            deposit_rows = []
            deposit_number = 0

            for number, (rma_id, details) in enumerate(
                return_details.items(), start=1
            ):
                asset_id = details["asset_id"]
                amount = round(rng.uniform(500, 5000), 2)
                deposit_number += 1

                deposit_rows.append(
                    (
                        "DEP-2026-{:06d}".format(deposit_number),
                        asset_id,
                        rma_id,
                        "Charge",
                        amount,
                        "INR",
                        (base_time + timedelta(days=number)).isoformat(),
                        "DEPOSIT-REF-{:06d}".format(number),
                        "Synthetic deposit charge",
                    )
                )

                if (
                    details["status"] == "Received"
                    and rng.random() < 0.4
                ):
                    deposit_number += 1
                    deposit_rows.append(
                        (
                            "DEP-2026-{:06d}".format(deposit_number),
                            asset_id,
                            rma_id,
                            "Refund",
                            amount,
                            "INR",
                            (
                                base_time
                                + timedelta(days=number + 200)
                            ).isoformat(),
                            "REFUND-REF-{:06d}".format(number),
                            "Synthetic deposit refund",
                        )
                    )

            connection.executemany(
                """
                INSERT INTO deposit_ledger
                    (deposit_event_id, asset_id, rma_id,
                     transaction_type, amount, currency,
                     transaction_at, reference_number, notes)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                deposit_rows,
            )

        # 10. Validate before reporting success.
        counts = print_validation_report(
            connection,
            expected_counts={
                "reusable_assets": asset_count,
                "shipments": shipment_count,
                "custody_events": event_count,
            },
        )

        print("\nSynthetic dataset created successfully.")
        print("Output: {}".format(output))
        print("Seed: {}".format(seed))

        for table in TABLES:
            print("{}: {}".format(table, counts[table]))

    finally:
        connection.close()


def main():
    parser = argparse.ArgumentParser(
        description="Generate synthetic reverse-logistics data."
    )
    parser.add_argument("--assets", type=int, default=100)
    parser.add_argument("--shipments", type=int, default=50)
    parser.add_argument("--events", type=int, default=500)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument(
        "--output",
        default="data/generated/reverse_logistics_full.db",
    )

    args = parser.parse_args()

    generate_dataset(
        output=PROJECT_ROOT / args.output,
        asset_count=args.assets,
        shipment_count=args.shipments,
        event_count=args.events,
        seed=args.seed,
    )


if __name__ == "__main__":
    main()
