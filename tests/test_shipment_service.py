
import sqlite3
import tempfile
import unittest
from pathlib import Path

from database.connection import SCHEMA_PATH
from src.services.shipment_service import (
    get_all_shipments,
    get_shipment_by_id,
    get_shipment_exceptions,
    get_shipment_counts,
)


class TestShipmentService(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_shipments.db"

        with sqlite3.connect(str(self.db_path)) as connection:
            connection.execute("PRAGMA foreign_keys = ON")
            connection.executescript(
                SCHEMA_PATH.read_text(encoding="utf-8")
            )

            connection.executemany("""
                INSERT INTO locations
                    (location_id, location_name, location_type, city, country)
                VALUES (?, ?, 'Warehouse', 'Chennai', 'India')
            """, [
                (1, "Warehouse A"),
                (2, "Warehouse B"),
            ])

            connection.executemany("""
                INSERT INTO shipments
                    (shipment_id, origin_location_id,
                     destination_location_id, shipment_status,
                     dispatched_at, delivered_at)
                VALUES (?, 1, 2, ?, ?, ?)
            """, [
                ("SHP-1", "Created", None, None),
                ("SHP-2", "Dispatched", "2026-10-27 09:00:00", None),
                ("SHP-3", "Exception", "2026-10-27 10:00:00", None),
                (
                    "SHP-4",
                    "Delivered",
                    "2026-10-26 09:00:00",
                    "2026-10-27 09:00:00",
                ),
            ])

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_get_all_shipments(self):
        shipments = get_all_shipments(self.db_path)
        self.assertEqual(len(shipments), 4)

    def test_get_shipment_by_id(self):
        shipment = get_shipment_by_id("SHP-1", self.db_path)
        self.assertIsNotNone(shipment)
        self.assertEqual(shipment["shipment_id"], "SHP-1")
        self.assertEqual(shipment["origin_location"], "Warehouse A")
        self.assertEqual(shipment["destination_location"], "Warehouse B")

    def test_missing_shipment_returns_none(self):
        self.assertIsNone(
            get_shipment_by_id("NOT-FOUND", self.db_path)
        )

    def test_get_shipment_exceptions(self):
        exceptions = get_shipment_exceptions(self.db_path)
        self.assertEqual(
            {shipment["shipment_id"] for shipment in exceptions},
            {"SHP-3"},
        )

    def test_get_shipment_counts(self):
        counts = get_shipment_counts(self.db_path)
        self.assertEqual(counts["total_shipments"], 4)
        self.assertEqual(counts["created_shipments"], 1)
        self.assertEqual(counts["dispatched_shipments"], 1)
        self.assertEqual(counts["exception_shipments"], 1)
        self.assertEqual(counts["delivered_shipments"], 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
