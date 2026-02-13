import json
from datetime import datetime
from typing import TYPE_CHECKING, cast

from huddle_chat.constants import DEFAULT_AGENT_PROFILE_ID
from huddle_chat.models import AgentProfile, MemoryPolicy, RoutingPolicy, ToolPolicy

if TYPE_CHECKING:
    from chat import ChatApp


class AgentService:
    def __init__(self, app: "ChatApp"):
        self.app = app

    def get_default_profile(self) -> AgentProfile:
        return {
            "id": DEFAULT_AGENT_PROFILE_ID,
            "name": "Default Agent",
            "description": "Balanced general assistant profile.",
            "system_prompt": "You are a pragmatic AI assistant for collaborative chat and planning.",
            "tool_policy": {
                "mode": "scoped_allowlist",
                "require_approval": True,
                "allowed_tools": ["search", "read", "tests", "lint", "mypy"],
            },
            "memory_policy": {"scopes": ["private", "repo", "team"]},
            "routing_policy": {
                "routes": {
                    "chat_general": {"provider": "gemini", "model": "gemini-2.5-flash"},
                    "memory_rerank": {"provider": "openai", "model": "gpt-4o-mini"},
                    "code_analysis": {"provider": "openai", "model": "gpt-4o-mini"},
                }
            },
            "created_by": "system",
            "updated_by": "system",
            "updated_at": datetime.now().isoformat(timespec="seconds"),
            "version": 1,
        }

    def ensure_default_profile(self) -> None:
        self.app.ensure_agent_paths()
        profile_path = self.app.get_agent_profile_path(DEFAULT_AGENT_PROFILE_ID)
        if profile_path.exists():
            return
        default = self.get_default_profile()
        profile_path.write_text(json.dumps(default, indent=2), encoding="utf-8")
        self.append_agent_audit("create", default["id"], "system")

    def list_profiles(self) -> list[AgentProfile]:
        self.ensure_default_profile()
        profiles: list[AgentProfile] = []
        for path in sorted(self.app.get_agent_profiles_dir().glob("*.json")):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if isinstance(data, dict) and str(data.get("id", "")).strip():
                profiles.append(cast(AgentProfile, data))
        return profiles

    def get_profile(self, profile_id: str) -> AgentProfile | None:
        safe_id = self.app.sanitize_agent_id(profile_id)
        path = self.app.get_agent_profile_path(safe_id)
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        if isinstance(data, dict):
            return cast(AgentProfile, data)
        return None

    def get_active_profile_id(self) -> str:
        profile_id = str(
            getattr(self.app, "active_agent_profile_id", DEFAULT_AGENT_PROFILE_ID)
        ).strip()
        if not profile_id:
            return DEFAULT_AGENT_PROFILE_ID
        return self.app.sanitize_agent_id(profile_id)

    def get_active_profile(self) -> AgentProfile:
        active_id = self.get_active_profile_id()
        profile = self.get_profile(active_id)
        if profile is not None:
            return profile
        return self.get_default_profile()

    def set_active_profile(self, profile_id: str) -> tuple[bool, str]:
        safe_id = self.app.sanitize_agent_id(profile_id)
        if self.get_profile(safe_id) is None:
            return False, f"Unknown agent profile '{safe_id}'."
        self.app.active_agent_profile_id = safe_id
        self.app.save_config()
        return True, f"Active agent set to '{safe_id}'."

    def append_agent_audit(self, action: str, profile_id: str, actor: str) -> None:
        row = {
            "ts": datetime.now().isoformat(timespec="seconds"),
            "action": action,
            "profile_id": profile_id,
            "actor": actor,
        }
        self.app.append_jsonl_row(self.app.get_agent_audit_file(), row)

    def upsert_profile(
        self,
        *,
        profile_id: str,
        name: str,
        description: str,
        system_prompt: str,
        actor: str,
    ) -> tuple[bool, str]:
        safe_id = self.app.sanitize_agent_id(profile_id)
        existing = self.get_profile(safe_id) or cast(AgentProfile, {})
        version = int(existing.get("version", 0)) + 1
        default_profile = self.get_default_profile()
        tool_policy = existing.get("tool_policy")
        if not isinstance(tool_policy, dict):
            tool_policy = default_profile.get("tool_policy", {})
        memory_policy = existing.get("memory_policy")
        if not isinstance(memory_policy, dict):
            memory_policy = default_profile.get("memory_policy", {})
        routing_policy = existing.get("routing_policy")
        if not isinstance(routing_policy, dict):
            routing_policy = default_profile.get("routing_policy", {})
        profile: AgentProfile = {
            "id": safe_id,
            "name": name.strip() or safe_id,
            "description": description.strip(),
            "system_prompt": system_prompt.strip(),
            "tool_policy": cast(ToolPolicy, tool_policy),
            "memory_policy": cast(MemoryPolicy, memory_policy),
            "routing_policy": cast(RoutingPolicy, routing_policy),
            "created_by": str(existing.get("created_by", actor)),
            "updated_by": actor,
            "updated_at": datetime.now().isoformat(timespec="seconds"),
            "version": version,
        }
        path = self.app.get_agent_profile_path(safe_id)
        try:
            path.write_text(json.dumps(profile, indent=2), encoding="utf-8")
        except OSError as exc:
            return False, f"Failed to save profile: {exc}"
        self.append_agent_audit("upsert", safe_id, actor)
        return True, f"Saved profile '{safe_id}' (v{version})."

    def save_profile(self, profile: AgentProfile, actor: str) -> tuple[bool, str]:
        profile_id = self.app.sanitize_agent_id(str(profile.get("id", "")))
        if not profile_id:
            return False, "Profile id is required."
        existing = self.get_profile(profile_id) or cast(AgentProfile, {})
        version = int(existing.get("version", profile.get("version", 0) or 0)) + 1
        profile["id"] = profile_id
        profile["version"] = version
        profile["updated_by"] = actor
        profile["updated_at"] = datetime.now().isoformat(timespec="seconds")
        if "created_by" not in profile:
            profile["created_by"] = str(existing.get("created_by", actor))
        path = self.app.get_agent_profile_path(profile_id)
        try:
            path.write_text(json.dumps(profile, indent=2), encoding="utf-8")
        except OSError as exc:
            return False, f"Failed to save profile: {exc}"
        self.append_agent_audit("save", profile_id, actor)
        return True, f"Saved profile '{profile_id}' (v{version})."

    def build_status_text(self) -> str:
        profile = self.get_active_profile()
        memory_policy = profile.get("memory_policy", {})
        scopes = []
        if isinstance(memory_policy, dict):
            scopes = memory_policy.get("scopes", [])
        scope_text = (
            ", ".join(str(x) for x in scopes) if isinstance(scopes, list) else ""
        )
        return (
            f"Agent: {profile.get('id', DEFAULT_AGENT_PROFILE_ID)} | "
            f"name={profile.get('name', '')} | "
            f"memory_scopes={scope_text or 'team'} | "
            f"version={profile.get('version', 1)}"
        )
