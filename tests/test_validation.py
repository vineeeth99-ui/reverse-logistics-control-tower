
import sqlite3
import unittest
from pathlib import Path

from src.services.validation_service import validate_database
from database.connection import SCHEMA_PATH


class TestLogisticsValidation(unittest.TestCase):

    def setUp(self):
        """Create a fresh, isolated database for each test."""
        self.connection = sqlite3.connect(":memory:")
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys = ON")
        self.connection.executescript(
            SCHEMA_PATH.read_text(encoding="utf-8")
        )

        # Minimum reference records needed by test fixtures.
        self.connection.execute(
            """
            INSERT INTO asset_types (asset_type_id, type_name)
            VALUES (1, 'Pallet')
            """
        )
        self.connection.execute(
            """
            INSERT INTO owners (owner_id, owner_name, owner_type)
            VALUES (1, 'Test Supplier', 'Supplier')
            """
        )
        self.connection.execute(
            """
            INSERT INTO locations
                (location_id, location_name, location_type)
            VALUES
                (1, 'Warehouse A', 'Warehouse'),
                (2, 'Warehouse B', 'Warehouse')
            """
        )
        self.connection.execute(
            """
            INSERT INTO actors (actor_id, actor_name, role)
            VALUES (1, 'Test Planner', 'Planner')
            """
        )
        self.connection.execute(
            """
            INSERT INTO reusable_assets
                (asset_id, asset_type_id, owner_id, current_location_id)
            VALUES ('ASSET-0000001', 1, 1, 1)
            """
        )
        self.connection.commit()

    def tearDown(self):
        self.connection.close()

    def get_issue_names(self):
        result = validate_database(self.connection)
        return {issue["check"] for issue in result["issues"]}

    def test_valid_database_passes(self):
        """A database with valid reference records should pass."""
        result = validate_database(self.connection)

        self.assertTrue(result["passed"])
        self.assertEqual(result["issue_count"], 0)

    def test_missing_custody_actor_is_detected(self):
        """Custody records without an actor should be flagged."""
        self.connection.execute(
            """
            INSERT INTO custody_events (
                custody_event_id, asset_id, actor_id,
                from_location_id, to_location_id,
                event_type, occurred_at
            )
            VALUES (
                'CUST-ASSET-0000001-000001',
                'ASSET-0000001', NULL, 1, 2,
                'Transferred', '2026-01-01T10:00:00'
            )
            """
        )

        self.assertIn(
            "custody_event_missing_actor",
            self.get_issue_names(),
        )

    def test_duplicate_refunds_are_detected(self):
        """Two refunds for the same asset and RMA should be flagged."""
        self.connection.execute(
            """
            INSERT INTO return_authorizations (
                rma_id, asset_id, return_location_id, requested_at
            )
            VALUES (
                'RMA-2026-000001',
                'ASSET-0000001', 1, '2026-01-01T09:00:00'
            )
            """
        )

        self.connection.executemany(
            """
            INSERT INTO deposit_ledger (
                deposit_event_id, asset_id, rma_id,
                transaction_type, amount, currency, transaction_at
            )
            VALUES (?, ?, ?, 'Refund', 500, 'INR', ?)
            """,
            [
                (
                    "DEP-2026-000001",
                    "ASSET-0000001",
                    "RMA-2026-000001",
                    "2026-01-02T10:00:00",
                ),
                (
                    "DEP-2026-000002",
                    "ASSET-0000001",
                    "RMA-2026-000001",
                    "2026-01-03T10:00:00",
                ),
            ],
        )

        self.assertIn(
            "possible_duplicate_refunds",
            self.get_issue_names(),
        )

    def test_completed_repair_without_inspection_is_detected(self):
        """A completed repair with no inspection should be flagged."""
        self.connection.execute(
            """
            INSERT INTO repairs (
                repair_id, asset_id, inspection_id,
                repair_status, repair_cost, opened_at, closed_at
            )
            VALUES (
                'REP-2026-000001',
                'ASSET-0000001', NULL,
                'Completed', 500,
                '2026-01-01T10:00:00',
                '2026-01-02T10:00:00'
            )
            """
        )

        self.assertIn(
            "completed_repair_without_inspection",
            self.get_issue_names(),
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
