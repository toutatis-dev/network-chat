import re
from typing import TYPE_CHECKING

from prompt_toolkit.completion import Completer, Completion
from prompt_toolkit.lexers import Lexer

from huddle_chat.constants import THEMES

if TYPE_CHECKING:
    from chat import ChatApp


class SlashCompleter(Completer):
    def __init__(self, app_ref: "ChatApp"):
        self.app_ref = app_ref
        self.model_hints = {
            "gemini": ["gemini-2.5-flash", "gemini-2.5-pro"],
            "openai": ["gpt-4o-mini", "gpt-4o", "gpt-5-mini"],
        }

    def _yield_candidates(
        self, prefix: str, options: list[str], metas: dict[str, str] | None = None
    ):
        metas = metas or {}
        for value in options:
            if value.startswith(prefix):
                yield Completion(
                    value,
                    start_position=-len(prefix),
                    display=value,
                    display_meta=metas.get(value, ""),
                )

    def _provider_names(self) -> list[str]:
        ai_config = getattr(self.app_ref, "ai_config", {})
        providers = (
            ai_config.get("providers", {}) if isinstance(ai_config, dict) else {}
        )
        if isinstance(providers, dict):
            names = [str(name).strip().lower() for name in providers.keys() if name]
            if names:
                return sorted(set(names))
        return ["gemini", "openai"]

    def _provider_for_ai_tokens(self, tokens: list[str]) -> str | None:
        if "--provider" in tokens:
            idx = tokens.index("--provider")
            if idx + 1 < len(tokens):
                return tokens[idx + 1].strip().lower()
        return None

    def _complete_ai_command(self, text: str):
        tokens = text.split()
        trailing_space = text.endswith(" ")
        if len(tokens) == 1 and not trailing_space:
            return self._yield_candidates(text, ["/ai"])
        if len(tokens) == 1 and trailing_space:
            return self._yield_candidates(
                "",
                [
                    "status",
                    "cancel",
                    "--provider",
                    "--model",
                    "--private",
                    "--no-memory",
                    "--memory-scope",
                    "--act",
                ],
                {
                    "status": "Show active AI request",
                    "cancel": "Cancel active AI request",
                    "--provider": "Override provider for this call",
                    "--model": "Override model for this call",
                    "--private": "Run AI privately in ai-dm",
                    "--no-memory": "Disable shared memory for this call",
                    "--memory-scope": "Limit memory scopes: private,repo,team",
                    "--act": "Ask AI to propose approval-gated tool actions",
                },
            )

        current = "" if trailing_space else tokens[-1]
        values = tokens if trailing_space else tokens[:-1]
        prev = values[-1] if values else ""

        if prev == "--provider":
            return self._yield_candidates(current, self._provider_names())
        if prev == "--model":
            provider = self._provider_for_ai_tokens(tokens)
            hints = self.model_hints.get(provider or "", [])
            if not hints:
                hints = self.model_hints.get("gemini", []) + self.model_hints.get(
                    "openai", []
                )
            return self._yield_candidates(current, hints)
        if prev == "--memory-scope":
            return self._yield_candidates(current, ["private", "repo", "team"])

        if len(tokens) == 2 and not trailing_space:
            return self._yield_candidates(
                current,
                [
                    "status",
                    "cancel",
                    "--provider",
                    "--model",
                    "--private",
                    "--no-memory",
                    "--memory-scope",
                    "--act",
                ],
                {
                    "status": "Show active AI request",
                    "cancel": "Cancel active AI request",
                    "--provider": "Override provider for this call",
                    "--model": "Override model for this call",
                    "--private": "Run AI privately in ai-dm",
                    "--no-memory": "Disable shared memory for this call",
                    "--memory-scope": "Limit memory scopes: private,repo,team",
                    "--act": "Ask AI to propose approval-gated tool actions",
                },
            )
        return []

    def _complete_aiconfig_command(self, text: str):
        tokens = text.split()
        trailing_space = text.endswith(" ")
        providers = self._provider_names()
        subcommands = ["set-key", "set-model", "set-provider"]

        if len(tokens) == 1 and not trailing_space:
            return self._yield_candidates(text, ["/aiconfig"])
        if len(tokens) == 1 and trailing_space:
            return self._yield_candidates(
                "",
                subcommands + providers,
                {
                    "set-key": "Set provider API key",
                    "set-model": "Set default model for provider",
                    "set-provider": "Set default active provider",
                },
            )

        current = "" if trailing_space else tokens[-1]
        values = tokens if trailing_space else tokens[:-1]
        if len(values) == 1:
            return self._yield_candidates(current, subcommands + providers)

        first = values[1] if len(values) > 1 else ""
        second = values[2] if len(values) > 2 else ""

        if first in ("set-key", "set-model", "set-provider"):
            if len(values) == 2:
                return self._yield_candidates(current, providers)
            if first == "set-model" and len(values) == 3:
                provider = values[2].strip().lower()
                return self._yield_candidates(
                    current, self.model_hints.get(provider, [])
                )
            return []

        if first in providers:
            if len(values) == 2:
                return self._yield_candidates(current, ["set-key", "set-model"])
            if second == "set-model" and len(values) == 3:
                provider = first
                return self._yield_candidates(
                    current, self.model_hints.get(provider, [])
                )
            return []
        return []

    def _complete_memory_command(self, text: str):
        tokens = text.split()
        trailing_space = text.endswith(" ")
        subcommands = [
            "add",
            "confirm",
            "cancel",
            "edit",
            "show-draft",
            "list",
            "search",
            "scope",
            "help",
        ]
        if len(tokens) == 1 and not trailing_space:
            return self._yield_candidates(text, ["/memory"])
        if len(tokens) == 1 and trailing_space:
            return self._yield_candidates("", subcommands)

        current = "" if trailing_space else tokens[-1]
        values = tokens if trailing_space else tokens[:-1]
        if len(values) == 1:
            return self._yield_candidates(current, subcommands)
        if len(values) == 2 and values[1] == "edit":
            return self._yield_candidates(
                current, ["summary", "topic", "confidence", "source"]
            )
        if len(values) == 3 and values[1] == "edit" and values[2] == "confidence":
            return self._yield_candidates(current, ["low", "med", "high"])
        if len(values) == 2 and values[1] == "scope":
            return self._yield_candidates(current, ["private", "repo", "team"])
        if len(values) == 3 and values[1] == "edit" and values[2] == "scope":
            return self._yield_candidates(current, ["private", "repo", "team"])
        return []

    def _complete_agent_command(self, text: str):
        tokens = text.split()
        trailing_space = text.endswith(" ")
        subcommands = ["status", "list", "use", "show", "memory", "route"]
        if len(tokens) == 1 and not trailing_space:
            return self._yield_candidates(text, ["/agent"])
        if len(tokens) == 1 and trailing_space:
            return self._yield_candidates("", subcommands)

        current = "" if trailing_space else tokens[-1]
        values = tokens if trailing_space else tokens[:-1]
        if len(values) == 1:
            return self._yield_candidates(current, subcommands)
        if len(values) == 2 and values[1] == "memory":
            return self._yield_candidates(current, ["private,repo,team", "team"])
        if len(values) == 2 and values[1] == "route":
            return self._yield_candidates(
                current, ["chat_general", "code_analysis", "memory_rerank"]
            )
        if len(values) == 3 and values[1] == "route":
            return self._yield_candidates(current, self._provider_names())
        return []

    def _complete_toolpaths_command(self, text: str):
        tokens = text.split()
        trailing_space = text.endswith(" ")
        if len(tokens) == 1 and not trailing_space:
            return self._yield_candidates(text, ["/toolpaths"])
        current = "" if trailing_space else tokens[-1]
        values = tokens if trailing_space else tokens[:-1]
        if len(values) == 1:
            return self._yield_candidates(current, ["list", "add", "remove"])
        return []

    def get_completions(self, document, complete_event):
        text = document.text_before_cursor
        if re.match(r"^/aiconfig(\s|$)", text):
            yield from self._complete_aiconfig_command(text)
            return

        if re.match(r"^/memory(\s|$)", text):
            yield from self._complete_memory_command(text)
            return

        if re.match(r"^/agent(\s|$)", text):
            yield from self._complete_agent_command(text)
            return

        if re.match(r"^/toolpaths(\s|$)", text):
            yield from self._complete_toolpaths_command(text)
            return

        if re.match(r"^/ai(\s|$)", text):
            yield from self._complete_ai_command(text)
            return

        if text.startswith("/theme "):
            prefix = text[7:].lower()
            for theme_name in THEMES.keys():
                if theme_name.startswith(prefix):
                    yield Completion(
                        theme_name, start_position=-len(prefix), display=theme_name
                    )
            return

        if text.startswith("/join "):
            prefix = text[6:].lower()
            for room_name in self.app_ref.list_rooms():
                if room_name.startswith(prefix):
                    yield Completion(
                        room_name, start_position=-len(prefix), display=room_name
                    )
            return

        if text.startswith("/"):
            commands = [
                ("/status", "Set your status (e.g. /status Busy)"),
                ("/theme", "Change color theme (e.g. /theme nord)"),
                ("/me", "Perform an action (e.g. /me waves)"),
                ("/setpath", "Change the chat server path"),
                ("/join", "Join or create room (e.g. /join dev)"),
                ("/rooms", "List available rooms"),
                ("/room", "Show current room"),
                ("/search", "Search messages in current room"),
                ("/next", "Jump to next search match"),
                ("/prev", "Jump to previous search match"),
                ("/clearsearch", "Clear active search"),
                ("/ai", "Ask AI in current room or private mode"),
                ("/ask", "Alias for /ai"),
                ("/aiproviders", "List configured AI providers"),
                ("/aiconfig", "Manage local AI config"),
                ("/agent", "Show/update agent profile and routing"),
                ("/memory", "Draft and manage shared memory entries"),
                ("/share", "Share AI DM messages into a room"),
                ("/actions", "Show pending approval actions"),
                ("/action", "Show action details by id"),
                ("/approve", "Approve an action by id"),
                ("/deny", "Deny an action by id"),
                ("/toolpaths", "Manage allowed external tool paths"),
                ("/exit", "Quit the application"),
                ("/clear", "Clear local chat history"),
            ]
            word = text.lower()
            for cmd, desc in commands:
                if cmd.startswith(word):
                    yield Completion(
                        cmd, start_position=-len(word), display=cmd, display_meta=desc
                    )
            return

        mention_context = self.app_ref.get_mention_context(text)
        if mention_context is not None:
            prefix, start_position = mention_context
            prefix_cf = prefix.casefold()
            candidates = self.app_ref.get_mention_candidates()
            ranked = sorted(
                candidates,
                key=lambda item: (
                    not item["name"].casefold().startswith(prefix_cf),
                    item["name"].casefold(),
                ),
            )
            for item in ranked:
                name_cf = item["name"].casefold()
                if prefix and prefix_cf not in name_cf:
                    continue
                meta = f"[{item['status']}]" if item["status"] else "online"
                yield Completion(
                    f"{item['name']} ",
                    start_position=start_position,
                    display=item["name"],
                    display_meta=meta,
                )


class ChatLexer(Lexer):
    def __init__(self, app_ref: "ChatApp"):
        self.app_ref = app_ref

    def lex_document(self, document):
        def get_line_tokens(line_num):
            try:
                line_text = document.lines[line_num]
                return self.app_ref.lex_line(line_text)
            except Exception:
                return [("", document.lines[line_num])]

        return get_line_tokens
