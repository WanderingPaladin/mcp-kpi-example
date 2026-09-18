from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest
from fastapi.testclient import TestClient
from fastmcp import Client

from app.chat import ChatService, LLMTurn, ToolCall
from app.config import Settings
from app.main import app
from app.mcp_server import mcp


@dataclass
class ScriptedLLM:
    turns: list[LLMTurn]
    calls: list[dict[str, Any]] = field(default_factory=list)

    async def complete(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> LLMTurn:
        self.calls.append({"messages": messages, "tools": tools})
        if not self.turns:
            return LLMTurn(content="unexpected extra round")
        return self.turns.pop(0)


def _settings(**overrides) -> Settings:
    data = {
        "openai_api_key": "test-key",
        "max_tool_rounds": 6,
        "max_tool_calls": 12,
        "mcp_url": "in-process",
    }
    data.update(overrides)
    return Settings(**data)


@pytest.mark.asyncio
async def test_chat_tool_call_flow_with_mocked_llm(engine):
    llm = ScriptedLLM(
        turns=[
            LLMTurn(
                content="",
                tool_calls=[
                    ToolCall(
                        id="call_search",
                        name="search_catalog",
                        arguments='{"query": "IGC"}',
                    )
                ],
            ),
            LLMTurn(
                content="",
                tool_calls=[
                    ToolCall(
                        id="call_estimates",
                        name="get_company_estimates",
                        arguments='{"ticker": "IGC", "kpi": "Total Revenue ($MM)"}',
                    )
                ],
            ),
            LLMTurn(
                content=(
                    "IGC Total Revenue is 627.45 $MM QTD for fiscal 2026Q1 as of 2026-03-15. "
                    "That is an intra-quarter snapshot, not a completed quarter."
                )
            ),
        ]
    )
    service = ChatService(
        settings=_settings(),
        llm=llm,
        mcp_factory=lambda: Client(mcp),
    )
    result = await service.reply("What is IGC's QTD revenue?", "testcid1234")
    assert result["ok"] is True
    assert "627.45" in result["answer"]
    assert "2026Q1" in result["answer"]
    assert "2026-03-15" in result["answer"]
    assert [event["tool"] for event in result["trace"]] == [
        "search_catalog",
        "get_company_estimates",
    ]
    assert result["trace"][0]["arguments"]["query"] == "IGC"
    assert result["trace"][1]["arguments"]["ticker"] == "IGC"
    assert all(event["ok"] for event in result["trace"])
    assert len(llm.calls) == 3
    assert result["timings"]["total_ms"] >= 0
    assert result["timings"]["llm_ms"] >= 0
    assert result["rounds"] == 3


@pytest.mark.asyncio
async def test_chat_stops_unbounded_tool_loop(engine):
    repeating = ToolCall(
        id="loop",
        name="search_catalog",
        arguments='{"query": "IGC"}',
    )
    llm = ScriptedLLM(
        turns=[LLMTurn(content="", tool_calls=[repeating]) for _ in range(10)]
    )
    service = ChatService(
        settings=_settings(max_tool_rounds=2, max_tool_calls=4),
        llm=llm,
        mcp_factory=lambda: Client(mcp),
    )
    with pytest.raises(Exception) as exc_info:
        await service.reply("loop please", "loopcid")
    assert "Stopped after" in str(exc_info.value)


def test_chat_endpoint_requires_llm_key(engine):
    from app.config import get_settings

    get_settings.cache_clear()
    settings = Settings(openai_api_key=None)
    with TestClient(app) as client:
        app.state.chat_service = ChatService(
            settings=settings,
            llm=None,
            mcp_factory=lambda: Client(mcp),
        )
        response = client.post("/api/chat", json={"message": "How is IGC doing?"})
    assert response.status_code == 503
    body = response.json()
    assert body["error"] == "llm_not_configured"
    assert "OPENAI_API_KEY" in body["message"]
    get_settings.cache_clear()
