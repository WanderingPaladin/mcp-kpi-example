# Investor KPI Assistant

Chat UI for public-investor KPI estimates. A customer asks a question, an LLM calls read-only MCP tools, and the answer is grounded in PostgreSQL. External clients (Cursor, Claude Desktop, FastMCP) can attach to the MCP server directly.

**You must run three processes and leave those terminals open:** Vite (5173), chat API (8000), MCP server (8001). Closing a window stops that process. Closing PowerShell also deactivates the Python virtualenv; installed packages are still on disk.

## What you need

| Tool | Why |
| --- | --- |
| **Git** | Clone the repo |
| **Python 3.12+** | Backend, MCP server, seed, tests (`python` on Windows, `python3` on macOS/Linux) |
| **Node.js 18+ and npm** | React / Vite frontend |
| **Docker Desktop** (or Postgres 16) | Database. Compose creates user/password/db `kpi` / `kpi` / `kpi` on port `5432` |
| **OpenAI API key** | Live chat. Without it the UI loads but chat returns a setup error and will not invent numbers |

You do **not** need Redis, nginx, or Claude Desktop unless you want an external MCP client.

## One-time setup (Windows PowerShell)

Run these from the **repo root** (`mcp-kpi-example`).

```powershell
docker compose up -d postgres

python -m venv backend\.venv
backend\.venv\Scripts\Activate.ps1
pip install -r backend\requirements.txt

copy .env.example .env
notepad .env
# set OPENAI_API_KEY=sk-... then save

cd backend
python -m app.seed
```

The seed command is `python -m app.seed` **inside `backend`**. `python -m seed` from the repo root will fail.

If activation is blocked (`running scripts is disabled`):

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
backend\.venv\Scripts\Activate.ps1
```

Success for seed: `Imported 2000 KPI records from ...\data\kpi_sample_2000.csv`.

### macOS / Linux

```bash
docker compose up -d postgres
python3 -m venv backend/.venv
source backend/.venv/bin/activate
pip install -r backend/requirements.txt
cp .env.example .env   # then set OPENAI_API_KEY
cd backend
python -m app.seed
```

## Every time you run the app

You need **three terminals**. In **each** new PowerShell, from the repo root:

```powershell
backend\.venv\Scripts\Activate.ps1
```

The prompt should show `(.venv)`. Confirm:

```powershell
python -c "import sys; print(sys.executable)"
```

That path must contain `backend\.venv`.

**Terminal 1 — MCP server** (leave open)

```powershell
cd backend
python -m app.mcp_server --transport http
```

Expect `http://127.0.0.1:8001/mcp`. Health: http://127.0.0.1:8001/health

**Terminal 2 — chat API** (leave open)

```powershell
cd backend
python -m app.main
```

Health: http://127.0.0.1:8000/api/health

**Terminal 3 — frontend** (leave open)

```powershell
cd frontend
npm install
npm run dev -- --host 127.0.0.1 --port 5173
```

`npm install` is only needed the first time, or after pulling dependency changes.

Open **http://127.0.0.1:5173/** in the browser. Prefer `127.0.0.1` over `localhost` on Windows (localhost can hit IPv6 `::1` while Vite is on IPv4).

| Port | Process |
| --- | --- |
| 5432 | PostgreSQL |
| 8001 | MCP server |
| 8000 | FastAPI chat |
| 5173 | Vite frontend |

If `OPENAI_API_KEY` is empty, the UI shows a setup banner and `/api/chat` returns `503 llm_not_configured`. That is intentional.

## If you closed PowerShell

Nothing you `pip install`ed was deleted. Only the session died.

1. Open a new PowerShell in the repo root.
2. `backend\.venv\Scripts\Activate.ps1`
3. Re-run seed only if you never imported data (`cd backend; python -m app.seed`).
4. Start the three processes again.

If `backend\.venv` does not exist, redo the one-time setup.

## Troubleshooting

| What you see | Likely cause | Fix |
| --- | --- | --- |
| `No module named seed` | Wrong module, or not in `backend` | `cd backend` then `python -m app.seed` |
| `No module named app` | Current directory is not `backend` | `cd backend` |
| `No module named sqlalchemy` / `fastapi` | venv not active, or wrong `python` | Activate `backend\.venv`, check `sys.executable` |
| `connection refused` to Postgres / auth failed | Database not running | `docker compose up -d postgres` from repo root |
| Browser `ERR_CONNECTION_REFUSED` on 5173 | Vite is not running, or wrong host | Restart `npm run dev` in `frontend`; open http://127.0.0.1:5173/ |
| Vite printed port **5174** | 5173 already in use | Use the URL Vite printed, or free 5173 |
| Chat banner “LLM key missing” | `.env` has no `OPENAI_API_KEY`, or API started before you saved `.env` | Edit `.env`, restart `python -m app.main` |
| Chat error about MCP unavailable | Terminal 1 is not running | Start `python -m app.mcp_server --transport http` |
| `Activate.ps1` cannot run | PowerShell execution policy | `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass` |

Check listeners on Windows:

```powershell
netstat -ano | findstr "5173 8000 8001 5432"
```

## Tests

From a shell with the venv activated:

```powershell
cd backend
python -m pytest -q
```

## Connecting an external AI client

MCP is available over **Streamable HTTP** at `http://127.0.0.1:8001/mcp` (while terminal 1 is running) or **stdio**.

### Cursor / Claude Desktop (stdio)

Windows example (`claude_desktop_config.json` or Cursor MCP settings). Use your real clone path and keep `cwd` on `backend`:

```json
{
  "mcpServers": {
    "yipitdata-kpi": {
      "command": "C:\\ABS\\PATH\\mcp-kpi-example\\backend\\.venv\\Scripts\\python.exe",
      "args": ["-m", "app.mcp_server", "--transport", "stdio"],
      "cwd": "C:\\ABS\\PATH\\mcp-kpi-example\\backend",
      "env": {
        "DATABASE_URL": "postgresql+psycopg://kpi:kpi@localhost:5432/kpi"
      }
    }
  }
}
```

macOS / Linux: point `command` at `backend/.venv/bin/python` and `cwd` at `backend`.

### HTTP client

```json
{
  "mcpServers": {
    "yipitdata-kpi": {
      "url": "http://127.0.0.1:8001/mcp"
    }
  }
}
```

Python (venv activated, MCP HTTP server already running):

```python
import asyncio
from fastmcp import Client

async def main():
    async with Client("http://127.0.0.1:8001/mcp") as client:
        print(await client.list_tools())
        print(await client.call_tool("search_catalog", {"query": "IGC"}))

asyncio.run(main())
```

Repo helper:

```powershell
cd backend
python -m app.demo_mcp_client
python -m app.demo_mcp_client --in-process
```

| Tool | Use when |
| --- | --- |
| `search_catalog` | Discover sectors, companies, tickers, KPI names |
| `get_company_estimates` | History plus the **latest** QTD snapshot (`max(as_of)` per company/KPI/period) |
| `get_qtd_snapshots` | Drill into earlier dated QTD prints |

Unknown tickers, misspelled KPIs, bad periods, and unknown sectors return `{ok: false, error, message, suggestions}` so an agent can recover.

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

Query logic lives in `KpiService`, not in the chat loop. MCP tools are a thin, logged façade. The chat API is an MCP **client**; it does not query Postgres itself.

```
data/kpi_sample_2000.csv
docker-compose.yml
.env.example
backend/app/models.py
backend/app/seed.py
backend/app/services/kpi.py
backend/app/mcp_server.py
backend/app/chat.py
backend/app/main.py
backend/app/demo_mcp_client.py
frontend/
```

## Data assumptions

- Sample CSV has **2,000** rows: 20 companies × 5 KPIs × 16 historical quarters (2022Q1–2025Q4) plus four 2026Q1 QTD snapshots.
- Latest QTD snapshot is **2026-03-15**. It is not “current” relative to today. Always show fiscal period and `as_of`.
- Historical rows have `as_of = NULL` (completed quarter). QTD rows always have `as_of`.
- Values are `NUMERIC(18, 2)` with the CSV `unit` (`$`, `$MM`, `subs`, `units`).
- Uniqueness: `(ticker, kpi, period, estimate_type, as_of)` with `NULLS NOT DISTINCT`, plus a check that historical/QTD nullability matches the type.
- QTD is **intra-quarter**. The app does not treat it as a finished quarter, does not infer a subscriber growth rate from net-added subscribers, and does not extrapolate a full-quarter value unless that math is explicit and labeled.

## Example investor questions

- What is IGC’s QTD total revenue for 2026Q1?
- Show CloudNine SaaS (`CLD9`) historical Global Net Added Subscribers versus the latest QTD snapshot.
- How did IGC’s QTD revenue change across `as_of` dates in 2026Q1?
- What KPIs does YipitData cover in Software?
- Compare ACME ASP in 2025Q4 (historical) with 2026Q1 QTD as of 2026-03-15.

## Design decisions and trade-offs

1. **Three tools, not a REST mirror.** `search_catalog` / `get_company_estimates` / `get_qtd_snapshots` match how an LLM hunts: discover, fetch the working set, drill into QTD.
2. **Shared service behind MCP.** Chat never imports SQL. Swap stdio/HTTP or add tenants later without duplicating queries.
3. **Recoverable tool errors over thrown exceptions.** Structured `ok: false` plus suggestions lets the model retry. Ambiguous aliases such as “subscribers” are not auto-resolved.
4. **Latest QTD is `max(as_of)`, never `CURRENT_DATE`.** This sample would otherwise look stale after March 2026.
5. **Chat is a real MCP client.** Tests inject the in-process FastMCP `Client`; production uses Streamable HTTP. Missing API key does not fall back to scripted answers.
6. **Loop guards.** `MAX_TOOL_ROUNDS` (default 6) and `MAX_TOOL_CALLS` (default 12). Failures return the trace rather than a made-up number.
7. **No login** (assignment exclusion). Production boundaries are sketched below rather than faked.

Trade-off: HTTP MCP on localhost is easy to demo and attach Cursor to; stdio is what many desktop hosts still expect, so both are supported. History for one company/KPI is small here; `limit` is still enforced so a wider catalog cannot dump unbounded JSON into the model.

## Observability, tenancy, and security (not built)

- **Tenant isolation.** Rows are global today. Production would add `tenant_id` (or product entitlement), set it from a verified credential *before* tool dispatch, and use Postgres RLS so the MCP process cannot read another tenant even if a prompt injects a ticker. Do not let the LLM pass `tenant_id`.
- **Security boundary.** The model only sees tool JSON. It never gets `DATABASE_URL` or `OPENAI_API_KEY`. MCP should stay read-only. Prompt injection is contained by: no write tools, bounded result size, and refusing to answer from the model’s prior knowledge.
- **Monitoring / auditing.** Each tool log line has `tool`, redacted `arguments`, `outcome`, `duration_ms`, and `correlation_id`. Production would ship those to an audit store, add OpenTelemetry traces spanning chat → MCP → SQL, and alert on error rate, loop-limit hits, and P95 latency. The UI tool trace is the human-facing subset of the same events.

## Future improvements

- Stream assistant tokens and tool events over SSE.
- Entitlements for which products/KPIs a customer may see.
- Materialized “latest QTD” view if snapshot volume grows past daily.
- KPI aliases in the database rather than Python.
- Eval set of investor questions with golden tool traces.
- Rate limits and per-tenant quotas on MCP.

## Where AI helped vs deliberate decisions

AI was used as a coding partner: scaffolding FastAPI/Vite files, drafting tests, and shaping README prose. Installed APIs were still checked (`fastmcp` 4.x `Client.call_tool`, OpenAI 3.x nested `tools[].function`, SQLAlchemy `postgresql_nulls_not_distinct`) instead of guessed.

Deliberate choices:

- Tool schemas and the “latest QTD ≠ today” rule
- Structured recoverable errors (unknown ticker/KPI, ambiguous subscribers)
- Shared `KpiService` as the only SQL owner
- Chat as an MCP client with loop caps and no silent LLM fallback
- Uniqueness + historical/QTD check constraints
- Logging redaction and correlation IDs without putting secrets in tool arguments

## Limitations

- Chat quality depends on a real `OPENAI_API_KEY`; tests mock the LLM.
- Compose runs Postgres only; the app processes are started locally as above.
- Sample coverage is 20 fictional companies and five KPIs.
