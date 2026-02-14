# Local/Internal File Contract

This document defines local-only and app-internal file contracts used by the current client.
These files are not the shared cross-client interoperability contract.

## Scope

Local-only:
- `.local_chat/ai_config.json`
- `.local_chat/rooms/ai-dm/messages.jsonl`
- `.local_chat/memory/private.jsonl`
- `.local_chat/memory/repo.jsonl`
- `.local_chat/onboarding_state.json`
- `chat_config.json`

App-internal (stored under shared base path but not part of minimal shared chat wire contract):
- `agents/profiles/*.json`
- `agents/audit.jsonl`
- `agents/actions.jsonl`

## `.local_chat/ai_config.json`

Shape:
- `default_provider` (`gemini` | `openai`)
- `providers` (object)
  - `gemini.api_key` (string)
  - `gemini.model` (string)
  - `openai.api_key` (string)
  - `openai.model` (string)
- `streaming` (object)
  - `enabled` (bool; default `true`)
  - `providers.gemini` (bool)
  - `providers.openai` (bool)

Loader behavior:
- Missing or malformed file falls back to defaults.
- Missing subkeys are merged from defaults.

## `.local_chat/rooms/ai-dm/messages.jsonl`

Format:
- UTF-8 JSONL event log.
- Uses same event row shape as shared `messages.jsonl`.

Semantics:
- Local private room for AI prompts/responses.
- Not shared to other clients unless explicitly bridged via `/share`.

## `.local_chat/memory/private.jsonl` and `.local_chat/memory/repo.jsonl`

Format:
- UTF-8 JSONL memory rows.

App-generated row shape:
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
- `scope` (`private` or `repo`)

Reader behavior:
- Invalid JSON/non-object rows are skipped.
- Unknown fields are tolerated.

## `chat_config.json`

Current app-managed keys:
- `path` (string)
- `theme` (string)
- `username` (string)
- `room` (string)
- `client_id` (string)
- `agent_profile` (string)
- `tool_paths` (array of strings)

Behavior:
- Missing file yields defaults/in-memory fallbacks.
- Corrupt JSON is ignored with warning and defaults are used.

## `.local_chat/onboarding_state.json`

Shape:
- `started_at` (string timestamp or empty)
- `completed_at` (string timestamp or empty)
- `steps` (object)
  - `provider_configured` (bool)
  - `sent_ai_prompt` (bool)
  - `reviewed_or_decided_action` (bool)
  - `saved_memory` (bool)

Behavior:
- Missing/corrupt file defaults to all-false step state.
- File is updated by `/onboard status|start|reset`.

## `agents/profiles/*.json`

Agent profile object keys:
- `id`, `name`, `description`, `system_prompt`
- `tool_policy` (mode/approval/allowed tool list)
- `memory_policy` (scopes)
- `routing_policy` (task route map)
- `created_by`, `updated_by`, `updated_at`, `version`

## `agents/audit.jsonl`

Agent audit row shape:
- `ts` (string timestamp)
- `action` (string)
- `profile_id` (string)
- `actor` (string)

## `agents/actions.jsonl`

Action rows are append-only lifecycle records keyed by `action_id`.
Current row families include:
- Pending action creation rows (`status: pending`, tool/summary/inputs fields)
- Decision rows (`decision: approved|denied`)
- Runtime status rows (`status: running|completed|failed|expired`)
- Result rows (`result` payload for completed/failed runs)

Readers should tolerate unknown additive fields.

## Encoding and Newlines

- UTF-8 required.
- JSONL files use `\n` as canonical delimiter.
- Readers should tolerate CRLF/LF variations.
