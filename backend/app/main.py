from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import text

from app.chat import ChatService, LLMNotConfigured, MCPUnavailable, OpenAILLM, ToolLoopLimit
from app.config import Settings, get_settings
from app.db import configure_engine, get_engine, init_db
from app.logging_utils import configure_logging, new_correlation_id
from fastmcp import Client

logger = logging.getLogger("kpi.api")


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)


def make_mcp_client() -> Client:
    return Client(get_settings().mcp_url)


def build_chat_service(settings: Settings) -> ChatService:
    llm = None
    if settings.llm_configured:
        llm = OpenAILLM(
            api_key=settings.openai_api_key or "",
            model=settings.openai_model,
            base_url=settings.openai_base_url,
        )
    return ChatService(settings=settings, llm=llm, mcp_factory=make_mcp_client)


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    settings = get_settings()
    configure_engine(settings.database_url)
    init_db()
    app.state.settings = settings
    app.state.chat_service = build_chat_service(settings)
    logger.info("chat_api_started", extra={"mcp_url": settings.mcp_url})
    yield


app = FastAPI(title="YipitData KPI Chat API", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health() -> dict[str, Any]:
    database = False
    try:
        with get_engine().connect() as connection:
            connection.execute(text("SELECT 1"))
            database = True
    except Exception:
        database = False
    settings = get_settings()
    return {
        "status": "ok" if database else "degraded",
        "database": database,
        "llm_configured": settings.llm_configured,
        "mcp_url": settings.mcp_url,
    }


@app.post("/api/chat")
async def chat(payload: ChatRequest, request: Request) -> dict[str, Any]:
    correlation_id = request.headers.get("x-correlation-id") or new_correlation_id()
    service: ChatService = request.app.state.chat_service
    try:
        return await service.reply(payload.message.strip(), correlation_id)
    except LLMNotConfigured as exc:
        raise HTTPException(
            status_code=503,
            detail={
                "error": "llm_not_configured",
                "message": str(exc),
                "correlation_id": correlation_id,
            },
        ) from exc
    except MCPUnavailable as exc:
        raise HTTPException(
            status_code=503,
            detail={
                "error": "mcp_unavailable",
                "message": str(exc),
                "correlation_id": correlation_id,
            },
        ) from exc
    except ToolLoopLimit as exc:
        raise HTTPException(
            status_code=409,
            detail={
                "error": "tool_loop_limit",
                "message": str(exc),
                "trace": exc.trace,
                "correlation_id": correlation_id,
            },
        ) from exc


@app.exception_handler(HTTPException)
async def http_exception_handler(_request: Request, exc: HTTPException) -> JSONResponse:
    if isinstance(exc.detail, dict):
        return JSONResponse(status_code=exc.status_code, content=exc.detail)
    return JSONResponse(status_code=exc.status_code, content={"message": exc.detail})


def main() -> None:
    import uvicorn

    settings = get_settings()
    uvicorn.run(
        "app.main:app",
        host=settings.chat_host,
        port=settings.chat_port,
        reload=False,
    )


if __name__ == "__main__":
    main()
