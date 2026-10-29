
import sqlite3
import tempfile
import unittest
from pathlib import Path

from database.connection import SCHEMA_PATH
from src.services.asset_service import (
    get_all_assets,
    get_asset_by_id,
    get_asset_exceptions,
    get_asset_counts,
)


class TestAssetService(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_assets.db"

        with sqlite3.connect(str(self.db_path)) as connection:
            connection.execute("PRAGMA foreign_keys = ON")
            connection.executescript(
                SCHEMA_PATH.read_text(encoding="utf-8")
            )

            connection.execute("""
                INSERT INTO asset_types (asset_type_id, type_name, description)
                VALUES (1, 'Pallet', 'Reusable pallet')
            """)
            connection.execute("""
                INSERT INTO owners (owner_id, owner_name, owner_type)
                VALUES (1, 'Test Owner', 'Supplier')
            """)
            connection.execute("""
                INSERT INTO locations
                    (location_id, location_name, location_type, city, country)
                VALUES (1, 'Warehouse A', 'Warehouse', 'Chennai', 'India')
            """)

            connection.executemany("""
                INSERT INTO reusable_assets
                    (asset_id, asset_type_id, owner_id, current_location_id,
                     asset_status, condition_status)
                VALUES (?, 1, 1, 1, ?, ?)
            """, [
                ("ASSET-1", "Available", "Good"),
                ("ASSET-2", "Lost", "Good"),
                ("ASSET-3", "Available", "Damaged"),
                ("ASSET-4", "Available", "Unusable"),
            ])

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_get_all_assets(self):
        assets = get_all_assets(self.db_path)
        self.assertEqual(len(assets), 4)

    def test_get_asset_by_id(self):
        asset = get_asset_by_id("ASSET-1", self.db_path)
        self.assertIsNotNone(asset)
        self.assertEqual(asset["asset_id"], "ASSET-1")
        self.assertEqual(asset["asset_type"], "Pallet")

    def test_get_missing_asset_returns_none(self):
        self.assertIsNone(
            get_asset_by_id("DOES-NOT-EXIST", self.db_path)
        )

    def test_get_asset_exceptions(self):
        exceptions = get_asset_exceptions(self.db_path)
        self.assertEqual(
            {asset["asset_id"] for asset in exceptions},
            {"ASSET-2", "ASSET-3", "ASSET-4"},
        )

    def test_get_asset_counts(self):
        counts = get_asset_counts(self.db_path)
        self.assertEqual(counts["total_assets"], 4)
        self.assertEqual(counts["lost_assets"], 1)
        self.assertEqual(counts["damaged_assets"], 1)
        self.assertEqual(counts["unusable_assets"], 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
