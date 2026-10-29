
from dataclasses import dataclass
from typing import Optional


@dataclass
class Asset:
    """Represents a reusable logistics asset."""

    asset_id: str
    asset_type_id: str
    owner_id: str
    current_location_id: Optional[str]
    asset_status: str
    condition_status: str
    deposit_amount: float = 0.0

    @classmethod
    def from_row(cls, row):
        """Create an Asset from a SQLite row or mapping."""
        data = dict(row)
        return cls(
            asset_id=data["asset_id"],
            asset_type_id=data["asset_type_id"],
            owner_id=data["owner_id"],
            current_location_id=data.get("current_location_id"),
            asset_status=data["asset_status"],
            condition_status=data["condition_status"],
            deposit_amount=float(data.get("deposit_amount") or 0.0),
        )

    def is_exception(self) -> bool:
        """Return True when an asset needs operational attention."""
        return (
            self.asset_status.strip().lower() == "lost"
            or self.condition_status.strip().lower()
            in {"damaged", "unusable"}
        )
