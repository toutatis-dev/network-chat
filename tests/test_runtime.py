import asyncio
import json
import logging
from pathlib import Path
from types import SimpleNamespace

import chat


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


def build_runtime_app(tmp_path: Path) -> chat.ChatApp:
    app = chat.ChatApp.__new__(chat.ChatApp)
    app.name = "RuntimeUser"
    app.client_id = "runtime1234ab"
    app.status = "online"
    app.color = "green"
    app.running = True
    app.current_room = "general"
    app.current_theme = "default"
    app.base_dir = str(tmp_path)
    app.rooms_root = str(tmp_path / "rooms")
    app.presence_file_id = app.client_id
    app.messages = []
    app.message_events = []
    app.last_pos_by_room = {}
    app.online_users = {}
    app.search_query = ""
    app.search_hits = []
    app.active_search_hit_idx = -1
    app.sidebar_control = SimpleNamespace(text=[])
    app.output_field = SimpleNamespace(
        text="", buffer=SimpleNamespace(cursor_position=0)
    )
    app.application = SimpleNamespace(invalidate=lambda: None)
    app.input_field = SimpleNamespace(text="")
    app.ensure_locking_dependency = lambda: None
    app.ensure_paths()
    app.update_room_paths()
    app.controller = chat.ChatController(app)
    return app


def test_heartbeat_presence_lifecycle(tmp_path, monkeypatch):
    app = build_runtime_app(tmp_path)

    def stop_after_first_sleep(_seconds):
        app.running = False

    monkeypatch.setattr(chat.time, "sleep", stop_after_first_sleep)

    app.heartbeat()

    presence_path = app.get_presence_path("general")
    assert not presence_path.exists()


def test_force_heartbeat_writes_presence_data(tmp_path):
    app = build_runtime_app(tmp_path)
    app.force_heartbeat()

    presence_path = app.get_presence_path("general")
    assert presence_path.exists()
    payload = json.loads(presence_path.read_text(encoding="utf-8"))
    assert payload["name"] == "RuntimeUser"
    assert payload["status"] == "online"
    assert payload["color"] == "green"
    assert payload["room"] == "general"
    online_users = app.get_online_users("general")
    assert any(user.get("name") == "RuntimeUser" for user in online_users.values())


def test_get_online_users_keeps_duplicate_display_names(tmp_path):
    app = build_runtime_app(tmp_path)
    presence_dir = app.get_presence_dir("general")
    presence_dir.mkdir(parents=True, exist_ok=True)

    (presence_dir / "abc11111aaaa").write_text(
        json.dumps({"name": "Alex", "color": "green", "status": "one"}),
        encoding="utf-8",
    )
    (presence_dir / "def22222bbbb").write_text(
        json.dumps({"name": "Alex", "color": "cyan", "status": "two"}),
        encoding="utf-8",
    )

    online_users = app.get_online_users("general")
    assert len(online_users) == 2
    assert {user["client_id"] for user in online_users.values()} == {
        "abc11111aaaa",
        "def22222bbbb",
    }
    assert all(user["name"] == "Alex" for user in online_users.values())


def test_get_online_users_all_rooms_includes_room_metadata(tmp_path):
    app = build_runtime_app(tmp_path)
    general_presence = app.get_presence_dir("general")
    dev_presence = app.get_presence_dir("dev")
    general_presence.mkdir(parents=True, exist_ok=True)
    dev_presence.mkdir(parents=True, exist_ok=True)

    (general_presence / "aaa11111bbbb").write_text(
        json.dumps({"name": "Alice", "color": "green", "status": "online"}),
        encoding="utf-8",
    )
    (dev_presence / "ccc22222dddd").write_text(
        json.dumps({"name": "Bob", "color": "cyan", "status": "busy"}),
        encoding="utf-8",
    )

    online_users = app.get_online_users_all_rooms()
    assert len(online_users) == 2
    assert online_users["aaa11111bbbb"]["room"] == "general"
    assert online_users["ccc22222dddd"]["room"] == "dev"


def test_get_online_users_all_rooms_drops_malformed_presence(tmp_path):
    app = build_runtime_app(tmp_path)
    general_presence = app.get_presence_dir("general")
    general_presence.mkdir(parents=True, exist_ok=True)
    malformed_path = general_presence / "badpresence1234"
    malformed_path.write_text("{not-json", encoding="utf-8")

    online_users = app.get_online_users_all_rooms()
    assert online_users == {}
    assert not malformed_path.exists()


def test_refresh_presence_sidebar_is_rate_limited(tmp_path):
    app = build_runtime_app(tmp_path)
    calls = {"count": 0}

    def fake_get_online():
        calls["count"] += 1
        return {}

    app.get_online_users_all_rooms = fake_get_online
    app.refresh_presence_sidebar(force=True)
    app.refresh_presence_sidebar()
    assert calls["count"] == 1


def test_repeated_malformed_presence_gets_quarantined_when_enabled(
    tmp_path, monkeypatch
):
    app = build_runtime_app(tmp_path)
    monkeypatch.setenv("HUDDLE_PRESENCE_QUARANTINE", "1")
    presence_dir = app.get_presence_dir("general")
    presence_dir.mkdir(parents=True, exist_ok=True)
    malformed_name = "badpresence1234"
    malformed_path = presence_dir / malformed_name

    for _ in range(chat.PRESENCE_MALFORMED_QUARANTINE_THRESHOLD):
        malformed_path.write_text("{bad-json", encoding="utf-8")
        app.get_online_users("general")

    quarantine_dir = (
        Path(app.rooms_root) / chat.PRESENCE_QUARANTINE_DIR_NAME / "general"
    )
    quarantined = list(quarantine_dir.glob(f"{malformed_name}.*.badjson"))
    assert quarantined
    assert (
        app.presence_malformed_dropped >= chat.PRESENCE_MALFORMED_QUARANTINE_THRESHOLD
    )
    assert app.presence_quarantined >= 1


def test_update_sidebar_shows_user_room_suffix(tmp_path):
    app = build_runtime_app(tmp_path)
    app.online_users = {
        "aaa11111bbbb": {
            "name": "Alice",
            "client_id": "aaa11111bbbb",
            "color": "green",
            "status": "online",
            "room": "dev",
        }
    }

    app.update_sidebar()

    rendered_text = "".join(fragment[1] for fragment in app.sidebar_control.text)
    assert "#dev" in rendered_text


def test_monitor_messages_logs_and_recovers_from_oserror(tmp_path, monkeypatch, caplog):
    app = build_runtime_app(tmp_path)
    app.running = True

    async def stop_after_first_sleep(_seconds):
        app.running = False

    monkeypatch.setattr(chat.asyncio, "sleep", stop_after_first_sleep)

    def broken_open(*args, **kwargs):
        raise OSError("read failed")

    monkeypatch.setattr("builtins.open", broken_open)

    with caplog.at_level(logging.WARNING):
        asyncio.run(app.monitor_messages())

    assert "Failed while monitoring room" in caplog.text


def test_message_flow_and_room_isolation(tmp_path, monkeypatch):
    app = build_runtime_app(tmp_path)
    monkeypatch.setattr(chat, "portalocker", FakePortalocker())

    app.controller.handle_input("hello general")

    app.controller.switch_room("dev")
    app.controller.handle_input("hello dev")

    general_rows = (
        app.get_message_file("general").read_text(encoding="utf-8").strip().splitlines()
    )
    dev_rows = (
        app.get_message_file("dev").read_text(encoding="utf-8").strip().splitlines()
    )

    assert len(general_rows) == 1
    assert len(dev_rows) == 1
    assert "hello general" in general_rows[0]
    assert "hello dev" in dev_rows[0]


def test_load_recent_messages_uses_tail_for_large_history(tmp_path):
    app = build_runtime_app(tmp_path)
    path = app.get_message_file("general")
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for i in range(chat.MAX_MESSAGES + 25):
            row = {
                "v": 1,
                "ts": f"2026-01-01T00:00:{i % 60:02d}",
                "type": "chat",
                "author": "RuntimeUser",
                "text": f"line-{i}",
            }
            f.write(json.dumps(row) + "\n")

    app.ensure_services_initialized()
    app.storage_service.load_recent_messages()

    assert len(app.message_events) == chat.MAX_MESSAGES
    assert app.message_events[0].text == "line-25"
    assert app.message_events[-1].text == f"line-{chat.MAX_MESSAGES + 24}"
