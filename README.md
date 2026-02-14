# Huddle Chat (Network Edition)

Huddle Chat is a serverless, room-based terminal chat client for shared filesystems, with built-in AI workflows (provider routing, memory grounding, private AI DM history, and approval-gated tool actions).

## Features

- Serverless shared-folder sync for rooms, messages, and presence.
- Cross-platform TUI client (Windows, Linux, macOS).
- Room-based chat with search/navigation (`/search`, `/next`, `/prev`).
- AI commands with provider/model overrides and private/local AI room support.
- Streaming AI responses (enabled by default; configurable per provider).
- Shared memory grounding with citation lines (`Memory used: ...`).
- Agent profile controls for memory scopes and task routing.
- Approval-gated actions and tool execution with local audit trail.
- Presence hardening against malformed presence files.
- Built-in topic help and onboarding checklist (`/help`, `/onboard`).

## Quick Start

1. Clone:
   ```bash
   git clone https://github.com/toutatis-dev/network-chat.git
   cd network-chat
   ```
2. Run:
   - Windows: `run_chat.bat`
   - Linux/macOS: `./run_chat.sh`
3. First launch:
   - Set shared server path.
   - Set username.

Launchers create/use a local venv and install runtime dependencies.

## Commands

- `/status [text]` set presence status.
- `/theme [name]` switch theme.
- `/me [action]` send action-style event.
- `/join <room>` join/create room.
- `/rooms` list rooms.
- `/room` show current room.
- `/search <text>` search current room history.
- `/next` jump to next search hit.
- `/prev` jump to previous search hit.
- `/clearsearch` clear active search.
- `/ai [--provider <gemini|openai>] [--model <name>] [--private] [--no-memory] [--memory-scope <private|repo|team[,..]>] [--act] <prompt>` run AI request.
- `/ask ...` alias for `/ai`.
- `/ai status` show active AI request.
- `/ai cancel` cancel active AI request.
- `/aiproviders` show provider summary.
- `/aiconfig` show local AI config summary.
- `/aiconfig set-key <provider> <api-key>` set provider key.
- `/aiconfig set-model <provider> <model>` set provider default model.
- `/aiconfig set-provider <provider>` set default provider.
- `/aiconfig streaming status` show streaming status.
- `/aiconfig streaming on|off` toggle global streaming.
- `/aiconfig streaming <provider> on|off` toggle provider streaming.
- `/aiconfig streaming provider <provider> on|off` alternate provider toggle syntax.
- `/memory add` draft memory from latest AI response.
- `/memory confirm` save active memory draft.
- `/memory cancel` discard active memory draft.
- `/memory edit <summary|topic|confidence|source> <value>` edit active draft.
- `/memory show-draft` preview active draft.
- `/memory list [limit]` list memory entries.
- `/memory search <query>` search memory entries.
- `/share <target-room> <id|start-end>` share selected `ai-dm` messages into shared room.
- `/agent status|list|use <id>|show [id]|memory <private,repo,team>|route <task> <provider> <model>` manage agent profile routing/memory scopes.
- `/actions` list pending actions.
- `/actions prune` clear terminal action records from in-memory pending set.
- `/action <action-id>` show action details.
- `/approve <action-id>` approve action.
- `/deny <action-id>` deny action.
- `/toolpaths list|add <path>|remove <path>` manage allowed tool roots.
- `/setpath <path>` set shared base path and restart.
- `/help [topic]` show workflow-oriented help pages.
- `/onboard [status|start|reset]` guided setup/checklist for first workflow.
- `/clear` clear local viewport state.
- `/exit` or `/quit` exit app.

## Storage and File Contracts

Shared/network-authoritative files:
- `rooms/<room>/messages.jsonl`
- `rooms/<room>/presence/<presence-id>`
- `memory/global.jsonl`

Local/internal files:
- `.local_chat/rooms/ai-dm/messages.jsonl`
- `.local_chat/ai_config.json`
- `.local_chat/memory/private.jsonl`
- `.local_chat/memory/repo.jsonl`
- `.local_chat/onboarding_state.json`
- `chat_config.json`
- `agents/profiles/*.json`
- `agents/audit.jsonl`
- `agents/actions.jsonl`

Authoritative docs:
- `docs/shared-file-contract.md` (cross-client shared compatibility)
- `docs/local-file-contract.md` (local/internal and app-internal contracts)
- `docs/compatibility-policy.md` (versioning/compatibility rules)
- `docs/shared-file-examples/`
- `docs/local-file-examples/`

## Requirements

- Python 3.x in PATH.
- Shared folder readable/writable by all clients.

Runtime dependencies are pinned in `requirements.txt` and include provider SDKs used for streaming (`openai`, `google-genai`).

## Development

Checks:
- `./check.sh --check` (Linux/macOS)
- `check.bat --check` (Windows)

Project structure:
- `chat.py` app entrypoint/orchestration.
- `huddle_chat/services/` domain services.
- `huddle_chat/providers/` provider clients.
- `huddle_chat/commands/` slash command registry.
- `docs/` contracts and examples.
- `tests/` unit/behavior tests.
