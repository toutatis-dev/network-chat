# Shared File Contract

This document defines the canonical wire format for shared storage files used by Huddle Chat.
It is the interoperability contract across clients.

## Scope

Shared (network authoritative):

- `rooms/<room>/messages.jsonl`
- `rooms/<room>/presence/<presence-id>.json`
- `memory/global.jsonl`

Local-only (not part of cross-client compatibility):

- `.local_chat/rooms/ai-dm/messages.jsonl`
- `.local_chat/ai_config.json`
- `chat_config.json`

## Compatibility Policy

This contract follows the "Strict Reader + Additive Writer" model. See `docs/compatibility-policy.md`.

## Event Log: `rooms/<room>/messages.jsonl`

Format:

- UTF-8 text file.
- One JSON object per line (JSONL).
- Each row is an event.

Required event fields:

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

- Invalid JSON row: ignore row.
- Unknown `type`: ignore row.
- `author`/`text` not strings: ignore row.
- Missing `v`: treat as current supported version.
- `v` greater than supported version: ignore row.
- Unknown optional fields: allowed and preserved in-memory; consumers may ignore them.

Writer behavior:

- Writes one newline-terminated JSON object per event row.
- Includes required fields for app-generated events.
- Emits current schema version in `v`.

## Presence: `rooms/<room>/presence/<presence-id>.json`

Format:

- UTF-8 JSON object per file.
- One file per active client identity in a room.

Fields written by current client:

- `name` (string)
- `color` (string)
- `last_seen` (number, epoch seconds)
- `status` (string)

Reader behavior:

- Non-JSON or unreadable file: skip file.
- Missing/invalid fields: sanitize where possible.
- Stale presence files may be deleted by readers/writers.

Path safety:

- `<presence-id>` must be sanitized to prevent path traversal and invalid characters.

## Shared Memory: `memory/global.jsonl`

Format:

- UTF-8 JSONL.
- One memory entry per line.

Current entry shape:

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

Reader behavior:

- Invalid JSON row: ignore row.
- Non-object row: ignore row.
- Unknown fields: allowed.

Writer behavior:

- Writes newline-terminated JSON object rows.
- Emits normalized `confidence` enum (`low`/`med`/`high`) for app-generated entries.

## Encoding and Newlines

- UTF-8 is required.
- `\n` line delimiters are canonical for JSONL.
- Readers should tolerate CRLF/LF variations.

## Versioning

- Current event schema: `v=1`.
- Breaking changes require:
  - schema version update,
  - this document update,
  - example updates,
  - conformance test updates.
