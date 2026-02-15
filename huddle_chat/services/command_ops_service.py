import shlex
from typing import TYPE_CHECKING, Any

from huddle_chat.event_helpers import emit_system_message
from huddle_chat.models import ChatEvent, MemoryPolicy, RoutingPolicy

if TYPE_CHECKING:
    from chat import ChatApp


class CommandOpsService:
    def __init__(self, app: "ChatApp"):
        self.app = app

    def _ensure_streaming_config(self) -> dict[str, Any]:
        streaming = self.app.ai_config.get("streaming")
        if not isinstance(streaming, dict):
            streaming = {}
            self.app.ai_config["streaming"] = streaming
        if not isinstance(streaming.get("enabled"), bool):
            streaming["enabled"] = False
        providers = streaming.get("providers")
        if not isinstance(providers, dict):
            providers = {}
            streaming["providers"] = providers
        for provider in ("gemini", "openai"):
            if not isinstance(providers.get(provider), bool):
                providers[provider] = True
        return streaming

    def get_streaming_summary(self) -> str:
        streaming = self._ensure_streaming_config()
        enabled = "on" if bool(streaming.get("enabled")) else "off"
        providers = streaming.get("providers", {})
        assert isinstance(providers, dict)
        provider_parts: list[str] = []
        for provider in ("gemini", "openai"):
            provider_enabled = "on" if bool(providers.get(provider, True)) else "off"
            provider_parts.append(f"{provider}={provider_enabled}")
        return f"streaming={enabled}; providers: {', '.join(provider_parts)}"

    def get_ai_provider_summary(self) -> str:
        providers = self.app.ai_config.get("providers", {})
        default_provider = str(self.app.ai_config.get("default_provider", "gemini"))
        parts: list[str] = [f"default={default_provider}", self.get_streaming_summary()]
        for provider in ("gemini", "openai"):
            data = providers.get(provider, {})
            if not isinstance(data, dict):
                data = {}
            configured = (
                "configured" if str(data.get("api_key", "")).strip() else "missing-key"
            )
            model = str(data.get("model", "")).strip() or "<unset>"
            parts.append(f"{provider}({configured}, model={model})")
        return "; ".join(parts)

    def handle_aiconfig_command(self, args: str) -> None:
        if not args.strip():
            emit_system_message(
                self.app, f"AI config: {self.get_ai_provider_summary()}"
            )
            return

        try:
            tokens = shlex.split(args)
        except ValueError:
            emit_system_message(
                self.app,
                self.app.help_service.format_guided_error(
                    problem="Invalid /aiconfig syntax.",
                    why="Unbalanced quotes or malformed token boundaries were detected.",
                    next_step="Run /help aiconfig, then retry your /aiconfig command.",
                ),
            )
            return
        if not tokens:
            emit_system_message(
                self.app, f"AI config: {self.get_ai_provider_summary()}"
            )
            return

        providers = {"gemini", "openai"}
        provider_first = len(tokens) >= 2 and tokens[0].strip().lower() in providers
        command_second = tokens[1].strip().lower() in {"set-key", "set-model"}
        if provider_first and command_second:
            tokens = [tokens[1], tokens[0], *tokens[2:]]

        action = tokens[0].lower()
        if action == "set-key" and len(tokens) >= 3:
            provider = tokens[1].strip().lower()
            key = tokens[2].strip()
            if provider not in ("gemini", "openai"):
                emit_system_message(self.app, "Unknown provider. Use gemini or openai.")
                return
            self.app.ai_config.setdefault("providers", {})
            provider_cfg = self.app.ai_config["providers"].setdefault(provider, {})
            if not isinstance(provider_cfg, dict):
                provider_cfg = {}
                self.app.ai_config["providers"][provider] = provider_cfg
            provider_cfg["api_key"] = key
            self.app.save_ai_config_data()
            emit_system_message(self.app, f"Saved API key for {provider}.")
            return

        if action == "set-model" and len(tokens) >= 3:
            provider = tokens[1].strip().lower()
            model = tokens[2].strip()
            if provider not in ("gemini", "openai"):
                emit_system_message(self.app, "Unknown provider. Use gemini or openai.")
                return
            self.app.ai_config.setdefault("providers", {})
            provider_cfg = self.app.ai_config["providers"].setdefault(provider, {})
            if not isinstance(provider_cfg, dict):
                provider_cfg = {}
                self.app.ai_config["providers"][provider] = provider_cfg
            provider_cfg["model"] = model
            self.app.save_ai_config_data()
            emit_system_message(self.app, f"Saved model for {provider}: {model}")
            return

        if action == "set-provider" and len(tokens) >= 2:
            provider = tokens[1].strip().lower()
            if provider not in ("gemini", "openai"):
                emit_system_message(self.app, "Unknown provider. Use gemini or openai.")
                return
            self.app.ai_config["default_provider"] = provider
            self.app.save_ai_config_data()
            emit_system_message(self.app, f"Default AI provider set to {provider}.")
            return

        if action == "streaming":
            providers_set = {"gemini", "openai"}
            streaming = self._ensure_streaming_config()
            provider_flags = streaming["providers"]

            if len(tokens) == 1 or (
                len(tokens) == 2 and tokens[1].strip().lower() == "status"
            ):
                emit_system_message(
                    self.app, f"AI config: {self.get_streaming_summary()}"
                )
                return

            if len(tokens) == 2 and tokens[1].strip().lower() in {"on", "off"}:
                enabled = tokens[1].strip().lower() == "on"
                streaming["enabled"] = enabled
                self.app.save_ai_config_data()
                emit_system_message(
                    self.app, f"Streaming set to {'on' if enabled else 'off'}."
                )
                return

            if len(tokens) == 3:
                provider = tokens[1].strip().lower()
                value = tokens[2].strip().lower()
                if provider in providers_set and value in {"on", "off"}:
                    provider_flags[provider] = value == "on"
                    self.app.save_ai_config_data()
                    emit_system_message(
                        self.app, f"Streaming for {provider} set to {value}."
                    )
                    return

            if len(tokens) == 4 and tokens[1].strip().lower() == "provider":
                provider = tokens[2].strip().lower()
                value = tokens[3].strip().lower()
                if provider in providers_set and value in {"on", "off"}:
                    provider_flags[provider] = value == "on"
                    self.app.save_ai_config_data()
                    emit_system_message(
                        self.app, f"Streaming for {provider} set to {value}."
                    )
                    return

            emit_system_message(
                self.app,
                "Usage: /aiconfig streaming [status|on|off|<provider> <on|off>|provider <provider> <on|off>]",
            )
            return

        emit_system_message(
            self.app,
            self.app.help_service.format_guided_error(
                problem="Unsupported /aiconfig command form.",
                why="Only documented /aiconfig subcommands are accepted.",
                next_step="Run /help aiconfig for supported forms and examples.",
            ),
        )

    def parse_share_selector(self, selector: str) -> list[ChatEvent]:
        if not self.app.message_events:
            return []
        selector = selector.strip()
        if "-" in selector:
            left, right = selector.split("-", 1)
            start = int(left)
            end = int(right)
            if start > end:
                start, end = end, start
            start = max(start, 1)
            end = min(end, len(self.app.message_events))
            return self.app.message_events[start - 1 : end]
        index = int(selector)
        if index < 1 or index > len(self.app.message_events):
            return []
        return [self.app.message_events[index - 1]]

    def handle_share_command(self, args: str) -> None:
        if not self.app.is_local_room():
            emit_system_message(
                self.app,
                self.app.help_service.format_guided_error(
                    problem="/share is only available in #ai-dm.",
                    why="Share copies selected local AI-DM messages into a shared room.",
                    next_step="Run /join ai-dm, then retry /share <target-room> <id|start-end>.",
                ),
            )
            return
        try:
            tokens = shlex.split(args)
        except ValueError:
            emit_system_message(self.app, "Invalid /share syntax. Check quotes.")
            return
        if len(tokens) < 2:
            emit_system_message(self.app, "Usage: /share <target-room> <id|start-end>")
            return
        target_room = self.app.sanitize_room_name(tokens[0])
        if self.app.is_local_room(target_room):
            emit_system_message(self.app, "Cannot share into local-only room.")
            return
        selector = tokens[1]
        try:
            selected_events = self.parse_share_selector(selector)
        except ValueError:
            emit_system_message(
                self.app, "Invalid selector. Use numeric id or range like 2-4."
            )
            return
        if not selected_events:
            emit_system_message(self.app, "No matching messages to share.")
            return

        shared_count = 0
        for event in selected_events:
            event_type = str(event.type or "chat")
            if event_type not in ("ai_prompt", "ai_response", "chat", "me", "system"):
                continue
            payload = self.app.build_event(event_type, str(event.text or ""))
            if event_type in ("ai_prompt", "ai_response"):
                payload.provider = event.provider or self.app.ai_config.get(
                    "default_provider", "ai"
                )
                payload.model = event.model or ""
            if self.app.write_to_file(payload, room=target_room):
                shared_count += 1
        emit_system_message(
            self.app, f"Shared {shared_count} message(s) from #ai-dm to #{target_room}."
        )

    def _parse_scopes(self, raw: str) -> list[str]:
        scopes: list[str] = []
        for part in raw.replace(",", " ").split():
            candidate = part.strip().lower()
            if candidate in {"private", "repo", "team"} and candidate not in scopes:
                scopes.append(candidate)
        return scopes

    def handle_agent_command(self, args: str) -> None:
        trimmed = args.strip()
        if not trimmed or trimmed.lower() in {"status", "help"}:
            emit_system_message(
                self.app,
                "Agent commands: /agent status, /agent list, /agent use <id>, "
                "/agent show [id], /agent memory <private,repo,team>, "
                "/agent route <task> <provider> <model>",
            )
            emit_system_message(self.app, self.app.agent_service.build_status_text())
            return

        try:
            tokens = shlex.split(trimmed)
        except ValueError:
            emit_system_message(
                self.app,
                self.app.help_service.format_guided_error(
                    problem="Invalid /agent syntax.",
                    why="Unbalanced quotes or malformed token boundaries were detected.",
                    next_step="Run /help agent, then retry the command.",
                ),
            )
            return
        if not tokens:
            emit_system_message(self.app, "Usage: /agent status")
            return

        action = tokens[0].strip().lower()
        if action == "list":
            profiles = self.app.agent_service.list_profiles()
            active_id = self.app.agent_service.get_active_profile_id()
            if not profiles:
                emit_system_message(self.app, "No agent profiles found.")
                return
            lines = ["Agent profiles:"]
            for profile in profiles:
                profile_id = str(profile.id).strip()
                marker = "*" if profile_id == active_id else " "
                name = str(profile.name).strip()
                lines.append(
                    f"{marker} {profile_id} ({name or 'unnamed'}) v{profile.version or 1}"
                )
            emit_system_message(self.app, "\n".join(lines))
            return

        if action == "use":
            if len(tokens) < 2:
                emit_system_message(self.app, "Usage: /agent use <profile-id>")
                return
            ok, msg = self.app.agent_service.set_active_profile(tokens[1])
            emit_system_message(self.app, msg)
            return

        if action == "show":
            profile_id = (
                tokens[1]
                if len(tokens) >= 2
                else self.app.agent_service.get_active_profile_id()
            )
            profile_data = self.app.agent_service.get_profile(profile_id)
            if profile_data is None:
                emit_system_message(
                    self.app,
                    f"Unknown agent profile '{self.app.sanitize_agent_id(profile_id)}'.",
                )
                return
            memory_policy = profile_data.memory_policy
            scopes = memory_policy.scopes
            routes = profile_data.routing_policy.routes
            route_count = len(routes)
            emit_system_message(
                self.app,
                f"Agent profile {profile_data.id}: "
                f"name={profile_data.name}, "
                f"memory_scopes={','.join(scopes) if scopes else 'team'}, "
                f"routes={route_count}, version={profile_data.version or 1}",
            )
            return

        if action == "memory":
            if len(tokens) < 2:
                emit_system_message(
                    self.app, "Usage: /agent memory <private,repo,team>"
                )
                return
            scopes = self._parse_scopes(" ".join(tokens[1:]))
            if not scopes:
                emit_system_message(
                    self.app, "Invalid scopes. Use any of: private, repo, team."
                )
                return
            active = self.app.agent_service.get_active_profile()
            active.memory_policy = MemoryPolicy(scopes=scopes)
            ok, msg = self.app.agent_service.save_profile(active, actor=self.app.name)
            if not ok:
                emit_system_message(self.app, msg)
                return
            emit_system_message(self.app, f"Updated memory scopes: {', '.join(scopes)}")
            return

        if action == "route":
            if len(tokens) < 4:
                emit_system_message(
                    self.app, "Usage: /agent route <task-class> <provider> <model>"
                )
                return
            task_class = tokens[1].strip()
            provider = tokens[2].strip().lower()
            model = tokens[3].strip()
            if provider not in {"gemini", "openai"}:
                emit_system_message(self.app, "Unknown provider. Use gemini or openai.")
                return
            active = self.app.agent_service.get_active_profile()
            if not active.routing_policy:
                active.routing_policy = RoutingPolicy()
            active.routing_policy.routes[task_class] = {
                "provider": provider,
                "model": model,
            }
            ok, msg = self.app.agent_service.save_profile(active, actor=self.app.name)
            if not ok:
                emit_system_message(self.app, msg)
                return
            emit_system_message(
                self.app, f"Route set: {task_class} -> {provider}:{model}"
            )
            return

        emit_system_message(
            self.app,
            self.app.help_service.format_guided_error(
                problem=f"Unknown /agent command '{action}'.",
                why="The subcommand is not part of the current /agent command set.",
                next_step="Run /help agent for supported subcommands and examples.",
            ),
        )

    def handle_toolpaths_command(self, args: str) -> None:
        trimmed = args.strip()
        if not trimmed or trimmed.lower() == "list":
            paths = self.app.get_tool_paths()
            if not paths:
                emit_system_message(self.app, "Tool paths: (none)")
                return
            emit_system_message(
                self.app, "Tool paths:\n" + "\n".join(f"- {path}" for path in paths)
            )
            return
        try:
            tokens = shlex.split(trimmed)
        except ValueError:
            emit_system_message(
                self.app,
                self.app.help_service.format_guided_error(
                    problem="Invalid /toolpaths syntax.",
                    why="Unbalanced quotes or malformed token boundaries were detected.",
                    next_step="Run /help tools, then retry /toolpaths command.",
                ),
            )
            return
        if not tokens:
            emit_system_message(
                self.app,
                self.app.help_service.format_guided_error(
                    problem="Missing /toolpaths subcommand.",
                    why="The command requires list/add/remove action.",
                    next_step="Run /help tools for valid /toolpaths usage.",
                ),
            )
            return
        action = tokens[0].lower()
        if action == "add":
            if len(tokens) < 2:
                emit_system_message(self.app, "Usage: /toolpaths add <absolute-path>")
                return
            ok, msg = self.app.add_tool_path(tokens[1])
            emit_system_message(self.app, msg)
            return
        if action == "remove":
            if len(tokens) < 2:
                emit_system_message(
                    self.app, "Usage: /toolpaths remove <absolute-path>"
                )
                return
            ok, msg = self.app.remove_tool_path(tokens[1])
            emit_system_message(self.app, msg)
            return
        emit_system_message(
            self.app,
            self.app.help_service.format_guided_error(
                problem=f"Unknown /toolpaths subcommand '{action}'.",
                why="Only list, add, and remove are supported.",
                next_step="Run /help tools for examples.",
            ),
        )
