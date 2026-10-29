
from pathlib import Path
import sqlite3

# Find the root folder of the project.
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Store the database inside the project's data folder.
DATA_DIR = PROJECT_ROOT / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

DATABASE_PATH = DATA_DIR / "reverse_logistics.db"
SCHEMA_PATH = PROJECT_ROOT / "database" / "schema.sql"


def get_connection():
    """Open a connection to the local SQLite database."""
    connection = sqlite3.connect(DATABASE_PATH)
    connection.row_factory = sqlite3.Row

    # SQLite foreign keys must be enabled on each connection.
    connection.execute("PRAGMA foreign_keys = ON")

    return connection


def initialize_database():
    """Create the database tables if they do not exist."""
    if not SCHEMA_PATH.exists():
        raise FileNotFoundError(
            f"Database schema not found: {SCHEMA_PATH}"
        )

    with get_connection() as connection:
        schema_sql = SCHEMA_PATH.read_text(encoding="utf-8")
        connection.executescript(schema_sql)

    print(f"Database initialized: {DATABASE_PATH}")


if __name__ == "__main__":
    initialize_database()
