import os
import time
import json
import asyncio
import string
import re
import logging
import shlex
from typing import Any
from datetime import datetime
from threading import Event, Lock, Thread
from pathlib import Path
from uuid import uuid4
from urllib import error as urlerror
from urllib import request as urlrequest

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
from prompt_toolkit.layout.menus import CompletionsMenu

from huddle_chat.constants import (
    AI_CONFIG_FILE,
    AI_DM_ROOM,
    AI_HTTP_TIMEOUT_SECONDS,
    CLIENT_ID_LENGTH,
    COLORS,
    CONFIG_FILE,
    DEFAULT_PATH,
    DEFAULT_ROOM,
    EVENT_SCHEMA_VERSION,
    LOCAL_CHAT_ROOT,
    LOCAL_ROOMS_ROOT,
    MAX_MESSAGES,
    MAX_PRESENCE_ID_LENGTH,
    MEMORY_DIR_NAME,
    MEMORY_GLOBAL_FILE,
    MONITOR_POLL_INTERVAL_ACTIVE_SECONDS,
    THEMES,
)
from huddle_chat.services import (
    AIService,
    MemoryService,
    RuntimeService,
    StorageService,
)
from huddle_chat.ui import ChatLexer, SlashCompleter

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

Observer: Any
FileSystemEventHandler: Any
_WATCHDOG_IMPORT_ERROR: ImportError | None
try:
    from watchdog.events import (  # type: ignore[import-not-found]
        FileSystemEventHandler as _FileSystemEventHandler,
    )
    from watchdog.observers import Observer as _Observer  # type: ignore[import-not-found]
except ImportError as exc:
    Observer = None
    FileSystemEventHandler = object
    _WATCHDOG_IMPORT_ERROR = exc
else:
    Observer = _Observer
    FileSystemEventHandler = _FileSystemEventHandler
    _WATCHDOG_IMPORT_ERROR = None

logger = logging.getLogger(__name__)


class MessageFileWatchHandler(FileSystemEventHandler):
    def __init__(self, app_ref: "ChatApp"):
        super().__init__()
        self.app_ref = app_ref

    def _handle_path(self, path: str) -> None:
        normalized = str(path).replace("\\", "/").lower()
        if normalized.endswith("/messages.jsonl"):
            self.app_ref.signal_monitor_refresh()

    def on_created(self, event) -> None:
        if getattr(event, "is_directory", False):
            return
        self._handle_path(getattr(event, "src_path", ""))

    def on_modified(self, event) -> None:
        if getattr(event, "is_directory", False):
            return
        self._handle_path(getattr(event, "src_path", ""))

    def on_moved(self, event) -> None:
        if getattr(event, "is_directory", False):
            return
        self._handle_path(getattr(event, "src_path", ""))
        self._handle_path(getattr(event, "dest_path", ""))


class ChatApp:
    def __init__(self):
        self.ensure_locking_dependency()
        self.name = "Anonymous"
        self.color = "white"
        self.status = ""
        self.running = True
        self.current_theme = "default"
        self.current_room = DEFAULT_ROOM
        self.client_id = self.generate_client_id()
        self.presence_file_id = self.client_id

        self.messages: list[str] = []
        self.message_events: list[dict[str, Any]] = []
        self.online_users: dict[str, dict[str, Any]] = {}
        self.last_pos_by_room: dict[str, int] = {}
        self.search_query = ""
        self.search_hits: list[int] = []
        self.active_search_hit_idx = -1
        self.monitor_refresh_event = Event()
        self.monitor_poll_interval_seconds = MONITOR_POLL_INTERVAL_ACTIVE_SECONDS
        self.monitor_idle_cycles = 0
        self.file_observer = None
        self.ai_state_lock = Lock()
        self.ai_active_request_id: str | None = None
        self.ai_active_started_at = 0.0
        self.ai_active_provider = ""
        self.ai_active_model = ""
        self.ai_active_scope = ""
        self.ai_active_room = ""
        self.ai_retry_count = 0
        self.ai_preview_text = ""
        self.ai_cancel_event = Event()
        self.memory_draft_active = False
        self.memory_draft_mode = "none"
        self.memory_draft: dict[str, Any] | None = None
        self.storage_service = StorageService(self)
        self.memory_service = MemoryService(self)
        self.ai_service = AIService(self)
        self.runtime_service = RuntimeService(self)

        # Load Config
        config_data = self.load_config_data()
        self.base_dir = config_data.get("path", DEFAULT_PATH)
        self.current_theme = config_data.get("theme", "default")
        configured_name = str(config_data.get("username", "")).strip()
        if configured_name:
            self.name = configured_name
        self.current_room = self.sanitize_room_name(
            config_data.get("room", DEFAULT_ROOM)
        )
        self.client_id = self.normalize_client_id(config_data.get("client_id"))
        self.presence_file_id = self.client_id

        if not self.base_dir or not os.path.exists(self.base_dir):
            self.base_dir = self.prompt_for_path()

        self.rooms_root = os.path.join(self.base_dir, "rooms")
        self.ai_config = self.load_ai_config_data()
        self.ensure_paths()
        self.ensure_local_paths()
        self.ensure_memory_paths()
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

        @self.kb.add("tab")
        def _(event):
            buffer = event.current_buffer
            complete_state = buffer.complete_state
            if complete_state is not None:
                completion = complete_state.current_completion
                if completion is None and complete_state.completions:
                    completion = complete_state.completions[0]
                if completion is not None:
                    buffer.apply_completion(completion)
                    return
            buffer.start_completion(select_first=True)

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
        self.command_handlers = self.build_command_handlers()

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
                    "client_id": self.client_id,
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

    def generate_client_id(self) -> str:
        return uuid4().hex[:CLIENT_ID_LENGTH]

    def normalize_client_id(self, value: Any) -> str:
        raw = str(value).strip().lower()
        cleaned = re.sub(r"[^a-f0-9]", "", raw)
        if len(cleaned) >= 8:
            return cleaned[:CLIENT_ID_LENGTH]
        return self.generate_client_id()

    def is_local_room(self, room: str | None = None) -> bool:
        active_room = self.sanitize_room_name(room or self.current_room)
        return active_room == AI_DM_ROOM

    def get_local_rooms_root(self) -> Path:
        return Path(LOCAL_ROOMS_ROOT).resolve()

    def get_local_room_dir(self, room: str | None = None) -> Path:
        active_room = self.sanitize_room_name(room or self.current_room)
        base = self.get_local_rooms_root()
        target = (base / active_room).resolve()
        if target.parent != base:
            raise ValueError("Invalid local room path.")
        return target

    def get_local_message_file(self, room: str | None = None) -> Path:
        return self.get_local_room_dir(room) / "messages.jsonl"

    def ensure_local_paths(self) -> None:
        try:
            os.makedirs(LOCAL_CHAT_ROOT, exist_ok=True)
            os.makedirs(self.get_local_rooms_root(), exist_ok=True)
            local_room_dir = self.get_local_room_dir(AI_DM_ROOM)
            os.makedirs(local_room_dir, exist_ok=True)
            self.get_local_message_file(AI_DM_ROOM).touch(exist_ok=True)
        except OSError as exc:
            logger.warning("Failed ensuring local AI paths: %s", exc)

    def get_memory_dir(self) -> Path:
        return (Path(self.base_dir) / MEMORY_DIR_NAME).resolve()

    def get_memory_file(self) -> Path:
        return self.get_memory_dir() / MEMORY_GLOBAL_FILE

    def ensure_memory_paths(self) -> None:
        try:
            memory_dir = self.get_memory_dir()
            os.makedirs(memory_dir, exist_ok=True)
            self.get_memory_file().touch(exist_ok=True)
        except OSError as exc:
            logger.warning("Failed ensuring memory paths: %s", exc)

    def get_default_ai_config(self) -> dict[str, Any]:
        return {
            "default_provider": "gemini",
            "providers": {
                "gemini": {"api_key": "", "model": "gemini-2.5-flash"},
                "openai": {"api_key": "", "model": "gpt-4o-mini"},
            },
        }

    def load_ai_config_data(self) -> dict[str, Any]:
        default = self.get_default_ai_config()
        path = Path(AI_CONFIG_FILE)
        if not path.exists():
            return default
        try:
            with open(path, "r", encoding="utf-8") as f:
                loaded = json.load(f)
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("Failed to load AI config from %s: %s", AI_CONFIG_FILE, exc)
            return default

        if not isinstance(loaded, dict):
            return default
        providers = loaded.get("providers", {})
        if not isinstance(providers, dict):
            providers = {}
        merged = default
        for provider_name in ("gemini", "openai"):
            existing = providers.get(provider_name, {})
            if isinstance(existing, dict):
                merged["providers"][provider_name].update(existing)
        default_provider = str(loaded.get("default_provider", "")).strip().lower()
        if default_provider in merged["providers"]:
            merged["default_provider"] = default_provider
        return merged

    def save_ai_config_data(self) -> None:
        try:
            os.makedirs(LOCAL_CHAT_ROOT, exist_ok=True)
            with open(AI_CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(self.ai_config, f, indent=2)
        except OSError as exc:
            logger.warning("Failed saving AI config: %s", exc)

    def parse_ai_args(self, arg_text: str) -> tuple[dict[str, Any], str | None]:
        self.ensure_services_initialized()
        return self.ai_service.parse_ai_args(arg_text)

    def resolve_ai_provider_config(
        self, provider_override: str | None, model_override: str | None
    ) -> tuple[dict[str, str], str | None]:
        self.ensure_services_initialized()
        return self.ai_service.resolve_ai_provider_config(
            provider_override, model_override
        )

    def call_ai_provider(
        self, provider: str, api_key: str, model: str, prompt: str
    ) -> str:
        if provider == "gemini":
            return self.call_gemini_api(api_key, model, prompt)
        if provider == "openai":
            return self.call_openai_api(api_key, model, prompt)
        raise ValueError(f"Unsupported provider '{provider}'")

    def post_json_request(
        self, url: str, headers: dict[str, str], payload: dict[str, Any]
    ) -> dict[str, Any]:
        body = json.dumps(payload).encode("utf-8")
        request = urlrequest.Request(
            url=url,
            data=body,
            headers={"Content-Type": "application/json", **headers},
            method="POST",
        )
        try:
            with urlrequest.urlopen(
                request, timeout=AI_HTTP_TIMEOUT_SECONDS
            ) as response:
                raw = response.read().decode("utf-8")
                data = json.loads(raw) if raw else {}
                if isinstance(data, dict):
                    return data
                return {}
        except urlerror.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(
                f"HTTP {exc.code} from provider. {detail[:200]}"
            ) from exc
        except (OSError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"Provider request failed: {exc}") from exc

    def call_gemini_api(self, api_key: str, model: str, prompt: str) -> str:
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/{model}:"
            f"generateContent?key={api_key}"
        )
        payload = {"contents": [{"parts": [{"text": prompt}]}]}
        data = self.post_json_request(url, {}, payload)
        candidates = data.get("candidates", [])
        if not isinstance(candidates, list) or not candidates:
            raise RuntimeError("Gemini returned no candidates.")
        first = candidates[0]
        if not isinstance(first, dict):
            raise RuntimeError("Gemini response format was invalid.")
        content = first.get("content", {})
        if not isinstance(content, dict):
            raise RuntimeError("Gemini response content missing.")
        parts = content.get("parts", [])
        if not isinstance(parts, list) or not parts:
            raise RuntimeError("Gemini returned empty content.")
        for part in parts:
            if isinstance(part, dict):
                text = str(part.get("text", "")).strip()
                if text:
                    return text
        raise RuntimeError("Gemini response did not contain text.")

    def call_openai_api(self, api_key: str, model: str, prompt: str) -> str:
        url = "https://api.openai.com/v1/chat/completions"
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
        }
        headers = {"Authorization": f"Bearer {api_key}"}
        data = self.post_json_request(url, headers, payload)
        choices = data.get("choices", [])
        if not isinstance(choices, list) or not choices:
            raise RuntimeError("OpenAI returned no choices.")
        first = choices[0]
        if not isinstance(first, dict):
            raise RuntimeError("OpenAI response format was invalid.")
        message = first.get("message", {})
        if not isinstance(message, dict):
            raise RuntimeError("OpenAI response message missing.")
        text = str(message.get("content", "")).strip()
        if not text:
            raise RuntimeError("OpenAI response was empty.")
        return text

    def get_room_dir(self, room: str | None = None) -> Path:
        active_room = self.sanitize_room_name(room or self.current_room)
        base = Path(self.rooms_root).resolve()
        target = (base / active_room).resolve()
        if target.parent != base:
            raise ValueError("Invalid room path.")
        return target

    def get_message_file(self, room: str | None = None) -> Path:
        if self.is_local_room(room):
            return self.get_local_message_file(room)
        return self.get_room_dir(room) / "messages.jsonl"

    def get_presence_dir(self, room: str | None = None) -> Path:
        if self.is_local_room(room):
            return self.get_local_room_dir(room) / "presence"
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
            return sorted({self.current_room, AI_DM_ROOM})
        for entry in root.iterdir():
            if entry.is_dir():
                rooms.append(self.sanitize_room_name(entry.name))
        rooms.append(AI_DM_ROOM)
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
            if not self.is_local_room():
                room_dir = self.get_room_dir()
                os.makedirs(room_dir, exist_ok=True)
                os.makedirs(self.get_presence_dir(), exist_ok=True)
                self.get_message_file().touch(exist_ok=True)
        except OSError as exc:
            logger.warning("Failed ensuring room paths: %s", exc)

    def get_online_users(self, room: str | None = None) -> dict[str, dict[str, Any]]:
        online: dict[str, dict[str, Any]] = {}
        if self.is_local_room(room):
            return online
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
                    client_id = self.normalize_client_id(path.name)
                    if isinstance(data, dict):
                        display_name = str(data.get("name", "Anonymous")).strip()
                        if not display_name:
                            display_name = "Anonymous"
                        normalized = dict(data)
                        normalized["name"] = display_name
                        normalized["client_id"] = client_id
                        online[client_id] = normalized
                    else:
                        online[client_id] = {
                            "name": "Anonymous",
                            "color": "white",
                            "status": "",
                            "client_id": client_id,
                        }
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
                if self.is_local_room(room):
                    if current_presence_path is not None:
                        try:
                            current_presence_path.unlink(missing_ok=True)
                        except OSError as exc:
                            logger.warning(
                                "Failed cleaning presence while in local room %s: %s",
                                current_presence_path,
                                exc,
                            )
                        current_presence_path = None
                    current_room = room
                    time.sleep(10)
                    continue
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
        if self.is_local_room():
            self.sidebar_control.text = [
                ("fg:#aaaaaa", f"Room: #{self.current_room} (local)"),
                ("", "\n"),
                ("fg:#888888", "Private AI DM"),
            ]
            self.application.invalidate()
            return
        fragments: list[tuple[str, str]] = [
            ("fg:#aaaaaa", f"Room: #{self.current_room}"),
            ("", "\n"),
            ("", "\n"),
        ]
        users = sorted(
            self.online_users.values(),
            key=lambda data: (
                str(data.get("name", "Anonymous")).lower(),
                str(data.get("client_id", "")),
            ),
        )
        name_counts: dict[str, int] = {}
        for data in users:
            name = self.sanitize_sidebar_text(data.get("name", "Anonymous"), 64)
            name_counts[name] = name_counts.get(name, 0) + 1

        for idx, data in enumerate(users):
            color = self.sanitize_sidebar_color(data.get("color", "white"))
            display_name = self.sanitize_sidebar_text(data.get("name", "Anonymous"), 64)
            client_id = self.sanitize_sidebar_text(data.get("client_id", ""), 12)
            if name_counts.get(display_name, 0) > 1 and client_id:
                display_name = f"{display_name} ({client_id[:4]})"
            status = self.sanitize_sidebar_text(data.get("status", ""), 80)
            fragments.append((f"fg:{color}", f"* {display_name}"))
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

    def get_mention_context(self, text_before_cursor: str) -> tuple[str, int] | None:
        at_index = text_before_cursor.rfind("@")
        if at_index == -1:
            return None

        if at_index > 0:
            prev = text_before_cursor[at_index - 1]
            if prev.isalnum() or prev == "_":
                return None

        prefix = text_before_cursor[at_index + 1 :]
        if not prefix:
            return ("", 0)

        if "\n" in prefix or "\r" in prefix:
            return None

        return (prefix, -len(prefix))

    def get_mention_candidates(self) -> list[dict[str, str]]:
        candidates: list[dict[str, str]] = []
        seen_names: set[str] = set()
        self_name = self.name.casefold()
        for user_data in self.online_users.values():
            raw_name = self.sanitize_sidebar_text(user_data.get("name", ""), 64).strip()
            if not raw_name:
                continue
            if raw_name.casefold() == self_name:
                continue
            dedupe_key = raw_name.casefold()
            if dedupe_key in seen_names:
                continue
            seen_names.add(dedupe_key)
            status = self.sanitize_sidebar_text(user_data.get("status", ""), 80).strip()
            candidates.append({"name": raw_name, "status": status})
        return candidates

    def build_event(self, event_type: str, text: str) -> dict[str, Any]:
        return {
            "v": EVENT_SCHEMA_VERSION,
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
        if event_type == "ai_prompt":
            return f"[{ts}] {author} -> AI: {text}"
        if event_type == "ai_response":
            provider = self.sanitize_sidebar_text(event.get("provider", "ai"), 24)
            model = self.sanitize_sidebar_text(event.get("model", ""), 40)
            model_suffix = f":{model}" if model else ""
            return f"[{ts}] AI[{provider}{model_suffix}]: {text}"
        return f"[{ts}] {author}: {text}"

    def ensure_monitor_state_initialized(self) -> None:
        if not hasattr(self, "monitor_refresh_event"):
            self.monitor_refresh_event = Event()
            self.monitor_poll_interval_seconds = MONITOR_POLL_INTERVAL_ACTIVE_SECONDS
            self.monitor_idle_cycles = 0
            self.file_observer = None

    def signal_monitor_refresh(self) -> None:
        self.ensure_monitor_state_initialized()
        self.monitor_refresh_event.set()

    def start_file_watcher(self) -> None:
        self.ensure_monitor_state_initialized()
        if Observer is None or self.file_observer is not None:
            return

        watch_paths = {str(Path(self.rooms_root).resolve())}
        try:
            watch_paths.add(str(self.get_local_rooms_root().resolve()))
        except Exception:
            pass

        try:
            observer = Observer()
            handler = MessageFileWatchHandler(self)
            for watch_path in sorted(watch_paths):
                if os.path.isdir(watch_path):
                    observer.schedule(handler, watch_path, recursive=True)
            observer.daemon = True
            observer.start()
            self.file_observer = observer
        except Exception as exc:
            logger.warning("File watcher unavailable, falling back to polling: %s", exc)
            self.file_observer = None

    def stop_file_watcher(self) -> None:
        self.ensure_monitor_state_initialized()
        observer = self.file_observer
        if observer is None:
            return
        try:
            observer.stop()
            observer.join(timeout=1.5)
        except Exception as exc:
            logger.warning("Failed stopping file watcher cleanly: %s", exc)
        self.file_observer = None

    def read_recent_lines(self, path: Path, max_lines: int) -> list[str]:
        self.ensure_services_initialized()
        return self.storage_service.read_recent_lines(path, max_lines)

    def parse_event_line(self, line: str) -> dict[str, Any] | None:
        self.ensure_services_initialized()
        return self.storage_service.parse_event_line(line)

    def append_local_event(self, event: dict[str, Any]) -> None:
        self.message_events.append(event)
        if len(self.message_events) > MAX_MESSAGES:
            self.message_events.pop(0)
        self.refresh_output_from_events()
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

    def render_event_for_display(self, event: dict[str, Any], index: int) -> str:
        rendered = self.render_event(event)
        if self.is_local_room():
            return f"({index}) {rendered}"
        return rendered

    def refresh_output_from_events(self) -> None:
        self.messages = [
            self.render_event_for_display(event, idx + 1)
            for idx, event in enumerate(self.message_events)
        ]
        preview_line = self.get_ai_preview_line()
        if preview_line:
            self.messages.append(preview_line)
        if len(self.messages) > MAX_MESSAGES:
            overflow = len(self.messages) - MAX_MESSAGES
            self.messages = self.messages[overflow:]
            self.message_events = self.message_events[overflow:]
        self.output_field.text = "\n".join(self.messages)
        self.output_field.buffer.cursor_position = len(self.output_field.text)
        self.application.invalidate()

    def get_ai_preview_line(self) -> str:
        self.ensure_ai_state_initialized()
        with self.ai_state_lock:
            if not self.ai_active_request_id:
                return ""
            if self.ai_active_room != self.current_room:
                return ""
            elapsed = int(max(0, time.monotonic() - self.ai_active_started_at))
            provider = self.ai_active_provider or "ai"
            model = self.ai_active_model
            model_suffix = f":{model}" if model else ""
            base = f"[AI pending {provider}{model_suffix} {elapsed}s]"
            if self.ai_preview_text:
                return f"{base} {self.ai_preview_text}"
            return base

    def ensure_ai_state_initialized(self) -> None:
        if not hasattr(self, "ai_state_lock"):
            self.ai_state_lock = Lock()
            self.ai_active_request_id = None
            self.ai_active_started_at = 0.0
            self.ai_active_provider = ""
            self.ai_active_model = ""
            self.ai_active_scope = ""
            self.ai_active_room = ""
            self.ai_retry_count = 0
            self.ai_preview_text = ""
            self.ai_cancel_event = Event()

    def ensure_services_initialized(self) -> None:
        if not hasattr(self, "storage_service"):
            self.storage_service = StorageService(self)
        if not hasattr(self, "memory_service"):
            self.memory_service = MemoryService(self)
        if not hasattr(self, "ai_service"):
            self.ai_service = AIService(self)
        if not hasattr(self, "runtime_service"):
            self.runtime_service = RuntimeService(self)

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
                match_start = match.start()
                match_end = match.end()
                if match.start() > start:
                    result.append((style, text[start:match_start]))
                result.append(("class:search-match", text[match_start:match_end]))
                start = match_end
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
            match_start = match.start()
            match_end = match.end()
            if match.start() > start:
                result.append((style, text[start:match_start]))
            result.append(("class:mention", text[match_start:match_end]))
            start = match_end
        if start < len(text):
            result.append((style, text[start:]))
        return result

    def lex_line(self, line_text: str) -> list[tuple[str, str]]:
        chat_match = re.match(r"^\[(\d{2}:\d{2}:\d{2})\] ([^:]+): (.*)$", line_text)
        if chat_match:
            ts, name, body = chat_match.groups()
            u_color = "white"
            for user_data in self.online_users.values():
                online_name = self.sanitize_sidebar_text(user_data.get("name", ""), 64)
                if online_name.lower() == name.lower():
                    u_color = self.sanitize_sidebar_color(
                        user_data.get("color", "white")
                    )
                    break
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
        self.signal_monitor_refresh()
        self.append_system_message(f"Joined room #{room}.")

    def load_recent_messages(self) -> None:
        self.ensure_services_initialized()
        self.storage_service.load_recent_messages()

    def get_ai_provider_summary(self) -> str:
        providers = self.ai_config.get("providers", {})
        default_provider = str(self.ai_config.get("default_provider", "gemini"))
        parts: list[str] = [f"default={default_provider}"]
        for provider in ("gemini", "openai"):
            data = providers.get(provider, {})
            if not isinstance(data, dict):
                data = {}
            configured = (
                "configured" if str(data.get("api_key", "")).strip() else "missing-key"
            )
            model = str(data.get("model", "")).strip() or "<unset>"
            parts.append(f"{provider}({configured}, model={model})")
        return "; ".join(parts)

    def handle_aiconfig_command(self, args: str) -> None:
        if not args.strip():
            self.append_system_message(f"AI config: {self.get_ai_provider_summary()}")
            return

        try:
            tokens = shlex.split(args)
        except ValueError:
            self.append_system_message("Invalid /aiconfig syntax. Check quotes.")
            return
        if not tokens:
            self.append_system_message(f"AI config: {self.get_ai_provider_summary()}")
            return

        providers = {"gemini", "openai"}
        provider_first = len(tokens) >= 2 and tokens[0].strip().lower() in providers
        command_second = tokens[1].strip().lower() in {"set-key", "set-model"}
        if provider_first and command_second:
            tokens = [tokens[1], tokens[0], *tokens[2:]]

        action = tokens[0].lower()
        if action == "set-key" and len(tokens) >= 3:
            provider = tokens[1].strip().lower()
            key = tokens[2].strip()
            if provider not in ("gemini", "openai"):
                self.append_system_message("Unknown provider. Use gemini or openai.")
                return
            self.ai_config.setdefault("providers", {})
            provider_cfg = self.ai_config["providers"].setdefault(provider, {})
            if not isinstance(provider_cfg, dict):
                provider_cfg = {}
                self.ai_config["providers"][provider] = provider_cfg
            provider_cfg["api_key"] = key
            self.save_ai_config_data()
            self.append_system_message(f"Saved API key for {provider}.")
            return

        if action == "set-model" and len(tokens) >= 3:
            provider = tokens[1].strip().lower()
            model = tokens[2].strip()
            if provider not in ("gemini", "openai"):
                self.append_system_message("Unknown provider. Use gemini or openai.")
                return
            self.ai_config.setdefault("providers", {})
            provider_cfg = self.ai_config["providers"].setdefault(provider, {})
            if not isinstance(provider_cfg, dict):
                provider_cfg = {}
                self.ai_config["providers"][provider] = provider_cfg
            provider_cfg["model"] = model
            self.save_ai_config_data()
            self.append_system_message(f"Saved model for {provider}: {model}")
            return

        if action == "set-provider" and len(tokens) >= 2:
            provider = tokens[1].strip().lower()
            if provider not in ("gemini", "openai"):
                self.append_system_message("Unknown provider. Use gemini or openai.")
                return
            self.ai_config["default_provider"] = provider
            self.save_ai_config_data()
            self.append_system_message(f"Default AI provider set to {provider}.")
            return

        self.append_system_message(
            "Usage: /aiconfig [set-key <provider> <key> | set-model <provider> <model> | set-provider <provider>] "
            "(also accepts: <provider> set-key <key>, <provider> set-model <model>)"
        )

    def parse_share_selector(self, selector: str) -> list[dict[str, Any]]:
        if not self.message_events:
            return []
        selector = selector.strip()
        if "-" in selector:
            left, right = selector.split("-", 1)
            start = int(left)
            end = int(right)
            if start > end:
                start, end = end, start
            start = max(start, 1)
            end = min(end, len(self.message_events))
            return self.message_events[start - 1 : end]
        index = int(selector)
        if index < 1 or index > len(self.message_events):
            return []
        return [self.message_events[index - 1]]

    def handle_share_command(self, args: str) -> None:
        if not self.is_local_room():
            self.append_system_message("Use /share only inside #ai-dm.")
            return
        try:
            tokens = shlex.split(args)
        except ValueError:
            self.append_system_message("Invalid /share syntax. Check quotes.")
            return
        if len(tokens) < 2:
            self.append_system_message("Usage: /share <target-room> <id|start-end>")
            return
        target_room = self.sanitize_room_name(tokens[0])
        if self.is_local_room(target_room):
            self.append_system_message("Cannot share into local-only room.")
            return
        selector = tokens[1]
        try:
            selected_events = self.parse_share_selector(selector)
        except ValueError:
            self.append_system_message(
                "Invalid selector. Use numeric id or range like 2-4."
            )
            return
        if not selected_events:
            self.append_system_message("No matching messages to share.")
            return

        shared_count = 0
        for event in selected_events:
            event_type = str(event.get("type", "chat"))
            if event_type not in ("ai_prompt", "ai_response", "chat", "me", "system"):
                continue
            payload = self.build_event(event_type, str(event.get("text", "")))
            if event_type in ("ai_prompt", "ai_response"):
                payload["provider"] = event.get(
                    "provider", self.ai_config.get("default_provider", "ai")
                )
                payload["model"] = event.get("model", "")
            if self.write_to_file(payload, room=target_room):
                shared_count += 1
        self.append_system_message(
            f"Shared {shared_count} message(s) from #ai-dm to #{target_room}."
        )

    def ensure_memory_state_initialized(self) -> None:
        self.ensure_services_initialized()
        self.memory_service.ensure_memory_state_initialized()

    def clear_memory_draft(self) -> None:
        self.ensure_services_initialized()
        self.memory_service.clear_memory_draft()

    def load_memory_entries(self) -> list[dict[str, Any]]:
        self.ensure_services_initialized()
        return self.memory_service.load_memory_entries()

    def normalize_text_tokens(self, text: str) -> set[str]:
        self.ensure_services_initialized()
        return self.memory_service.normalize_text_tokens(text)

    def score_memory_candidate(
        self, prompt_tokens: set[str], entry: dict[str, Any]
    ) -> float:
        self.ensure_services_initialized()
        return self.memory_service.score_memory_candidate(prompt_tokens, entry)

    def prefilter_memory_candidates(
        self, prompt: str, entries: list[dict[str, Any]], limit: int
    ) -> list[dict[str, Any]]:
        self.ensure_services_initialized()
        return self.memory_service.prefilter_memory_candidates(prompt, entries, limit)

    def rerank_memory_candidates_with_ai(
        self,
        provider_cfg: dict[str, str],
        prompt: str,
        candidates: list[dict[str, Any]],
    ) -> list[str] | None:
        self.ensure_services_initialized()
        return self.memory_service.rerank_memory_candidates_with_ai(
            provider_cfg, prompt, candidates
        )

    def select_memory_for_prompt(
        self, prompt: str, provider_cfg: dict[str, str]
    ) -> tuple[list[dict[str, Any]], str | None]:
        self.ensure_services_initialized()
        return self.memory_service.select_memory_for_prompt(prompt, provider_cfg)

    def build_memory_context_block(self, selected: list[dict[str, Any]]) -> str:
        self.ensure_services_initialized()
        return self.memory_service.build_memory_context_block(selected)

    def format_memory_ids_line(self, memory_ids: list[str]) -> str:
        self.ensure_services_initialized()
        return self.memory_service.format_memory_ids_line(memory_ids)

    def find_duplicate_memory_candidates(
        self, draft: dict[str, Any], limit: int = 3
    ) -> list[dict[str, Any]]:
        self.ensure_services_initialized()
        return self.memory_service.find_duplicate_memory_candidates(draft, limit)

    def maybe_warn_memory_duplicates(self, draft: dict[str, Any]) -> None:
        self.ensure_services_initialized()
        self.memory_service.maybe_warn_memory_duplicates(draft)

    def write_memory_entry(self, entry: dict[str, Any]) -> bool:
        self.ensure_services_initialized()
        return self.memory_service.write_memory_entry(entry)

    def get_last_ai_response_event(self) -> dict[str, Any] | None:
        self.ensure_services_initialized()
        return self.memory_service.get_last_ai_response_event()

    def extract_json_object(self, text: str) -> dict[str, Any] | None:
        self.ensure_services_initialized()
        return self.memory_service.extract_json_object(text)

    def build_memory_source(self, event: dict[str, Any]) -> str:
        self.ensure_services_initialized()
        return self.memory_service.build_memory_source(event)

    def draft_memory_from_last_ai_response(
        self,
    ) -> tuple[dict[str, Any] | None, str | None]:
        self.ensure_services_initialized()
        return self.memory_service.draft_memory_from_last_ai_response()

    def show_memory_draft_preview(self) -> None:
        self.ensure_services_initialized()
        self.memory_service.show_memory_draft_preview()

    def confirm_memory_draft(self) -> None:
        self.ensure_services_initialized()
        self.memory_service.confirm_memory_draft()

    def handle_memory_confirmation_input(self, text: str) -> bool:
        self.ensure_services_initialized()
        return self.memory_service.handle_memory_confirmation_input(text)

    def handle_memory_command(self, args: str) -> None:
        self.ensure_services_initialized()
        self.memory_service.handle_memory_command(args)

    def is_transient_ai_error(self, exc: Exception) -> bool:
        self.ensure_services_initialized()
        return self.ai_service.is_transient_ai_error(exc)

    def start_ai_request_state(
        self, provider: str, model: str, target_room: str, scope: str
    ) -> str | None:
        self.ensure_ai_state_initialized()
        with self.ai_state_lock:
            if self.ai_active_request_id is not None:
                return None
            request_id = uuid4().hex[:10]
            self.ai_active_request_id = request_id
            self.ai_active_started_at = time.monotonic()
            self.ai_active_provider = provider
            self.ai_active_model = model
            self.ai_active_scope = scope
            self.ai_active_room = target_room
            self.ai_retry_count = 0
            self.ai_preview_text = "connecting..."
            self.ai_cancel_event = Event()
            return request_id

    def clear_ai_request_state(self, request_id: str) -> None:
        self.ensure_ai_state_initialized()
        with self.ai_state_lock:
            if self.ai_active_request_id != request_id:
                return
            self.ai_active_request_id = None
            self.ai_active_started_at = 0.0
            self.ai_active_provider = ""
            self.ai_active_model = ""
            self.ai_active_scope = ""
            self.ai_active_room = ""
            self.ai_retry_count = 0
            self.ai_preview_text = ""
            self.ai_cancel_event = Event()

    def is_ai_request_active(self) -> bool:
        self.ensure_ai_state_initialized()
        with self.ai_state_lock:
            return self.ai_active_request_id is not None

    def set_ai_preview_text(self, request_id: str, text: str) -> None:
        self.ensure_ai_state_initialized()
        with self.ai_state_lock:
            if self.ai_active_request_id != request_id:
                return
            self.ai_preview_text = text[:180]
        self.refresh_output_from_events()

    def is_ai_request_cancelled(self, request_id: str) -> bool:
        self.ensure_ai_state_initialized()
        with self.ai_state_lock:
            if self.ai_active_request_id != request_id:
                return True
            return self.ai_cancel_event.is_set()

    def request_ai_cancel(self) -> bool:
        self.ensure_ai_state_initialized()
        with self.ai_state_lock:
            if self.ai_active_request_id is None:
                return False
            self.ai_cancel_event.set()
            self.ai_preview_text = "cancellation requested..."
            return True

    def build_ai_status_text(self) -> str:
        self.ensure_ai_state_initialized()
        with self.ai_state_lock:
            if self.ai_active_request_id is None:
                return "No active AI request."
            elapsed = int(max(0, time.monotonic() - self.ai_active_started_at))
            return (
                f"AI status: request={self.ai_active_request_id}, "
                f"provider={self.ai_active_provider}, model={self.ai_active_model}, "
                f"scope={self.ai_active_scope}, room=#{self.ai_active_room}, "
                f"elapsed={elapsed}s, retry={self.ai_retry_count}, "
                f"cancelled={self.ai_cancel_event.is_set()}"
            )

    def run_ai_preview_pulse(self, request_id: str) -> None:
        self.ensure_ai_state_initialized()
        while True:
            with self.ai_state_lock:
                if self.ai_active_request_id != request_id:
                    return
            self.refresh_output_from_events()
            time.sleep(0.5)

    def run_ai_request_with_retry(
        self, request_id: str, provider: str, api_key: str, model: str, prompt: str
    ) -> tuple[str | None, str | None]:
        self.ensure_services_initialized()
        return self.ai_service.run_ai_request_with_retry(
            request_id, provider, api_key, model, prompt
        )

    def handle_ai_command(self, args: str) -> None:
        self.ensure_services_initialized()
        self.ai_service.handle_ai_command(args)

    def process_ai_response(
        self,
        request_id: str,
        provider: str,
        api_key: str,
        model: str,
        prompt: str,
        target_room: str,
        is_private: bool,
        memory_ids_used: list[str],
        memory_topics_used: list[str],
    ) -> None:
        self.ensure_services_initialized()
        self.ai_service.process_ai_response(
            request_id,
            provider,
            api_key,
            model,
            prompt,
            target_room,
            is_private,
            memory_ids_used,
            memory_topics_used,
        )

    def build_command_handlers(self) -> dict[str, Any]:
        return {
            "/theme": self.command_theme,
            "/setpath": self.command_setpath,
            "/status": self.command_status,
            "/join": self.command_join,
            "/rooms": self.command_rooms,
            "/room": self.command_room,
            "/aiproviders": self.command_aiproviders,
            "/aiconfig": self.command_aiconfig,
            "/ai": self.command_ai,
            "/share": self.command_share,
            "/memory": self.command_memory,
            "/search": self.command_search,
            "/next": self.command_next,
            "/prev": self.command_prev,
            "/clearsearch": self.command_clearsearch,
            "/exit": self.command_exit,
            "/quit": self.command_exit,
            "/clear": self.command_clear,
            "/me": self.command_me,
        }

    def command_theme(self, args: str) -> None:
        if not args:
            avail = ", ".join(THEMES.keys())
            self.append_system_message(f"Available themes: {avail}")
            return
        target = args.strip().lower()
        if target in THEMES:
            self.current_theme = target
            self.save_config()
            self.application.style = self.get_style()
            self.application.invalidate()
            return
        self.append_system_message(f"Unknown theme '{target}'.")

    def command_setpath(self, args: str) -> None:
        self.base_dir = args.strip()
        self.save_config()
        self.application.exit(result="restart")

    def command_status(self, args: str) -> None:
        self.status = args[:20]
        self.force_heartbeat()

    def command_join(self, args: str) -> None:
        if not args.strip():
            self.append_system_message("Usage: /join <room>")
            return
        self.switch_room(args.strip())

    def command_rooms(self, _args: str) -> None:
        rooms = ", ".join(self.list_rooms())
        self.append_system_message(f"Rooms: {rooms}")

    def command_room(self, _args: str) -> None:
        self.append_system_message(f"Current room: #{self.current_room}")

    def command_aiproviders(self, _args: str) -> None:
        self.append_system_message(self.get_ai_provider_summary())

    def command_aiconfig(self, args: str) -> None:
        self.handle_aiconfig_command(args)

    def command_ai(self, args: str) -> None:
        self.handle_ai_command(args)

    def command_share(self, args: str) -> None:
        self.handle_share_command(args)

    def command_memory(self, args: str) -> None:
        self.handle_memory_command(args)

    def command_search(self, args: str) -> None:
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

    def command_next(self, _args: str) -> None:
        if not self.jump_to_search_hit(1):
            self.append_system_message("No search matches.")

    def command_prev(self, _args: str) -> None:
        if not self.jump_to_search_hit(-1):
            self.append_system_message("No search matches.")

    def command_clearsearch(self, _args: str) -> None:
        self.search_query = ""
        self.search_hits = []
        self.active_search_hit_idx = -1
        self.append_system_message("Search cleared.")

    def command_exit(self, _args: str) -> None:
        self.application.exit()

    def command_clear(self, _args: str) -> None:
        self.messages = []
        self.message_events = []
        self.output_field.text = ""
        self.search_query = ""
        self.search_hits = []
        self.active_search_hit_idx = -1

    def command_me(self, args: str) -> None:
        event = self.build_event("me", args)
        if not self.write_to_file(event):
            self.append_system_message(
                "Error: Could not send message. Network busy or locked."
            )

    def handle_input(self, text: str) -> None:
        text = text.strip()
        if not text:
            return

        if self.handle_memory_confirmation_input(text):
            self.input_field.text = ""
            return

        if text.startswith("/"):
            if not hasattr(self, "command_handlers"):
                self.command_handlers = self.build_command_handlers()
            parts = text.split(" ", 1)
            command = parts[0].lower()
            args = parts[1] if len(parts) > 1 else ""
            handler = self.command_handlers.get(command)
            if handler is None:
                self.append_system_message(f"Unknown command: {command}")
                self.input_field.text = ""
                return
            handler(args)
            self.input_field.text = ""
            return

        event = self.build_event("chat", text)
        if self.write_to_file(event):
            self.input_field.text = ""
        else:
            self.append_system_message(
                "Error: Could not send message. Network busy or locked."
            )

    def write_to_file(
        self, payload: dict[str, Any] | str, room: str | None = None
    ) -> bool:
        self.ensure_services_initialized()
        return self.storage_service.write_to_file(payload, room)

    def force_heartbeat(self) -> None:
        if self.is_local_room():
            self.refresh_presence_sidebar()
            return
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
        self.ensure_services_initialized()
        await self.runtime_service.monitor_messages()

    def run(self) -> None:
        print(f"Connecting to: {self.base_dir}")

        config_data = self.load_config_data()
        saved_name = config_data.get("username", "")

        if saved_name:
            user_input = input(f"Enter your name [Default: {saved_name}]: ").strip()
            self.name = user_input if user_input else saved_name
        else:
            self.name = input("Enter your name: ").strip() or "Anonymous"
        self.presence_file_id = self.client_id

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

        self.start_file_watcher()
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
            self.stop_file_watcher()


if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s: %(message)s")
    ChatApp().run()
