from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Protocol

from fastmcp import Client
from openai import APIError, AsyncOpenAI

from app.config import Settings
from app.logging_utils import correlation_id_var, log_tool_call, redact

logger = logging.getLogger("kpi.chat")

SYSTEM_PROMPT = """You are a YipitData assistant for time-constrained public investors.

You answer only from MCP tool results. If tools return an error, use the suggestions
and retry. If data is missing, say so. Never invent tickers, KPIs, values, or dates.

Data rules you must follow:
- Historical rows are completed fiscal quarters. QTD rows are intra-quarter snapshots.
- Never call QTD "current" relative to today's calendar date. Always state the fiscal
  period (e.g. 2026Q1) and the as_of date. In this sample the QTD window is 2026Q1
  and the latest snapshot is 2026-03-15.
- Do not treat QTD as a finished quarter.
- Do not infer a subscriber growth rate from net-added subscribers.
- Do not extrapolate a full-quarter value from QTD unless the user asks for that math
  and you label it as an explicit, unofficial calculation.

Keep answers concise. Lead with the figure, unit, period, and as_of date, then a
short comparison to recent history when the tools returned it.
"""


class LLMNotConfigured(RuntimeError):
    pass


class MCPUnavailable(RuntimeError):
    pass


class ToolLoopLimit(RuntimeError):
    def __init__(self, message: str, trace: list[dict[str, Any]] | None = None):
        super().__init__(message)
        self.trace = trace or []


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: str


@dataclass
class LLMTurn:
    content: str | None
    tool_calls: list[ToolCall] = field(default_factory=list)


class LLMClient(Protocol):
    async def complete(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> LLMTurn:
        ...


class OpenAILLM:
    def __init__(self, api_key: str, model: str, base_url: str | None = None):
        kwargs: dict[str, Any] = {"api_key": api_key}
        if base_url:
            kwargs["base_url"] = base_url
        self._client = AsyncOpenAI(**kwargs)
        self._model = model

    async def complete(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> LLMTurn:
        request: dict[str, Any] = {
            "model": self._model,
            "messages": messages,
            "temperature": 0.1,
        }
        if tools:
            request["tools"] = tools
            request["tool_choice"] = "auto"
        response = await self._client.chat.completions.create(**request)
        message = response.choices[0].message
        calls: list[ToolCall] = []
        for item in message.tool_calls or []:
            calls.append(
                ToolCall(
                    id=item.id,
                    name=item.function.name,
                    arguments=item.function.arguments or "{}",
                )
            )
        return LLMTurn(content=message.content, tool_calls=calls)


@dataclass
class TraceEvent:
    tool: str
    arguments: dict[str, Any]
    ok: bool
    duration_ms: float
    error: str | None = None

    def as_dict(self) -> dict[str, Any]:
        payload = {
            "tool": self.tool,
            "arguments": self.arguments,
            "ok": self.ok,
            "duration_ms": round(self.duration_ms, 2),
        }
        if self.error:
            payload["error"] = self.error
        return payload


def mcp_tools_to_openai(tools: list[Any]) -> list[dict[str, Any]]:
    converted = []
    for tool in tools:
        schema = tool.input_schema
        if hasattr(schema, "model_dump"):
            schema = schema.model_dump()
        converted.append(
            {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description or "",
                    "parameters": schema or {"type": "object", "properties": {}},
                },
            }
        )
    return converted


def parse_arguments(raw: str) -> dict[str, Any]:
    try:
        parsed = json.loads(raw or "{}")
    except json.JSONDecodeError:
        return {"_parse_error": raw}
    return parsed if isinstance(parsed, dict) else {"value": parsed}


class ChatService:
    def __init__(
        self,
        settings: Settings,
        llm: LLMClient | None,
        mcp_factory,
    ):
        self.settings = settings
        self.llm = llm
        self.mcp_factory = mcp_factory

    async def reply(self, message: str, correlation_id: str) -> dict[str, Any]:
        if self.llm is None:
            raise LLMNotConfigured(
                "OPENAI_API_KEY is not set. Copy .env.example to .env in the repo root "
                "and add a key. The server will not invent KPI answers without a model."
            )

        token = correlation_id_var.set(correlation_id)
        trace: list[TraceEvent] = []
        tool_calls_used = 0
        try:
            try:
                mcp_client = self.mcp_factory()
            except Exception as exc:
                raise MCPUnavailable(f"Could not create MCP client: {exc}") from exc

            try:
                async with mcp_client as client:
                    try:
                        mcp_tools = await client.list_tools()
                    except Exception as exc:
                        raise MCPUnavailable(
                            f"Could not list MCP tools at {self.settings.mcp_url}: {exc}"
                        ) from exc
                    openai_tools = mcp_tools_to_openai(mcp_tools)
                    messages: list[dict[str, Any]] = [
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": message},
                    ]

                    for round_index in range(self.settings.max_tool_rounds):
                        try:
                            turn = await self.llm.complete(messages, openai_tools)
                        except APIError as exc:
                            return {
                                "ok": False,
                                "error": "llm_error",
                                "message": f"The language model request failed: {exc}",
                                "answer": None,
                                "trace": [event.as_dict() for event in trace],
                                "correlation_id": correlation_id,
                            }
                        except Exception as exc:
                            return {
                                "ok": False,
                                "error": "llm_error",
                                "message": f"The language model request failed: {exc}",
                                "answer": None,
                                "trace": [event.as_dict() for event in trace],
                                "correlation_id": correlation_id,
                            }

                        if not turn.tool_calls:
                            answer = (turn.content or "").strip()
                            if not answer:
                                answer = (
                                    "The model returned an empty answer after consulting the KPI tools. "
                                    "Try rephrasing the question."
                                )
                            return {
                                "ok": True,
                                "answer": answer,
                                "trace": [event.as_dict() for event in trace],
                                "correlation_id": correlation_id,
                                "rounds": round_index + 1,
                            }

                        assistant_message: dict[str, Any] = {
                            "role": "assistant",
                            "content": turn.content or "",
                            "tool_calls": [
                                {
                                    "id": call.id,
                                    "type": "function",
                                    "function": {
                                        "name": call.name,
                                        "arguments": call.arguments,
                                    },
                                }
                                for call in turn.tool_calls
                            ],
                        }
                        messages.append(assistant_message)

                        for call in turn.tool_calls:
                            tool_calls_used += 1
                            if tool_calls_used > self.settings.max_tool_calls:
                                raise ToolLoopLimit(
                                    f"Stopped after {self.settings.max_tool_calls} tool calls "
                                    "to prevent an unbounded loop.",
                                    trace=[event.as_dict() for event in trace],
                                )
                            arguments = parse_arguments(call.arguments)
                            started = time.perf_counter()
                            if "_parse_error" in arguments:
                                payload = {
                                    "ok": False,
                                    "error": "invalid_arguments",
                                    "message": "Tool arguments were not valid JSON. Resend a JSON object.",
                                }
                                ok = False
                                error = "invalid_arguments"
                            else:
                                try:
                                    result = await client.call_tool(
                                        call.name,
                                        arguments,
                                        raise_on_error=False,
                                    )
                                    if result.data is not None:
                                        payload = result.data
                                    elif result.content:
                                        payload = {"result": result.content[0].text}
                                    else:
                                        payload = {"ok": False, "error": "empty_tool_result"}
                                    if result.is_error:
                                        ok = False
                                        error = "tool_error"
                                        payload = {
                                            "ok": False,
                                            "error": "tool_error",
                                            "message": result.content[0].text if result.content else "Tool failed",
                                        }
                                    else:
                                        ok = not (
                                            isinstance(payload, dict) and payload.get("ok") is False
                                        )
                                        error = (
                                            payload.get("error")
                                            if isinstance(payload, dict) and not ok
                                            else None
                                        )
                                except Exception as exc:
                                    payload = {
                                        "ok": False,
                                        "error": "tool_error",
                                        "message": f"MCP tool {call.name} failed: {exc}",
                                    }
                                    ok = False
                                    error = "tool_error"

                            duration_ms = (time.perf_counter() - started) * 1000
                            trace.append(
                                TraceEvent(
                                    tool=call.name,
                                    arguments=redact(arguments),
                                    ok=ok,
                                    duration_ms=duration_ms,
                                    error=error,
                                )
                            )
                            log_tool_call(
                                logger,
                                tool=call.name,
                                arguments=arguments,
                                outcome="ok" if ok else (error or "error"),
                                duration_ms=duration_ms,
                                error=error,
                            )
                            messages.append(
                                {
                                    "role": "tool",
                                    "tool_call_id": call.id,
                                    "content": json.dumps(payload, default=str),
                                }
                            )

                    raise ToolLoopLimit(
                        f"Stopped after {self.settings.max_tool_rounds} model rounds "
                        "without a final answer.",
                        trace=[event.as_dict() for event in trace],
                    )
            except ToolLoopLimit:
                raise
            except MCPUnavailable:
                raise
            except Exception as exc:
                raise MCPUnavailable(
                    f"Could not connect to the MCP server at {self.settings.mcp_url}: {exc}"
                ) from exc
        finally:
            correlation_id_var.reset(token)
