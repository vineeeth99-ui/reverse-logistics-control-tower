
"""Central entry point for Reverse Logistics Control Tower."""

from pathlib import Path
import runpy


PROJECT_ROOT = Path(__file__).resolve().parent
DASHBOARD_PATH = PROJECT_ROOT / "src" / "ui" / "dashboard.py"


def main():
    """Launch the existing Streamlit dashboard."""
    if not DASHBOARD_PATH.is_file():
        raise FileNotFoundError(
            "Dashboard not found: {}".format(DASHBOARD_PATH)
        )

    runpy.run_path(str(DASHBOARD_PATH), run_name="__main__")


if __name__ == "__main__":
    main()
