"""Idempotent synchronization keyed by client-generated UUIDs."""
import uuid


def apply_sync(records: list, existing_ids: set):
    """Return per-record results. Duplicate UUIDs are acknowledged (idempotent), never
    re-inserted; invalid records are rejected with a reason so the client keeps them queued."""
    results, accepted, seen = [], [], set(existing_ids)
    for r in records:
        rid = r.get("client_uuid")
        try:
            uuid.UUID(str(rid))
        except (ValueError, AttributeError, TypeError):
            results.append({"client_uuid": rid, "status": "rejected", "reason": "invalid uuid"})
            continue
        if rid in seen:
            results.append({"client_uuid": rid, "status": "duplicate"})
            continue
        seen.add(rid)
        accepted.append(r)
        results.append({"client_uuid": rid, "status": "accepted"})
    return results, accepted
