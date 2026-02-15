from typing import TYPE_CHECKING

from huddle_chat.constants import DEFAULT_AGENT_PROFILE_ID
from huddle_chat.models import ResolvedRoute

if TYPE_CHECKING:
    from chat import ChatApp


class RoutingService:
    def __init__(self, app: "ChatApp"):
        self.app = app

    def resolve_route(
        self,
        *,
        task_class: str,
        provider_override: str | None,
        model_override: str | None,
    ) -> tuple[ResolvedRoute | None, str | None]:
        profile = self.app.get_active_agent_profile()
        profile_id = str(profile.id or DEFAULT_AGENT_PROFILE_ID)
        route_provider = provider_override
        route_model = model_override
        reason_parts = [f"task={task_class}", f"profile={profile_id}"]

        routing_policy = profile.routing_policy
        # Pydantic models are not dicts, assume valid structure if initialized
        routes = routing_policy.routes
        route_cfg = routes.get(task_class)

        if route_cfg:
            # route_cfg is a dict in the current Pydantic model definition?
            # models.py: routes: dict[str, dict[str, str]]
            # Yes, it's a dict of dicts.
            if route_provider is None:
                candidate = str(route_cfg.get("provider", "")).strip().lower()
                if candidate:
                    route_provider = candidate
                    reason_parts.append("provider=policy")
            if route_model is None:
                candidate_model = str(route_cfg.get("model", "")).strip()
                if candidate_model:
                    route_model = candidate_model
                    reason_parts.append("model=policy")

        provider_cfg, error = self.app.resolve_ai_provider_config(
            route_provider, route_model
        )
        if error:
            return None, error
        assert provider_cfg
        return (
            ResolvedRoute(
                provider=provider_cfg["provider"],
                model=provider_cfg["model"],
                api_key=provider_cfg["api_key"],
                reason=",".join(reason_parts),
            ),
            None,
        )
