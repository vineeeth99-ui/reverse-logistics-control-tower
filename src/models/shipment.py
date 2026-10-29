
from dataclasses import dataclass
from typing import Optional


@dataclass
class Shipment:
    """Represents a shipment in the reverse logistics workflow."""

    shipment_id: str
    origin_location_id: str
    destination_location_id: str
    shipment_status: str
    dispatched_at: Optional[str] = None
    delivered_at: Optional[str] = None
    carrier_id: Optional[str] = None

    def is_exception(self) -> bool:
        """Return True when the shipment is marked as an exception."""
        return self.shipment_status.strip().lower() == "exception"

    def is_delivered(self) -> bool:
        """Return True when the shipment has been delivered."""
        return self.shipment_status.strip().lower() == "delivered"
