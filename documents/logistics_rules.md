
# Reverse Logistics Control Tower — Business Rules

## Shipment delay monitoring
A shipment is potentially delayed when its status is Dispatched or In Transit and its dispatch age is greater than 3 days.

The delay threshold is strictly greater than 3 days. A shipment at exactly 3 days does not meet this rule.

Potential delay is an age-based indicator. It does not prove that a delivery commitment has been missed.

## Explicit shipment exceptions
Shipments marked with status Exception are tracked separately from potentially delayed shipments.

Do not treat every delayed shipment as an explicitly declared exception.

## Asset exceptions
Assets with status Lost are exceptions.

Assets with condition Damaged or Unusable are also exceptions.

## Custody traceability
Custody events should have an assigned actor. Events without an actor require investigation.

Custody history helps trace asset movement between locations and shipment handoffs.

## Operational data integrity
Operational facts such as shipment IDs, statuses, counts, locations, and dispatch dates must come from the operational database.

Do not invent missing identifiers or claim a database record was changed unless an actual write operation was performed and verified.

## AI assistant response rules
Use retrieved documents to explain business rules.

Use verified database context to answer questions about current operational records.

If the available information is insufficient, clearly state that limitation.

Keep recommendations separate from verified facts.
