# Investor KPI Assistant

Full-stack take-home: a React chat UI for public investors, a FastAPI orchestrator, and a Python MCP server over PostgreSQL. An LLM can only answer after calling read-only MCP tools. External AI clients can attach to the MCP server directly.

## Architecture

```mermaid
flowchart LR
  subgraph Clients
    UI[React chat UI]
    Ext[External MCP client<br/>Claude Desktop / Cursor / FastMCP Client]
  end

  UI -->|HTTP POST /api/chat| API[FastAPI chat API]
  API -->|OpenAI-compatible tools| LLM[Configured LLM]
  API -->|FastMCP Client / Streamable HTTP| MCP[FastMCP KPI server]
  Ext -->|stdio or HTTP /mcp| MCP
  MCP --> Svc[Shared KpiService]
  Svc --> PG[(PostgreSQL)]
```

The important split: **query logic lives in `KpiService`**, not in the chat loop. MCP tools are a thin, logged façade. The chat API is an MCP *client*; it does not query Postgres itself. That is the security boundary the live review asks about.

## Repository layout

```
data/kpi_sample_2000.csv      # 2,000-row sample
docker-compose.yml            # PostgreSQL 16
.env.example
backend/app/models.py         # kpi_estimates table
backend/app/seed.py           # repeatable CSV import
backend/app/services/kpi.py   # catalog, history, latest QTD, snapshots
backend/app/mcp_server.py     # FastMCP tools over HTTP or stdio
backend/app/chat.py           # LLM + MCP tool loop
backend/app/main.py           # FastAPI
backend/app/demo_mcp_client.py
frontend/                     # Vite + React + TypeScript
```

## Setup and run

### 1. PostgreSQL

```bash
docker compose up -d postgres
```

Equivalent local database: user `kpi`, password `kpi`, database `kpi` on port `5432`.

### 2. Backend

```bash
python3 -m venv backend/.venv
source backend/.venv/bin/activate   # Windows: backend\.venv\Scripts\activate
pip install -r backend/requirements.txt
cp .env.example .env                # then set OPENAI_API_KEY
cd backend
python -m app.seed                  # imports all 2,000 rows; safe to re-run
```

### 3. MCP server (terminal 1)

```bash
cd backend
python -m app.mcp_server --transport http
# Streamable HTTP endpoint: http://127.0.0.1:8001/mcp
# Health: http://127.0.0.1:8001/health
```

### 4. Chat API (terminal 2)

```bash
cd backend
python -m app.main
# http://127.0.0.1:8000/api/health
```

### 5. Frontend (terminal 3)

```bash
cd frontend
npm install
npm run dev
# http://127.0.0.1:5173  (proxies /api to the chat backend)
```

If `OPENAI_API_KEY` is missing, the UI shows a setup banner and `/api/chat` returns `503 llm_not_configured`. The server will **not** invent KPI answers.

### Tests

```bash
cd backend
python -m pytest -q
```

### Independent MCP client

```bash
# Against a running HTTP server
cd backend && python -m app.demo_mcp_client

# In-process (no HTTP listener; uses the same tools and database)
cd backend && python -m app.demo_mcp_client --in-process
```

## Connecting an external AI client

The server speaks MCP over **Streamable HTTP** (`http://127.0.0.1:8001/mcp`) or **stdio**.

### Cursor / Claude Desktop (stdio)

Add to MCP config (Claude Desktop: `claude_desktop_config.json`; Cursor: MCP settings):

```json
{
  "mcpServers": {
    "yipitdata-kpi": {
      "command": "/ABS/PATH/mcp-kpi-example/backend/.venv/bin/python",
      "args": ["-m", "app.mcp_server", "--transport", "stdio"],
      "cwd": "/ABS/PATH/mcp-kpi-example/backend",
      "env": {
        "DATABASE_URL": "postgresql+psycopg://kpi:kpi@localhost:5432/kpi"
      }
    }
  }
}
```

### HTTP client (Cursor, FastMCP, or any Streamable HTTP MCP client)

```json
{
  "mcpServers": {
    "yipitdata-kpi": {
      "url": "http://127.0.0.1:8001/mcp"
    }
  }
}
```

Python:

```python
import asyncio
from fastmcp import Client

async def main():
    async with Client("http://127.0.0.1:8001/mcp") as client:
        print(await client.list_tools())
        print(await client.call_tool("search_catalog", {"query": "IGC"}))

asyncio.run(main())
```

Tools:

| Tool | Use when |
| --- | --- |
| `search_catalog` | Discover sectors, companies, tickers, KPI names |
| `get_company_estimates` | History + **latest** QTD snapshot (`as_of` max per company/KPI/period) |
| `get_qtd_snapshots` | Drill into earlier dated QTD prints |

Unknown tickers, misspelled KPIs, bad periods, and unknown sectors return structured `{ok: false, error, message, suggestions}` so an agent can recover.

## Data assumptions

- Sample CSV has **2,000** rows: 20 companies × 5 KPIs × 16 historical quarters (2022Q1–2025Q4) + four 2026Q1 QTD snapshots.
- Latest QTD snapshot is **2026-03-15**. It is not “current” relative to today. Always show fiscal period and `as_of`.
- Historical rows have `as_of = NULL` (completed quarter). QTD rows always have `as_of`.
- Values are `NUMERIC(18, 2)` with the CSV `unit` (`$`, `$MM`, `subs`, `units`).
- Uniqueness: `(ticker, kpi, period, estimate_type, as_of)` with `NULLS NOT DISTINCT`, plus a check that historical/QTD nullability matches the type.
- QTD is **intra-quarter**. The app does not treat it as a finished quarter, does not infer a subscriber growth rate from net-added subscribers, and does not extrapolate a full-quarter value unless a human/LLM explicitly labels that math.

## Example investor questions

- What is IGC’s QTD total revenue for 2026Q1?
- Show CloudNine SaaS (`CLD9`) historical Global Net Added Subscribers versus the latest QTD snapshot.
- How did IGC’s QTD revenue change across `as_of` dates in 2026Q1?
- What KPIs does YipitData cover in Software?
- Compare ACME ASP in 2025Q4 (historical) with 2026Q1 QTD as of 2026-03-15.

## Design decisions and trade-offs

1. **Three tools, not a REST mirror.** `search_catalog` / `get_company_estimates` / `get_qtd_snapshots` match how an LLM actually hunts: discover, fetch the working set, drill into QTD. A fourth “list sectors” tool would add tokens without new information.
2. **Shared service behind MCP.** Chat never imports SQL. That keeps the live-review story clean: swap stdio/HTTP, add tenants later, keep one query implementation.
3. **Recoverable tool errors over thrown exceptions.** FastMCP `ToolError` looks like a crash. Structured `ok: false` plus suggestions lets the model retry. Ambiguous aliases such as “subscribers” are *not* auto-resolved.
4. **Latest QTD is `max(as_of)`, never `CURRENT_DATE`.** The sample would otherwise look stale in 2026+.
5. **Chat is a real MCP client.** Tests can inject the in-process FastMCP `Client`; production uses Streamable HTTP. The LLM is not stubbed when the API key is missing.
6. **Loop guards.** `MAX_TOOL_ROUNDS` (default 6) and `MAX_TOOL_CALLS` (default 12) stop runaway tool use. Failures return the trace rather than a made-up number.
7. **No auth in this build** (assignment exclusion). Production boundaries are sketched below rather than faked with a login screen.

Trade-off: HTTP MCP on localhost is easy to demo and to attach Cursor to; stdio is what desktop hosts still expect, so both are supported. Trade-off: returning full history for one company/KPI is small here (~16 rows); `limit` is still enforced so a future wider catalog cannot dump unbounded JSON into the model.

## Observability, tenancy, and security (not built)

- **Tenant isolation.** Today every row is global. Production would add `tenant_id` (or product entitlement) on `kpi_estimates`, set it from a verified credential *before* tool dispatch, and use Postgres RLS so the MCP process cannot read another tenant even if a prompt injects a ticker. Do not let the LLM pass `tenant_id`.
- **Security boundary.** The model only sees tool JSON. It never gets `DATABASE_URL` or `OPENAI_API_KEY`. MCP should stay read-only, network-isolated, and (in prod) mTLS/OAuth to the chat orchestrator. Prompt injection is contained by: no write tools, bounded result size, and refusing to answer from the model’s prior knowledge.
- **Monitoring / auditing.** Each tool log line already has `tool`, redacted `arguments`, `outcome`, `duration_ms`, and `correlation_id`. Production would ship those to an audit store, add OpenTelemetry traces spanning chat round → MCP → SQL, and alert on error rate, loop-limit hits, and P95 tool latency. Chat traces shown in the UI are the human-facing subset of the same events.

## Future improvements

- Stream assistant tokens and tool events over SSE.
- Entitlements: which products/KPIs a customer may see.
- Materialized “latest QTD” view if snapshot volume grows past daily.
- Stronger KPI ontology (aliases maintained in-table, not in Python).
- Eval set of investor questions with golden tool traces.
- Rate limits and per-tenant quotas on MCP.

## Where AI helped vs deliberate decisions

AI was used as a coding partner: scaffolding FastAPI/Vite files, drafting tests, and shaping README prose. I still had to **read installed APIs** (`fastmcp` 4.x `Client.call_tool`, OpenAI 3.x nested `tools[].function`, SQLAlchemy `postgresql_nulls_not_distinct`) instead of guessing.

Deliberate, interview-relevant choices I would defend:

- Tool schemas and the “latest QTD ≠ today” rule
- Structured recoverable errors (unknown ticker/KPI, ambiguous subscribers)
- Shared `KpiService` as the only SQL owner
- Chat as an MCP client with loop caps and no silent LLM fallback
- Uniqueness + historical/QTD check constraints
- Logging redaction and correlation IDs without putting secrets in tool arguments

## Limitations

- Chat quality depends on a real `OPENAI_API_KEY`; CI uses a mocked LLM.
- No Docker image for the app processes (Compose is Postgres-only, per a simple local-run setup).
- Sample coverage is 20 fictional companies and five KPIs; catalog search is in-process filtering, which is enough at this size.
