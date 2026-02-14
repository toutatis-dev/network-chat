import json
from pathlib import Path
from types import SimpleNamespace

import chat
from huddle_chat.services.tool_contract import validate_tool_call_args


class FakeLockException(Exception):
    pass


class FakeFileLock:
    def __init__(self, filename, mode="a", encoding="utf-8", **kwargs):
        self.filename = filename
        self.mode = mode
        self.encoding = encoding
        self._file = None

    def __enter__(self):
        self._file = open(self.filename, self.mode, encoding=self.encoding)
        return self._file

    def __exit__(self, exc_type, exc, tb):
        if self._file is not None:
            self._file.close()


class FakePortalocker:
    class exceptions:
        LockException = FakeLockException

    def Lock(self, filename, mode="a", timeout=None, fail_when_locked=False, **kwargs):
        return FakeFileLock(filename, mode=mode, **kwargs)


def build_contract_app(tmp_path: Path) -> chat.ChatApp:
    app = chat.ChatApp.__new__(chat.ChatApp)
    app.name = "ContractUser"
    app.client_id = "contract12345"
    app.presence_file_id = app.client_id
    app.current_room = "general"
    app.current_theme = "default"
    app.base_dir = str(tmp_path)
    app.rooms_root = str(tmp_path / "rooms")
    app.messages = []
    app.message_events = []
    app.online_users = {}
    app.last_pos_by_room = {}
    app.search_query = ""
    app.search_hits = []
    app.active_search_hit_idx = -1
    app.status = ""
    app.color = "green"
    app.output_field = SimpleNamespace(
        text="", buffer=SimpleNamespace(cursor_position=0)
    )
    app.application = SimpleNamespace(invalidate=lambda: None)
    app.input_field = SimpleNamespace(text="")
    app.sidebar_control = SimpleNamespace(text=[])
    app.ensure_locking_dependency = lambda: None
    app.ensure_paths()
    app.ensure_local_paths()
    app.ensure_memory_paths()
    app.update_room_paths()
    return app


def test_parse_event_line_accepts_missing_version_and_extra_fields(tmp_path):
    app = build_contract_app(tmp_path)
    event = app.parse_event_line(
        '{"ts":"2026-02-13T12:00:00","type":"chat","author":"a","text":"b","x_meta":"ok"}'
    )
    assert event is not None
    assert event["v"] == chat.EVENT_SCHEMA_VERSION
    assert event["x_meta"] == "ok"


def test_parse_event_line_rejects_future_schema_version(tmp_path):
    app = build_contract_app(tmp_path)
    event = app.parse_event_line(
        '{"v":999,"ts":"2026-02-13T12:00:00","type":"chat","author":"a","text":"b"}'
    )
    assert event is None


def test_build_event_emits_required_contract_fields(tmp_path):
    app = build_contract_app(tmp_path)
    event = app.build_event("chat", "hello")
    assert event["v"] == chat.EVENT_SCHEMA_VERSION
    assert isinstance(event["ts"], str)
    assert event["type"] == "chat"
    assert event["author"] == "ContractUser"
    assert event["text"] == "hello"


def test_write_to_file_writes_jsonl_row_with_newline(tmp_path, monkeypatch):
    app = build_contract_app(tmp_path)
    monkeypatch.setattr(chat, "portalocker", FakePortalocker())
    payload = app.build_event("chat", "hello world")

    assert app.write_to_file(payload) is True
    message_file = app.get_message_file("general")
    raw = message_file.read_bytes()
    assert raw.endswith(b"\n")

    line = message_file.read_text(encoding="utf-8").strip()
    row = json.loads(line)
    assert row["type"] == "chat"
    assert row["text"] == "hello world"


def test_append_jsonl_row_uses_locked_append(tmp_path, monkeypatch):
    app = build_contract_app(tmp_path)
    monkeypatch.setattr(chat, "portalocker", FakePortalocker())
    target = tmp_path / "audit.jsonl"
    ok = app.append_jsonl_row(target, {"k": "v"})
    assert ok is True
    rows = target.read_text(encoding="utf-8").strip().splitlines()
    assert len(rows) == 1
    assert json.loads(rows[0]) == {"k": "v"}


def test_get_online_users_skips_malformed_presence_files(tmp_path):
    app = build_contract_app(tmp_path)
    presence_dir = app.get_presence_dir("general")
    presence_dir.mkdir(parents=True, exist_ok=True)

    (presence_dir / "goodclient123").write_text(
        json.dumps({"name": "Alice", "color": "green", "status": "online"}),
        encoding="utf-8",
    )
    (presence_dir / "badclient456").write_text("{bad-json", encoding="utf-8")

    online = app.get_online_users("general")
    assert len(online) == 1
    only_user = next(iter(online.values()))
    assert only_user["name"] == "Alice"
    assert only_user["status"] == "online"


def test_load_memory_entries_skips_invalid_rows(tmp_path):
    app = build_contract_app(tmp_path)
    memory_file = app.get_memory_file()
    memory_file.parent.mkdir(parents=True, exist_ok=True)
    memory_file.write_text(
        "\n".join(
            [
                '{"id":"mem_1","summary":"valid","confidence":"med","source":"room:general"}',
                '{"id":"broken"',
                '["not","an","object"]',
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    entries = app.load_memory_entries()
    assert len(entries) == 1
    assert entries[0]["id"] == "mem_1"


def test_validate_tool_call_args_rejects_unknown_fields():
    definition = {
        "name": "read_file",
        "title": "Read File",
        "description": "Read a bounded line range from a file.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "startLine": {"type": "integer"},
            },
            "required": ["path"],
        },
        "annotations": {},
    }
    ok, err = validate_tool_call_args(
        definition,
        {"path": "chat.py", "startLine": 1, "unknownField": "nope"},
    )
    assert ok is False
    assert err == "Unsupported argument 'unknownField'."


def test_validate_tool_call_args_rejects_bool_for_integer():
    definition = {
        "name": "read_file",
        "title": "Read File",
        "description": "Read a bounded line range from a file.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "startLine": {"type": "integer"},
            },
            "required": ["path"],
        },
        "annotations": {},
    }
    ok, err = validate_tool_call_args(
        definition, {"path": "chat.py", "startLine": True}
    )
    assert ok is False
    assert err == "Argument 'startLine' must be an integer."
