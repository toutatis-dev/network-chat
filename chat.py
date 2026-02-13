import os
import time
import json
import asyncio
import string
import random
import re
import logging
from typing import Any
from datetime import datetime
from threading import Thread
from pathlib import Path

from prompt_toolkit.application import Application
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout.containers import (
    HSplit,
    Window,
    VSplit,
    FloatContainer,
    Float,
)
from prompt_toolkit.layout.layout import Layout
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.widgets import TextArea, Frame
from prompt_toolkit.styles import Style
from prompt_toolkit.lexers import Lexer
from prompt_toolkit.completion import Completer, Completion
from prompt_toolkit.layout.menus import CompletionsMenu

portalocker: Any
_PORTALOCKER_IMPORT_ERROR: ImportError | None
try:
    import portalocker as _portalocker  # type: ignore[import-not-found]
except ImportError as exc:  # pragma: no cover - tested via startup guard
    portalocker = None
    _PORTALOCKER_IMPORT_ERROR = exc
else:
    portalocker = _portalocker
    _PORTALOCKER_IMPORT_ERROR = None

# Global Configuration
CONFIG_FILE = "chat_config.json"
DEFAULT_PATH = None
LOCK_TIMEOUT_SECONDS = 2.0
LOCK_MAX_ATTEMPTS = 20
LOCK_BACKOFF_BASE_SECONDS = 0.05
LOCK_BACKOFF_MAX_SECONDS = 0.5
MAX_PRESENCE_ID_LENGTH = 64
logger = logging.getLogger(__name__)

# Themes Configuration
THEMES = {
    "default": {
        "chat-area": "bg:#000000 #ffffff",
        "input-area": "bg:#222222 #ffffff",
        "sidebar": "bg:#111111 #88ff88",
        "frame.label": "bg:#0000aa #ffffff bold",
        "status": "bg:#004400 #ffffff",
        "completion-menu": "bg:#333333 #ffffff",
        "completion-menu.completion.current": "bg:#00aaaa #000000",
    },
    "nord": {
        "chat-area": "bg:#2E3440 #D8DEE9",  # Polar Night / Snow Storm
        "input-area": "bg:#3B4252 #ECEFF4",  # Slightly lighter background
        "sidebar": "bg:#434C5E #8FBCBB",  # Frost / Aurora
        "frame.label": "bg:#5E81AC #ECEFF4 bold",  # Frost Blue
        "status": "bg:#A3BE8C #2E3440",  # Aurora Green
        "completion-menu": "bg:#4C566A #ECEFF4",
        "completion-menu.completion.current": "bg:#88C0D0 #2E3440",
    },
    "matrix": {
        "chat-area": "bg:#000000 #00FF00",
        "input-area": "bg:#001100 #00DD00",
        "sidebar": "bg:#001100 #00FF00",
        "frame.label": "bg:#003300 #00FF00 bold",
        "status": "bg:#004400 #ffffff",
        "completion-menu": "bg:#002200 #00FF00",
        "completion-menu.completion.current": "bg:#00FF00 #000000",
    },
    "solarized-dark": {
        "chat-area": "bg:#002b36 #839496",
        "input-area": "bg:#073642 #93a1a1",
        "sidebar": "bg:#073642 #2aa198",
        "frame.label": "bg:#268bd2 #fdf6e3 bold",
        "status": "bg:#859900 #fdf6e3",
        "completion-menu": "bg:#073642 #93a1a1",
        "completion-menu.completion.current": "bg:#2aa198 #002b36",
    },
    "monokai": {
        "chat-area": "bg:#272822 #F8F8F2",
        "input-area": "bg:#3E3D32 #F8F8F2",
        "sidebar": "bg:#272822 #A6E22E",
        "frame.label": "bg:#F92672 #F8F8F2 bold",
        "status": "bg:#66D9EF #272822",
        "completion-menu": "bg:#3E3D32 #F8F8F2",
        "completion-menu.completion.current": "bg:#FD971F #272822",
    },
}

COLORS = [
    "green",
    "cyan",
    "magenta",
    "yellow",
    "blue",
    "red",
    "white",
    "brightgreen",
    "brightcyan",
    "brightmagenta",
    "brightyellow",
    "brightblue",
    "brightred",
]


class SlashCompleter(Completer):
    def get_completions(self, document, complete_event):
        text = document.text_before_cursor
        if text.startswith("/theme "):
            # Suggest themes
            prefix = text[7:].lower()
            for theme_name in THEMES.keys():
                if theme_name.startswith(prefix):
                    yield Completion(
                        theme_name, start_position=-len(prefix), display=theme_name
                    )
        elif text.startswith("/"):
            commands = [
                ("/status", "Set your status (e.g. /status Busy)"),
                ("/theme", "Change color theme (e.g. /theme nord)"),
                ("/me", "Perform an action (e.g. /me waves)"),
                ("/setpath", "Change the chat server path"),
                ("/exit", "Quit the application"),
                ("/clear", "Clear local chat history"),
            ]
            word = text.lower()
            for cmd, desc in commands:
                if cmd.startswith(word):
                    yield Completion(
                        cmd, start_position=-len(word), display=cmd, display_meta=desc
                    )


class ChatLexer(Lexer):
    def __init__(self, app_ref):
        self.app_ref = app_ref

    def lex_document(self, document):
        def get_line_tokens(line_num):
            try:
                line_text = document.lines[line_num]
                if ": " in line_text:
                    parts = line_text.split(": ", 1)
                    prefix = parts[0]
                    if "] " in prefix:
                        ts_str, name = prefix.split("] ", 1)
                        ts_clean = ts_str.replace("[", "")
                        user_data = self.app_ref.online_users.get(name, {})
                        u_color = user_data.get("color", "white")
                        return [
                            ("class:timestamp", "[" + ts_clean + "] "),
                            (f"fg:{u_color} bold", name),
                            ("", ": " + parts[1]),
                        ]
            except Exception:
                pass
            return [("", document.lines[line_num])]

        return get_line_tokens


class ChatApp:
    def __init__(self):
        self.ensure_locking_dependency()
        self.name = "Anonymous"
        self.presence_file_id = self.sanitize_presence_id(self.name)
        self.color = "white"
        self.status = ""
        self.running = True
        self.last_pos = 0
        self.messages = []
        self.online_users = {}

        # Load Config
        config_data = self.load_config_data()
        self.base_dir = config_data.get("path", DEFAULT_PATH)
        self.current_theme = config_data.get("theme", "default")

        # Validate path if missing (prompt user)
        if not self.base_dir or not os.path.exists(self.base_dir):
            self.base_dir = self.prompt_for_path()
            self.save_config()

        self.chat_file = os.path.join(self.base_dir, "Shared_chat.txt")
        self.presence_dir = os.path.join(self.base_dir, "presence")
        self.ensure_paths()

        # TUI Setup
        self.output_field = TextArea(
            style="class:chat-area",
            focusable=False,
            wrap_lines=True,
            lexer=ChatLexer(self),
        )
        self.input_field = TextArea(
            height=3,
            prompt="> ",
            style="class:input-area",
            multiline=False,
            wrap_lines=False,
            completer=SlashCompleter(),
            complete_while_typing=True,
        )
        self.sidebar_control = FormattedTextControl()
        self.sidebar_window = Window(
            content=self.sidebar_control, width=30, style="class:sidebar"
        )

        self.kb = KeyBindings()

        @self.kb.add("enter")
        def _(event):
            self.handle_input(self.input_field.text)

        @self.kb.add("c-c")
        def _(event):
            event.app.exit()

        root_container = HSplit(
            [
                VSplit(
                    [
                        Frame(self.output_field, title="Chat History"),
                        Frame(self.sidebar_window, title="Online"),
                    ]
                ),
                Frame(self.input_field, title="Your Message (/ for commands)"),
            ]
        )

        self.layout_container = FloatContainer(
            content=root_container,
            floats=[
                Float(
                    xcursor=True,
                    ycursor=True,
                    content=CompletionsMenu(max_height=16, scroll_offset=1),
                )
            ],
        )

        self.application = Application(
            layout=Layout(self.layout_container),
            key_bindings=self.kb,
            style=self.get_style(),
            full_screen=True,
            mouse_support=True,
        )

    def ensure_locking_dependency(self) -> None:
        if portalocker is not None:
            return

        detail = ""
        if _PORTALOCKER_IMPORT_ERROR is not None:
            detail = f" Original error: {_PORTALOCKER_IMPORT_ERROR}."
        raise SystemExit(
            "Missing dependency 'portalocker'. "
            "Install dependencies with 'pip install -r requirements.txt'." + detail
        )

    def load_config_data(self) -> dict[str, Any]:
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r") as f:
                    return json.load(f)
            except (OSError, json.JSONDecodeError) as exc:
                logger.warning("Failed to load config from %s: %s", CONFIG_FILE, exc)
        return {}

    def save_config(self) -> None:
        with open(CONFIG_FILE, "w") as f:
            json.dump(
                {
                    "path": self.base_dir,
                    "theme": self.current_theme,
                    "username": self.name,
                },
                f,
            )

    def get_style(self) -> Style:
        theme_dict = THEMES.get(self.current_theme, THEMES["default"])
        # Merge basic defaults if needed, but THEMES should be complete enough
        base_dict = {
            "scrollbar.background": "bg:#222222",
            "scrollbar.button": "bg:#777777",
        }
        base_dict.update(theme_dict)
        return Style.from_dict(base_dict)

    def get_available_drives(self) -> list[str]:
        drives = []
        try:
            if os.name == "nt":
                os.popen("fsutil fsinfo drives").read().strip()
            # This often returns junk text on some systems, fallback loop is safer
        except Exception:
            pass
        for letter in string.ascii_uppercase:
            if os.path.exists(f"{letter}:\\"):
                drives.append(f"{letter}:\\")
        return drives

    def sanitize_presence_id(self, name: str) -> str:
        cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", name).strip(" .")
        if not cleaned or not re.search(r"[A-Za-z0-9]", cleaned):
            return "Anonymous"
        return cleaned[:MAX_PRESENCE_ID_LENGTH]

    def get_presence_path(self) -> Path:
        base = Path(self.presence_dir).resolve()
        target = (base / self.presence_file_id).resolve()
        if target.parent != base:
            raise ValueError("Invalid username for presence path.")
        return target

    def prompt_for_path(self) -> str:
        print("--- Huddle Chat Setup ---")
        print("Available Drives detected:")
        try:
            drives = self.get_available_drives()
            print("  " + ", ".join(drives))
        except Exception:
            pass

        if DEFAULT_PATH:
            print(f"\nDefault Server: {DEFAULT_PATH}")
            prompt_msg = "Enter server path [Press Enter for default]: "
        else:
            prompt_msg = "Enter server path: "

        while True:
            user_path = input(prompt_msg).strip()

            if not user_path:
                if DEFAULT_PATH:
                    base_dir = DEFAULT_PATH
                else:
                    continue
            else:
                base_dir = user_path

            base_dir = base_dir.replace('"', "").replace("'", "")

            if os.path.exists(base_dir):
                return base_dir
            else:
                print(f"Warning: Path '{base_dir}' was not found.")
                choice = input(
                    "Is this a mapped drive? Force use anyway? (y/n/create): "
                ).lower()
                if choice == "y":
                    return base_dir
                elif choice == "create":
                    try:
                        os.makedirs(base_dir)
                        return base_dir
                    except Exception as e:
                        print(f"Failed to create: {e}")

    def ensure_paths(self) -> None:
        if not os.path.exists(self.presence_dir):
            try:
                os.makedirs(self.presence_dir)
            except Exception:
                pass

    def get_online_users(self) -> dict[str, dict[str, Any]]:
        online: dict[str, dict[str, Any]] = {}
        now = time.time()
        if not os.path.exists(self.presence_dir):
            return online
        for filename in os.listdir(self.presence_dir):
            path = os.path.join(self.presence_dir, filename)
            try:
                if now - os.path.getmtime(path) < 30:
                    with open(path, "r") as f:
                        data = json.load(f)
                        if isinstance(data, dict):
                            display_name = (
                                str(data.get("name", filename)).strip() or filename
                            )
                            online[display_name] = data
                        else:
                            online[filename] = {"color": "white", "status": ""}
                else:
                    try:
                        os.remove(path)
                    except OSError as exc:
                        logger.warning(
                            "Failed to remove stale presence file %s: %s", path, exc
                        )
            except (OSError, json.JSONDecodeError, ValueError) as exc:
                logger.warning("Failed to process presence file %s: %s", path, exc)
        return online

    def heartbeat(self) -> None:
        try:
            presence_path = self.get_presence_path()
        except ValueError:
            return

        while self.running:
            try:
                data = {
                    "name": self.name,
                    "color": self.color,
                    "last_seen": time.time(),
                    "status": self.status,
                }
                with open(presence_path, "w") as f:
                    json.dump(data, f)
            except OSError as exc:
                logger.warning("Failed heartbeat write to %s: %s", presence_path, exc)
            self.online_users = self.get_online_users()
            self.update_sidebar()
            time.sleep(10)
        if os.path.exists(presence_path):
            try:
                os.remove(presence_path)
            except OSError as exc:
                logger.warning(
                    "Failed to remove presence file on shutdown %s: %s",
                    presence_path,
                    exc,
                )

    def update_sidebar(self) -> None:
        fragments: list[tuple[str, str]] = []
        users = sorted(self.online_users.keys())
        for idx, user in enumerate(users):
            data = self.online_users[user]
            color = self.sanitize_sidebar_color(data.get("color", "white"))
            display_name = self.sanitize_sidebar_text(user, 64)
            status = self.sanitize_sidebar_text(data.get("status", ""), 80)
            fragments.append((f"fg:{color}", f"● {display_name}"))
            if status:
                fragments.append(("fg:#888888", f" [{status}]"))
            if idx < len(users) - 1:
                fragments.append(("", "\n"))
        self.sidebar_control.text = fragments
        self.application.invalidate()

    def sanitize_sidebar_text(self, value: Any, max_len: int) -> str:
        text = str(value).replace("\r", " ").replace("\n", " ").replace("\t", " ")
        return text[:max_len]

    def sanitize_sidebar_color(self, value: Any) -> str:
        color = str(value).strip().lower()
        if color in COLORS:
            return color
        return "white"

    def handle_input(self, text: str) -> None:
        text = text.strip()
        if not text:
            return

        if text.startswith("/"):
            parts = text.split(" ", 1)
            command = parts[0].lower()
            args = parts[1] if len(parts) > 1 else ""

            if command == "/theme":
                if not args:
                    # List themes in chat
                    avail = ", ".join(THEMES.keys())
                    self.output_field.text += f"\n[System] Available themes: {avail}\n"
                    self.output_field.buffer.cursor_position = len(
                        self.output_field.text
                    )
                else:
                    target = args.strip().lower()
                    if target in THEMES:
                        self.current_theme = target
                        self.save_config()
                        self.application.style = self.get_style()  # Hot-reload style
                        self.application.invalidate()
                    else:
                        self.output_field.text += (
                            f"\n[System] Unknown theme '{target}'.\n"
                        )
                        self.output_field.buffer.cursor_position = len(
                            self.output_field.text
                        )
                self.input_field.text = ""
                return

            if command == "/setpath":
                new_path = args.strip()
                self.base_dir = new_path
                self.save_config()
                self.application.exit(result="restart")
                return

            if command == "/status":
                self.status = args[:20]
                Thread(target=self.force_heartbeat).start()
                self.input_field.text = ""
                return
            if command in ["/exit", "/quit"]:
                self.application.exit()
                return
            if command == "/clear":
                self.messages = []
                self.output_field.text = ""
                self.input_field.text = ""
                return
            if command == "/me":
                timestamp = datetime.now().strftime("%H:%M:%S")
                if self.write_to_file(f"[{timestamp}] * {self.name} {args}\n"):
                    self.input_field.text = ""
                else:
                    self.output_field.text += "\n[System] Error: Could not send message. Network busy or locked.\n"
                    self.output_field.buffer.cursor_position = len(
                        self.output_field.text
                    )
                return

        timestamp = datetime.now().strftime("%H:%M:%S")
        if self.write_to_file(f"[{timestamp}] {self.name}: {text}\n"):
            self.input_field.text = ""
        else:
            self.output_field.text += (
                "\n[System] Error: Could not send message. Network busy or locked.\n"
            )
            self.output_field.buffer.cursor_position = len(self.output_field.text)

    def write_to_file(self, msg: str) -> bool:
        self.ensure_locking_dependency()
        assert portalocker is not None

        for attempt in range(LOCK_MAX_ATTEMPTS):
            try:
                with portalocker.Lock(
                    self.chat_file,
                    mode="a",
                    timeout=LOCK_TIMEOUT_SECONDS,
                    fail_when_locked=True,
                    encoding="utf-8",
                ) as f:
                    f.write(msg)
                    f.flush()
                    os.fsync(f.fileno())
                return True
            except portalocker.exceptions.LockException:
                pass
            except OSError:
                pass
            except Exception:
                return False

            if attempt == LOCK_MAX_ATTEMPTS - 1:
                break
            delay = min(
                LOCK_BACKOFF_MAX_SECONDS,
                LOCK_BACKOFF_BASE_SECONDS * (2 ** min(attempt, 5)),
            )
            time.sleep(delay + random.uniform(0, 0.03))

        return False

    def force_heartbeat(self) -> None:
        try:
            presence_path = self.get_presence_path()
            data = {
                "name": self.name,
                "color": self.color,
                "last_seen": time.time(),
                "status": self.status,
            }
            with open(presence_path, "w") as f:
                json.dump(data, f)
            self.online_users = self.get_online_users()
            self.update_sidebar()
        except (OSError, ValueError) as exc:
            logger.warning("Failed forced heartbeat update: %s", exc)

    async def monitor_messages(self) -> None:
        while self.running:
            if os.path.exists(self.chat_file):
                try:
                    with open(self.chat_file, "r") as f:
                        current_size = os.path.getsize(self.chat_file)
                        if current_size < self.last_pos:
                            logger.warning(
                                "Chat file shrank from offset %s to %s; resetting.",
                                self.last_pos,
                                current_size,
                            )
                            self.last_pos = 0
                        f.seek(self.last_pos)
                        new_lines = f.readlines()
                        if new_lines:
                            for line in new_lines:
                                if line.strip():
                                    self.messages.append(line.strip())
                                    if len(self.messages) > 200:
                                        self.messages.pop(0)
                            self.last_pos = f.tell()
                            self.output_field.text = "\n".join(self.messages)
                            self.output_field.buffer.cursor_position = len(
                                self.output_field.text
                            )
                            self.application.invalidate()
                except OSError as exc:
                    logger.warning(
                        "Failed while monitoring chat file %s: %s", self.chat_file, exc
                    )
            await asyncio.sleep(0.5)

    def run(self) -> None:
        print(f"Connecting to: {self.base_dir}")

        # Load persisted username
        config_data = self.load_config_data()
        saved_name = config_data.get("username", "")

        if saved_name:
            user_input = input(f"Enter your name [Default: {saved_name}]: ").strip()
            self.name = user_input if user_input else saved_name
        else:
            self.name = input("Enter your name: ").strip() or "Anonymous"
        self.presence_file_id = self.sanitize_presence_id(self.name)

        # Save config immediately to persist the name (or update it)
        self.save_config()

        online = self.get_online_users()
        taken = set()
        for u_data in online.values():
            if isinstance(u_data, dict):
                taken.add(u_data.get("color"))
            else:
                taken.add(u_data)
        self.color = next((c for c in COLORS if c not in taken), "white")
        if self.color == "white" and "white" in taken:
            self.color = COLORS[hash(self.name) % len(COLORS)]

        if os.path.exists(self.chat_file):
            self.last_pos = max(0, os.path.getsize(self.chat_file) - 5000)

        Thread(target=self.heartbeat, daemon=True).start()
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.create_task(self.monitor_messages())

        try:
            result = loop.run_until_complete(self.application.run_async())
            if result == "restart":
                print("\nRestarting...")
        except KeyboardInterrupt:
            pass
        finally:
            self.running = False


if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s: %(message)s")
    ChatApp().run()
