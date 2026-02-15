from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

from huddle_chat.constants import (
    AI_CONFIG_FILE,
    LOCAL_CHAT_ROOT,
    CONFIG_FILE,
    ONBOARDING_STATE_FILE,
)

logger = logging.getLogger(__name__)


class ConfigRepository:
    def load_config(self) -> dict[str, Any]:
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        return data
            except (OSError, json.JSONDecodeError) as exc:
                logger.warning("Failed to load config from %s: %s", CONFIG_FILE, exc)
        return {}

    def save_config(self, payload: dict[str, Any]) -> None:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(payload, f)

    def load_ai_config(self, default: dict[str, Any]) -> dict[str, Any]:
        path = Path(AI_CONFIG_FILE)
        if not path.exists():
            return default
        try:
            with open(path, "r", encoding="utf-8") as f:
                loaded = json.load(f)
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("Failed to load AI config from %s: %s", AI_CONFIG_FILE, exc)
            return default

        if not isinstance(loaded, dict):
            return default
        providers = loaded.get("providers", {})
        if not isinstance(providers, dict):
            providers = {}
        merged = default
        for provider_name in ("gemini", "openai"):
            existing = providers.get(provider_name, {})
            if isinstance(existing, dict):
                merged["providers"][provider_name].update(existing)
        default_provider = str(loaded.get("default_provider", "")).strip().lower()
        if default_provider in merged["providers"]:
            merged["default_provider"] = default_provider
        loaded_streaming = loaded.get("streaming", {})
        if isinstance(loaded_streaming, dict):
            loaded_enabled = loaded_streaming.get("enabled")
            if isinstance(loaded_enabled, bool):
                merged["streaming"]["enabled"] = loaded_enabled
            loaded_streaming_providers = loaded_streaming.get("providers", {})
            if isinstance(loaded_streaming_providers, dict):
                for provider_name in ("gemini", "openai"):
                    provider_enabled = loaded_streaming_providers.get(provider_name)
                    if isinstance(provider_enabled, bool):
                        merged["streaming"]["providers"][
                            provider_name
                        ] = provider_enabled
        return merged

    def save_ai_config(self, payload: dict[str, Any]) -> None:
        try:
            os.makedirs(LOCAL_CHAT_ROOT, exist_ok=True)
            with open(AI_CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2)
        except OSError as exc:
            logger.warning("Failed saving AI config: %s", exc)

    def get_onboarding_state_path(self) -> Path:
        return Path(ONBOARDING_STATE_FILE)
