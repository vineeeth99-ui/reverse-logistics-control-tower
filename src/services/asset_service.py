
from pathlib import Path
import sqlite3
from typing import Any, Optional, Union

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


def get_all_assets(
    db_path: Optional[PathLike] = None,
) -> list:
    """Return assets with their type, owner, and current location."""
    query = """
        SELECT
            a.asset_id,
            a.asset_type_id,
            at.type_name AS asset_type,
            a.owner_id,
            o.owner_name,
            a.current_location_id,
            l.location_name AS current_location,
            a.asset_status,
            a.condition_status,
            a.acquired_at,
            a.created_at
        FROM reusable_assets AS a
        LEFT JOIN asset_types AS at ON at.asset_type_id = a.asset_type_id
        LEFT JOIN owners AS o ON o.owner_id = a.owner_id
        LEFT JOIN locations AS l ON l.location_id = a.current_location_id
        ORDER BY a.asset_id
    """
    with _connect(db_path) as connection:
        return [dict(row) for row in connection.execute(query)]


def get_asset_by_id(
    asset_id: str,
    db_path: Optional[PathLike] = None,
) -> Optional[dict]:
    """Return one asset by ID, or None if it does not exist."""
    query = """
        SELECT
            a.asset_id,
            a.asset_type_id,
            at.type_name AS asset_type,
            a.owner_id,
            o.owner_name,
            a.current_location_id,
            l.location_name AS current_location,
            a.asset_status,
            a.condition_status,
            a.acquired_at,
            a.created_at
        FROM reusable_assets AS a
        LEFT JOIN asset_types AS at ON at.asset_type_id = a.asset_type_id
        LEFT JOIN owners AS o ON o.owner_id = a.owner_id
        LEFT JOIN locations AS l ON l.location_id = a.current_location_id
        WHERE a.asset_id = ?
    """
    with _connect(db_path) as connection:
        row = connection.execute(query, (asset_id,)).fetchone()
        return dict(row) if row else None


def get_asset_exceptions(
    db_path: Optional[PathLike] = None,
) -> list:
    """Return lost, damaged, or unusable assets."""
    query = """
        SELECT
            a.asset_id,
            at.type_name AS asset_type,
            o.owner_name,
            l.location_name AS current_location,
            a.asset_status,
            a.condition_status
        FROM reusable_assets AS a
        LEFT JOIN asset_types AS at ON at.asset_type_id = a.asset_type_id
        LEFT JOIN owners AS o ON o.owner_id = a.owner_id
        LEFT JOIN locations AS l ON l.location_id = a.current_location_id
        WHERE LOWER(TRIM(a.asset_status)) = 'lost'
           OR LOWER(TRIM(a.condition_status)) IN ('damaged', 'unusable')
        ORDER BY a.asset_id
    """
    with _connect(db_path) as connection:
        return [dict(row) for row in connection.execute(query)]


def get_asset_counts(
    db_path: Optional[PathLike] = None,
) -> dict:
    """Return total, lost, damaged, and unusable asset counts."""
    query = """
        SELECT
            COUNT(*) AS total_assets,
            SUM(CASE WHEN LOWER(TRIM(asset_status)) = 'lost'
                     THEN 1 ELSE 0 END) AS lost_assets,
            SUM(CASE WHEN LOWER(TRIM(condition_status)) = 'damaged'
                     THEN 1 ELSE 0 END) AS damaged_assets,
            SUM(CASE WHEN LOWER(TRIM(condition_status)) = 'unusable'
                     THEN 1 ELSE 0 END) AS unusable_assets
        FROM reusable_assets
    """
    with _connect(db_path) as connection:
        row = connection.execute(query).fetchone()
        return {
            key: int(row[key] or 0)
            for key in (
                "total_assets",
                "lost_assets",
                "damaged_assets",
                "unusable_assets",
            )
        }
