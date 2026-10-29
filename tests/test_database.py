
import sqlite3
import unittest

from database.connection import SCHEMA_PATH


EXPECTED_TABLES = {
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
}


class TestDatabaseSchema(unittest.TestCase):

    def setUp(self):
        """Create an isolated in-memory database."""
        self.connection = sqlite3.connect(":memory:")
        self.connection.execute("PRAGMA foreign_keys = ON")
        schema = SCHEMA_PATH.read_text(encoding="utf-8")
        self.connection.executescript(schema)

    def tearDown(self):
        self.connection.close()

    def test_all_expected_tables_exist(self):
        cursor = self.connection.execute("""
            SELECT name
            FROM sqlite_master
            WHERE type = 'table'
              AND name NOT LIKE 'sqlite_%'
        """)
        actual_tables = {row[0] for row in cursor.fetchall()}

        self.assertEqual(
            EXPECTED_TABLES,
            actual_tables,
            f"Missing tables: {EXPECTED_TABLES - actual_tables}",
        )

    def test_foreign_keys_are_enabled(self):
        enabled = self.connection.execute(
            "PRAGMA foreign_keys"
        ).fetchone()[0]

        self.assertEqual(enabled, 1)

    def test_schema_has_no_foreign_key_violations(self):
        violations = self.connection.execute(
            "PRAGMA foreign_key_check"
        ).fetchall()

        self.assertEqual(violations, [])

    def test_important_indexes_exist(self):
        cursor = self.connection.execute("""
            SELECT name
            FROM sqlite_master
            WHERE type = 'index'
        """)
        indexes = {row[0] for row in cursor.fetchall()}

        self.assertGreater(
            len(indexes),
            0,
            "Expected database indexes were not created.",
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
