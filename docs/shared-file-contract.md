# Shared File Contract

This document defines the canonical cross-client contract for shared files.

## Scope

Shared/network-authoritative files:
- `rooms/<room>/messages.jsonl`
- `rooms/<room>/presence/<presence-id>`
- `memory/global.jsonl`

Not in scope here (documented separately):
- local/internal files in `docs/local-file-contract.md`

## Compatibility Model

This contract follows **Strict Reader + Additive Writer**.
See `docs/compatibility-policy.md`.

## Event Log: `rooms/<room>/messages.jsonl`

Format:
- UTF-8 JSONL (one JSON object per line).
- Canonical delimiter is `\n`.

Required fields:
- `v` (integer schema version)
- `ts` (string timestamp)
- `type` (string enum)
- `author` (string)
- `text` (string)

Allowed `type` values:
- `chat`
- `me`
- `system`
- `ai_prompt`
- `ai_response`

Optional fields currently used:
- `provider` (string)
- `model` (string)
- `request_id` (string)
- `memory_ids_used` (array of strings)
- `memory_topics_used` (array of strings)

Reader behavior:
- Invalid JSON row: skip row.
- Non-object row: skip row.
- Unknown `type`: skip row.
- `author`/`text` not strings: skip row.
- `v` missing: treat as current supported version.
- `v` present but non-integer: skip row.
- `v` greater than supported version: skip row.
- `ts` missing/non-string: normalize to string timestamp in memory.
- Unknown optional fields: tolerated.

Writer behavior:
- Emit one newline-terminated JSON object per event row.
- Emit required fields for app-generated events.
- Emit current schema version in `v`.

## Presence: `rooms/<room>/presence/<presence-id>`

Format:
- UTF-8 JSON object per file.
- One file per active client identity per room.

Fields written by current client:
- `name` (string)
- `color` (string)
- `status` (string)
- `room` (string)
- `last_seen` (number, epoch seconds)

Reader behavior:
- Non-JSON/unreadable file: skip file.
- Missing/invalid fields: sanitize where possible.
- Stale files may be removed by clients.
- Repeated malformed files may be dropped/quarantined by hardened clients.

Path safety:
- `<presence-id>` must be sanitized to prevent traversal/invalid path generation.

## Shared Memory: `memory/global.jsonl`

Format:
- UTF-8 JSONL.
- One memory entry per line.

Current app-generated entry shape:
- `id` (string)
- `ts` (string timestamp)
- `author` (string)
- `summary` (string)
- `topic` (string)
- `confidence` (`low` | `med` | `high`)
- `source` (string)
- `room` (string)
- `origin_event_ref` (string)
- `tags` (array of strings)
- `scope` (string; typically `team` for shared file)

Reader behavior:
- Invalid JSON row: skip row.
- Non-object row: skip row.
- Unknown fields: tolerated.

Writer behavior:
- Emit newline-terminated JSON objects.
- Emit normalized confidence enum for app-generated entries.

## Encoding and Newlines

- UTF-8 required.
- `\n` canonical for JSONL.
- Readers should tolerate CRLF/LF variations.

## Versioning

- Current event schema version: `v=1`.
- Breaking changes require schema/version updates and synchronized docs/examples/tests.
