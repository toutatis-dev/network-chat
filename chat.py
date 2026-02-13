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
DEFAULT_ROOM = "general"
MAX_MESSAGES = 200
LOCK_TIMEOUT_SECONDS = 2.0
LOCK_MAX_ATTEMPTS = 20
LOCK_BACKOFF_BASE_SECONDS = 0.05
LOCK_BACKOFF_MAX_SECONDS = 0.5
MAX_PRESENCE_ID_LENGTH = 64
PRESENCE_REFRESH_INTERVAL_SECONDS = 1.0
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
        "search-match": "bg:#333300 #ffff66",
        "mention": "fg:#ffaf00 bold",
        "timestamp": "fg:#888888",
    },
    "nord": {
        "chat-area": "bg:#2E3440 #D8DEE9",
        "input-area": "bg:#3B4252 #ECEFF4",
        "sidebar": "bg:#434C5E #8FBCBB",
        "frame.label": "bg:#5E81AC #ECEFF4 bold",
        "status": "bg:#A3BE8C #2E3440",
        "completion-menu": "bg:#4C566A #ECEFF4",
        "completion-menu.completion.current": "bg:#88C0D0 #2E3440",
        "search-match": "bg:#5e81ac #eceff4",
        "mention": "fg:#ebcb8b bold",
        "timestamp": "fg:#81a1c1",
    },
    "matrix": {
        "chat-area": "bg:#000000 #00FF00",
        "input-area": "bg:#001100 #00DD00",
        "sidebar": "bg:#001100 #00FF00",
        "frame.label": "bg:#003300 #00FF00 bold",
        "status": "bg:#004400 #ffffff",
        "completion-menu": "bg:#002200 #00FF00",
        "completion-menu.completion.current": "bg:#00FF00 #000000",
        "search-match": "bg:#003300 #aaffaa",
        "mention": "fg:#ffffff bold",
        "timestamp": "fg:#66cc66",
    },
    "solarized-dark": {
        "chat-area": "bg:#002b36 #839496",
        "input-area": "bg:#073642 #93a1a1",
        "sidebar": "bg:#073642 #2aa198",
        "frame.label": "bg:#268bd2 #fdf6e3 bold",
        "status": "bg:#859900 #fdf6e3",
        "completion-menu": "bg:#073642 #93a1a1",
        "completion-menu.completion.current": "bg:#2aa198 #002b36",
        "search-match": "bg:#586e75 #fdf6e3",
        "mention": "fg:#cb4b16 bold",
        "timestamp": "fg:#93a1a1",
    },
    "monokai": {
        "chat-area": "bg:#272822 #F8F8F2",
        "input-area": "bg:#3E3D32 #F8F8F2",
        "sidebar": "bg:#272822 #A6E22E",
        "frame.label": "bg:#F92672 #F8F8F2 bold",
        "status": "bg:#66D9EF #272822",
        "completion-menu": "bg:#3E3D32 #F8F8F2",
        "completion-menu.completion.current": "bg:#FD971F #272822",
        "search-match": "bg:#49483e #f8f8f2",
        "mention": "fg:#fd971f bold",
        "timestamp": "fg:#a59f85",
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
    def __init__(self, app_ref: "ChatApp"):
        self.app_ref = app_ref

    def get_completions(self, document, complete_event):
        text = document.text_before_cursor
        if text.startswith("/theme "):
            prefix = text[7:].lower()
            for theme_name in THEMES.keys():
                if theme_name.startswith(prefix):
                    yield Completion(
                        theme_name, start_position=-len(prefix), display=theme_name
                    )
            return

        if text.startswith("/join "):
            prefix = text[6:].lower()
            for room_name in self.app_ref.list_rooms():
                if room_name.startswith(prefix):
                    yield Completion(
                        room_name, start_position=-len(prefix), display=room_name
                    )
            return

        if text.startswith("/"):
            commands = [
                ("/status", "Set your status (e.g. /status Busy)"),
                ("/theme", "Change color theme (e.g. /theme nord)"),
                ("/me", "Perform an action (e.g. /me waves)"),
                ("/setpath", "Change the chat server path"),
                ("/join", "Join or create room (e.g. /join dev)"),
                ("/rooms", "List available rooms"),
                ("/room", "Show current room"),
                ("/search", "Search messages in current room"),
                ("/next", "Jump to next search match"),
                ("/prev", "Jump to previous search match"),
                ("/clearsearch", "Clear active search"),
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
    def __init__(self, app_ref: "ChatApp"):
        self.app_ref = app_ref

    def lex_document(self, document):
        def get_line_tokens(line_num):
            try:
                line_text = document.lines[line_num]
                return self.app_ref.lex_line(line_text)
            except Exception:
                return [("", document.lines[line_num])]

        return get_line_tokens


class ChatApp:
    def __init__(self):
        self.ensure_locking_dependency()
        self.name = "Anonymous"
        self.color = "white"
        self.status = ""
        self.running = True
        self.current_theme = "default"
        self.current_room = DEFAULT_ROOM
        self.presence_file_id = self.sanitize_presence_id(self.name)

        self.messages: list[str] = []
        self.message_events: list[dict[str, Any]] = []
        self.online_users: dict[str, dict[str, Any]] = {}
        self.last_pos_by_room: dict[str, int] = {}
        self.search_query = ""
        self.search_hits: list[int] = []
        self.active_search_hit_idx = -1

        # Load Config
        config_data = self.load_config_data()
        self.base_dir = config_data.get("path", DEFAULT_PATH)
        self.current_theme = config_data.get("theme", "default")
        self.current_room = self.sanitize_room_name(
            config_data.get("room", DEFAULT_ROOM)
        )

        if not self.base_dir or not os.path.exists(self.base_dir):
            self.base_dir = self.prompt_for_path()

        self.rooms_root = os.path.join(self.base_dir, "rooms")
        self.ensure_paths()
        self.update_room_paths()

        legacy_path = os.path.join(self.base_dir, "Shared_chat.txt")
        if os.path.exists(legacy_path):
            print(
                "Warning: Legacy Shared_chat.txt detected. "
                "This version uses rooms/*/messages.jsonl only."
            )

        self.save_config()

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
            completer=SlashCompleter(self),
            complete_while_typing=True,
        )
        self.sidebar_control = FormattedTextControl()
        self.sidebar_window = Window(
            content=self.sidebar_control, width=34, style="class:sidebar"
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
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
            except (OSError, json.JSONDecodeError) as exc:
                logger.warning("Failed to load config from %s: %s", CONFIG_FILE, exc)
        return {}

    def save_config(self) -> None:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "path": self.base_dir,
                    "theme": self.current_theme,
                    "username": self.name,
                    "room": self.current_room,
                },
                f,
            )

    def get_style(self) -> Style:
        theme_dict = THEMES.get(self.current_theme, THEMES["default"])
        base_dict = {
            "scrollbar.background": "bg:#222222",
            "scrollbar.button": "bg:#777777",
            "search-match": theme_dict.get("search-match", "bg:#333300 #ffff66"),
            "mention": theme_dict.get("mention", "fg:#ffaf00 bold"),
            "timestamp": theme_dict.get("timestamp", "fg:#888888"),
        }
        base_dict.update(theme_dict)
        return Style.from_dict(base_dict)

    def get_available_drives(self) -> list[str]:
        drives = []
        try:
            if os.name == "nt":
                os.popen("fsutil fsinfo drives").read().strip()
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

    def sanitize_room_name(self, room: str) -> str:
        cleaned = re.sub(r"[^a-zA-Z0-9_-]+", "-", str(room).strip().lower())
        cleaned = cleaned.strip("-_")
        return cleaned or DEFAULT_ROOM

    def get_room_dir(self, room: str | None = None) -> Path:
        active_room = self.sanitize_room_name(room or self.current_room)
        base = Path(self.rooms_root).resolve()
        target = (base / active_room).resolve()
        if target.parent != base:
            raise ValueError("Invalid room path.")
        return target

    def get_message_file(self, room: str | None = None) -> Path:
        return self.get_room_dir(room) / "messages.jsonl"

    def get_presence_dir(self, room: str | None = None) -> Path:
        return self.get_room_dir(room) / "presence"

    def get_presence_path(self, room: str | None = None) -> Path:
        base = self.get_presence_dir(room).resolve()
        target = (base / self.presence_file_id).resolve()
        if target.parent != base:
            raise ValueError("Invalid username for presence path.")
        return target

    def update_room_paths(self) -> None:
        # Compatibility aliases used by existing tests.
        self.chat_file = str(self.get_message_file())
        self.presence_dir = str(self.get_presence_dir())

    def list_rooms(self) -> list[str]:
        rooms: list[str] = []
        root = Path(self.rooms_root)
        if not root.exists():
            return [self.current_room]
        for entry in root.iterdir():
            if entry.is_dir():
                rooms.append(self.sanitize_room_name(entry.name))
        if self.current_room not in rooms:
            rooms.append(self.current_room)
        return sorted(set(rooms))

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

            print(f"Warning: Path '{base_dir}' was not found.")
            choice = input(
                "Is this a mapped drive? Force use anyway? (y/n/create): "
            ).lower()
            if choice == "y":
                return base_dir
            if choice == "create":
                try:
                    os.makedirs(base_dir)
                    return base_dir
                except Exception as exc:
                    print(f"Failed to create: {exc}")

    def ensure_paths(self) -> None:
        try:
            os.makedirs(self.rooms_root, exist_ok=True)
            room_dir = self.get_room_dir()
            os.makedirs(room_dir, exist_ok=True)
            os.makedirs(self.get_presence_dir(), exist_ok=True)
            self.get_message_file().touch(exist_ok=True)
        except OSError as exc:
            logger.warning("Failed ensuring room paths: %s", exc)

    def get_online_users(self, room: str | None = None) -> dict[str, dict[str, Any]]:
        online: dict[str, dict[str, Any]] = {}
        now = time.time()
        presence_dir = self.get_presence_dir(room)
        if not presence_dir.exists():
            return online

        for path in presence_dir.iterdir():
            if not path.is_file():
                continue
            try:
                if now - path.stat().st_mtime < 30:
                    with open(path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    if isinstance(data, dict):
                        display_name = (
                            str(data.get("name", path.name)).strip() or path.name
                        )
                        online[display_name] = data
                    else:
                        online[path.name] = {"color": "white", "status": ""}
                else:
                    path.unlink(missing_ok=True)
            except (OSError, json.JSONDecodeError, ValueError) as exc:
                logger.warning("Failed to process presence file %s: %s", path, exc)

        return online

    def heartbeat(self) -> None:
        current_presence_path: Path | None = None
        current_room = ""

        while self.running:
            try:
                room = self.current_room
                presence_path = self.get_presence_path(room)
                if current_presence_path is not None and (
                    room != current_room or current_presence_path != presence_path
                ):
                    try:
                        current_presence_path.unlink(missing_ok=True)
                    except OSError as exc:
                        logger.warning(
                            "Failed cleaning previous room presence file %s: %s",
                            current_presence_path,
                            exc,
                        )

                current_presence_path = presence_path
                current_room = room
                data = {
                    "name": self.name,
                    "color": self.color,
                    "last_seen": time.time(),
                    "status": self.status,
                }
                with open(presence_path, "w", encoding="utf-8") as f:
                    json.dump(data, f)
            except (OSError, ValueError) as exc:
                logger.warning("Failed heartbeat write: %s", exc)

            time.sleep(10)

        if current_presence_path is not None:
            try:
                current_presence_path.unlink(missing_ok=True)
            except OSError as exc:
                logger.warning(
                    "Failed to remove presence file on shutdown %s: %s",
                    current_presence_path,
                    exc,
                )

    def update_sidebar(self) -> None:
        fragments: list[tuple[str, str]] = [
            ("fg:#aaaaaa", f"Room: #{self.current_room}"),
            ("", "\n"),
            ("", "\n"),
        ]
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

    def refresh_presence_sidebar(self) -> None:
        self.online_users = self.get_online_users()
        self.update_sidebar()

    def sanitize_sidebar_text(self, value: Any, max_len: int) -> str:
        text = str(value).replace("\r", " ").replace("\n", " ").replace("\t", " ")
        return text[:max_len]

    def sanitize_sidebar_color(self, value: Any) -> str:
        color = str(value).strip().lower()
        if color in COLORS:
            return color
        return "white"

    def build_event(self, event_type: str, text: str) -> dict[str, Any]:
        return {
            "ts": datetime.now().isoformat(timespec="seconds"),
            "type": event_type,
            "author": self.name,
            "text": text,
        }

    def render_event(self, event: dict[str, Any]) -> str:
        ts_raw = str(event.get("ts", ""))
        ts = ts_raw[-8:] if len(ts_raw) >= 8 else ts_raw
        event_type = str(event.get("type", "chat"))
        author = self.sanitize_sidebar_text(event.get("author", "Unknown"), 64)
        text = self.sanitize_sidebar_text(event.get("text", ""), 400)

        if event_type == "me":
            return f"[{ts}] * {author} {text}".rstrip()
        if event_type == "system":
            return f"[System] {text}"
        return f"[{ts}] {author}: {text}"

    def parse_event_line(self, line: str) -> dict[str, Any] | None:
        line = line.strip()
        if not line:
            return None
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            logger.warning("Invalid message JSONL row ignored.")
            return None
        if not isinstance(data, dict):
            return None
        if "type" not in data or "author" not in data or "text" not in data:
            return None
        if "ts" not in data:
            data["ts"] = datetime.now().isoformat(timespec="seconds")
        return data

    def append_local_event(self, event: dict[str, Any]) -> None:
        self.message_events.append(event)
        self.messages.append(self.render_event(event))
        if len(self.messages) > MAX_MESSAGES:
            self.messages.pop(0)
            self.message_events.pop(0)
        self.output_field.text = "\n".join(self.messages)
        self.output_field.buffer.cursor_position = len(self.output_field.text)
        self.application.invalidate()
        self.rebuild_search_hits()

    def append_system_message(self, text: str) -> None:
        self.append_local_event(self.build_event("system", text))

    def rebuild_search_hits(self) -> None:
        self.search_hits = []
        self.active_search_hit_idx = -1
        if not self.search_query:
            return

        pattern = self.search_query.lower()
        for idx, line in enumerate(self.messages):
            if pattern in line.lower():
                self.search_hits.append(idx)

        if self.search_hits:
            self.active_search_hit_idx = 0
            self.jump_to_search_hit(0)

    def jump_to_search_hit(self, direction: int) -> bool:
        if not self.search_hits:
            return False

        if direction != 0:
            self.active_search_hit_idx = (self.active_search_hit_idx + direction) % len(
                self.search_hits
            )

        target_line = self.search_hits[self.active_search_hit_idx]
        cursor = 0
        for idx, line in enumerate(self.messages):
            if idx == target_line:
                break
            cursor += len(line) + 1
        self.output_field.buffer.cursor_position = cursor
        self.application.invalidate()
        return True

    def apply_search_highlight(
        self, tokens: list[tuple[str, str]], query: str
    ) -> list[tuple[str, str]]:
        if not query:
            return tokens

        pattern = re.compile(re.escape(query), re.IGNORECASE)
        result: list[tuple[str, str]] = []
        for style, text in tokens:
            start = 0
            for match in pattern.finditer(text):
                if match.start() > start:
                    result.append((style, text[start : match.start()]))
                result.append(("class:search-match", text[match.start() : match.end()]))
                start = match.end()
            if start < len(text):
                result.append((style, text[start:]))
        return result

    def apply_mention_highlight(self, style: str, text: str) -> list[tuple[str, str]]:
        if not self.name:
            return [(style, text)]

        mention_regex = re.compile(rf"@{re.escape(self.name)}\b", re.IGNORECASE)
        result: list[tuple[str, str]] = []
        start = 0
        for match in mention_regex.finditer(text):
            if match.start() > start:
                result.append((style, text[start : match.start()]))
            result.append(("class:mention", text[match.start() : match.end()]))
            start = match.end()
        if start < len(text):
            result.append((style, text[start:]))
        return result

    def lex_line(self, line_text: str) -> list[tuple[str, str]]:
        chat_match = re.match(r"^\[(\d{2}:\d{2}:\d{2})\] ([^:]+): (.*)$", line_text)
        if chat_match:
            ts, name, body = chat_match.groups()
            user_data = self.online_users.get(name, {})
            u_color = self.sanitize_sidebar_color(user_data.get("color", "white"))
            tokens: list[tuple[str, str]] = [
                ("class:timestamp", f"[{ts}] "),
                (f"fg:{u_color} bold", name),
                ("", ": "),
            ]
            tokens.extend(self.apply_mention_highlight("", body))
            return self.apply_search_highlight(tokens, self.search_query)

        me_match = re.match(r"^\[(\d{2}:\d{2}:\d{2})\] \* ([^ ]+) (.*)$", line_text)
        if me_match:
            ts, name, body = me_match.groups()
            tokens = [
                ("class:timestamp", f"[{ts}] "),
                ("fg:#bbbbbb", "* "),
                ("fg:#bbbbbb bold", name),
                ("fg:#bbbbbb", f" {body}"),
            ]
            return self.apply_search_highlight(tokens, self.search_query)

        return self.apply_search_highlight([("", line_text)], self.search_query)

    def switch_room(self, target_room: str) -> None:
        room = self.sanitize_room_name(target_room)
        if room == self.current_room:
            self.append_system_message(f"Already in #{room}.")
            return

        self.current_room = room
        self.update_room_paths()
        self.ensure_paths()
        self.search_query = ""
        self.search_hits = []
        self.active_search_hit_idx = -1
        self.messages = []
        self.message_events = []
        self.load_recent_messages()
        self.refresh_presence_sidebar()
        self.save_config()
        self.append_system_message(f"Joined room #{room}.")

    def load_recent_messages(self) -> None:
        message_file = self.get_message_file()
        if not message_file.exists():
            self.output_field.text = ""
            self.last_pos_by_room[self.current_room] = 0
            return

        loaded_events: list[dict[str, Any]] = []
        try:
            with open(message_file, "r", encoding="utf-8") as f:
                for line in f:
                    event = self.parse_event_line(line)
                    if event is not None:
                        loaded_events.append(event)
                self.last_pos_by_room[self.current_room] = f.tell()
        except OSError as exc:
            logger.warning(
                "Failed loading history for room %s: %s", self.current_room, exc
            )
            loaded_events = []
            self.last_pos_by_room[self.current_room] = 0

        self.message_events = loaded_events[-MAX_MESSAGES:]
        self.messages = [self.render_event(event) for event in self.message_events]
        self.output_field.text = "\n".join(self.messages)
        self.output_field.buffer.cursor_position = len(self.output_field.text)
        self.application.invalidate()
        self.rebuild_search_hits()

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
                    avail = ", ".join(THEMES.keys())
                    self.append_system_message(f"Available themes: {avail}")
                else:
                    target = args.strip().lower()
                    if target in THEMES:
                        self.current_theme = target
                        self.save_config()
                        self.application.style = self.get_style()
                        self.application.invalidate()
                    else:
                        self.append_system_message(f"Unknown theme '{target}'.")
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
                self.force_heartbeat()
                self.input_field.text = ""
                return

            if command == "/join":
                if not args.strip():
                    self.append_system_message("Usage: /join <room>")
                else:
                    self.switch_room(args.strip())
                self.input_field.text = ""
                return

            if command == "/rooms":
                rooms = ", ".join(self.list_rooms())
                self.append_system_message(f"Rooms: {rooms}")
                self.input_field.text = ""
                return

            if command == "/room":
                self.append_system_message(f"Current room: #{self.current_room}")
                self.input_field.text = ""
                return

            if command == "/search":
                query = args.strip()
                self.search_query = query
                self.rebuild_search_hits()
                if not query:
                    self.append_system_message("Search cleared.")
                elif self.search_hits:
                    self.append_system_message(
                        f"Found {len(self.search_hits)} matches for '{query}'."
                    )
                    self.jump_to_search_hit(0)
                else:
                    self.append_system_message(f"No matches for '{query}'.")
                self.input_field.text = ""
                return

            if command == "/next":
                if not self.jump_to_search_hit(1):
                    self.append_system_message("No search matches.")
                self.input_field.text = ""
                return

            if command == "/prev":
                if not self.jump_to_search_hit(-1):
                    self.append_system_message("No search matches.")
                self.input_field.text = ""
                return

            if command == "/clearsearch":
                self.search_query = ""
                self.search_hits = []
                self.active_search_hit_idx = -1
                self.append_system_message("Search cleared.")
                self.input_field.text = ""
                return

            if command in ["/exit", "/quit"]:
                self.application.exit()
                return

            if command == "/clear":
                self.messages = []
                self.message_events = []
                self.output_field.text = ""
                self.input_field.text = ""
                self.search_query = ""
                self.search_hits = []
                self.active_search_hit_idx = -1
                return

            if command == "/me":
                event = self.build_event("me", args)
                if self.write_to_file(event):
                    self.input_field.text = ""
                else:
                    self.append_system_message(
                        "Error: Could not send message. Network busy or locked."
                    )
                return

            self.append_system_message(f"Unknown command: {command}")
            self.input_field.text = ""
            return

        event = self.build_event("chat", text)
        if self.write_to_file(event):
            self.input_field.text = ""
        else:
            self.append_system_message(
                "Error: Could not send message. Network busy or locked."
            )

    def write_to_file(self, payload: dict[str, Any] | str) -> bool:
        self.ensure_locking_dependency()
        assert portalocker is not None

        message_file = self.get_message_file()
        for attempt in range(LOCK_MAX_ATTEMPTS):
            try:
                with portalocker.Lock(
                    str(message_file),
                    mode="a",
                    timeout=LOCK_TIMEOUT_SECONDS,
                    fail_when_locked=True,
                    encoding="utf-8",
                ) as f:
                    if isinstance(payload, dict):
                        row = json.dumps(payload, ensure_ascii=True)
                    else:
                        row = payload.rstrip("\n")
                    f.write(row + "\n")
                    f.flush()
                    os.fsync(f.fileno())
                return True
            except portalocker.exceptions.LockException:
                pass
            except OSError:
                pass
            except Exception as exc:
                logger.warning("Unexpected write_to_file failure: %s", exc)
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
            with open(presence_path, "w", encoding="utf-8") as f:
                json.dump(data, f)
            self.refresh_presence_sidebar()
        except (OSError, ValueError) as exc:
            logger.warning("Failed forced heartbeat update: %s", exc)

    async def monitor_messages(self) -> None:
        next_presence_refresh = 0.0
        while self.running:
            now = time.monotonic()
            if now >= next_presence_refresh:
                self.refresh_presence_sidebar()
                next_presence_refresh = now + PRESENCE_REFRESH_INTERVAL_SECONDS

            room = self.current_room
            message_file = self.get_message_file(room)
            self.last_pos_by_room.setdefault(room, 0)

            if message_file.exists():
                try:
                    with open(message_file, "r", encoding="utf-8") as f:
                        current_size = os.path.getsize(message_file)
                        last_pos = self.last_pos_by_room[room]
                        if current_size < last_pos:
                            logger.warning(
                                "Chat file shrank in room %s from offset %s to %s; resetting.",
                                room,
                                last_pos,
                                current_size,
                            )
                            last_pos = 0
                        f.seek(last_pos)
                        new_lines = f.readlines()
                        if new_lines and room == self.current_room:
                            for line in new_lines:
                                event = self.parse_event_line(line)
                                if event is None:
                                    continue
                                self.message_events.append(event)
                                self.messages.append(self.render_event(event))
                                if len(self.messages) > MAX_MESSAGES:
                                    self.messages.pop(0)
                                    self.message_events.pop(0)
                            self.output_field.text = "\n".join(self.messages)
                            self.output_field.buffer.cursor_position = len(
                                self.output_field.text
                            )
                            self.application.invalidate()
                            self.rebuild_search_hits()
                        self.last_pos_by_room[room] = f.tell()
                except OSError as exc:
                    logger.warning(
                        "Failed while monitoring room %s chat file %s: %s",
                        room,
                        message_file,
                        exc,
                    )
            await asyncio.sleep(0.5)

    def run(self) -> None:
        print(f"Connecting to: {self.base_dir}")

        config_data = self.load_config_data()
        saved_name = config_data.get("username", "")

        if saved_name:
            user_input = input(f"Enter your name [Default: {saved_name}]: ").strip()
            self.name = user_input if user_input else saved_name
        else:
            self.name = input("Enter your name: ").strip() or "Anonymous"
        self.presence_file_id = self.sanitize_presence_id(self.name)

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

        self.load_recent_messages()

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
