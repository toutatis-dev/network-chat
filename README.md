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
    *   Enter the UNC path to your shared folder (e.g., `\fileserver\Share\Chat`).
    *   Enter your desired username.

## Usage

*   **Chat:** Type your message and press Enter.
*   **Commands:**
    *   `/status [text]` - Set your status (e.g., "In a meeting").
    *   `/theme [name]` - Change the color theme (e.g., `/theme nord`).
    *   `/me [action]` - Perform an action (e.g., `/me waves`).
    *   `/setpath [path]` - Change the shared server path.
    *   `/clear` - Clear your local chat history.
    *   `/exit` - Quit the application.

## Requirements

*   **Python 3.x** must be installed and added to your system PATH.
*   A shared network folder that all users can read/write to.

## Development

This project uses `pytest` for testing. To run tests manually:

1.  Activate the virtual environment:
    ```cmd
    venv\Scripts\activate
    ```
2.  Run tests:
    ```cmd
    pytest
    ```
