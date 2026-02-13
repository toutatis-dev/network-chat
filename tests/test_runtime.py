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
    app.status = "online"
    app.color = "green"
    app.running = True
    app.current_room = "general"
    app.current_theme = "default"
    app.base_dir = str(tmp_path)
    app.rooms_root = str(tmp_path / "rooms")
    app.presence_file_id = app.sanitize_presence_id(app.name)
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
    assert "RuntimeUser" in app.get_online_users("general")


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

    app.handle_input("hello general")

    app.switch_room("dev")
    app.handle_input("hello dev")

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
