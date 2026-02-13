import difflib
import json
import logging
import os
import random
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
    LOCK_BACKOFF_BASE_SECONDS,
    LOCK_BACKOFF_MAX_SECONDS,
    LOCK_MAX_ATTEMPTS,
    LOCK_TIMEOUT_SECONDS,
    MEMORY_DUPLICATE_THRESHOLD,
)

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

    def load_memory_entries(self) -> list[dict[str, Any]]:
        self.app.ensure_memory_paths()
        entries: list[dict[str, Any]] = []
        try:
            with open(self.app.get_memory_file(), "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if isinstance(data, dict):
                        entries.append(data)
        except OSError as exc:
            logger.warning("Failed reading memory entries: %s", exc)
        return entries

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
        self, prompt: str, provider_cfg: dict[str, str]
    ) -> tuple[list[dict[str, Any]], str | None]:
        used_override, override_entries = self._call_instance_override(
            "load_memory_entries"
        )
        entries = override_entries if used_override else self.load_memory_entries()
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
            provider_cfg=provider_cfg,
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
        entries = override_entries if used_override else self.load_memory_entries()
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
        self.app.append_system_message("\n".join(lines))

    def write_memory_entry(self, entry: dict[str, Any]) -> bool:
        self.app.ensure_locking_dependency()
        import chat

        assert chat.portalocker is not None
        self.app.ensure_memory_paths()
        memory_file = self.app.get_memory_file()
        row = json.dumps(entry, ensure_ascii=True)
        max_attempts = int(getattr(chat, "LOCK_MAX_ATTEMPTS", LOCK_MAX_ATTEMPTS))
        for attempt in range(max_attempts):
            try:
                with chat.portalocker.Lock(
                    str(memory_file),
                    mode="a",
                    timeout=LOCK_TIMEOUT_SECONDS,
                    fail_when_locked=True,
                    encoding="utf-8",
                ) as f:
                    f.write(row + "\n")
                    f.flush()
                    os.fsync(f.fileno())
                return True
            except chat.portalocker.exceptions.LockException:
                pass
            except OSError:
                pass
            if attempt == max_attempts - 1:
                break
            delay = min(
                LOCK_BACKOFF_MAX_SECONDS,
                LOCK_BACKOFF_BASE_SECONDS * (2 ** min(attempt, 5)),
            )
            time.sleep(delay + random.uniform(0, 0.03))
        return False

    def get_last_ai_response_event(self) -> dict[str, Any] | None:
        for event in reversed(self.app.message_events):
            if str(event.get("type", "")) == "ai_response":
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

    def build_memory_source(self, event: dict[str, Any]) -> str:
        request_id = str(event.get("request_id", "")).strip()
        ts = str(event.get("ts", "")).strip()
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

        source_text = str(source_event.get("text", "")).strip()
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
            "origin_event_ref": str(
                source_event.get("request_id", source_event.get("ts", ""))
            ),
            "tags": [str(tag).strip() for tag in tags if str(tag).strip()],
        }
        return draft, None

    def show_memory_draft_preview(self) -> None:
        self.ensure_memory_state_initialized()
        if not self.app.memory_draft_active or not isinstance(
            self.app.memory_draft, dict
        ):
            self.app.append_system_message("No active memory draft.")
            return
        draft = self.app.memory_draft
        preview = (
            "Memory Draft:\n"
            f"Summary: {draft.get('summary', '')}\n"
            f"Topic: {draft.get('topic', '')}\n"
            f"Confidence: {draft.get('confidence', '')}\n"
            f"Source: {draft.get('source', '')}"
        )
        self.app.append_system_message(preview)
        if self.app.memory_draft_mode == "confirm":
            self.app.append_system_message("Confirm memory entry? (y/n)")

    def confirm_memory_draft(self) -> None:
        self.ensure_memory_state_initialized()
        if not self.app.memory_draft_active or not isinstance(
            self.app.memory_draft, dict
        ):
            self.app.append_system_message("No active memory draft.")
            return
        draft = self.app.memory_draft
        summary = str(draft.get("summary", "")).strip()
        source = str(draft.get("source", "")).strip()
        confidence = str(draft.get("confidence", "")).strip().lower()
        if not summary:
            self.app.append_system_message(
                "Draft summary is empty. Use /memory edit summary <text>."
            )
            return
        if not source:
            self.app.append_system_message(
                "Draft source is empty. Use /memory edit source <text>."
            )
            return
        if confidence not in {"low", "med", "high"}:
            self.app.append_system_message("Confidence must be low, med, or high.")
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
        }
        self.maybe_warn_memory_duplicates(entry)
        used_override, write_ok = self._call_instance_override(
            "write_memory_entry", entry
        )
        if not (bool(write_ok) if used_override else self.write_memory_entry(entry)):
            self.app.append_system_message("Failed to write shared memory entry.")
            return
        self.app.append_system_message(f"Memory saved: {entry['id']}")
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
            self.app.append_system_message(
                "Draft rejected. Edit fields: /memory edit summary|topic|confidence|source <value>. "
                "Then use /memory confirm or /memory cancel."
            )
            return True
        return False

    def handle_memory_command(self, args: str) -> None:
        self.ensure_memory_state_initialized()
        trimmed = args.strip()
        if not trimmed or trimmed.lower() == "help":
            self.app.append_system_message(
                "Memory commands: /memory add, /memory confirm, /memory cancel, "
                "/memory show-draft, /memory edit <field> <value>, /memory list [N], /memory search <text>"
            )
            return

        try:
            tokens = shlex.split(trimmed)
        except ValueError:
            self.app.append_system_message("Invalid /memory syntax. Check quotes.")
            return
        if not tokens:
            self.app.append_system_message("Usage: /memory help")
            return

        action = tokens[0].lower()
        if action == "add":
            if self.app.memory_draft_active:
                self.app.append_system_message(
                    "A memory draft is already active. Use /memory confirm or /memory cancel."
                )
                return
            draft, error = self.draft_memory_from_last_ai_response()
            if error:
                self.app.append_system_message(error)
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
                self.app.append_system_message("No active memory draft.")
                return
            self.clear_memory_draft()
            self.app.append_system_message("Memory draft canceled.")
            return

        if action == "edit":
            if not self.app.memory_draft_active or not isinstance(
                self.app.memory_draft, dict
            ):
                self.app.append_system_message("No active memory draft.")
                return
            if len(tokens) < 3:
                self.app.append_system_message(
                    "Usage: /memory edit <summary|topic|confidence|source> <value>"
                )
                return
            field = tokens[1].strip().lower()
            value = " ".join(tokens[2:]).strip()
            if field not in {"summary", "topic", "confidence", "source"}:
                self.app.append_system_message(
                    "Editable fields: summary, topic, confidence, source."
                )
                return
            if field == "confidence":
                value = value.lower()
                if value not in {"low", "med", "high"}:
                    self.app.append_system_message(
                        "Confidence must be low, med, or high."
                    )
                    return
            self.app.memory_draft[field] = value
            self.app.append_system_message(f"Updated draft {field}.")
            self.show_memory_draft_preview()
            return

        if action == "list":
            limit = 10
            if len(tokens) > 1:
                try:
                    limit = max(1, min(100, int(tokens[1])))
                except ValueError:
                    self.app.append_system_message("Usage: /memory list [limit]")
                    return
            used_override, override_entries = self._call_instance_override(
                "load_memory_entries"
            )
            entries = override_entries if used_override else self.load_memory_entries()
            if not entries:
                self.app.append_system_message("No shared memory entries found.")
                return
            lines = ["Shared Memory:"]
            for entry in entries[-limit:]:
                lines.append(
                    f"{entry.get('id', '?')} [{entry.get('confidence', '?')}] "
                    f"{entry.get('topic', 'general')}: {entry.get('summary', '')}"
                )
            self.app.append_system_message("\n".join(lines))
            return

        if action == "search":
            if len(tokens) < 2:
                self.app.append_system_message("Usage: /memory search <query>")
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
                self.app.append_system_message(f"No memory matches for '{query}'.")
                return
            lines = [f"Memory matches ({len(matches)}):"]
            for entry in matches[-10:]:
                lines.append(
                    f"{entry.get('id', '?')} [{entry.get('topic', 'general')}] {entry.get('summary', '')}"
                )
            self.app.append_system_message("\n".join(lines))
            return

        self.app.append_system_message("Unknown /memory command. Use /memory help.")
