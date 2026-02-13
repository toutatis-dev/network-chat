from pathlib import Path
from unittest.mock import patch

import pytest

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


def build_app(tmp_path: Path) -> chat.ChatApp:
    app = chat.ChatApp.__new__(chat.ChatApp)
    app.base_dir = str(tmp_path)
    app.rooms_root = str(tmp_path / "rooms")
    app.current_room = "general"
    app.client_id = "user1234abcd"
    app.presence_file_id = app.client_id
    app.current_theme = "default"
    Path(app.rooms_root).mkdir(parents=True, exist_ok=True)
    app.ensure_locking_dependency = lambda: None
    app.ensure_paths()
    app.update_room_paths()
    return app


def test_write_to_file_success_jsonl(tmp_path, monkeypatch):
    app = build_app(tmp_path)
    monkeypatch.setattr(chat, "portalocker", FakePortalocker())

    payload = {
        "ts": "2026-02-13T10:20:30",
        "type": "chat",
        "author": "user",
        "text": "hello",
    }
    assert app.write_to_file(payload) is True

    rows = app.get_message_file().read_text(encoding="utf-8").strip().splitlines()
    assert len(rows) == 1
    assert '"text": "hello"' in rows[0]


def test_write_to_file_retries_then_succeeds(tmp_path, monkeypatch):
    app = build_app(tmp_path)
    fake_portalocker = FakePortalocker()
    lock_error = FakeLockException("busy")
    monkeypatch.setattr(chat, "portalocker", fake_portalocker)

    with (
        patch.object(
            fake_portalocker,
            "Lock",
            side_effect=[
                lock_error,
                lock_error,
                FakeFileLock(app.get_message_file()),
            ],
        ) as mock_lock,
        patch("chat.time.sleep"),
    ):
        assert app.write_to_file(
            {"ts": "x", "type": "chat", "author": "u", "text": "m"}
        )

    assert mock_lock.call_count == 3


def test_write_to_file_fails_after_retry_exhaustion(tmp_path, monkeypatch):
    app = build_app(tmp_path)
    fake_portalocker = FakePortalocker()
    lock_error = FakeLockException("busy")
    monkeypatch.setattr(chat, "portalocker", fake_portalocker)
    monkeypatch.setattr(chat, "LOCK_MAX_ATTEMPTS", 3)

    with (
        patch.object(fake_portalocker, "Lock", side_effect=lock_error) as mock_lock,
        patch("chat.time.sleep"),
    ):
        assert (
            app.write_to_file({"ts": "x", "type": "chat", "author": "u", "text": "m"})
            is False
        )

    assert mock_lock.call_count == 3


def test_missing_portalocker_fails_fast(monkeypatch):
    app = chat.ChatApp.__new__(chat.ChatApp)
    monkeypatch.setattr(chat, "portalocker", None)
    monkeypatch.setattr(chat, "_PORTALOCKER_IMPORT_ERROR", ImportError("not installed"))

    with pytest.raises(SystemExit, match="Missing dependency 'portalocker'"):
        app.ensure_locking_dependency()


def test_sanitize_presence_id_blocks_path_tokens():
    app = chat.ChatApp.__new__(chat.ChatApp)
    assert app.sanitize_presence_id("../Shared_chat.txt") == "_Shared_chat.txt"
    assert app.sanitize_presence_id(r"..\Shared_chat.txt") == "_Shared_chat.txt"
    assert app.sanitize_presence_id("   ") == "Anonymous"


def test_sanitize_room_name_normalizes_and_falls_back():
    app = chat.ChatApp.__new__(chat.ChatApp)
    assert app.sanitize_room_name("  Team Ops  ") == "team-ops"
    assert app.sanitize_room_name("@@@") == "general"


def test_get_presence_path_stays_within_room(tmp_path):
    app = build_app(tmp_path)
    app.presence_file_id = app.sanitize_presence_id("../escape")

    path = app.get_presence_path()
    base = app.get_presence_dir().resolve()
    assert path.parent == base
    assert str(path).startswith(str(base))
