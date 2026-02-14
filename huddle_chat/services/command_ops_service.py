import shlex
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from chat import ChatApp


class CommandOpsService:
    def __init__(self, app: "ChatApp"):
        self.app = app

    def get_ai_provider_summary(self) -> str:
        providers = self.app.ai_config.get("providers", {})
        default_provider = str(self.app.ai_config.get("default_provider", "gemini"))
        parts: list[str] = [f"default={default_provider}"]
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
            self.app.append_system_message(
                f"AI config: {self.get_ai_provider_summary()}"
            )
            return

        try:
            tokens = shlex.split(args)
        except ValueError:
            self.app.append_system_message("Invalid /aiconfig syntax. Check quotes.")
            return
        if not tokens:
            self.app.append_system_message(
                f"AI config: {self.get_ai_provider_summary()}"
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
                self.app.append_system_message(
                    "Unknown provider. Use gemini or openai."
                )
                return
            self.app.ai_config.setdefault("providers", {})
            provider_cfg = self.app.ai_config["providers"].setdefault(provider, {})
            if not isinstance(provider_cfg, dict):
                provider_cfg = {}
                self.app.ai_config["providers"][provider] = provider_cfg
            provider_cfg["api_key"] = key
            self.app.save_ai_config_data()
            self.app.append_system_message(f"Saved API key for {provider}.")
            return

        if action == "set-model" and len(tokens) >= 3:
            provider = tokens[1].strip().lower()
            model = tokens[2].strip()
            if provider not in ("gemini", "openai"):
                self.app.append_system_message(
                    "Unknown provider. Use gemini or openai."
                )
                return
            self.app.ai_config.setdefault("providers", {})
            provider_cfg = self.app.ai_config["providers"].setdefault(provider, {})
            if not isinstance(provider_cfg, dict):
                provider_cfg = {}
                self.app.ai_config["providers"][provider] = provider_cfg
            provider_cfg["model"] = model
            self.app.save_ai_config_data()
            self.app.append_system_message(f"Saved model for {provider}: {model}")
            return

        if action == "set-provider" and len(tokens) >= 2:
            provider = tokens[1].strip().lower()
            if provider not in ("gemini", "openai"):
                self.app.append_system_message(
                    "Unknown provider. Use gemini or openai."
                )
                return
            self.app.ai_config["default_provider"] = provider
            self.app.save_ai_config_data()
            self.app.append_system_message(f"Default AI provider set to {provider}.")
            return

        self.app.append_system_message(
            "Usage: /aiconfig [set-key <provider> <key> | set-model <provider> <model> | set-provider <provider>] "
            "(also accepts: <provider> set-key <key>, <provider> set-model <model>)"
        )

    def parse_share_selector(self, selector: str) -> list[dict[str, Any]]:
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
            self.app.append_system_message("Use /share only inside #ai-dm.")
            return
        try:
            tokens = shlex.split(args)
        except ValueError:
            self.app.append_system_message("Invalid /share syntax. Check quotes.")
            return
        if len(tokens) < 2:
            self.app.append_system_message("Usage: /share <target-room> <id|start-end>")
            return
        target_room = self.app.sanitize_room_name(tokens[0])
        if self.app.is_local_room(target_room):
            self.app.append_system_message("Cannot share into local-only room.")
            return
        selector = tokens[1]
        try:
            selected_events = self.parse_share_selector(selector)
        except ValueError:
            self.app.append_system_message(
                "Invalid selector. Use numeric id or range like 2-4."
            )
            return
        if not selected_events:
            self.app.append_system_message("No matching messages to share.")
            return

        shared_count = 0
        for event in selected_events:
            event_type = str(event.get("type", "chat"))
            if event_type not in ("ai_prompt", "ai_response", "chat", "me", "system"):
                continue
            payload = self.app.build_event(event_type, str(event.get("text", "")))
            if event_type in ("ai_prompt", "ai_response"):
                payload["provider"] = event.get(
                    "provider", self.app.ai_config.get("default_provider", "ai")
                )
                payload["model"] = event.get("model", "")
            if self.app.write_to_file(payload, room=target_room):
                shared_count += 1
        self.app.append_system_message(
            f"Shared {shared_count} message(s) from #ai-dm to #{target_room}."
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
            self.app.append_system_message(
                "Agent commands: /agent status, /agent list, /agent use <id>, "
                "/agent show [id], /agent memory <private,repo,team>, "
                "/agent route <task> <provider> <model>"
            )
            self.app.append_system_message(self.app.get_agent_status_text())
            return

        try:
            tokens = shlex.split(trimmed)
        except ValueError:
            self.app.append_system_message("Invalid /agent syntax. Check quotes.")
            return
        if not tokens:
            self.app.append_system_message("Usage: /agent status")
            return

        action = tokens[0].strip().lower()
        if action == "list":
            profiles = self.app.agent_service.list_profiles()
            active_id = self.app.agent_service.get_active_profile_id()
            if not profiles:
                self.app.append_system_message("No agent profiles found.")
                return
            lines = ["Agent profiles:"]
            for profile in profiles:
                profile_id = str(profile.get("id", "")).strip()
                marker = "*" if profile_id == active_id else " "
                name = str(profile.get("name", "")).strip()
                lines.append(
                    f"{marker} {profile_id} ({name or 'unnamed'}) v{profile.get('version', 1)}"
                )
            self.app.append_system_message("\n".join(lines))
            return

        if action == "use":
            if len(tokens) < 2:
                self.app.append_system_message("Usage: /agent use <profile-id>")
                return
            ok, msg = self.app.agent_service.set_active_profile(tokens[1])
            self.app.append_system_message(msg)
            return

        if action == "show":
            profile_id = (
                tokens[1]
                if len(tokens) >= 2
                else self.app.agent_service.get_active_profile_id()
            )
            profile_data: Any = self.app.agent_service.get_profile(profile_id)
            if profile_data is None:
                self.app.append_system_message(
                    f"Unknown agent profile '{self.app.sanitize_agent_id(profile_id)}'."
                )
                return
            memory_policy = profile_data.get("memory_policy", {})
            scopes: list[str] = []
            if isinstance(memory_policy, dict):
                raw_scopes = memory_policy.get("scopes", [])
                if isinstance(raw_scopes, list):
                    scopes = [str(item) for item in raw_scopes]
            routes = profile_data.get("routing_policy", {})
            route_count = 0
            if isinstance(routes, dict):
                route_map = routes.get("routes", {})
                if isinstance(route_map, dict):
                    route_count = len(route_map)
            self.app.append_system_message(
                f"Agent profile {profile_data.get('id', '?')}: "
                f"name={profile_data.get('name', '')}, "
                f"memory_scopes={','.join(scopes) if scopes else 'team'}, "
                f"routes={route_count}, version={profile_data.get('version', 1)}"
            )
            return

        if action == "memory":
            if len(tokens) < 2:
                self.app.append_system_message(
                    "Usage: /agent memory <private,repo,team>"
                )
                return
            scopes = self._parse_scopes(" ".join(tokens[1:]))
            if not scopes:
                self.app.append_system_message(
                    "Invalid scopes. Use any of: private, repo, team."
                )
                return
            active = self.app.agent_service.get_active_profile()
            active["memory_policy"] = {"scopes": scopes}
            ok, msg = self.app.agent_service.save_profile(active, actor=self.app.name)
            if not ok:
                self.app.append_system_message(msg)
                return
            self.app.append_system_message(
                f"Updated memory scopes: {', '.join(scopes)}"
            )
            return

        if action == "route":
            if len(tokens) < 4:
                self.app.append_system_message(
                    "Usage: /agent route <task-class> <provider> <model>"
                )
                return
            task_class = tokens[1].strip()
            provider = tokens[2].strip().lower()
            model = tokens[3].strip()
            if provider not in {"gemini", "openai"}:
                self.app.append_system_message(
                    "Unknown provider. Use gemini or openai."
                )
                return
            active = self.app.agent_service.get_active_profile()
            active_any: Any = active
            routing_policy_any: Any = active_any.get("routing_policy", {})
            if not isinstance(routing_policy_any, dict):
                routing_policy_any = {}
            route_map_any: Any = routing_policy_any.get("routes", {})
            if not isinstance(route_map_any, dict):
                route_map_any = {}
            route_map_any[task_class] = {"provider": provider, "model": model}
            routing_policy_any["routes"] = route_map_any
            active_any["routing_policy"] = routing_policy_any
            ok, msg = self.app.agent_service.save_profile(active, actor=self.app.name)
            if not ok:
                self.app.append_system_message(msg)
                return
            self.app.append_system_message(
                f"Route set: {task_class} -> {provider}:{model}"
            )
            return

        self.app.append_system_message("Unknown /agent command. Use /agent help.")

    def handle_toolpaths_command(self, args: str) -> None:
        trimmed = args.strip()
        if not trimmed or trimmed.lower() == "list":
            paths = self.app.get_tool_paths()
            if not paths:
                self.app.append_system_message("Tool paths: (none)")
                return
            self.app.append_system_message(
                "Tool paths:\n" + "\n".join(f"- {path}" for path in paths)
            )
            return
        try:
            tokens = shlex.split(trimmed)
        except ValueError:
            self.app.append_system_message("Invalid /toolpaths syntax. Check quotes.")
            return
        if not tokens:
            self.app.append_system_message(
                "Usage: /toolpaths <list|add <path>|remove <path>>"
            )
            return
        action = tokens[0].lower()
        if action == "add":
            if len(tokens) < 2:
                self.app.append_system_message("Usage: /toolpaths add <absolute-path>")
                return
            ok, msg = self.app.add_tool_path(tokens[1])
            self.app.append_system_message(msg)
            return
        if action == "remove":
            if len(tokens) < 2:
                self.app.append_system_message(
                    "Usage: /toolpaths remove <absolute-path>"
                )
                return
            ok, msg = self.app.remove_tool_path(tokens[1])
            self.app.append_system_message(msg)
            return
        self.app.append_system_message(
            "Usage: /toolpaths <list|add <path>|remove <path>>"
        )
