# backend-python/api/routers/agent/reply_stream_worker.py
"""Background worker for streamed agent replies."""

from __future__ import annotations

import asyncio
import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any

from core.usecases.agent.engine import run_agent_chat_stream
from core.usecases.agent.grounding.turn_state import (
    get_active_page_text_box_count,
    sanitize_agent_reply_text,
    stale_context_warning_message,
)
from infra.db.agent_store import add_agent_message
from infra.logging.correlation import append_correlation, normalize_correlation

from .helpers import log_agent_sdk_attempt, persist_action_event_messages
from .reply_stream_fallback import handle_stream_failure, recover_empty_primary_output

logger = logging.getLogger(__name__)


@dataclass
class StreamReplyWorker:
    """Own the background execution for one streamed reply request."""

    session_id: str
    volume_id: str
    model_id: str
    payload: list[dict[str, Any]]
    current_filename: str | None
    queue: asyncio.Queue[dict[str, object]]
    loop: asyncio.AbstractEventLoop
    stop_event: threading.Event
    text_chunks: list[str] = field(default_factory=list)
    action_events: list[dict[str, str]] = field(default_factory=list)
    runtime_active_filename: str | None = None
    stream_started_at: float = field(default_factory=time.monotonic)
    initial_text_box_count: int | None = None

    def __post_init__(self) -> None:
        self.runtime_active_filename = self.current_filename
        self.initial_text_box_count = get_active_page_text_box_count(
            volume_id=self.volume_id,
            current_filename=self.runtime_active_filename,
        )

    def run(self) -> None:
        """Run the streaming worker and emit queue events for the SSE layer."""
        logger.info(
            append_correlation(
                "agent stream start",
                self._corr(),
                max_messages=len(self.payload),
            )
        )
        try:
            self._run_primary_stream()
        except Exception as exc:
            self._handle_stream_failure(exc)

    def _run_primary_stream(self) -> None:
        primary_stream_used_retry = False
        for stream_event in run_agent_chat_stream(
            self.payload,
            model_id=self.model_id,
            volume_id=self.volume_id,
            current_filename=self.current_filename,
            session_id=self.session_id,
            stop_event=self.stop_event,
        ):
            self._process_stream_event(stream_event)

        if self.stop_event.is_set():
            self._emit({"type": "canceled"})
            logger.info(append_correlation("agent stream canceled", self._corr()))
            return

        response_text = "".join(self.text_chunks).strip()
        if not response_text:
            response_text, primary_stream_used_retry = self._recover_empty_primary_output()

        self._finalize_primary_reply(
            response_text=response_text,
            primary_stream_used_retry=primary_stream_used_retry,
        )

    def _process_stream_event(self, stream_event: dict[str, Any]) -> None:
        event_type = str(stream_event.get("type") or "").strip()
        if event_type == "delta":
            delta = str(stream_event.get("delta") or "")
            if delta:
                self.text_chunks.append(delta)
                logger.debug(
                    append_correlation(
                        "agent stream delta",
                        self._corr(),
                        chars=len(delta),
                    )
                )
        elif event_type in {"activity", "tool_called", "tool_output", "page_switch"}:
            if event_type == "tool_called" and self.text_chunks:
                # Discard provisional draft text once tool execution starts.
                # The post-tool model pass should produce the grounded final answer.
                self.text_chunks.clear()
                self._emit({"type": "delta_reset"})
                self.action_events.append(
                    {
                        "type": "activity",
                        "message": "Reset draft response after tool call; waiting for grounded final answer",
                    }
                )
            switched_filename = ""
            if event_type == "page_switch":
                switched_filename = str(stream_event.get("filename") or "").strip()
                if switched_filename:
                    self.runtime_active_filename = switched_filename
            msg = str(stream_event.get("message") or "").strip()
            if msg:
                action: dict[str, str] = {"type": event_type, "message": msg}
                if event_type in {"tool_called", "tool_output", "page_switch"}:
                    tool_name = str(stream_event.get("tool") or "").strip()
                    if tool_name:
                        action["tool"] = tool_name
                if event_type == "page_switch" and switched_filename:
                    action["filename"] = switched_filename
                self.action_events.append(action)
                self.action_events = self.action_events[-40:]
        elif event_type:
            logger.info(
                append_correlation(
                    "agent stream event",
                    self._corr(),
                    event_type=event_type,
                )
            )

        self._emit(stream_event)

    def _recover_empty_primary_output(self) -> tuple[str, bool]:
        return recover_empty_primary_output(self)

    def _finalize_primary_reply(
        self,
        *,
        response_text: str,
        primary_stream_used_retry: bool,
    ) -> None:
        active_text_box_count = get_active_page_text_box_count(
            volume_id=self.volume_id,
            current_filename=self.runtime_active_filename,
        )
        if (
            self.initial_text_box_count is not None
            and active_text_box_count is not None
            and active_text_box_count != self.initial_text_box_count
        ):
            self.action_events.append(
                {
                    "type": "activity",
                    "message": (
                        "Refreshed active page state after tool calls: "
                        f"text boxes {self.initial_text_box_count} -> {active_text_box_count}"
                    ),
                }
            )

        response_text, guard_reason = sanitize_agent_reply_text(
            response_text=response_text,
            messages=self.payload,
            active_filename=self.runtime_active_filename,
            active_text_box_count=active_text_box_count,
        )
        if guard_reason == "stale_context_warning":
            self.action_events.append(
                {
                    "type": "activity",
                    "message": stale_context_warning_message(
                        active_filename=self.runtime_active_filename,
                        active_text_box_count=active_text_box_count,
                    ),
                }
            )
        elif guard_reason == "empty_output_no_boxes":
            self.action_events.append(
                {
                    "type": "activity",
                    "message": "Model returned empty output; returned no-box deterministic reply",
                }
            )
        elif guard_reason == "empty_output":
            self.action_events.append(
                {
                    "type": "activity",
                    "message": "Model returned empty output; returned deterministic fallback",
                }
            )

        meta: dict[str, object] = {"source": "agent_reply"}
        if self.action_events:
            meta["actions"] = self.action_events
        persisted_timeline = persist_action_event_messages(self.session_id, self.action_events)
        message = add_agent_message(
            self.session_id,
            role="assistant",
            content=response_text,
            meta=meta,
        )
        self._emit(
            {
                "type": "done",
                "message": message,
                "timelineMessages": persisted_timeline,
            }
        )

        if not primary_stream_used_retry:
            log_agent_sdk_attempt(
                component="agent.chat.stream.sdk",
                status="success",
                session_id=self.session_id,
                volume_id=self.volume_id,
                filename=self.runtime_active_filename,
                model_id=self.model_id,
                messages=self.payload,
                action_events=self.action_events,
                response_text=response_text,
                latency_ms=round((time.monotonic() - self.stream_started_at) * 1000),
                finish_reason="completed",
                phase="stream_primary",
            )
        logger.info(
            append_correlation(
                "agent stream done",
                self._corr(),
                response_chars=len(response_text),
            )
        )

    def _handle_stream_failure(self, exc: Exception) -> None:
        handle_stream_failure(self, exc)

    def _corr(self, **extras: object) -> dict[str, object]:
        return normalize_correlation(
            {
                "component": "agent.reply.stream",
                "session_id": self.session_id,
                "volume_id": self.volume_id,
                "filename": self.runtime_active_filename,
                "model_id": self.model_id,
            },
            **extras,
        )

    def _emit(self, payload: dict[str, object]) -> None:
        self.loop.call_soon_threadsafe(self.queue.put_nowait, payload)
