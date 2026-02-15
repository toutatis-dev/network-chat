import difflib
import json
import logging
import re
import shlex
import time
from datetime import datetime
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from huddle_chat.constants import (
    AI_MEMORY_CONTEXT_CHAR_BUDGET,
    AI_MEMORY_FINAL_LIMIT,
    AI_MEMORY_PREFILTER_LIMIT,
    AI_MEMORY_SUMMARY_CHAR_LIMIT,
    MEMORY_DUPLICATE_THRESHOLD,
)
from huddle_chat.event_helpers import emit_system_message
from huddle_chat.models import ChatEvent

if TYPE_CHECKING:
    from chat import ChatApp

logger = logging.getLogger(__name__)


class MemoryService:
    def __init__(self, app: "ChatApp"):
        self.app = app

    def _call_instance_override(
        self, name: str, *args: Any, **kwargs: Any
    ) -> tuple[bool, Any]:
        override = self.app.__dict__.get(name)
        if callable(override):
            return True, override(*args, **kwargs)
        return False, None

    def ensure_memory_state_initialized(self) -> None:
        if not hasattr(self.app, "memory_draft_active"):
            self.app.memory_draft_active = False
            self.app.memory_draft_mode = "none"
            self.app.memory_draft = None

    def clear_memory_draft(self) -> None:
        self.ensure_memory_state_initialized()
        self.app.memory_draft_active = False
        self.app.memory_draft_mode = "none"
        self.app.memory_draft = None

    def normalize_memory_scopes(self, scopes: list[str] | None) -> list[str]:
        if not scopes:
            return ["team"]
        normalized: list[str] = []
        for value in scopes:
            candidate = str(value).strip().lower()
            if candidate in {"private", "repo", "team"} and candidate not in normalized:
                normalized.append(candidate)
        return normalized or ["team"]

    def get_memory_file_for_scope(self, scope: str):
        return self.app.memory_repository.get_memory_file_for_scope(scope)

    def load_memory_entries(
        self, scopes: list[str] | None = None
    ) -> list[dict[str, Any]]:
        normalized_scopes = self.normalize_memory_scopes(scopes)
        return self.app.memory_repository.load_entries_for_scopes(normalized_scopes)

    def normalize_text_tokens(self, text: str) -> set[str]:
        return {
            token
            for token in re.findall(r"[a-z0-9]{2,}", text.lower())
            if len(token) >= 2
        }

    def score_memory_candidate(
        self, prompt_tokens: set[str], entry: dict[str, Any]
    ) -> float:
        summary = str(entry.get("summary", ""))
        topic = str(entry.get("topic", ""))
        source = str(entry.get("source", ""))
        tags = entry.get("tags", [])
        if not isinstance(tags, list):
            tags = []

        summary_tokens = self.normalize_text_tokens(summary)
        topic_tokens = self.normalize_text_tokens(topic)
        source_tokens = self.normalize_text_tokens(source)
        tag_tokens = self.normalize_text_tokens(" ".join(str(tag) for tag in tags))

        if not prompt_tokens:
            return 0.0

        overlap_summary = len(prompt_tokens & summary_tokens)
        overlap_topic = len(prompt_tokens & topic_tokens)
        overlap_tags = len(prompt_tokens & tag_tokens)
        overlap_source = len(prompt_tokens & source_tokens)

        confidence = str(entry.get("confidence", "")).strip().lower()
        confidence_boost = 0.0
        if confidence == "high":
            confidence_boost = 0.4
        elif confidence == "med":
            confidence_boost = 0.15

        recency_boost = 0.0
        ts = str(entry.get("ts", "")).strip()
        if ts:
            recency_boost = 0.05

        return sum(
            [
                overlap_summary * 2.2,
                overlap_topic * 1.6,
                overlap_tags * 1.1,
                overlap_source * 0.4,
                confidence_boost,
                recency_boost,
            ]
        )

    def prefilter_memory_candidates(
        self, prompt: str, entries: list[dict[str, Any]], limit: int
    ) -> list[dict[str, Any]]:
        prompt_tokens = self.normalize_text_tokens(prompt)
        scored: list[tuple[float, dict[str, Any]]] = []

        for entry in entries:
            if not isinstance(entry, dict):
                continue
            mem_id = str(entry.get("id", "")).strip()
            summary = str(entry.get("summary", "")).strip()
            if not mem_id or not summary:
                continue
            score = self.score_memory_candidate(prompt_tokens, entry)
            if score <= 0:
                continue
            scored.append((score, entry))

        scored.sort(
            key=lambda item: (
                item[0],
                str(item[1].get("confidence", "")).lower() == "high",
                str(item[1].get("ts", "")),
            ),
            reverse=True,
        )
        return [entry for _, entry in scored[:limit]]

    def rerank_memory_candidates_with_ai(
        self,
        provider_cfg: dict[str, str],
        prompt: str,
        candidates: list[dict[str, Any]],
    ) -> list[str] | None:
        if not candidates:
            return []

        lines = []
        for entry in candidates:
            mem_id = str(entry.get("id", "")).strip()
            topic = str(entry.get("topic", "general")).strip()
            confidence = str(entry.get("confidence", "med")).strip().lower()
            summary = str(entry.get("summary", "")).strip()
            if not mem_id or not summary:
                continue
            lines.append(
                f"{mem_id} | topic={topic} | confidence={confidence} | summary={summary[:AI_MEMORY_SUMMARY_CHAR_LIMIT]}"
            )
        if not lines:
            return []

        rerank_prompt = (
            "Given the user prompt and candidate memory entries, return strict JSON only: "
            '{"ids":["mem_id1","mem_id2", "..."]}. '
            "Rank by usefulness for answering the prompt. Use only provided ids.\n\n"
            f"User prompt:\n{prompt}\n\n"
            "Candidates:\n" + "\n".join(lines)
        )
        try:
            raw = self.app.call_ai_provider(
                provider=provider_cfg["provider"],
                api_key=provider_cfg["api_key"],
                model=provider_cfg["model"],
                prompt=rerank_prompt,
            )
        except Exception:
            return None

        data = self.extract_json_object(raw)
        if not isinstance(data, dict):
            return None
        ids = data.get("ids", [])
        if not isinstance(ids, list):
            return None
        allowed = {str(entry.get("id", "")).strip() for entry in candidates}
        ranked_ids = []
        for value in ids:
            mem_id = str(value).strip()
            if mem_id and mem_id in allowed and mem_id not in ranked_ids:
                ranked_ids.append(mem_id)
        return ranked_ids

    def select_memory_for_prompt(
        self,
        prompt: str,
        provider_cfg: dict[str, str],
        scopes: list[str] | None = None,
        rerank_provider_cfg: dict[str, str] | None = None,
    ) -> tuple[list[dict[str, Any]], str | None]:
        used_override, override_entries = self._call_instance_override(
            "load_memory_entries"
        )
        entries = (
            override_entries
            if used_override
            else self.load_memory_entries(scopes=scopes)
        )
        if not entries:
            return [], None

        prefiltered = self.prefilter_memory_candidates(
            prompt=prompt,
            entries=entries,
            limit=AI_MEMORY_PREFILTER_LIMIT,
        )
        if not prefiltered:
            return [], None

        ranked_ids = self.rerank_memory_candidates_with_ai(
            provider_cfg=rerank_provider_cfg or provider_cfg,
            prompt=prompt,
            candidates=prefiltered,
        )
        fallback_warning: str | None = None
        if ranked_ids is None:
            ranked = prefiltered
            fallback_warning = (
                "Memory rerank unavailable; using lexical memory selection."
            )
        else:
            index = {str(entry.get("id", "")).strip(): entry for entry in prefiltered}
            ranked = [index[mem_id] for mem_id in ranked_ids if mem_id in index]
            if not ranked:
                ranked = prefiltered

        return ranked[:AI_MEMORY_FINAL_LIMIT], fallback_warning

    def build_memory_context_block(self, selected: list[dict[str, Any]]) -> str:
        if not selected:
            return ""
        lines: list[str] = []
        budget = AI_MEMORY_CONTEXT_CHAR_BUDGET
        for entry in selected:
            mem_id = str(entry.get("id", "")).strip()
            topic = str(entry.get("topic", "general")).strip()
            confidence = str(entry.get("confidence", "med")).strip().lower()
            summary = str(entry.get("summary", "")).strip()[
                :AI_MEMORY_SUMMARY_CHAR_LIMIT
            ]
            source = str(entry.get("source", "")).strip()[:80]
            if not mem_id or not summary:
                continue
            row = (
                f"- {mem_id} | topic={topic} | confidence={confidence} | "
                f"summary={summary} | source={source}"
            )
            if len(row) > budget:
                break
            lines.append(row)
            budget -= len(row)
            if budget <= 0:
                break

        if not lines:
            return ""
        return (
            "Shared memory context (use if relevant, do not fabricate):\n"
            + "\n".join(lines)
        )

    def format_memory_ids_line(self, memory_ids: list[str]) -> str:
        if not memory_ids:
            return ""
        return f"Memory used: {', '.join(memory_ids)}"

    def find_duplicate_memory_candidates(
        self, draft: dict[str, Any], limit: int = 3
    ) -> list[dict[str, Any]]:
        draft_summary = str(draft.get("summary", "")).strip().lower()
        draft_topic = str(draft.get("topic", "")).strip().lower()
        if not draft_summary:
            return []

        used_override, override_entries = self._call_instance_override(
            "load_memory_entries"
        )
        entries = (
            override_entries
            if used_override
            else self.load_memory_entries(scopes=["private", "repo", "team"])
        )
        scored: list[tuple[float, dict[str, Any]]] = []
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            existing_summary = str(entry.get("summary", "")).strip().lower()
            if not existing_summary:
                continue
            sim = difflib.SequenceMatcher(None, draft_summary, existing_summary).ratio()
            draft_tokens = self.normalize_text_tokens(draft_summary)
            existing_tokens = self.normalize_text_tokens(existing_summary)
            overlap_ratio = 0.0
            if draft_tokens and existing_tokens:
                overlap_ratio = len(draft_tokens & existing_tokens) / max(
                    len(draft_tokens), 1
                )
            topic_bonus = 0.0
            if (
                draft_topic
                and draft_topic == str(entry.get("topic", "")).strip().lower()
            ):
                topic_bonus = 0.08
            score = max(sim, overlap_ratio) + topic_bonus
            if score >= MEMORY_DUPLICATE_THRESHOLD:
                scored.append((score, entry))

        scored.sort(key=lambda item: item[0], reverse=True)
        return [entry for _, entry in scored[:limit]]

    def maybe_warn_memory_duplicates(self, draft: dict[str, Any]) -> None:
        matches = self.find_duplicate_memory_candidates(draft)
        if not matches:
            return
        lines = ["Potential duplicate memory entries:"]
        for entry in matches:
            mem_id = str(entry.get("id", "?"))
            topic = str(entry.get("topic", "general"))
            summary = str(entry.get("summary", ""))[:120]
            lines.append(f"{mem_id} [{topic}] {summary}")
        emit_system_message(self.app, "\n".join(lines))

    def write_memory_entry(self, entry: dict[str, Any], scope: str = "team") -> bool:
        normalized_scope = self.normalize_memory_scopes([scope])[0]
        entry.setdefault("scope", normalized_scope)
        return self.app.memory_repository.append_entry(entry, normalized_scope)

    def get_last_ai_response_event(self) -> ChatEvent | None:
        for event in reversed(self.app.message_events):
            if event.type == "ai_response":
                return event
        return None

    def extract_json_object(self, text: str) -> dict[str, Any] | None:
        text = text.strip()
        if not text:
            return None
        try:
            obj = json.loads(text)
            if isinstance(obj, dict):
                return obj
        except json.JSONDecodeError:
            pass
        match = re.search(r"\{.*\}", text, flags=re.DOTALL)
        if not match:
            return None
        try:
            obj = json.loads(match.group(0))
            if isinstance(obj, dict):
                return obj
        except json.JSONDecodeError:
            return None
        return None

    def build_memory_source(self, event: ChatEvent) -> str:
        request_id = str(event.request_id or "").strip()
        ts = str(event.ts).strip()
        if request_id:
            return f"room:{self.app.current_room} request:{request_id} ts:{ts}"
        return f"room:{self.app.current_room} ts:{ts}"

    def draft_memory_from_last_ai_response(
        self,
    ) -> tuple[dict[str, Any] | None, str | None]:
        source_event = self.get_last_ai_response_event()
        if source_event is None:
            return None, "No recent AI response found. Run /ai first."

        provider_cfg, config_error = self.app.resolve_ai_provider_config(None, None)
        if config_error:
            return None, config_error
        assert provider_cfg

        source_text = str(source_event.text or "").strip()
        if not source_text:
            return None, "Last AI response was empty."

        prompt = (
            "Summarize the following assistant response into reusable team memory. "
            "Return strict JSON only with keys: summary, topic, confidence, tags. "
            "confidence must be low, med, or high.\n\n"
            f"Assistant response:\n{source_text}"
        )
        try:
            drafted = self.app.call_ai_provider(
                provider=provider_cfg["provider"],
                api_key=provider_cfg["api_key"],
                model=provider_cfg["model"],
                prompt=prompt,
            )
        except Exception as exc:
            return None, f"Memory draft generation failed: {exc}"

        data = self.extract_json_object(drafted) or {}
        summary = str(data.get("summary", "")).strip()
        if not summary:
            summary = source_text[:280]
        topic = str(data.get("topic", "")).strip() or "general"
        confidence = str(data.get("confidence", "")).strip().lower() or "med"
        if confidence not in {"low", "med", "high"}:
            confidence = "med"
        tags = data.get("tags", [])
        if not isinstance(tags, list):
            tags = []

        draft = {
            "summary": summary,
            "topic": topic,
            "confidence": confidence,
            "source": self.build_memory_source(source_event),
            "room": self.app.current_room,
            "origin_event_ref": str(source_event.request_id or source_event.ts or ""),
            "tags": [str(tag).strip() for tag in tags if str(tag).strip()],
            "scope": "team",
        }
        return draft, None

    def show_memory_draft_preview(self) -> None:

        self.ensure_memory_state_initialized()
        if not self.app.memory_draft_active or not isinstance(
            self.app.memory_draft, dict
        ):
            emit_system_message(self.app, "No active memory draft.")
            return
        draft = self.app.memory_draft
        preview = (
            "Memory Draft:\n"
            f"Summary: {draft.get('summary', '')}\n"
            f"Topic: {draft.get('topic', '')}\n"
            f"Confidence: {draft.get('confidence', '')}\n"
            f"Source: {draft.get('source', '')}\n"
            f"Scope: {draft.get('scope', 'team')}"
        )
        emit_system_message(self.app, preview)
        if self.app.memory_draft_mode == "confirm":
            emit_system_message(self.app, "Confirm memory entry? (y/n)")

    def confirm_memory_draft(self) -> None:
        self.ensure_memory_state_initialized()
        if not self.app.memory_draft_active or not isinstance(
            self.app.memory_draft, dict
        ):
            emit_system_message(self.app, "No active memory draft.")
            return
        draft = self.app.memory_draft
        summary = str(draft.get("summary", "")).strip()
        source = str(draft.get("source", "")).strip()
        confidence = str(draft.get("confidence", "")).strip().lower()
        if not summary:
            emit_system_message(
                self.app, "Draft summary is empty. Use /memory edit summary <text>."
            )
            return
        if not source:
            emit_system_message(
                self.app, "Draft source is empty. Use /memory edit source <text>."
            )
            return
        if confidence not in {"low", "med", "high"}:
            emit_system_message(self.app, "Confidence must be low, med, or high.")
            return

        entry = {
            "id": f"mem_{int(time.time())}_{uuid4().hex[:6]}",
            "ts": datetime.now().isoformat(timespec="seconds"),
            "author": self.app.name,
            "summary": summary,
            "topic": str(draft.get("topic", "general")).strip() or "general",
            "confidence": confidence,
            "source": source,
            "room": str(draft.get("room", self.app.current_room)),
            "origin_event_ref": str(draft.get("origin_event_ref", "")),
            "tags": list(draft.get("tags", [])),
            "scope": str(draft.get("scope", "team")).strip().lower() or "team",
        }
        self.maybe_warn_memory_duplicates(entry)
        used_override, write_ok = self._call_instance_override(
            "write_memory_entry", entry
        )
        if not (
            bool(write_ok)
            if used_override
            else self.write_memory_entry(entry, scope=str(entry.get("scope", "team")))
        ):
            emit_system_message(self.app, "Failed to write shared memory entry.")
            return
        emit_system_message(self.app, f"Memory saved: {entry['id']}")
        self.clear_memory_draft()

    def handle_memory_confirmation_input(self, text: str) -> bool:
        self.ensure_memory_state_initialized()
        if not self.app.memory_draft_active:
            return False
        if self.app.memory_draft_mode != "confirm":
            return False
        lowered = text.strip().lower()
        if lowered == "y":
            self.confirm_memory_draft()
            return True
        if lowered == "n":
            self.app.memory_draft_mode = "edit"
            emit_system_message(
                self.app,
                "Draft rejected. Edit fields: /memory edit summary|topic|confidence|source|scope <value>. "
                "Then use /memory confirm or /memory cancel.",
            )
            return True
        return False

    def handle_memory_command(self, args: str) -> None:
        self.ensure_memory_state_initialized()
        trimmed = args.strip()
        if not trimmed or trimmed.lower() == "help":
            emit_system_message(
                self.app,
                "Memory commands: /memory add, /memory confirm, /memory cancel, "
                "/memory show-draft, /memory edit <field> <value>, /memory list [N], /memory search <text>, "
                "/memory scope <private|repo|team>",
            )
            return

        try:
            tokens = shlex.split(trimmed)
        except ValueError:
            emit_system_message(
                self.app,
                self.app.help_service.format_guided_error(
                    problem="Invalid /memory syntax.",
                    why="Unbalanced quotes or malformed token boundaries were detected.",
                    next_step="Run /help memory and retry your /memory command.",
                ),
            )
            return
        if not tokens:
            emit_system_message(self.app, "Usage: /memory help")
            return

        action = tokens[0].lower()
        if action == "add":
            if self.app.memory_draft_active:
                emit_system_message(
                    self.app,
                    "A memory draft is already active. Use /memory confirm or /memory cancel.",
                )
                return
            draft, error = self.draft_memory_from_last_ai_response()
            if error:
                emit_system_message(self.app, error)
                return
            assert draft is not None
            self.app.memory_draft = draft
            self.app.memory_draft_active = True
            self.app.memory_draft_mode = "confirm"
            self.maybe_warn_memory_duplicates(draft)
            self.show_memory_draft_preview()
            return

        if action == "show-draft":
            self.show_memory_draft_preview()
            return

        if action == "confirm":
            self.confirm_memory_draft()
            return

        if action == "cancel":
            if not self.app.memory_draft_active:
                emit_system_message(
                    self.app,
                    self.app.help_service.format_guided_error(
                        problem="No active memory draft.",
                        why="There is nothing to confirm or cancel yet.",
                        next_step="Run /memory add to draft from the latest AI response.",
                    ),
                )
                return
            self.clear_memory_draft()
            emit_system_message(self.app, "Memory draft canceled.")
            return

        if action == "edit":
            if not self.app.memory_draft_active or not isinstance(
                self.app.memory_draft, dict
            ):
                emit_system_message(
                    self.app,
                    self.app.help_service.format_guided_error(
                        problem="No active memory draft.",
                        why="Draft editing requires an existing draft context.",
                        next_step="Run /memory add first, then /memory edit ...",
                    ),
                )
                return
            if len(tokens) < 3:
                emit_system_message(
                    self.app,
                    "Usage: /memory edit <summary|topic|confidence|source|scope> <value>",
                )
                return
            field = tokens[1].strip().lower()
            value = " ".join(tokens[2:]).strip()
            if field not in {"summary", "topic", "confidence", "source", "scope"}:
                emit_system_message(
                    self.app,
                    "Editable fields: summary, topic, confidence, source, scope.",
                )
                return
            if field == "confidence":
                value = value.lower()
                if value not in {"low", "med", "high"}:
                    emit_system_message(
                        self.app, "Confidence must be low, med, or high."
                    )
                    return
            if field == "scope":
                value = self.normalize_memory_scopes([value])[0]
            self.app.memory_draft[field] = value
            emit_system_message(self.app, f"Updated draft {field}.")
            self.show_memory_draft_preview()
            return

        if action == "scope":
            if not self.app.memory_draft_active or not isinstance(
                self.app.memory_draft, dict
            ):
                emit_system_message(
                    self.app, "No active memory draft. Run /memory add first."
                )
                return
            if len(tokens) < 2:
                emit_system_message(
                    self.app, "Usage: /memory scope <private|repo|team>"
                )
                return
            self.app.memory_draft["scope"] = self.normalize_memory_scopes([tokens[1]])[
                0
            ]
            emit_system_message(
                self.app, f"Updated draft scope to {self.app.memory_draft['scope']}."
            )
            self.show_memory_draft_preview()
            return

        if action == "list":
            limit = 10
            if len(tokens) > 1:
                try:
                    limit = max(1, min(100, int(tokens[1])))
                except ValueError:
                    emit_system_message(self.app, "Usage: /memory list [limit]")
                    return
            used_override, override_entries = self._call_instance_override(
                "load_memory_entries"
            )
            entries = override_entries if used_override else self.load_memory_entries()
            if not entries:
                emit_system_message(self.app, "No shared memory entries found.")
                return
            lines = ["Shared Memory:"]
            for entry in entries[-limit:]:
                lines.append(
                    f"{entry.get('id', '?')} [{entry.get('confidence', '?')}] "
                    f"{entry.get('topic', 'general')}: {entry.get('summary', '')}"
                )
            emit_system_message(self.app, "\n".join(lines))
            return

        if action == "search":
            if len(tokens) < 2:
                emit_system_message(self.app, "Usage: /memory search <query>")
                return
            query = " ".join(tokens[1:]).strip().lower()
            used_override, override_entries = self._call_instance_override(
                "load_memory_entries"
            )
            entries = override_entries if used_override else self.load_memory_entries()
            matches = []
            for entry in entries:
                haystack = " ".join(
                    [
                        str(entry.get("summary", "")),
                        str(entry.get("topic", "")),
                        str(entry.get("source", "")),
                    ]
                ).lower()
                if query in haystack:
                    matches.append(entry)
            if not matches:
                emit_system_message(self.app, f"No memory matches for '{query}'.")
                return
            lines = [f"Memory matches ({len(matches)}):"]
            for entry in matches[-10:]:
                lines.append(
                    f"{entry.get('id', '?')} [{entry.get('topic', 'general')}] {entry.get('summary', '')}"
                )
            emit_system_message(self.app, "\n".join(lines))
            return

        emit_system_message(
            self.app,
            self.app.help_service.format_guided_error(
                problem=f"Unknown /memory command '{action}'.",
                why="The subcommand is not part of the current /memory command set.",
                next_step="Run /help memory for supported commands.",
            ),
        )
