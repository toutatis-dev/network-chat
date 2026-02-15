from pathlib import Path

SERVICE_FILES = [
    "huddle_chat/services/action_service.py",
    "huddle_chat/services/ai_service.py",
    "huddle_chat/services/agent_service.py",
    "huddle_chat/services/command_ops_service.py",
    "huddle_chat/services/explain_service.py",
    "huddle_chat/services/help_service.py",
    "huddle_chat/services/memory_service.py",
    "huddle_chat/services/playbook_service.py",
]


def test_services_do_not_call_ui_entrypoints_directly() -> None:
    forbidden = [
        "self.app.append_system_message(",
        "self.app.refresh_output_from_events(",
        "self.app.rebuild_search_hits(",
        "self.app.controller.handle_input(",
        "self.app.write_to_file(",
    ]
    for rel_path in SERVICE_FILES:
        content = Path(rel_path).read_text(encoding="utf-8")
        for pattern in forbidden:
            assert pattern not in content, f"{rel_path} still uses '{pattern}'"
