
from pathlib import Path
import sqlite3
from typing import Optional, Union

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATABASE = PROJECT_ROOT / "data" / "reverse_logistics.db"
PathLike = Union[str, Path]


def _connect(
    db_path: Optional[PathLike] = None,
) -> sqlite3.Connection:
    """Open a read-only connection to the selected logistics database."""
    path = Path(db_path) if db_path else DEFAULT_DATABASE

    if not path.is_absolute():
        path = PROJECT_ROOT / path

    if not path.exists():
        raise FileNotFoundError("Database not found: {}".format(path))

    connection = sqlite3.connect(
        "{}?mode=ro".format(path.resolve().as_uri()),
        uri=True,
    )
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def get_all_shipments(
    db_path: Optional[PathLike] = None,
) -> list:
    """Return shipments with their origin and destination names."""
    query = """
        SELECT
            s.*,
            origin.location_name AS origin_location,
            destination.location_name AS destination_location
        FROM shipments AS s
        LEFT JOIN locations AS origin
            ON origin.location_id = s.origin_location_id
        LEFT JOIN locations AS destination
            ON destination.location_id = s.destination_location_id
        ORDER BY s.shipment_id
    """
    with _connect(db_path) as connection:
        return [dict(row) for row in connection.execute(query)]


def get_shipment_by_id(
    shipment_id: str,
    db_path: Optional[PathLike] = None,
) -> Optional[dict]:
    """Return one shipment by ID, or None if it does not exist."""
    query = """
        SELECT
            s.*,
            origin.location_name AS origin_location,
            destination.location_name AS destination_location
        FROM shipments AS s
        LEFT JOIN locations AS origin
            ON origin.location_id = s.origin_location_id
        LEFT JOIN locations AS destination
            ON destination.location_id = s.destination_location_id
        WHERE s.shipment_id = ?
    """
    with _connect(db_path) as connection:
        row = connection.execute(query, (shipment_id,)).fetchone()
        return dict(row) if row else None


def get_shipment_exceptions(
    db_path: Optional[PathLike] = None,
) -> list:
    """Return shipments marked as exceptions."""
    query = """
        SELECT
            s.*,
            origin.location_name AS origin_location,
            destination.location_name AS destination_location
        FROM shipments AS s
        LEFT JOIN locations AS origin
            ON origin.location_id = s.origin_location_id
        LEFT JOIN locations AS destination
            ON destination.location_id = s.destination_location_id
        WHERE LOWER(TRIM(s.shipment_status)) = 'exception'
        ORDER BY s.shipment_id
    """
    with _connect(db_path) as connection:
        return [dict(row) for row in connection.execute(query)]


def get_shipment_counts(
    db_path: Optional[PathLike] = None,
) -> dict:
    """Return shipment totals grouped by status."""
    query = """
        SELECT shipment_status, COUNT(*) AS total
        FROM shipments
        GROUP BY shipment_status
        ORDER BY shipment_status
    """
    with _connect(db_path) as connection:
        rows = connection.execute(query).fetchall()

    counts = {
        "total_shipments": sum(int(row["total"]) for row in rows)
    }
    for row in rows:
        status = str(row["shipment_status"] or "Unknown").strip().lower()
        key = "{}_shipments".format(status.replace(" ", "_"))
        counts[key] = int(row["total"])

    return counts
