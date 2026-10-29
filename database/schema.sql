-- Reverse Logistics Control Tower
-- File: database/schema.sql
-- Database: SQLite

PRAGMA foreign_keys = ON;

-- 1. Asset categories
CREATE TABLE IF NOT EXISTS asset_types (
    asset_type_id INTEGER PRIMARY KEY,
    type_name TEXT NOT NULL UNIQUE,
    description TEXT
);

-- 2. Organizations that own reusable assets
CREATE TABLE IF NOT EXISTS owners (
    owner_id INTEGER PRIMARY KEY,
    owner_name TEXT NOT NULL UNIQUE,
    owner_type TEXT NOT NULL
        CHECK (owner_type IN ('Supplier', 'Customer', 'Company', 'Third Party'))
);

-- 3. Warehouses and other physical locations
CREATE TABLE IF NOT EXISTS locations (
    location_id INTEGER PRIMARY KEY,
    location_name TEXT NOT NULL,
    location_type TEXT NOT NULL
        CHECK (location_type IN (
            'Warehouse', 'Distribution Center', 'Supplier Site',
            'Customer Site', 'Repair Center', 'In Transit'
        )),
    city TEXT,
    country TEXT
);

-- 4. People or operational actors
CREATE TABLE IF NOT EXISTS actors (
    actor_id INTEGER PRIMARY KEY,
    actor_name TEXT NOT NULL,
    role TEXT NOT NULL
        CHECK (role IN (
            'Supplier', 'Planner', 'Carrier Operator',
            'Warehouse Operator', 'Logistics Analyst',
            'Operations Manager'
        )),
    organization TEXT,
    is_active INTEGER NOT NULL DEFAULT 1
        CHECK (is_active IN (0, 1))
);

-- 5. Individual reusable assets
CREATE TABLE IF NOT EXISTS reusable_assets (
    asset_id TEXT PRIMARY KEY,
    asset_type_id INTEGER NOT NULL,
    owner_id INTEGER NOT NULL,
    current_location_id INTEGER,
    asset_status TEXT NOT NULL DEFAULT 'Available'
        CHECK (asset_status IN (
            'Available', 'In Transit', 'In Use', 'Returned',
            'Under Inspection', 'Under Repair', 'Retired', 'Lost'
        )),
    condition_status TEXT NOT NULL DEFAULT 'Good'
        CHECK (condition_status IN (
            'New', 'Good', 'Damaged', 'Unusable'
        )),
    acquired_at TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (asset_type_id)
        REFERENCES asset_types(asset_type_id),
    FOREIGN KEY (owner_id)
        REFERENCES owners(owner_id),
    FOREIGN KEY (current_location_id)
        REFERENCES locations(location_id)
);

-- 6. Shipments
CREATE TABLE IF NOT EXISTS shipments (
    shipment_id TEXT PRIMARY KEY,
    origin_location_id INTEGER NOT NULL,
    destination_location_id INTEGER NOT NULL,
    shipment_status TEXT NOT NULL DEFAULT 'Created'
        CHECK (shipment_status IN (
            'Created', 'Dispatched', 'In Transit',
            'Delivered', 'Cancelled', 'Exception'
        )),
    dispatched_at TEXT,
    delivered_at TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (origin_location_id)
        REFERENCES locations(location_id),
    FOREIGN KEY (destination_location_id)
        REFERENCES locations(location_id),

    CHECK (
        delivered_at IS NULL
        OR dispatched_at IS NULL
        OR delivered_at >= dispatched_at
    )
);

-- 7. Bridge table: shipments and reusable assets
CREATE TABLE IF NOT EXISTS shipment_assets (
    shipment_id TEXT NOT NULL,
    asset_id TEXT NOT NULL,
    quantity INTEGER NOT NULL DEFAULT 1 CHECK (quantity > 0),
    loaded_at TEXT,
    unloaded_at TEXT,

    PRIMARY KEY (shipment_id, asset_id),

    FOREIGN KEY (shipment_id)
        REFERENCES shipments(shipment_id),
    FOREIGN KEY (asset_id)
        REFERENCES reusable_assets(asset_id),

    CHECK (
        unloaded_at IS NULL
        OR loaded_at IS NULL
        OR unloaded_at >= loaded_at
    )
);

-- 8. Immutable custody history
CREATE TABLE IF NOT EXISTS custody_events (
    custody_event_id TEXT PRIMARY KEY,
    asset_id TEXT NOT NULL,
    shipment_id TEXT,
    actor_id INTEGER,
    from_location_id INTEGER,
    to_location_id INTEGER,
    event_type TEXT NOT NULL
        CHECK (event_type IN (
            'Created', 'Dispatched', 'Received',
            'Transferred', 'Returned', 'Inspected',
            'Sent for Repair', 'Repair Completed', 'Retired'
        )),
    occurred_at TEXT NOT NULL,
    recorded_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    notes TEXT,

    FOREIGN KEY (asset_id)
        REFERENCES reusable_assets(asset_id),
    FOREIGN KEY (shipment_id)
        REFERENCES shipments(shipment_id),
    FOREIGN KEY (actor_id)
        REFERENCES actors(actor_id),
    FOREIGN KEY (from_location_id)
        REFERENCES locations(location_id),
    FOREIGN KEY (to_location_id)
        REFERENCES locations(location_id)
);

-- 9. Return approvals
CREATE TABLE IF NOT EXISTS return_authorizations (
    rma_id TEXT PRIMARY KEY,
    asset_id TEXT NOT NULL,
    requested_by INTEGER,
    return_location_id INTEGER NOT NULL,
    return_status TEXT NOT NULL DEFAULT 'Requested'
        CHECK (return_status IN (
            'Requested', 'Approved', 'In Transit',
            'Received', 'Rejected', 'Closed'
        )),
    requested_at TEXT NOT NULL,
    approved_at TEXT,
    received_at TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (asset_id)
        REFERENCES reusable_assets(asset_id),
    FOREIGN KEY (requested_by)
        REFERENCES actors(actor_id),
    FOREIGN KEY (return_location_id)
        REFERENCES locations(location_id)
);

-- 10. Asset inspections
CREATE TABLE IF NOT EXISTS inspections (
    inspection_id TEXT PRIMARY KEY,
    asset_id TEXT NOT NULL,
    rma_id TEXT,
    inspected_by INTEGER,
    inspection_status TEXT NOT NULL DEFAULT 'Pending'
        CHECK (inspection_status IN (
            'Pending', 'Passed', 'Failed'
        )),
    condition_found TEXT
        CHECK (
            condition_found IS NULL
            OR condition_found IN (
                'New', 'Good', 'Damaged', 'Unusable'
            )
        ),
    inspected_at TEXT,
    notes TEXT,

    FOREIGN KEY (asset_id)
        REFERENCES reusable_assets(asset_id),
    FOREIGN KEY (rma_id)
        REFERENCES return_authorizations(rma_id),
    FOREIGN KEY (inspected_by)
        REFERENCES actors(actor_id)
);

-- 11. Repair work
CREATE TABLE IF NOT EXISTS repairs (
    repair_id TEXT PRIMARY KEY,
    asset_id TEXT NOT NULL,
    inspection_id TEXT,
    repair_status TEXT NOT NULL DEFAULT 'Open'
        CHECK (repair_status IN (
            'Open', 'In Progress', 'Completed', 'Cancelled'
        )),
    repair_cost REAL NOT NULL DEFAULT 0
        CHECK (repair_cost >= 0),
    opened_at TEXT NOT NULL,
    closed_at TEXT,
    repair_notes TEXT,

    FOREIGN KEY (asset_id)
        REFERENCES reusable_assets(asset_id),
    FOREIGN KEY (inspection_id)
        REFERENCES inspections(inspection_id),

    CHECK (
        closed_at IS NULL
        OR closed_at >= opened_at
    )
);

-- 12. Deposit charges, refunds, and adjustments
CREATE TABLE IF NOT EXISTS deposit_ledger (
    deposit_event_id TEXT PRIMARY KEY,
    asset_id TEXT NOT NULL,
    rma_id TEXT,
    transaction_type TEXT NOT NULL
        CHECK (transaction_type IN (
            'Charge', 'Refund', 'Adjustment'
        )),
    amount REAL NOT NULL CHECK (amount > 0),
    currency TEXT NOT NULL DEFAULT 'INR',
    transaction_at TEXT NOT NULL,
    reference_number TEXT,
    notes TEXT,

    FOREIGN KEY (asset_id)
        REFERENCES reusable_assets(asset_id),
    FOREIGN KEY (rma_id)
        REFERENCES return_authorizations(rma_id)
);

-- Indexes to speed up common searches
CREATE INDEX IF NOT EXISTS idx_assets_status
    ON reusable_assets(asset_status);

CREATE INDEX IF NOT EXISTS idx_assets_location
    ON reusable_assets(current_location_id);

CREATE INDEX IF NOT EXISTS idx_shipments_status
    ON shipments(shipment_status);

CREATE INDEX IF NOT EXISTS idx_custody_asset_time
    ON custody_events(asset_id, occurred_at);

CREATE INDEX IF NOT EXISTS idx_returns_status
    ON return_authorizations(return_status);

CREATE INDEX IF NOT EXISTS idx_inspections_asset
    ON inspections(asset_id);

CREATE INDEX IF NOT EXISTS idx_repairs_status
    ON repairs(repair_status);

CREATE INDEX IF NOT EXISTS idx_deposits_asset_time
    ON deposit_ledger(asset_id, transaction_at);