import json
from datetime import datetime
from typing import TYPE_CHECKING

from huddle_chat.constants import DEFAULT_AGENT_PROFILE_ID
from huddle_chat.models import AgentProfile, MemoryPolicy, RoutingPolicy, ToolPolicy

if TYPE_CHECKING:
    from chat import ChatApp


class AgentService:
    def __init__(self, app: "ChatApp"):
        self.app = app

    def get_default_profile(self) -> AgentProfile:
        return AgentProfile(
            id=DEFAULT_AGENT_PROFILE_ID,
            name="Default Agent",
            description="Balanced general assistant profile.",
            system_prompt="You are a pragmatic AI assistant for collaborative chat and planning.",
            tool_policy=ToolPolicy(
                mode="scoped_allowlist",
                require_approval=True,
                allowed_tools=[
                    "search_repo",
                    "list_files",
                    "read_file",
                    "run_tests",
                    "run_lint",
                    "run_typecheck",
                    "git_status",
                    "git_diff",
                ],
            ),
            memory_policy=MemoryPolicy(scopes=["private", "repo", "team"]),
            routing_policy=RoutingPolicy(
                routes={
                    "chat_general": {"provider": "gemini", "model": "gemini-2.5-flash"},
                    "memory_rerank": {"provider": "openai", "model": "gpt-4o-mini"},
                    "code_analysis": {"provider": "openai", "model": "gpt-4o-mini"},
                }
            ),
            created_by="system",
            updated_by="system",
            updated_at=datetime.now().isoformat(timespec="seconds"),
            version=1,
        )

    def ensure_default_profile(self) -> None:
        repo = getattr(self.app, "agent_repository", None)
        if repo is not None:
            repo.ensure_agent_paths()
            profile_path = repo.get_agent_profile_path(DEFAULT_AGENT_PROFILE_ID)
        else:
            self.app.ensure_agent_paths()
            profile_path = self.app.get_agent_profile_path(DEFAULT_AGENT_PROFILE_ID)
        if profile_path.exists():
            return
        default = self.get_default_profile()
        profile_path.write_text(
            json.dumps(default.to_dict(), indent=2), encoding="utf-8"
        )
        self.append_agent_audit("create", default.id, "system")

    def list_profiles(self) -> list[AgentProfile]:
        self.ensure_default_profile()
        profiles: list[AgentProfile] = []
        repo = getattr(self.app, "agent_repository", None)
        profiles_dir = (
            repo.get_agent_profiles_dir()
            if repo is not None
            else self.app.get_agent_profiles_dir()
        )
        for path in sorted(profiles_dir.glob("*.json")):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if isinstance(data, dict) and str(data.get("id", "")).strip():
                try:
                    profiles.append(AgentProfile(**data))
                except Exception:
                    pass
        return profiles

    def get_profile(self, profile_id: str) -> AgentProfile | None:
        safe_id = self.app.sanitize_agent_id(profile_id)
        repo = getattr(self.app, "agent_repository", None)
        path = (
            repo.get_agent_profile_path(safe_id)
            if repo is not None
            else self.app.get_agent_profile_path(safe_id)
        )
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        if isinstance(data, dict):
            try:
                return AgentProfile(**data)
            except Exception:
                return None
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
        repo = getattr(self.app, "agent_repository", None)
        if repo is not None:
            repo.append_agent_audit_row(row)
        else:
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
        existing = self.get_profile(safe_id)
        defaults = self.get_default_profile()
        base_profile = existing if existing else defaults
        version = ((existing.version or 0) + 1) if existing else 1
        created_by = (existing.created_by if existing else actor) or actor

        profile = AgentProfile(
            id=safe_id,
            name=name.strip() or safe_id,
            description=description.strip(),
            system_prompt=system_prompt.strip(),
            tool_policy=base_profile.tool_policy,
            memory_policy=base_profile.memory_policy,
            routing_policy=base_profile.routing_policy,
            created_by=created_by,
            updated_by=actor,
            updated_at=datetime.now().isoformat(timespec="seconds"),
            version=version,
        )

        repo = getattr(self.app, "agent_repository", None)
        path = (
            repo.get_agent_profile_path(safe_id)
            if repo is not None
            else self.app.get_agent_profile_path(safe_id)
        )
        try:
            path.write_text(json.dumps(profile.to_dict(), indent=2), encoding="utf-8")
        except OSError as exc:
            return False, f"Failed to save profile: {exc}"
        self.append_agent_audit("upsert", safe_id, actor)
        return True, f"Saved profile '{safe_id}' (v{version})."

    def save_profile(self, profile: AgentProfile, actor: str) -> tuple[bool, str]:
        profile_id = self.app.sanitize_agent_id(str(profile.id or ""))
        if not profile_id:
            return False, "Profile id is required."
        existing = self.get_profile(profile_id)

        current_version = existing.version if existing else (profile.version or 0)
        version = current_version + 1

        profile.id = profile_id
        profile.version = version
        profile.updated_by = actor
        profile.updated_at = datetime.now().isoformat(timespec="seconds")

        if not profile.created_by:
            profile.created_by = existing.created_by if existing else actor

        repo = getattr(self.app, "agent_repository", None)
        path = (
            repo.get_agent_profile_path(profile_id)
            if repo is not None
            else self.app.get_agent_profile_path(profile_id)
        )
        try:
            path.write_text(json.dumps(profile.to_dict(), indent=2), encoding="utf-8")
        except OSError as exc:
            return False, f"Failed to save profile: {exc}"
        self.append_agent_audit("save", profile_id, actor)
        return True, f"Saved profile '{profile_id}' (v{version})."

    def build_status_text(self) -> str:
        profile = self.get_active_profile()
        scopes = profile.memory_policy.scopes
        scope_text = (
            ", ".join(str(x) for x in scopes) if isinstance(scopes, list) else ""
        )
        return (
            f"Agent: {profile.id or DEFAULT_AGENT_PROFILE_ID} | "
            f"name={profile.name} | "
            f"memory_scopes={scope_text or 'team'} | "
            f"version={profile.version}"
        )
