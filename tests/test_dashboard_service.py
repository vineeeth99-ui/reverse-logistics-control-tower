
import unittest

import pandas as pd

from src.services.dashboard_service import (
    find_delayed_shipments,
    find_exception_shipments,
    find_asset_exceptions,
)


class TestDashboardService(unittest.TestCase):

    def test_finds_delayed_in_progress_shipments(self):
        shipments = pd.DataFrame({
            "shipment_id": ["S1", "S2", "S3", "S4"],
            "shipment_status": [
                "In Transit",
                "Dispatched",
                "Delivered",
                "Exception",
            ],
            "days_since_dispatch": [5, 2, 10, 8],
        })

        result = find_delayed_shipments(shipments, 3)

        self.assertEqual(result["shipment_id"].tolist(), ["S1"])

    def test_delay_threshold_is_strict(self):
        shipments = pd.DataFrame({
            "shipment_id": ["S1", "S2"],
            "shipment_status": ["In Transit", "In Transit"],
            "days_since_dispatch": [3, 4],
        })

        result = find_delayed_shipments(shipments, 3)

        self.assertEqual(result["shipment_id"].tolist(), ["S2"])

    def test_finds_exception_shipments(self):
        shipments = pd.DataFrame({
            "shipment_id": ["S1", "S2", "S3"],
            "shipment_status": [
                "Delivered",
                "Exception",
                "In Transit",
            ],
        })

        result = find_exception_shipments(shipments)

        self.assertEqual(result["shipment_id"].tolist(), ["S2"])

    def test_finds_lost_and_damaged_assets(self):
        assets = pd.DataFrame({
            "asset_id": ["A1", "A2", "A3", "A4"],
            "asset_status": [
                "Lost",
                "Available",
                "Available",
                "Available",
            ],
            "condition_status": [
                "Good",
                "Damaged",
                "Unusable",
                "Good",
            ],
        })

        result = find_asset_exceptions(assets)

        self.assertEqual(
            set(result["asset_id"]),
            {"A1", "A2", "A3"},
        )

    def test_negative_delay_threshold_is_rejected(self):
        shipments = pd.DataFrame({
            "shipment_status": ["In Transit"],
            "days_since_dispatch": [5],
        })

        with self.assertRaises(ValueError):
            find_delayed_shipments(shipments, -1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
