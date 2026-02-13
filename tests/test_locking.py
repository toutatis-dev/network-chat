from unittest.mock import patch

import pytest
from pathlib import Path

import chat


def build_app(chat_file):
    app = chat.ChatApp.__new__(chat.ChatApp)
    app.chat_file = str(chat_file)
    return app


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


def test_write_to_file_success(tmp_path, monkeypatch):
    app = build_app(tmp_path / "Shared_chat.txt")
    monkeypatch.setattr(chat, "portalocker", FakePortalocker())

    assert app.write_to_file("hello\n") is True
    assert (tmp_path / "Shared_chat.txt").read_text(encoding="utf-8") == "hello\n"


def test_write_to_file_retries_then_succeeds(tmp_path, monkeypatch):
    app = build_app(tmp_path / "Shared_chat.txt")
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
                FakeFileLock(tmp_path / "Shared_chat.txt"),
            ],
        ) as mock_lock,
        patch("chat.time.sleep"),
    ):
        assert app.write_to_file("message\n") is True

    assert mock_lock.call_count == 3
    assert (tmp_path / "Shared_chat.txt").read_text(encoding="utf-8") == "message\n"


def test_write_to_file_fails_after_retry_exhaustion(tmp_path, monkeypatch):
    app = build_app(tmp_path / "Shared_chat.txt")
    fake_portalocker = FakePortalocker()
    lock_error = FakeLockException("busy")
    monkeypatch.setattr(chat, "portalocker", fake_portalocker)
    monkeypatch.setattr(chat, "LOCK_MAX_ATTEMPTS", 3)

    with (
        patch.object(fake_portalocker, "Lock", side_effect=lock_error) as mock_lock,
        patch("chat.time.sleep"),
    ):
        assert app.write_to_file("message\n") is False

    assert mock_lock.call_count == 3
    chat_path = tmp_path / "Shared_chat.txt"
    if chat_path.exists():
        assert not chat_path.read_text(encoding="utf-8")


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


def test_get_presence_path_stays_within_presence_dir(tmp_path):
    app = chat.ChatApp.__new__(chat.ChatApp)
    app.presence_dir = str(tmp_path / "presence")
    app.presence_file_id = app.sanitize_presence_id("../escape")

    path = app.get_presence_path()

    base = Path(app.presence_dir).resolve()
    assert path.parent == base
    assert str(path).startswith(str(base))
