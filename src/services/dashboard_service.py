
import pandas as pd


def find_delayed_shipments(
    shipments: pd.DataFrame,
    threshold_days: int,
) -> pd.DataFrame:
    """Find in-progress shipments older than a chosen threshold."""
    required_columns = {
        "shipment_status",
        "days_since_dispatch",
    }

    missing = required_columns - set(shipments.columns)
    if missing:
        raise ValueError(
            f"Missing required columns: {sorted(missing)}"
        )

    if threshold_days < 0:
        raise ValueError("threshold_days cannot be negative.")

    active_statuses = ["Dispatched", "In Transit"]

    mask = (
        shipments["shipment_status"].isin(active_statuses)
        & (shipments["days_since_dispatch"] > threshold_days)
    )

    return shipments.loc[mask].copy()


def find_exception_shipments(
    shipments: pd.DataFrame,
) -> pd.DataFrame:
    """Return shipments explicitly marked as exceptions."""
    if "shipment_status" not in shipments.columns:
        raise ValueError("Missing required column: shipment_status")

    return shipments.loc[
        shipments["shipment_status"] == "Exception"
    ].copy()


def find_asset_exceptions(
    assets: pd.DataFrame,
) -> pd.DataFrame:
    """Find lost assets and assets in poor condition."""
    required_columns = {"asset_status", "condition_status"}

    missing = required_columns - set(assets.columns)
    if missing:
        raise ValueError(
            f"Missing required columns: {sorted(missing)}"
        )

    mask = (
        (assets["asset_status"] == "Lost")
        | assets["condition_status"].isin(["Damaged", "Unusable"])
    )

    return assets.loc[mask].copy()
