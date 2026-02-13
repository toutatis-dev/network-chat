import asyncio
import json
import logging
from pathlib import Path
from unittest.mock import MagicMock

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
    app.messages = []
    app.last_pos = 0
    app.online_users = {}
    app.presence_dir = str(tmp_path / "presence")
    Path(app.presence_dir).mkdir(parents=True, exist_ok=True)
    app.presence_file_id = app.sanitize_presence_id(app.name)
    app.chat_file = str(tmp_path / "Shared_chat.txt")
    Path(app.chat_file).touch()
    app.sidebar_control = MagicMock()
    app.output_field = MagicMock()
    app.output_field.text = ""
    app.output_field.buffer = MagicMock()
    app.application = MagicMock()
    app.input_field = MagicMock()
    return app


def test_heartbeat_presence_lifecycle(tmp_path, monkeypatch):
    app = build_runtime_app(tmp_path)

    def stop_after_first_sleep(_seconds):
        app.running = False

    monkeypatch.setattr(chat.time, "sleep", stop_after_first_sleep)

    app.heartbeat()

    presence_path = app.get_presence_path()
    assert app.online_users == {}
    assert not presence_path.exists()


def test_force_heartbeat_writes_presence_data(tmp_path):
    app = build_runtime_app(tmp_path)
    app.force_heartbeat()

    presence_path = app.get_presence_path()
    assert presence_path.exists()
    payload = json.loads(presence_path.read_text(encoding="utf-8"))
    assert payload["name"] == "RuntimeUser"
    assert payload["status"] == "online"
    assert payload["color"] == "green"
    assert "RuntimeUser" in app.get_online_users()


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

    assert "Failed while monitoring chat file" in caplog.text


def test_message_flow_from_handle_input_to_monitor(tmp_path, monkeypatch):
    app = build_runtime_app(tmp_path)
    app.ensure_locking_dependency = lambda: None
    monkeypatch.setattr(chat, "portalocker", FakePortalocker())
    app.input_field.text = "hello"

    app.handle_input("hello")

    app.running = True

    async def stop_after_first_sleep(_seconds):
        app.running = False

    monkeypatch.setattr(chat.asyncio, "sleep", stop_after_first_sleep)
    asyncio.run(app.monitor_messages())

    assert any("RuntimeUser: hello" in line for line in app.messages)
