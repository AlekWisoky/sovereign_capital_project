# ADR-0003: Hash-chained Append-only Audit Log

**Status:** Accepted

## Context
For sovereign operation, every decision and control change must be auditable and tamper-evident.

## Decision
Use an append-only JSONL log where each record includes `prev_hash` and a hash of canonicalized content.

## Consequences
- ✅ Tamper-evident change history
- ✅ Simple local-first storage in `VICTOR_DATA_DIR`
- ✅ Easy export and replay of event streams
- ❌ Not a substitute for remote backups or notarization

## Implementation
`backend/victor_ai_bot/command_center_overlay.py::AuditStore`
