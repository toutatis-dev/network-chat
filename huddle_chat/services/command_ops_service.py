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
