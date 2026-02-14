import shlex
import time
from threading import Thread
from typing import TYPE_CHECKING, Any

from huddle_chat.constants import AI_DM_ROOM, AI_RETRY_BACKOFF_SECONDS

if TYPE_CHECKING:
    from chat import ChatApp


class AIService:
    def __init__(self, app: "ChatApp"):
        self.app = app

    def parse_ai_args(self, arg_text: str) -> tuple[dict[str, Any], str | None]:
        try:
            tokens = shlex.split(arg_text)
        except ValueError:
            return {}, "Invalid /ai arguments. Check quotes and try again."

        provider_override: str | None = None
        model_override: str | None = None
        is_private = False
        disable_memory = False
        action_mode = False
        memory_scope_override: list[str] = []
        prompt_parts: list[str] = []
        i = 0
        while i < len(tokens):
            token = tokens[i]
            if token == "--provider":
                if i + 1 >= len(tokens):
                    return {}, "Usage: /ai --provider <gemini|openai> <prompt>"
                provider_override = tokens[i + 1].strip().lower()
                i += 2
                continue
            if token == "--model":
                if i + 1 >= len(tokens):
                    return {}, "Usage: /ai --model <model-name> <prompt>"
                model_override = tokens[i + 1].strip()
                i += 2
                continue
            if token == "--private":
                is_private = True
                i += 1
                continue
            if token == "--no-memory":
                disable_memory = True
                i += 1
                continue
            if token == "--act":
                action_mode = True
                i += 1
                continue
            if token == "--memory-scope":
                if i + 1 >= len(tokens):
                    return (
                        {},
                        "Usage: /ai --memory-scope <private|repo|team[,..]> <prompt>",
                    )
                raw_scopes = tokens[i + 1]
                for part in raw_scopes.replace(",", " ").split():
                    scope = part.strip().lower()
                    if (
                        scope in {"private", "repo", "team"}
                        and scope not in memory_scope_override
                    ):
                        memory_scope_override.append(scope)
                i += 2
                continue
            prompt_parts.append(token)
            i += 1

        prompt = " ".join(prompt_parts).strip()
        if not prompt:
            return (
                {},
                "Usage: /ai [--provider <name>] [--model <name>] [--private] "
                "[--no-memory] [--memory-scope <private|repo|team[,..]>] [--act] <prompt>",
            )

        return {
            "provider_override": provider_override,
            "model_override": model_override,
            "is_private": is_private,
            "disable_memory": disable_memory,
            "action_mode": action_mode,
            "prompt": prompt,
            "memory_scope_override": memory_scope_override,
        }, None

    def classify_task(self, prompt: str) -> str:
        lowered = prompt.lower()
        code_markers = [
            "code",
            "python",
            "traceback",
            "bug",
            "test",
            "refactor",
            "function",
            "class ",
        ]
        if any(marker in lowered for marker in code_markers):
            return "code_analysis"
        return "chat_general"

    def resolve_ai_provider_config(
        self, provider_override: str | None, model_override: str | None
    ) -> tuple[dict[str, str], str | None]:
        providers = self.app.ai_config.get("providers", {})
        default_provider = str(
            self.app.ai_config.get("default_provider", "gemini")
        ).lower()
        provider = provider_override or default_provider
        if provider not in ("gemini", "openai"):
            return {}, f"Unknown provider '{provider}'. Use /aiproviders."
        provider_data = providers.get(provider, {})
        if not isinstance(provider_data, dict):
            provider_data = {}
        api_key = str(provider_data.get("api_key", "")).strip()
        model = str(model_override or provider_data.get("model", "")).strip()
        if not api_key:
            return (
                {},
                f"Provider '{provider}' is missing API key. Run /aiconfig set-key {provider} <API_KEY>.",
            )
        if not model:
            return (
                {},
                f"Provider '{provider}' is missing model. Run /aiconfig set-model {provider} <model>.",
            )
        return {"provider": provider, "api_key": api_key, "model": model}, None

    def is_transient_ai_error(self, exc: Exception) -> bool:
        text = str(exc).lower()
        if "http 429" in text:
            return True
        if "http 5" in text:
            return True
        if "timed out" in text or "timeout" in text:
            return True
        if "temporarily unavailable" in text:
            return True
        return False

    def run_ai_request_with_retry(
        self, request_id: str, provider: str, api_key: str, model: str, prompt: str
    ) -> tuple[str | None, str | None]:
        self.app.ensure_ai_state_initialized()
        if self.app.is_ai_request_cancelled(request_id):
            return None, "AI request cancelled."
        try:
            answer = self.app.call_ai_provider(
                provider=provider,
                api_key=api_key,
                model=model,
                prompt=prompt,
            )
            return answer, None
        except Exception as exc:
            if self.app.is_ai_request_cancelled(request_id):
                return None, "AI request cancelled."
            if not self.is_transient_ai_error(exc):
                return None, f"AI request failed: {exc}"

            with self.app.ai_state_lock:
                if self.app.ai_active_request_id == request_id:
                    self.app.ai_retry_count = 1
            self.app.set_ai_preview_text(
                request_id, "retrying after transient error..."
            )
            time.sleep(AI_RETRY_BACKOFF_SECONDS)
            if self.app.is_ai_request_cancelled(request_id):
                return None, "AI request cancelled."
            try:
                answer = self.app.call_ai_provider(
                    provider=provider,
                    api_key=api_key,
                    model=model,
                    prompt=prompt,
                )
                return answer, None
            except Exception as retry_exc:
                return None, f"AI request failed after retry: {retry_exc}"

    def create_thread(self, target, args):
        try:
            import chat

            thread_class = getattr(chat, "Thread", Thread)
        except Exception:
            thread_class = Thread
        return thread_class(target=target, args=args, daemon=True)

    def handle_ai_command(self, args: str) -> None:
        lowered = args.strip().lower()
        if lowered == "status":
            self.app.append_system_message(self.app.build_ai_status_text())
            return
        if lowered == "cancel":
            if self.app.request_ai_cancel():
                self.app.append_system_message("AI cancellation requested.")
            else:
                self.app.append_system_message("No active AI request.")
            return

        parsed, parse_error = self.parse_ai_args(args)
        if parse_error:
            self.app.append_system_message(parse_error)
            return

        task_class = self.classify_task(parsed["prompt"])
        route, route_error = self.app.resolve_route(
            task_class=task_class,
            provider_override=parsed.get("provider_override"),
            model_override=parsed.get("model_override"),
        )
        if route_error:
            self.app.append_system_message(route_error)
            return
        assert route is not None
        provider = route["provider"]
        model = route["model"]
        prompt = parsed["prompt"]
        disable_memory = bool(parsed.get("disable_memory"))
        action_mode = bool(parsed.get("action_mode"))
        is_private = bool(parsed.get("is_private")) or self.app.is_local_room()
        target_room = AI_DM_ROOM if is_private else self.app.current_room
        scope = "private" if is_private else "room"
        memory_scopes = parsed.get("memory_scope_override") or []
        if not memory_scopes:
            profile = self.app.get_active_agent_profile()
            memory_policy = profile.get("memory_policy", {})
            if isinstance(memory_policy, dict):
                configured_scopes = memory_policy.get("scopes", [])
                if isinstance(configured_scopes, list):
                    for value in configured_scopes:
                        candidate = str(value).strip().lower()
                        if (
                            candidate in {"private", "repo", "team"}
                            and candidate not in memory_scopes
                        ):
                            memory_scopes.append(candidate)
        if not memory_scopes:
            memory_scopes = ["team"]

        request_id = self.app.start_ai_request_state(
            provider=provider, model=model, target_room=target_room, scope=scope
        )
        if request_id is None:
            self.app.append_system_message("AI busy. Use /ai status or /ai cancel.")
            return

        prompt_event = self.app.build_event("ai_prompt", prompt)
        prompt_event["provider"] = provider
        prompt_event["model"] = model
        prompt_event["request_id"] = request_id
        if not self.app.write_to_file(prompt_event, room=target_room):
            self.app.clear_ai_request_state(request_id)
            self.app.append_system_message("Error: Failed to persist AI prompt.")
            return

        self.app.append_system_message(
            f"AI request sent ({scope}) via {provider}:{model} [{request_id}]."
        )
        self.app.refresh_output_from_events()

        self.create_thread(
            target=self.process_ai_response,
            args=(
                request_id,
                provider,
                route["api_key"],
                model,
                prompt,
                target_room,
                is_private,
                disable_memory,
                action_mode,
                memory_scopes,
            ),
        ).start()
        self.create_thread(
            target=self.app.run_ai_preview_pulse, args=(request_id,)
        ).start()

    def process_ai_response(
        self,
        request_id: str,
        provider: str,
        api_key: str,
        model: str,
        prompt: str,
        target_room: str,
        is_private: bool,
        disable_memory: bool,
        action_mode: bool,
        memory_scopes: list[str],
    ) -> None:
        effective_prompt = prompt
        memory_ids_used: list[str] = []
        memory_topics_used: list[str] = []
        if not disable_memory:
            rerank_route, _ = self.app.resolve_route(
                task_class="memory_rerank",
                provider_override=None,
                model_override=None,
            )
            rerank_provider_cfg: dict[str, str] | None = None
            if rerank_route is not None:
                rerank_provider_cfg = {
                    "provider": rerank_route["provider"],
                    "api_key": rerank_route["api_key"],
                    "model": rerank_route["model"],
                }
            selected_memory, memory_warning = self.app.select_memory_for_prompt(
                prompt=prompt,
                provider_cfg={
                    "provider": provider,
                    "api_key": api_key,
                    "model": model,
                },
                scopes=memory_scopes,
                rerank_provider_cfg=rerank_provider_cfg,
            )
            if memory_warning:
                self.app.append_system_message(memory_warning)
            memory_context = self.app.build_memory_context_block(selected_memory)
            if memory_context:
                effective_prompt = f"{memory_context}\n\nUser prompt:\n{prompt}"
            memory_ids_used = [
                str(entry.get("id", "")).strip()
                for entry in selected_memory
                if str(entry.get("id", "")).strip()
            ]
            memory_topics_used = [
                str(entry.get("topic", "general")).strip() or "general"
                for entry in selected_memory
            ]

        answer, error_text = self.run_ai_request_with_retry(
            request_id=request_id,
            provider=provider,
            api_key=api_key,
            model=model,
            prompt=effective_prompt,
        )
        if error_text:
            error_event = self.app.build_event("system", error_text)
            error_event["request_id"] = request_id
            self.app.write_to_file(error_event, room=target_room)
            should_notify_private_failure = is_private and not self.app.is_local_room()
            if should_notify_private_failure:
                should_notify_private_failure = "cancelled" not in error_text.lower()
            if should_notify_private_failure:
                self.app.append_system_message(
                    f"AI request failed in #ai-dm: {error_text}"
                )
            self.app.clear_ai_request_state(request_id)
            self.app.refresh_output_from_events()
            return
        assert answer is not None

        action_warning: str | None = None
        action_ids: list[str] = []
        if action_mode and not self.app.is_ai_request_cancelled(request_id):
            tools_json = self.app.tool_service.build_tools_prompt_block()
            action_prompt = (
                "Return strict JSON only with keys: answer, proposed_actions. "
                "proposed_actions must be a list of objects with keys: tool, arguments, summary. "
                "Only propose tools from the provided list.\n\n"
                f"Available tools:\n{tools_json}\n\n"
                f"User prompt:\n{prompt}\n\n"
                f"Draft answer:\n{answer}"
            )
            action_raw, action_error = self.run_ai_request_with_retry(
                request_id=request_id,
                provider=provider,
                api_key=api_key,
                model=model,
                prompt=action_prompt,
            )
            if action_error:
                action_warning = f"Action proposal failed: {action_error}"
            else:
                assert action_raw is not None
                parsed_answer, proposals, parse_warning = (
                    self.app.tool_service.parse_ai_action_response(action_raw)
                )
                if parse_warning:
                    action_warning = parse_warning
                if parsed_answer:
                    answer = parsed_answer
                for proposal in proposals:
                    ok, result = self.app.tool_service.create_action_from_proposal(
                        request_id=request_id,
                        room=target_room,
                        tool=str(proposal.get("tool", "")),
                        arguments=proposal.get("arguments", {}),
                        summary=str(proposal.get("summary", "")),
                    )
                    if ok:
                        action_ids.append(result)
                    elif not action_warning:
                        action_warning = result

        if self.app.is_ai_request_cancelled(request_id):
            canceled_event = self.app.build_event("system", "AI request cancelled.")
            canceled_event["request_id"] = request_id
            self.app.write_to_file(canceled_event, room=target_room)
            self.app.clear_ai_request_state(request_id)
            self.app.refresh_output_from_events()
            return

        response_event = self.app.build_event("ai_response", answer)
        response_event["provider"] = provider
        response_event["model"] = model
        response_event["request_id"] = request_id
        if memory_ids_used:
            response_event["memory_ids_used"] = memory_ids_used
            response_event["memory_topics_used"] = memory_topics_used
        if not self.app.write_to_file(response_event, room=target_room):
            self.app.clear_ai_request_state(request_id)
            self.app.append_system_message("Error: Failed to persist AI response.")
            return

        ids_line = self.app.format_memory_ids_line(memory_ids_used)
        if ids_line:
            memory_event = self.app.build_event("system", ids_line)
            memory_event["request_id"] = request_id
            self.app.write_to_file(memory_event, room=target_room)
        if action_ids:
            actions_event = self.app.build_event(
                "system",
                f"Proposed actions: {', '.join(action_ids)}. Use /actions then /approve <id>.",
            )
            actions_event["request_id"] = request_id
            self.app.write_to_file(actions_event, room=target_room)
        if action_warning:
            warn_event = self.app.build_event("system", action_warning)
            warn_event["request_id"] = request_id
            self.app.write_to_file(warn_event, room=target_room)

        if is_private and not self.app.is_local_room():
            self.app.append_system_message(
                "Private AI response saved to #ai-dm. Use /join ai-dm to review."
            )
        self.app.clear_ai_request_state(request_id)
        self.app.refresh_output_from_events()
