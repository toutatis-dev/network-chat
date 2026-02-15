from pathlib import Path
from types import SimpleNamespace

from huddle_chat.services.tool_executor import ToolExecutorService
from huddle_chat.models import ToolCallRequest


def _request(tool_name: str) -> ToolCallRequest:
    return ToolCallRequest(
        toolName=tool_name,
        arguments={},
        requestId="req-1",
        actionId="act-1",
        room="general",
        user="tester",
    )


def test_run_lint_and_typecheck_use_repo_venv_python(tmp_path: Path):
    app = SimpleNamespace(base_dir=str(tmp_path), is_windows=lambda: False)
    service = ToolExecutorService(app)

    commands: list[list[str]] = []

    def fake_run(args: list[str], timeout: int) -> tuple[int, str, int]:
        commands.append(args)
        return 0, "ok", 1

    service._run = fake_run  # type: ignore[method-assign]
    service.execute_tool(_request("run_lint"))
    service.execute_tool(_request("run_typecheck"))

    venv_python = str(tmp_path / "venv" / "bin" / "python")
    assert commands[0][0] == venv_python
    assert commands[0][1:3] == ["-m", "flake8"]
    assert commands[1][0] == venv_python
    assert commands[1][1:3] == ["-m", "mypy"]
