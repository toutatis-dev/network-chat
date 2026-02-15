import threading
import time
from pathlib import Path
from threading import Event, Lock
from types import SimpleNamespace
from unittest.mock import patch

import chat
from huddle_chat.models import ChatEvent


def build_ai_app(tmp_path: Path) -> chat.ChatApp:
    app = chat.ChatApp.__new__(chat.ChatApp)
    app.name = "Tester"
    app.client_id = "tester123456"
    app.color = "green"
    app.status = ""
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
    app.ai_state_lock = Lock()
    app.ai_active_request_id = None
    app.ai_active_started_at = 0.0
    app.ai_active_provider = ""
    app.ai_active_model = ""
    app.ai_active_scope = ""
    app.ai_active_room = ""
    app.ai_retry_count = 0
    app.ai_preview_text = ""
    app.ai_cancel_event = Event()
    app.sidebar_control = SimpleNamespace(text=[])
    app.output_field = SimpleNamespace(
        text="", buffer=SimpleNamespace(cursor_position=0)
    )
    app.application = SimpleNamespace(invalidate=lambda: None)
    app.input_field = SimpleNamespace(text="")
    app.ensure_locking_dependency = lambda: None
    app.ai_config = {
        "default_provider": "gemini",
        "providers": {
            "gemini": {"api_key": "g-key", "model": "gemini-2.5-flash"},
            "openai": {"api_key": "o-key", "model": "gpt-4o-mini"},
        },
        "streaming": {
            "enabled": False,
            "providers": {
                "gemini": True,
                "openai": True,
            },
        },
    }
    app.ensure_paths()
    app.ensure_local_paths()
    app.update_room_paths()
    app.storage_service = SimpleNamespace(
        write_to_file=lambda payload, room=None: app.write_to_file(payload, room)
    )
    app.controller = chat.ChatController(app)
    return app


def test_parse_ai_args_accepts_flags():
    app = chat.ChatApp.__new__(chat.ChatApp)
    parsed, error = app.parse_ai_args(
        "--provider openai --model gpt-5-mini --private summarize this"
    )
    assert error is None
    assert parsed.provider_override == "openai"
    assert parsed.model_override == "gpt-5-mini"
    assert parsed.is_private is True
    assert parsed.prompt == "summarize this"


def test_parse_ai_args_accepts_no_memory_flag():
    app = chat.ChatApp.__new__(chat.ChatApp)
    parsed, error = app.parse_ai_args("--no-memory summarize this")
    assert error is None
    assert parsed.disable_memory is True
    assert parsed.prompt == "summarize this"


def test_parse_ai_args_accepts_act_flag():
    app = chat.ChatApp.__new__(chat.ChatApp)
    parsed, error = app.parse_ai_args("--act summarize this")
    assert error is None
    assert parsed.action_mode is True
    assert parsed.prompt == "summarize this"


def test_aiconfig_set_key_updates_local_config(tmp_path):
    app = build_ai_app(tmp_path)
    called = {"saved": 0}
    app.save_ai_config_data = lambda: called.__setitem__("saved", called["saved"] + 1)
    app.controller.handle_aiconfig_command("set-key gemini NEWKEY")
    assert app.ai_config["providers"]["gemini"]["api_key"] == "NEWKEY"
    assert called["saved"] == 1


def test_aiconfig_set_key_accepts_provider_first_syntax(tmp_path):
    app = build_ai_app(tmp_path)
    called = {"saved": 0}
    app.save_ai_config_data = lambda: called.__setitem__("saved", called["saved"] + 1)
    app.controller.handle_aiconfig_command("gemini set-key NEWKEY")
    assert app.ai_config["providers"]["gemini"]["api_key"] == "NEWKEY"
    assert called["saved"] == 1


def test_aiconfig_streaming_on_updates_local_config(tmp_path):
    app = build_ai_app(tmp_path)
    called = {"saved": 0}
    app.save_ai_config_data = lambda: called.__setitem__("saved", called["saved"] + 1)
    app.controller.handle_aiconfig_command("streaming on")
    assert app.ai_config["streaming"]["enabled"] is True
    assert called["saved"] == 1


def test_aiconfig_streaming_provider_toggle_updates_local_config(tmp_path):
    app = build_ai_app(tmp_path)
    called = {"saved": 0}
    app.save_ai_config_data = lambda: called.__setitem__("saved", called["saved"] + 1)
    app.controller.handle_aiconfig_command("streaming provider openai off")
    assert app.ai_config["streaming"]["providers"]["openai"] is False
    assert called["saved"] == 1


def test_ai_private_targets_local_dm_room(tmp_path):
    app = build_ai_app(tmp_path)
    written: list[tuple[str | None, dict]] = []

    def fake_write(payload, room=None):
        if hasattr(payload, "to_dict"):
            written.append((room, payload.to_dict()))
        elif isinstance(payload, dict):
            written.append((room, payload))
        return True

    app.write_to_file = fake_write
    app.call_ai_provider = lambda **kwargs: "local-answer"
    with patch.object(
        chat,
        "Thread",
        side_effect=lambda target, args, daemon: SimpleNamespace(
            start=lambda: target(*args)
        ),
    ):
        app.controller.handle_ai_command("--private hello from private")
    assert len(written) == 2
    assert written[0][0] == "ai-dm"
    assert written[1][0] == "ai-dm"
    assert written[0][1]["type"] == "ai_prompt"
    assert written[1][1]["type"] == "ai_response"


def test_get_message_file_routes_ai_dm_to_local_storage(tmp_path):
    app = build_ai_app(tmp_path)
    path = app.get_message_file("ai-dm")
    assert ".local_chat" in str(path)
    assert str(path).endswith("ai-dm\\messages.jsonl") or str(path).endswith(
        "ai-dm/messages.jsonl"
    )


def test_ai_dm_renders_share_indexes(tmp_path):
    app = build_ai_app(tmp_path)
    app.current_room = "ai-dm"
    app.message_events = [
        ChatEvent(
            ts="2026-01-01T10:00:00",
            type="ai_prompt",
            author="Tester",
            text="Q",
        ),
        ChatEvent(
            ts="2026-01-01T10:00:01",
            type="ai_response",
            author="Tester",
            text="A",
            provider="gemini",
            model="gemini-2.5-flash",
        ),
    ]
    app.refresh_output_from_events()
    lines = app.output_field.text.splitlines()
    assert lines[0].startswith("(1) ")
    assert lines[1].startswith("(2) ")


def test_ai_status_and_cancel_messages(tmp_path):
    app = build_ai_app(tmp_path)
    app.controller.handle_ai_command("status")
    assert "No active AI request" in app.output_field.text

    app.ai_active_request_id = "abc123"
    app.ai_cancel_event = Event()
    app.controller.handle_ai_command("cancel")
    assert "AI cancellation requested" in app.output_field.text
    assert app.ai_cancel_event.is_set()


def test_ai_busy_rejects_new_request(tmp_path):
    app = build_ai_app(tmp_path)
    app.ai_active_request_id = "busy123"
    app.ai_cancel_event = Event()
    app.controller.handle_ai_command("hello while busy")
    assert "Problem: AI busy: another request is active." in app.output_field.text


def test_memory_add_creates_confirm_draft_from_last_ai_response(tmp_path):
    app = build_ai_app(tmp_path)
    app.message_events = [
        ChatEvent(
            ts="2026-01-01T10:00:00",
            type="ai_response",
            author="Tester",
            text="Use runbook A for deploys and rollback with command B.",
            request_id="req123",
        )
    ]
    app.call_ai_provider = lambda **kwargs: (
        '{"summary":"Use runbook A for deploys.","topic":"deploy","confidence":"high","tags":["runbook"]}'
    )
    app.controller.handle_memory_command("add")
    assert app.memory_draft_active is True
    assert app.memory_draft_mode == "confirm"
    assert app.memory_draft["topic"] == "deploy"
    assert "Confirm memory entry? (y/n)" in app.output_field.text


def test_memory_confirm_writes_entry_and_clears_draft(tmp_path):
    app = build_ai_app(tmp_path)
    app.memory_draft_active = True
    app.memory_draft_mode = "confirm"
    app.memory_draft = {
        "summary": "Use runbook A.",
        "topic": "deploy",
        "confidence": "high",
        "source": "room:general request:req123 ts:2026-01-01T10:00:00",
        "room": "general",
        "origin_event_ref": "req123",
        "tags": [],
    }
    written = {"count": 0}

    def fake_write_memory_entry(entry, scope="team"):
        written["count"] += 1
        return True

    app.write_memory_entry = fake_write_memory_entry
    app.controller.handle_memory_command("confirm")
    assert written["count"] == 1
    assert app.memory_draft_active is False
    assert "Memory saved:" in app.output_field.text


def test_memory_reject_enters_edit_mode_and_edit_updates_field(tmp_path):
    app = build_ai_app(tmp_path)
    app.memory_draft_active = True
    app.memory_draft_mode = "confirm"
    app.memory_draft = {
        "summary": "old",
        "topic": "general",
        "confidence": "med",
        "source": "room:general ts:1",
        "room": "general",
        "origin_event_ref": "1",
        "tags": [],
    }
    app.controller.handle_input("n")
    assert app.memory_draft_mode == "edit"
    app.controller.handle_memory_command("edit summary updated summary")
    assert app.memory_draft["summary"] == "updated summary"


def test_process_ai_response_wrapper_forwards_updated_signature(tmp_path):
    app = build_ai_app(tmp_path)
    app.ensure_services_initialized()
    captured: dict[str, object] = {}

    def fake_process_ai_response(*args):
        captured["args"] = args

    app.ai_service.process_ai_response = fake_process_ai_response
    app.ai_service.process_ai_response(
        "req123",
        "gemini",
        "key",
        "gemini-2.5-flash",
        "hello",
        "general",
        False,
        True,
        True,
        ["team"],
    )
    forwarded = captured["args"]
    assert isinstance(forwarded, tuple)
    assert forwarded[7] is True  # disable_memory
    assert forwarded[8] is True  # action_mode
    assert forwarded[9] == ["team"]


def test_ai_uses_memory_and_persists_citations(tmp_path):
    app = build_ai_app(tmp_path)
    written: list[tuple[str | None, dict]] = []

    def fake_write(payload, room=None):
        if hasattr(payload, "to_dict"):
            written.append((room, payload.to_dict()))
        elif isinstance(payload, dict):
            written.append((room, payload))
        return True

    prompts: list[str] = []

    def fake_ai_provider(**kwargs):
        prompt = kwargs["prompt"]
        prompts.append(prompt)
        if "Given the user prompt and candidate memory entries" in prompt:
            return '{"ids":["mem_1"]}'
        return "grounded answer"

    app.write_to_file = fake_write
    app.load_memory_entries = lambda: [
        {
            "id": "mem_1",
            "summary": "Use runbook A for deploy rollback.",
            "topic": "deploy",
            "confidence": "high",
            "source": "room:general ts:1",
            "ts": "2026-01-01T10:00:00",
        }
    ]
    app.call_ai_provider = fake_ai_provider
    with patch.object(
        chat,
        "Thread",
        side_effect=lambda target, args, daemon: SimpleNamespace(
            start=lambda: target(*args)
        ),
    ):
        app.controller.handle_ai_command("how do we rollback deploy?")

    assert any("Shared memory context" in prompt for prompt in prompts)
    assert len(written) == 3
    assert written[0][1]["type"] == "ai_prompt"
    assert not written[0][1].get("memory_ids_used")
    assert written[1][1]["type"] == "ai_response"
    assert written[1][1]["memory_ids_used"] == ["mem_1"]
    assert written[2][1]["type"] == "system"
    assert "Memory used: mem_1" in written[2][1]["text"]


def test_ai_no_memory_flag_bypasses_memory_retrieval(tmp_path):
    app = build_ai_app(tmp_path)
    written: list[tuple[str | None, dict]] = []

    def fake_write(payload, room=None):
        if hasattr(payload, "to_dict"):
            written.append((room, payload.to_dict()))
        elif isinstance(payload, dict):
            written.append((room, payload))
        return True

    prompts: list[str] = []

    def fake_ai_provider(**kwargs):
        prompts.append(kwargs["prompt"])
        return "answer"

    app.write_to_file = fake_write
    app.load_memory_entries = lambda: [
        {
            "id": "mem_1",
            "summary": "Do X",
            "topic": "ops",
            "confidence": "high",
            "source": "room:general ts:1",
            "ts": "2026-01-01T10:00:00",
        }
    ]
    app.call_ai_provider = fake_ai_provider
    with patch.object(
        chat,
        "Thread",
        side_effect=lambda target, args, daemon: SimpleNamespace(
            start=lambda: target(*args)
        ),
    ):
        app.controller.handle_ai_command("--no-memory plain prompt")

    assert len(prompts) == 1
    assert prompts[0] == "plain prompt"
    assert not written[0][1].get("memory_ids_used")
    assert len(written) == 2


def test_ai_rerank_failure_falls_back_to_lexical(tmp_path):
    app = build_ai_app(tmp_path)
    written: list[tuple[str | None, dict]] = []

    def fake_write(payload, room=None):
        if hasattr(payload, "to_dict"):
            written.append((room, payload.to_dict()))
        elif isinstance(payload, dict):
            written.append((room, payload))
        return True

    def fake_ai_provider(**kwargs):
        prompt = kwargs["prompt"]
        if "Given the user prompt and candidate memory entries" in prompt:
            raise RuntimeError("rerank timeout")
        return "answer via fallback"

    app.write_to_file = fake_write
    app.load_memory_entries = lambda: [
        {
            "id": "mem_lex",
            "summary": "Rollback deploy with runbook A.",
            "topic": "deploy",
            "confidence": "high",
            "source": "room:general ts:1",
            "ts": "2026-01-01T10:00:00",
        }
    ]
    app.call_ai_provider = fake_ai_provider
    with patch.object(
        chat,
        "Thread",
        side_effect=lambda target, args, daemon: SimpleNamespace(
            start=lambda: target(*args)
        ),
    ):
        app.controller.handle_ai_command("how to rollback deploy")

    assert (
        "Memory rerank unavailable; using lexical memory selection."
        in app.output_field.text
    )
    assert written[1][1]["memory_ids_used"] == ["mem_lex"]


def test_memory_add_warns_on_duplicates(tmp_path):
    app = build_ai_app(tmp_path)
    app.message_events = [
        ChatEvent(
            ts="2026-01-01T10:00:00",
            type="ai_response",
            author="Tester",
            text="Use runbook A for deploy rollback.",
            request_id="req123",
        )
    ]
    app.call_ai_provider = lambda **kwargs: (
        '{"summary":"Use runbook A for deploy rollback.","topic":"deploy","confidence":"high","tags":["runbook"]}'
    )
    app.load_memory_entries = lambda: [
        {
            "id": "mem_old",
            "summary": "Use runbook A for deploy rollback.",
            "topic": "deploy",
            "confidence": "high",
            "source": "room:general ts:0",
        }
    ]
    app.controller.handle_memory_command("add")
    assert "Potential duplicate memory entries:" in app.output_field.text
    assert "mem_old" in app.output_field.text


def test_memory_confirm_warns_on_duplicates(tmp_path):
    app = build_ai_app(tmp_path)
    app.memory_draft_active = True
    app.memory_draft_mode = "confirm"
    app.memory_draft = {
        "summary": "Use runbook A for deploy rollback.",
        "topic": "deploy",
        "confidence": "high",
        "source": "room:general request:req123 ts:2026-01-01T10:00:00",
        "room": "general",
        "origin_event_ref": "req123",
        "tags": [],
    }
    app.load_memory_entries = lambda: [
        {
            "id": "mem_old",
            "summary": "Use runbook A for deploy rollback.",
            "topic": "deploy",
            "confidence": "high",
            "source": "room:general ts:0",
        }
    ]
    app.write_memory_entry = lambda entry, scope="team": True
    app.controller.handle_memory_command("confirm")
    assert "Potential duplicate memory entries:" in app.output_field.text
    assert "Memory saved:" in app.output_field.text


def test_run_ai_request_with_retry_interrupts_on_cancel(tmp_path):
    app = build_ai_app(tmp_path)
    app.ensure_services_initialized()
    request_id = app.start_ai_request_state(
        provider="gemini",
        model="gemini-2.5-flash",
        target_room="general",
        scope="room",
    )
    assert request_id is not None

    def slow_provider(**kwargs):
        time.sleep(1.0)
        return "late-answer"

    app.call_ai_provider = slow_provider

    def trigger_cancel():
        time.sleep(0.1)
        app.request_ai_cancel()

    threading.Thread(target=trigger_cancel, daemon=True).start()
    started = time.monotonic()
    answer, err = app.ai_service.run_ai_request_with_retry(
        request_id=request_id,
        provider="gemini",
        api_key="k",
        model="gemini-2.5-flash",
        prompt="hello",
    )
    elapsed = time.monotonic() - started
    assert answer is None
    assert err == "AI request cancelled."
    assert elapsed < 0.7


def test_ai_streaming_uses_stream_provider_and_persists_final_response_only(tmp_path):
    app = build_ai_app(tmp_path)
    app.ai_config["streaming"]["enabled"] = True
    written: list[tuple[str | None, dict]] = []

    def fake_write(payload, room=None):
        if hasattr(payload, "to_dict"):
            written.append((room, payload.to_dict()))
        elif isinstance(payload, dict):
            written.append((room, payload))
        return True

    stream_calls = {"count": 0}

    def fake_stream_provider(**kwargs):
        stream_calls["count"] += 1
        kwargs["on_token"]("hello ")
        kwargs["on_token"]("world")
        return "hello world"

    app.write_to_file = fake_write
    app.call_ai_provider_stream = fake_stream_provider
    app.call_ai_provider = lambda **kwargs: "non-stream"
    with patch.object(
        chat,
        "Thread",
        side_effect=lambda target, args, daemon: SimpleNamespace(
            start=lambda: target(*args)
        ),
    ):
        app.controller.handle_ai_command("--no-memory say hello")

    assert stream_calls["count"] == 1
    assert [entry[1]["type"] for entry in written] == ["ai_prompt", "ai_response"]
    assert written[1][1]["text"] == "hello world"


def test_ai_streaming_cancel_does_not_persist_partial_response(tmp_path):
    app = build_ai_app(tmp_path)
    app.ensure_services_initialized()
    app.ai_config["streaming"]["enabled"] = True
    written: list[tuple[str | None, dict]] = []

    def fake_write(payload, room=None):
        if hasattr(payload, "to_dict"):
            written.append((room, payload.to_dict()))
        elif isinstance(payload, dict):
            written.append((room, payload))
        return True

    app.write_to_file = fake_write

    def slow_stream_provider(**kwargs):
        kwargs["on_token"]("partial")
        time.sleep(1.0)
        return "late"

    app.call_ai_provider_stream = slow_stream_provider
    request_id = app.start_ai_request_state(
        provider="gemini",
        model="gemini-2.5-flash",
        target_room="general",
        scope="room",
    )
    assert request_id is not None

    def trigger_cancel():
        time.sleep(0.1)
        app.request_ai_cancel()

    threading.Thread(target=trigger_cancel, daemon=True).start()
    app.ai_service.process_ai_response(
        request_id=request_id,
        provider="gemini",
        api_key="k",
        model="gemini-2.5-flash",
        prompt="hello",
        target_room="general",
        is_private=False,
        disable_memory=True,
        action_mode=False,
        memory_scopes=["team"],
    )
    assert all(entry[1]["type"] != "ai_response" for entry in written)
    assert any(
        entry[1]["type"] == "system" and "cancelled" in entry[1]["text"].lower()
        for entry in written
    )
