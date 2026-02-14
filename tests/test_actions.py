from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import patch

from huddle_chat.services.action_service import ActionService


def test_approve_executes_action_and_updates_status():
    app = SimpleNamespace()
    app.name = "tester"
    app.current_room = "general"
    app.pending_actions = {
        "abc12345": {
            "action_id": "abc12345",
            "tool": "git_status",
            "summary": "show status",
            "status": "pending",
            "inputs": {},
            "request_id": "req1",
            "room": "general",
        }
    }
    app.get_active_agent_profile = lambda: {"id": "default"}
    app.append_jsonl_row = lambda path, row: True
    app.get_actions_audit_file = lambda: "actions.jsonl"
    messages: list[str] = []
    app.append_system_message = lambda text: messages.append(text)
    app.tool_service = SimpleNamespace(
        execute_action=lambda action: {
            "content": [{"type": "text", "text": "ok"}],
            "isError": False,
            "meta": {"exitCode": 0, "durationMs": 12},
        }
    )

    service = ActionService(app)
    with patch(
        "huddle_chat.services.action_service.Thread",
        side_effect=lambda target, args, daemon: SimpleNamespace(
            start=lambda: target(*args)
        ),
    ):
        ok, _ = service.decide_action("abc12345", "approved")

    assert ok is True
    assert app.pending_actions["abc12345"]["status"] == "completed"
    assert any("Running action abc12345" in msg for msg in messages)


def test_expired_action_cannot_be_approved():
    app = SimpleNamespace()
    app.name = "tester"
    app.current_room = "general"
    app.pending_actions = {
        "abc12345": {
            "action_id": "abc12345",
            "tool": "git_status",
            "summary": "show status",
            "status": "pending",
            "inputs": {},
            "request_id": "req1",
            "room": "general",
            "expires_at": (datetime.now() - timedelta(seconds=1)).isoformat(
                timespec="seconds"
            ),
        }
    }
    app.get_active_agent_profile = lambda: {"id": "default"}
    app.append_jsonl_row = lambda path, row: True
    app.get_actions_audit_file = lambda: "actions.jsonl"
    app.append_system_message = lambda text: None
    app.tool_service = SimpleNamespace(
        execute_action=lambda action: {
            "content": [{"type": "text", "text": "ok"}],
            "isError": False,
            "meta": {"exitCode": 0, "durationMs": 12},
        }
    )

    service = ActionService(app)
    ok, msg = service.decide_action("abc12345", "approved")
    assert ok is False
    assert "expired" in msg
    assert app.pending_actions["abc12345"]["status"] == "expired"


def test_format_pending_actions_reports_terminal_summary():
    app = SimpleNamespace()
    app.name = "tester"
    app.current_room = "general"
    app.pending_actions = {
        "a1": {"action_id": "a1", "tool": "git_status", "summary": "x", "status": "pending", "command_preview": "git_status {}"},
        "a2": {"action_id": "a2", "tool": "git_diff", "summary": "y", "status": "expired", "command_preview": "git_diff {}"},
        "a3": {"action_id": "a3", "tool": "run_tests", "summary": "z", "status": "failed", "command_preview": "run_tests {}"},
    }
    service = ActionService(app)
    text = service.format_pending_actions()
    assert "Pending actions:" in text
    assert "Other actions: expired=1, failed=1" in text
    assert "/actions prune" in text


def test_prune_terminal_actions_removes_stale_entries():
    app = SimpleNamespace()
    app.name = "tester"
    app.current_room = "general"
    app.pending_actions = {
        "a1": {"action_id": "a1", "status": "pending"},
        "a2": {"action_id": "a2", "status": "expired"},
        "a3": {"action_id": "a3", "status": "failed"},
        "a4": {"action_id": "a4", "status": "denied"},
        "a5": {"action_id": "a5", "status": "completed"},
    }
    service = ActionService(app)
    removed = service.prune_terminal_actions()
    assert removed == 4
    assert set(app.pending_actions.keys()) == {"a1"}
