# Huddle Chat (Network Edition)

A lightweight, serverless chat application designed for local networks. It uses a shared file system (like a Windows network drive) to sync messages and presence, making it instant to deploy on corporate LANs or home networks without needing a dedicated server.

## Features

*   **Serverless:** Relies entirely on a shared network folder for data sync.
*   **Zero Config Client:** Just run the script, point it to the shared folder, and chat.
*   **Cross-Platform Core:** Built with Python, running natively on Windows.
*   **TUI Interface:** Professional split-screen terminal interface.
*   **Real-time Presence:** See who is online in the sidebar.
*   **Themes:** Switch between multiple color themes (Default, Nord, Matrix, Solarized, Monokai).
*   **Persistent Identity:** Remembers your username and settings.
*   **Cross-Platform File Locking:** Uses robust write locking for shared chat files on Windows and Linux.

## Quick Start (Windows)

1.  **Clone the Repository:**
    Open Command Prompt or PowerShell and run:
    ```cmd
    git clone https://github.com/toutatis-dev/network-chat.git
    cd network-chat
    ```

2.  **Run:** Double-click `run_chat.bat` (or run it from the command line).
    *   The script will automatically detect if Python is installed.
    *   It will create a virtual environment and install all dependencies for you.

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
    *   `/ai [--provider <gemini|openai>] [--model <name>] [--private] [prompt]` - Ask AI.
    *   `/aiproviders` - Show local AI provider status.
    *   `/aiconfig` - Show local AI config status.
    *   `/aiconfig set-key <provider> <api-key>` - Save provider API key locally.
    *   `/aiconfig set-model <provider> <model>` - Save default model locally.
    *   `/aiconfig set-provider <provider>` - Set default provider locally.
    *   `/share <target-room> <id|start-end>` - Share message(s) from local `ai-dm` into a shared room (IDs are shown as `(n)` in `ai-dm`).
    *   `/setpath [path]` - Change the shared server path.
    *   `/clear` - Clear your local chat history.
    *   `/exit` - Quit the application.
    *   `/join ai-dm` - Enter local-only private AI room.

## Storage Format

This version uses a room-based JSONL storage layout:

*   `rooms/<room>/messages.jsonl` for chat events.
*   `rooms/<room>/presence/<user-id>.json` for online presence.
*   `.local_chat/rooms/ai-dm/messages.jsonl` for private local AI history.
*   `.local_chat/ai_config.json` for local AI provider credentials and defaults.

**Hard switch note:** legacy `Shared_chat.txt` is not read by this version.

## Requirements

*   **Python 3.x** must be installed and added to your system PATH.
*   A shared network folder that all users can read/write to.

## Development

This project uses a comprehensive suite of quality checks to maintain code resilience and professionalism.

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

### Continuous Integration
All pushes and pull requests are automatically verified via **GitHub Actions** on Ubuntu using Python 3.13.
