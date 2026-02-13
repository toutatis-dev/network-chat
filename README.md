# Huddle Chat (Network Edition)

A lightweight, serverless chat application designed for local networks. It uses a shared file system (like a Windows network drive) to sync messages and presence, making it instant to deploy on corporate LANs or home networks without needing a dedicated server.

## Features

*   **Serverless:** Relies entirely on a shared network folder for data sync.
*   **Zero Config Client:** Just run the script, point it to the shared folder, and chat.
*   **Cross-Platform Core:** Built with Python, running on Windows, Linux, and macOS.
*   **TUI Interface:** Professional split-screen terminal interface.
*   **Real-time Presence:** See who is online in the sidebar.
*   **Themes:** Switch between multiple color themes (Default, Nord, Matrix, Solarized, Monokai).
*   **Persistent Identity:** Remembers your username and settings.
*   **Cross-Platform File Locking:** Uses robust write locking for shared chat files on Windows and Linux.

## Quick Start

1.  **Clone the Repository:**
    Open Command Prompt or PowerShell and run:
    ```cmd
    git clone https://github.com/toutatis-dev/network-chat.git
    cd network-chat
    ```

2.  **Run:**
    *   **Windows:** Double-click `run_chat.bat` (or run from Command Prompt/PowerShell).
    *   **Linux/macOS:** Run `./run_chat.sh` from your terminal.
    *   Launchers auto-detect Python, create a virtual environment, and install runtime dependencies.

3.  **Setup:**
    *   On the first launch, you will be asked for the **Server Path**.
    *   Enter the UNC path to your shared folder (e.g., `\\fileserver\Share\Chat`).
    *   Enter your desired username.

## Usage

*   **Chat:** Type your message and press Enter.
*   **Commands:**
    *   `/status [text]` - Set your status (e.g., "In a meeting").
    *   `/theme [name]` - Change the color theme (e.g., `/theme nord`).
    *   `/me [action]` - Perform an action (e.g., `/me waves`).
    *   `/join [room]` - Join or create a room (e.g., `/join dev`).
    *   `/rooms` - List available rooms.
    *   `/room` - Show your current room.
    *   `/search [text]` - Search message history in the current room.
    *   `/next` - Jump to the next search match.
    *   `/prev` - Jump to the previous search match.
    *   `/clearsearch` - Clear the active search filter.
    *   `/ai [--provider <gemini|openai>] [--model <name>] [--private] [--no-memory] [prompt]` - Ask AI (uses shared memory by default unless `--no-memory`).
    *   `/aiproviders` - Show local AI provider status.
    *   `/aiconfig` - Show local AI config status.
    *   `/aiconfig set-key <provider> <api-key>` - Save provider API key locally.
    *   `/aiconfig set-model <provider> <model>` - Save default model locally.
    *   `/aiconfig set-provider <provider>` - Set default provider locally.
    *   `/ai status` - Show active local AI request status.
    *   `/ai cancel` - Request cancellation of active local AI request.
    *   `/memory add` - Draft a shared memory entry from the latest AI response (shows potential duplicate warnings).
    *   `/memory confirm` - Confirm and write active memory draft.
    *   `/memory cancel` - Cancel active memory draft.
    *   `/memory edit <field> <value>` - Edit draft fields (`summary`, `topic`, `confidence`, `source`).
    *   `/memory show-draft` - Show the active draft preview.
    *   `/memory list [limit]` - List recent shared memory entries.
    *   `/memory search <query>` - Search shared memory entries.
    *   `/share <target-room> <id|start-end>` - Share message(s) from local `ai-dm` into a shared room (IDs are shown as `(n)` in `ai-dm`).
    *   `/setpath [path]` - Change the shared server path.
    *   `/clear` - Clear your local chat history.
    *   `/exit` - Quit the application.
    *   `/join ai-dm` - Enter local-only private AI room.
*   **AI grounding notes:**
    *   `/ai` automatically retrieves relevant shared memory entries and injects them as context.
    *   AI responses include a system citation line when memory is used (for example: `Memory used: mem_...`).

## Storage Format

This version uses a room-based JSONL storage layout:

*   `rooms/<room>/messages.jsonl` for chat events.
*   `rooms/<room>/presence/<user-id>.json` for online presence.
*   `memory/global.jsonl` for shared memory entries.
*   `.local_chat/rooms/ai-dm/messages.jsonl` for private local AI history.
*   `.local_chat/ai_config.json` for local AI provider credentials and defaults.

**Hard switch note:** legacy `Shared_chat.txt` is not read by this version.

Canonical shared-file contract docs:

*   `docs/shared-file-contract.md` - authoritative wire format for shared files.
*   `docs/compatibility-policy.md` - compatibility/versioning rules.
*   `docs/shared-file-examples/` - example valid/invalid records.

## Requirements

*   **Python 3.x** must be installed and added to your system PATH.
*   A shared network folder that all users can read/write to.

## Supported Platforms

*   **Windows:** officially supported
*   **Linux:** officially supported
*   **macOS:** officially supported

## Development

This project uses a comprehensive suite of quality checks to maintain code resilience and professionalism.

### Project Layout
*   `run_chat.bat` / `run_chat.sh` - cross-platform launchers.
*   `chat.py` - application entrypoint/orchestration.
*   `huddle_chat/bootstrap.py` - shared venv/dependency bootstrap used by launchers and CI preflight.
*   `huddle_chat/constants.py` - shared constants, themes, and defaults.
*   `huddle_chat/ui.py` - prompt-toolkit completer/lexer UI components.
*   `huddle_chat/services/` - extracted domain services (`ai`, `command_ops`, `memory`, `storage`, `runtime`).
*   `huddle_chat/commands/` - slash-command registry and handlers.
*   `huddle_chat/providers/` - provider-specific AI clients (`gemini`, `openai`).
*   `huddle_chat/models.py` - shared TypedDicts for events/config/data shapes.
*   `docs/` - canonical shared-file contract, compatibility policy, and examples.
*   `tests/` - unit and behavior tests.

### Quality Checks
*   **Black**: Automatic code formatting.
*   **Flake8**: Linting for syntax and style issues.
*   **Mypy**: Static type checking to catch logic errors.
*   **Pytest**: Unit testing for core functionality.

### Running Checks
You should run the unified check script before committing any changes to ensure everything is in order.

*   **Windows:**
    ```cmd
    check.bat
    ```
*   **Linux/macOS:**
    ```bash
    ./check.sh
    ```

### Dependency Files
*   `requirements.in` - runtime dependency source list.
*   `requirements.txt` - pinned runtime lock file used by launchers.
*   `requirements-dev.in` - dev dependency source list.
*   `requirements-dev.txt` - pinned dev lock file used by check scripts and CI.

### Continuous Integration
All pushes and pull requests are automatically verified via **GitHub Actions** on Windows, Linux, and macOS using Python 3.13.
