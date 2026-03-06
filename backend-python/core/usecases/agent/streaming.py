# backend-python/core/usecases/agent/streaming.py
"""Streaming helpers for agent chat runtimes."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from queue import Empty, Queue
from threading import Event, Thread
from typing import Any

from config import (
    AGENT_MAX_OUTPUT_TOKENS,
    AGENT_MODEL,
    AGENT_REASONING_EFFORT,
    AGENT_TEMPERATURE,
)
from core.usecases.agent.mcp_runtime import cleanup_mcp_servers, connect_mcp_servers
from core.usecases.agent.stream_event_formatting import (
    extract_page_switch_filename,
    format_exception_details,
    format_tool_called_message,
    format_tool_output_message,
    preview_tool_arguments,
    summarize_tool_output,
)
from infra.llm import (
    build_response_params,
    create_openai_client,
    has_openai_sdk,
    openai_responses_stream_events,
)

logger = logging.getLogger(__name__)


def _is_provider_server_error(exc: Exception) -> bool:
    err_type = str(getattr(exc, "type", "") or "").strip().lower()
    err_code = str(getattr(exc, "code", "") or "").strip().lower()
    if err_type == "server_error" or err_code == "server_error":
        return True
    text = str(exc or "").strip().lower()
    return "server_error" in text


def _event_attr(value: Any, key: str) -> Any:
    if isinstance(value, dict):
        return value.get(key)
    return getattr(value, key, None)


def _extract_text_from_message_raw(raw_message: Any) -> str:
    content = _event_attr(raw_message, "content")
    if not isinstance(content, list):
        return ""

    chunks: list[str] = []
    for part in content:
        part_type = str(_event_attr(part, "type") or "").strip().lower()
        if part_type in {"output_text", "text"}:
            text = str(_event_attr(part, "text") or "").strip()
            if text:
                chunks.append(text)
        elif part_type in {"refusal", "output_refusal"}:
            refusal = str(_event_attr(part, "refusal") or "").strip()
            if refusal:
                chunks.append(refusal)
    return "".join(chunks).strip()


def _extract_text_from_run_items(items: Any) -> str:
    if not isinstance(items, list):
        return ""

    chunks: list[str] = []
    for item in items:
        raw_item = _event_attr(item, "raw_item")
        candidate = raw_item if raw_item is not None else item
        item_type = str(_event_attr(candidate, "type") or "").strip().lower()
        if item_type and item_type != "message":
            continue

        text = _extract_text_from_message_raw(candidate)
        if text:
            chunks.append(text)

    return "".join(chunks).strip()


def extract_sdk_result_text(result: Any) -> str:
    final_output = _event_attr(result, "final_output")
    if isinstance(final_output, str):
        text = final_output.strip()
        if text:
            return text
    elif final_output not in (None, "", []):
        text = str(final_output).strip()
        if text:
            return text

    new_items = _event_attr(result, "new_items")
    return _extract_text_from_run_items(new_items)


def run_legacy_stream_events(
    messages: list[dict[str, Any]],
    *,
    model_id: str | None,
    stop_event: Event | None,
    build_input: Callable[[list[dict[str, Any]]], list[dict[str, Any]]],
):
    if not has_openai_sdk():
        raise RuntimeError("OpenAI SDK is not available")

    resolved_model = model_id or AGENT_MODEL
    cfg: dict[str, Any] = {
        "model": resolved_model,
        "max_output_tokens": AGENT_MAX_OUTPUT_TOKENS,
    }
    if str(resolved_model).startswith("gpt-5"):
        effort = AGENT_REASONING_EFFORT
        if effort not in {"low", "medium", "high"}:
            effort = "medium"
        cfg["reasoning"] = {"effort": effort}
    else:
        cfg["temperature"] = AGENT_TEMPERATURE

    client = create_openai_client({})
    input_payload = build_input(messages)
    params = build_response_params(cfg, input_payload)
    params.setdefault("text", {"format": {"type": "text"}})

    had_delta = False
    if stop_event is not None and stop_event.is_set():
        return

    for event in openai_responses_stream_events(
        client,
        params,
        component="agent.chat.stream",
        context={"model_id": str(resolved_model)},
    ):
        if stop_event is not None and stop_event.is_set():
            break
        event_type = getattr(event, "type", None)
        if event_type is None and isinstance(event, dict):
            event_type = event.get("type")
        if event_type == "response.output_text.delta":
            delta = getattr(event, "delta", None)
            if delta is None and isinstance(event, dict):
                delta = event.get("delta")
            if delta:
                had_delta = True
                yield {"type": "delta", "delta": str(delta)}
        elif event_type == "response.output_text.done" and not had_delta:
            text_value = getattr(event, "text", None)
            if text_value is None and isinstance(event, dict):
                text_value = event.get("text")
            if text_value:
                yield {"type": "delta", "delta": str(text_value)}


def run_sdk_stream_events(
    *,
    runner_cls: Any,
    agent: Any,
    sdk_input: Any,
    run_context: Any,
    session: Any,
    mcp_servers: list[Any],
    stop_event: Event | None,
    max_turns: int,
):
    emitted_events: Queue[Any] = Queue()
    producer_done = object()
    producer_error: Exception | None = None

    async def produce() -> None:
        had_delta = False
        call_tool_name_by_id: dict[str, str] = {}
        connected_mcp_servers: list[Any] = []
        try:
            if stop_event is not None and stop_event.is_set():
                return

            connected_mcp_servers, failed_mcp_servers = await connect_mcp_servers(mcp_servers)
            for server in connected_mcp_servers:
                server_name = str(getattr(server, "name", "mcp-server") or "mcp-server")
                emitted_events.put(
                    {
                        "type": "activity",
                        "message": f"Connected MCP server: {server_name}",
                    }
                )
            for server_name, exc in failed_mcp_servers:
                logger.warning("mcp server unavailable during stream run %s: %s", server_name, exc)
                emitted_events.put(
                    {
                        "type": "activity",
                        "message": f"MCP server unavailable: {server_name}",
                    }
                )
            if not connected_mcp_servers:
                raise RuntimeError("No MCP tool servers are available for this agent run")
            if hasattr(agent, "mcp_servers"):
                agent.mcp_servers = connected_mcp_servers

            result = runner_cls.run_streamed(
                agent,
                input=sdk_input,
                context=run_context,
                session=session,
                max_turns=max(1, int(max_turns)),
            )
            stop_task: asyncio.Task[None] | None = None
            if stop_event is not None:
                stop_signal = stop_event

                async def watch_stop() -> None:
                    while not stop_signal.is_set():
                        await asyncio.sleep(0.1)
                    result.cancel(mode="immediate")

                stop_task = asyncio.create_task(watch_stop())

            try:
                async for stream_event in result.stream_events():
                    stream_type = str(_event_attr(stream_event, "type") or "").strip()
                    if stream_type == "raw_response_event":
                        raw_event = _event_attr(stream_event, "data")
                        raw_type = str(_event_attr(raw_event, "type") or "").strip()
                        if raw_type == "response.output_text.delta":
                            delta = _event_attr(raw_event, "delta")
                            if delta:
                                had_delta = True
                                emitted_events.put({"type": "delta", "delta": str(delta)})
                        elif raw_type == "response.output_text.done" and not had_delta:
                            text_value = _event_attr(raw_event, "text")
                            if text_value:
                                emitted_events.put({"type": "delta", "delta": str(text_value)})
                        continue

                    if stream_type != "run_item_stream_event":
                        continue

                    event_name = str(_event_attr(stream_event, "name") or "").strip()
                    item = _event_attr(stream_event, "item")
                    if event_name == "tool_called":
                        raw_item = _event_attr(item, "raw_item")
                        tool_name = str(
                            _event_attr(raw_item, "name")
                            or _event_attr(item, "description")
                            or "tool"
                        ).strip()
                        call_id_raw = _event_attr(raw_item, "call_id") or _event_attr(raw_item, "id")
                        call_id = str(call_id_raw or "").strip()
                        if call_id:
                            call_tool_name_by_id[call_id] = tool_name
                        args_preview = preview_tool_arguments(_event_attr(raw_item, "arguments"))
                        emitted_events.put(
                            {
                                "type": "tool_called",
                                "tool": tool_name,
                                "callId": call_id,
                                "message": format_tool_called_message(tool_name, args_preview),
                            }
                        )
                    elif event_name == "tool_output":
                        raw_item = _event_attr(item, "raw_item")
                        call_id_raw = _event_attr(raw_item, "call_id") or _event_attr(raw_item, "id")
                        call_id = str(call_id_raw or "").strip()
                        tool_name = call_tool_name_by_id.get(call_id) or str(
                            _event_attr(raw_item, "name") or "tool"
                        ).strip()
                        tool_output = _event_attr(item, "output")
                        summary = summarize_tool_output(tool_name, tool_output)
                        emitted_events.put(
                            {
                                "type": "tool_output",
                                "tool": tool_name,
                                "callId": call_id,
                                "message": format_tool_output_message(tool_name, summary),
                            }
                        )
                        page_switch_filename = extract_page_switch_filename(tool_name, tool_output)
                        if page_switch_filename:
                            emitted_events.put(
                                {
                                    "type": "page_switch",
                                    "tool": tool_name,
                                    "callId": call_id,
                                    "filename": page_switch_filename,
                                    "message": f"Agent switched active page to {page_switch_filename}",
                                }
                            )
            finally:
                if stop_task is not None:
                    stop_task.cancel()

            if stop_event is not None and stop_event.is_set():
                return
            final_text = extract_sdk_result_text(result)
            if final_text and not had_delta:
                emitted_events.put({"type": "delta", "delta": final_text})
        finally:
            await cleanup_mcp_servers(connected_mcp_servers)

    def run_producer() -> None:
        nonlocal producer_error
        try:
            asyncio.run(produce())
        except Exception as exc:  # pragma: no cover - network/provider/runtime path
            producer_error = exc
            if _is_provider_server_error(exc):
                logger.warning(
                    "agent sdk stream producer provider error: %s",
                    format_exception_details(exc),
                )
            else:
                logger.error("agent sdk stream producer failed: %s", format_exception_details(exc))
        finally:
            emitted_events.put(producer_done)

    producer_thread = Thread(target=run_producer, daemon=True)
    producer_thread.start()
    try:
        while True:
            try:
                item = emitted_events.get(timeout=0.25)
            except Empty:
                if not producer_thread.is_alive():
                    break
                continue
            if item is producer_done:
                break
            if isinstance(item, dict):
                yield item
    finally:
        producer_thread.join(timeout=0.5)

    if producer_error is not None:
        raise producer_error
