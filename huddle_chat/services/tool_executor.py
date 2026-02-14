from __future__ import annotations

import subprocess
from pathlib import Path
from time import monotonic
from typing import TYPE_CHECKING, Any

from huddle_chat.constants import (
    ACTION_MAX_OUTPUT_PREVIEW_BYTES,
    TOOL_CALL_TIMEOUT_SECONDS,
)
from huddle_chat.models import ToolCallRequest, ToolCallResult

if TYPE_CHECKING:
    from chat import ChatApp


class ToolExecutorService:
    def __init__(self, app: "ChatApp"):
        self.app = app

    def _preview(self, text: str) -> tuple[str, bool]:
        if len(text) <= ACTION_MAX_OUTPUT_PREVIEW_BYTES:
            return text, False
        return text[:ACTION_MAX_OUTPUT_PREVIEW_BYTES], True

    def _allowed_roots(self) -> list[Path]:
        roots: list[Path] = [Path(str(self.app.base_dir)).resolve()]
        configured = getattr(self.app, "tool_paths", [])
        if isinstance(configured, list):
            for raw in configured:
                value = str(raw).strip()
                if not value:
                    continue
                try:
                    roots.append(Path(value).resolve())
                except OSError:
                    continue
        unique: list[Path] = []
        seen: set[str] = set()
        for root in roots:
            key = str(root).lower()
            if key in seen:
                continue
            seen.add(key)
            unique.append(root)
        return unique

    def _assert_allowed_path(self, target: Path) -> tuple[bool, str | None]:
        try:
            resolved = target.resolve()
        except OSError:
            return False, f"Invalid path: {target}"
        for root in self._allowed_roots():
            try:
                resolved.relative_to(root)
                return True, None
            except ValueError:
                continue
        return (
            False,
            "Path is outside configured tool roots. Use /toolpaths add <path>.",
        )

    def _run(self, args: list[str], timeout: int) -> tuple[int, str, int]:
        start = monotonic()
        proc = subprocess.run(
            args,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=max(1, timeout),
            cwd=self.app.base_dir,
            shell=False,
        )
        duration_ms = int((monotonic() - start) * 1000)
        output = (proc.stdout or "") + ("\n" + proc.stderr if proc.stderr else "")
        return proc.returncode, output.strip(), duration_ms

    def _venv_python(self) -> str:
        venv_dir = Path(str(self.app.base_dir)) / "venv"
        if self.app.is_windows():
            return str(venv_dir / "Scripts" / "python.exe")
        return str(venv_dir / "bin" / "python")

    def execute_tool(self, request: ToolCallRequest) -> ToolCallResult:
        tool = request["toolName"]
        args = request.get("arguments", {})
        timeout = int(args.get("maxDurationSec", TOOL_CALL_TIMEOUT_SECONDS))
        try:
            if tool == "search_repo":
                query = str(args.get("query", "")).strip()
                path = str(args.get("path", ".")).strip() or "."
                max_results = max(1, min(1000, int(args.get("maxResults", 200))))
                target = (Path(str(self.app.base_dir)) / path).resolve()
                ok, err = self._assert_allowed_path(target)
                if not ok:
                    return self._error_result(request, err or "Path denied", None, 0)
                cmd = [
                    "rg",
                    "--line-number",
                    "--column",
                    "--max-count",
                    str(max_results),
                    query,
                    str(target),
                ]
                code, output, duration = self._run(cmd, timeout)
                return self._text_result(request, code, output, duration)

            if tool == "list_files":
                path = str(args.get("path", ".")).strip() or "."
                target = (Path(str(self.app.base_dir)) / path).resolve()
                ok, err = self._assert_allowed_path(target)
                if not ok:
                    return self._error_result(request, err or "Path denied", None, 0)
                files = []
                max_results = max(1, min(5000, int(args.get("maxResults", 500))))
                for p in target.rglob("*"):
                    if p.is_file():
                        files.append(str(p))
                        if len(files) >= max_results:
                            break
                text = "\n".join(files) if files else "(no files)"
                return self._structured_result(
                    request, False, text, {"files": files}, 0, 0
                )

            if tool == "read_file":
                path = str(args.get("path", "")).strip()
                if not path:
                    return self._error_result(request, "Missing path", None, 0)
                target = Path(path)
                if not target.is_absolute():
                    target = (Path(str(self.app.base_dir)) / target).resolve()
                ok, err = self._assert_allowed_path(target)
                if not ok:
                    return self._error_result(request, err or "Path denied", None, 0)
                start_line = max(1, int(args.get("startLine", 1)))
                line_count = max(1, min(2000, int(args.get("lineCount", 200))))
                lines = target.read_text(
                    encoding="utf-8", errors="replace"
                ).splitlines()
                end = min(len(lines), start_line - 1 + line_count)
                selected = lines[start_line - 1 : end]
                text = "\n".join(selected)
                return self._structured_result(
                    request,
                    False,
                    text,
                    {
                        "path": str(target),
                        "startLine": start_line,
                        "endLine": end,
                        "truncated": end < len(lines),
                    },
                    0,
                    0,
                )

            if tool == "run_tests":
                cmd = (
                    ["cmd", "/c", "check.bat"]
                    if self.app.is_windows()
                    else ["./check.sh"]
                )
                code, output, duration = self._run(cmd, timeout)
                return self._text_result(request, code, output, duration)

            if tool == "run_lint":
                venv_python = self._venv_python()
                cmd = [
                    venv_python,
                    "-m",
                    "flake8",
                    "chat.py",
                    "huddle_chat",
                    "tests",
                ]
                code, output, duration = self._run(cmd, timeout)
                return self._text_result(request, code, output, duration)

            if tool == "run_typecheck":
                venv_python = self._venv_python()
                cmd = [venv_python, "-m", "mypy", "chat.py", "huddle_chat"]
                code, output, duration = self._run(cmd, timeout)
                return self._text_result(request, code, output, duration)

            if tool == "git_status":
                code, output, duration = self._run(
                    ["git", "status", "--short"], timeout
                )
                return self._text_result(request, code, output, duration)

            if tool == "git_diff":
                cmd = ["git", "diff"]
                path = str(args.get("path", "")).strip()
                if path:
                    cmd.extend(["--", path])
                code, output, duration = self._run(cmd, timeout)
                max_lines = max(50, min(4000, int(args.get("maxLines", 400))))
                lines = output.splitlines()
                if len(lines) > max_lines:
                    output = "\n".join(lines[:max_lines])
                return self._text_result(request, code, output, duration)
        except subprocess.TimeoutExpired:
            return self._error_result(request, "Tool execution timed out.", None, 0)
        except Exception as exc:
            return self._error_result(request, f"Tool execution failed: {exc}", None, 0)

        return self._error_result(request, f"Unknown tool '{tool}'.", None, 0)

    def _text_result(
        self, request: ToolCallRequest, exit_code: int, output: str, duration_ms: int
    ) -> ToolCallResult:
        preview, truncated = self._preview(output or "(no output)")
        return self._structured_result(
            request,
            exit_code != 0,
            preview,
            {},
            exit_code,
            duration_ms,
            truncated,
        )

    def _error_result(
        self,
        request: ToolCallRequest,
        message: str,
        exit_code: int | None,
        duration_ms: int,
    ) -> ToolCallResult:
        return self._structured_result(
            request,
            True,
            message,
            {},
            exit_code,
            duration_ms,
            False,
        )

    def _structured_result(
        self,
        request: ToolCallRequest,
        is_error: bool,
        text: str,
        data: dict[str, Any],
        exit_code: int | None,
        duration_ms: int,
        truncated: bool = False,
    ) -> ToolCallResult:
        content: list[dict[str, Any]] = [{"type": "text", "text": text}]
        if data:
            content.append({"type": "json", "json": data})
        return {
            "content": content,
            "isError": is_error,
            "meta": {
                "exitCode": exit_code,
                "durationMs": duration_ms,
                "truncated": truncated,
                "toolName": request["toolName"],
                "actionId": request["actionId"],
            },
        }
