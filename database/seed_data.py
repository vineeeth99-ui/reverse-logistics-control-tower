
from database.connection import get_connection, initialize_database


def seed_sample_data():
    initialize_database()

    with get_connection() as connection:
        # Reference data
        connection.executemany(
            """
            INSERT OR IGNORE INTO asset_types
                (type_name, description)
            VALUES (?, ?)
            """,
            [
                ("Pallet", "Reusable transport pallet"),
                ("Container", "Reusable shipping container"),
            ],
        )

        connection.executemany(
            """
            INSERT OR IGNORE INTO owners (owner_name, owner_type)
            VALUES (?, ?)
            """,
            [
                ("Supplier A", "Supplier"),
                ("Example Logistics Ltd", "Company"),
            ],
        )

        connection.executemany(
            """
            INSERT OR IGNORE INTO locations
                (location_name, location_type, city, country)
            VALUES (?, ?, ?, ?)
            """,
            [
                ("Chennai Warehouse", "Warehouse", "Chennai", "India"),
                ("Bengaluru Distribution Center",
                 "Distribution Center", "Bengaluru", "India"),
            ],
        )

        connection.execute(
            """
            INSERT OR IGNORE INTO actors (actor_id, actor_name, role, organization)
            VALUES (1, 'Sample Planner', 'Planner', 'Example Logistics Ltd')
            """
        )

        # Retrieve generated reference IDs.
        pallet_type_id = connection.execute(
            "SELECT asset_type_id FROM asset_types WHERE type_name = 'Pallet'"
        ).fetchone()["asset_type_id"]

        supplier_id = connection.execute(
            "SELECT owner_id FROM owners WHERE owner_name = 'Supplier A'"
        ).fetchone()["owner_id"]

        warehouse_id = connection.execute(
            "SELECT location_id FROM locations WHERE location_name = 'Chennai Warehouse'"
        ).fetchone()["location_id"]

        destination_id = connection.execute(
            "SELECT location_id FROM locations WHERE location_name = 'Bengaluru Distribution Center'"
        ).fetchone()["location_id"]

        # One reusable pallet.
        connection.execute(
            """
            INSERT OR IGNORE INTO reusable_assets
                (asset_id, asset_type_id, owner_id,
                 current_location_id, asset_status, condition_status)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                "ASSET-0000001",
                pallet_type_id,
                supplier_id,
                warehouse_id,
                "Available",
                "Good",
            ),
        )

        # One shipment.
        connection.execute(
            """
            INSERT OR IGNORE INTO shipments
                (shipment_id, origin_location_id,
                 destination_location_id, shipment_status)
            VALUES (?, ?, ?, ?)
            """,
            (
                "SHP-2026-000001",
                warehouse_id,
                destination_id,
                "Created",
            ),
        )

        # Link the pallet to the shipment.
        connection.execute(
            """
            INSERT OR IGNORE INTO shipment_assets
                (shipment_id, asset_id, quantity)
            VALUES (?, ?, ?)
            """,
            ("SHP-2026-000001", "ASSET-0000001", 1),
        )

        print("Sample data inserted successfully.")

        asset_count = connection.execute(
            "SELECT COUNT(*) FROM reusable_assets"
        ).fetchone()[0]

        shipment_count = connection.execute(
            "SELECT COUNT(*) FROM shipments"
        ).fetchone()[0]

        link_count = connection.execute(
            "SELECT COUNT(*) FROM shipment_assets"
        ).fetchone()[0]

        print(f"Assets: {asset_count}")
        print(f"Shipments: {shipment_count}")
        print(f"Shipment-asset links: {link_count}")


if __name__ == "__main__":
    seed_sample_data()
