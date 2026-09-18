"""Generate anonymous review PDFs for the Greenhouse ZIP. No candidate name."""

from __future__ import annotations

from pathlib import Path

from reportlab.lib.colors import HexColor
from reportlab.lib.enums import TA_JUSTIFY, TA_LEFT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    KeepTogether,
    Paragraph,
    Preformatted,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

OUT = Path(__file__).resolve().parent
NAVY = HexColor("#10202b")
GOLD = HexColor("#8a6d2f")
LINE = HexColor("#c9d3d8")
MUTED = HexColor("#4a5b64")


def styles():
    base = getSampleStyleSheet()
    return {
        "kicker": ParagraphStyle(
            "kicker",
            parent=base["Normal"],
            textColor=GOLD,
            fontName="Times-Bold",
            fontSize=9,
            tracking=1,
            spaceAfter=4,
        ),
        "title": ParagraphStyle(
            "title",
            parent=base["Title"],
            fontName="Times-Bold",
            fontSize=18,
            textColor=NAVY,
            alignment=TA_LEFT,
            spaceAfter=8,
            leading=22,
        ),
        "h": ParagraphStyle(
            "h",
            parent=base["Heading2"],
            fontName="Times-Bold",
            fontSize=12,
            textColor=NAVY,
            spaceBefore=12,
            spaceAfter=6,
        ),
        "body": ParagraphStyle(
            "body",
            parent=base["Normal"],
            fontName="Times-Roman",
            fontSize=10,
            leading=14,
            alignment=TA_JUSTIFY,
            textColor=NAVY,
            spaceAfter=8,
        ),
        "bullet": ParagraphStyle(
            "bullet",
            parent=base["Normal"],
            fontName="Times-Roman",
            fontSize=10,
            leading=13,
            leftIndent=12,
            textColor=NAVY,
            spaceAfter=3,
        ),
        "code": ParagraphStyle(
            "code",
            parent=base["Code"],
            fontName="Courier",
            fontSize=8,
            leading=11,
            textColor=NAVY,
            backColor=HexColor("#f4f6f7"),
            spaceAfter=8,
            spaceBefore=4,
        ),
        "foot": ParagraphStyle(
            "foot",
            parent=base["Normal"],
            fontName="Times-Italic",
            fontSize=8,
            textColor=MUTED,
        ),
        "cell": ParagraphStyle(
            "cell",
            parent=base["Normal"],
            fontName="Times-Roman",
            fontSize=8.5,
            leading=11,
            textColor=NAVY,
        ),
        "cellh": ParagraphStyle(
            "cellh",
            parent=base["Normal"],
            fontName="Times-Bold",
            fontSize=8.5,
            leading=11,
            textColor=NAVY,
        ),
    }


def footer(canvas, doc):
    canvas.saveState()
    canvas.setStrokeColor(LINE)
    canvas.line(0.75 * inch, 0.55 * inch, 7.75 * inch, 0.55 * inch)
    canvas.setFont("Times-Roman", 8)
    canvas.setFillColor(MUTED)
    canvas.drawString(0.75 * inch, 0.38 * inch, "Investor KPI Assistant — anonymous review packet")
    canvas.drawRightString(7.75 * inch, 0.38 * inch, f"{doc.page}")
    canvas.restoreState()


def bullets(items, sty):
    return KeepTogether(
        [Paragraph(f"- {item}", sty["bullet"]) for item in items] + [Spacer(1, 4)]
    )


def table(rows, sty, col_widths):
    data = [
        [Paragraph(cell, sty["cellh"] if r == 0 else sty["cell"]) for cell in row]
        for r, row in enumerate(rows)
    ]
    t = Table(data, colWidths=col_widths)
    t.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), HexColor("#e8eef1")),
                ("GRID", (0, 0), (-1, -1), 0.4, LINE),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    return t


def build_doc(path: Path, story):
    doc = SimpleDocTemplate(
        str(path),
        pagesize=letter,
        leftMargin=0.75 * inch,
        rightMargin=0.75 * inch,
        topMargin=0.7 * inch,
        bottomMargin=0.75 * inch,
        title={
            "DESIGN.pdf": "Investor KPI Assistant design packet",
            "RUNBOOK.pdf": "Investor KPI Assistant runbook",
            "DATA-NOTES.pdf": "Investor KPI Assistant data notes",
        }.get(path.name, path.stem),
        author="",
        creator="Investor KPI Assistant review packet",
    )
    doc.build(story, onFirstPage=footer, onLaterPages=footer)


def design_pdf(sty):
    s = []
    s += [
        Paragraph("PUBLIC INVESTOR EXERCISE", sty["kicker"]),
        Paragraph("Investor KPI Assistant — Design and review packet", sty["title"]),
        Paragraph(
            "This PDF is the written submission for the agent-platform exercise. "
            "The working application is in the accompanying source folder. "
            "No candidate name appears on these materials. KPI figures come from the "
            "provided 2,000-row sample CSV loaded into PostgreSQL; there is no separate "
            "Excel model because the assignment is a software system, not a spreadsheet forecast.",
            sty["body"],
        ),
        Paragraph("1. Product", sty["h"]),
        Paragraph(
            "Time-constrained public-investor customers ask natural-language questions "
            "about YipitData-style KPI estimates (historical fiscal quarters and dated "
            "quarter-to-date snapshots). A React chat UI talks to a FastAPI orchestrator. "
            "The orchestrator is an MCP client: a configured LLM may call only the "
            "read-only tools on a Python MCP server. Those tools query a shared service "
            "over PostgreSQL. An external client (Cursor, Claude Desktop, or FastMCP) "
            "can attach to the same MCP server without going through the chat UI. "
            "Login was excluded by the assignment and is not built.",
            sty["body"],
        ),
        Paragraph("2. Architecture", sty["h"]),
        Preformatted(
            "React chat UI -- HTTP /api/chat --> FastAPI chat API -- tools --> LLM\n"
            "                                      |\n"
            "                                      +-- FastMCP Client -- HTTP /mcp or stdio --> MCP\n"
            "External MCP client -----------------/                                          |\n"
            "                                                                         KpiService\n"
            "                                                                              |\n"
            "                                                                         PostgreSQL",
            sty["code"],
        ),
        Paragraph(
            "The important split: SQL lives only in KpiService. MCP tools are a thin, "
            "logged façade. The chat API does not query the database. That is the "
            "security boundary between the model and the data layer.",
            sty["body"],
        ),
        Paragraph("3. How to run (Windows first)", sty["h"]),
        Paragraph(
            "Prerequisites: Git, Python 3.12+, Node.js 18+ / npm, Docker Desktop "
            "(or local PostgreSQL 16 with user/password/database kpi/kpi/kpi on port 5432), "
            "and an OpenAI API key for live chat. Three terminals must stay open.",
            sty["body"],
        ),
        Preformatted(
            "docker compose up -d postgres\n"
            "python -m venv backend\\.venv\n"
            "backend\\.venv\\Scripts\\Activate.ps1\n"
            "pip install -r backend\\requirements.txt\n"
            "copy .env.example .env     # set OPENAI_API_KEY, never commit .env\n"
            "cd backend\n"
            "python -m app.seed         # must be app.seed, from backend\\\n"
            "\n"
            "# three windows, venv activated in each:\n"
            "python -m app.mcp_server --transport http    # :8001/mcp\n"
            "python -m app.main                           # :8000\n"
            "cd ..\\frontend && npm install && npm run dev # :5173\n"
            "\n"
            "Open http://127.0.0.1:5173/  (prefer 127.0.0.1 over localhost on Windows)",
            sty["code"],
        ),
        table(
            [
                ["Port", "Process"],
                ["5432", "PostgreSQL"],
                ["8001", "MCP server (Streamable HTTP /mcp)"],
                ["8000", "FastAPI chat API"],
                ["5173", "Vite React UI"],
            ],
            sty,
            [1.2 * inch, 5.3 * inch],
        ),
        Spacer(1, 8),
        Paragraph(
            "If OPENAI_API_KEY is missing, the UI shows a setup error and does not invent KPI values. "
            "Tests use a mocked LLM and still exercise real MCP tool calls in-process.",
            sty["body"],
        ),
        Paragraph("4. Connecting an external MCP client", sty["h"]),
        Paragraph(
            "HTTP: http://127.0.0.1:8001/mcp while the MCP process is running. "
            "stdio: python -m app.mcp_server --transport stdio with cwd set to backend "
            "and DATABASE_URL pointing at the same Postgres. "
            "A helper client is python -m app.demo_mcp_client (HTTP) or --in-process.",
            sty["body"],
        ),
        Paragraph("5. Data rules (the “calculation” layer)", sty["h"]),
        Paragraph(
            "All numeric work is in the seeded table, not a workbook. The sample has "
            "2,000 rows: 20 companies × 5 KPIs × 16 historical quarters (2022Q1–2025Q4) "
            "plus four 2026Q1 QTD snapshots (as_of 2026-01-31, 2026-02-15, 2026-02-28, 2026-03-15).",
            sty["body"],
        ),
        bullets(
            [
                "Values stored as NUMERIC(18, 2) with the CSV unit ($, $MM, subs, units).",
                "Uniqueness: (ticker, kpi, period, estimate_type, as_of) with NULLS NOT DISTINCT.",
                "Historical rows have as_of NULL (completed quarter). QTD rows always have as_of.",
                "Latest QTD = max(as_of) per company/KPI/period. In this sample that is 2026-03-15, not “current” vs today.",
                "QTD is intra-quarter. The system does not treat it as a finished quarter, does not infer a subscriber growth rate from net-added subscribers, and does not extrapolate a full-quarter value unless that math is explicit and labeled.",
                "Worked example (source CSV): Imaginary Streaming Company (IGC), Total Revenue ($MM), 2026Q1 QTD as of 2026-03-15 = 627.45. Earlier snapshots: 263.09 (2026-01-31), 395.67 (2026-02-15), 503.52 (2026-02-28). 2022Q1 historical = 519.63 (no as_of).",
            ],
            sty,
        ),
        Paragraph("6. MCP tools", sty["h"]),
        table(
            [
                ["Tool", "When the model should call it"],
                ["search_catalog", "Discover sectors, companies, tickers, KPI names"],
                [
                    "get_company_estimates",
                    "History plus the latest QTD snapshot for a ticker",
                ],
                ["get_qtd_snapshots", "Earlier dated QTD prints / intra-quarter drill-down"],
            ],
            sty,
            [2.1 * inch, 4.4 * inch],
        ),
        Spacer(1, 8),
        Paragraph(
            "Unknown tickers, misspelled KPIs, bad periods, and unknown sectors return "
            "structured {ok: false, error, message, suggestions} so the model can recover. "
            "“Subscribers” is ambiguous and is not auto-resolved to one KPI.",
            sty["body"],
        ),
        Paragraph("7. Design decisions and trade-offs", sty["h"]),
        bullets(
            [
                "Three tools, not a REST mirror: discover, fetch the working set, drill into QTD.",
                "Shared KpiService behind MCP so chat never imports SQL.",
                "Recoverable tool errors instead of thrown ToolError, which looks like a crash to an agent.",
                "Latest QTD is max(as_of), never CURRENT_DATE.",
                "Chat is a real MCP client. Missing API key does not fall back to scripted answers.",
                "Loop guards: MAX_TOOL_ROUNDS=6 and MAX_TOOL_CALLS=12.",
                "No login (assignment exclusion). Production tenancy is described, not faked.",
                "Trade-off: HTTP MCP is easy to attach; stdio is still provided for desktop hosts. Result size is bounded with limit.",
            ],
            sty,
        ),
        Paragraph("8. Tenancy, security, monitoring (not built)", sty["h"]),
        Paragraph(
            "Today every row is global. Production would add tenant_id or product entitlement "
            "from a verified credential before tool dispatch, and Postgres RLS so the MCP "
            "process cannot read another tenant even if a prompt injects a ticker. The LLM "
            "must never pass tenant_id. The model only sees tool JSON — never DATABASE_URL "
            "or OPENAI_API_KEY. MCP stays read-only. Each tool log line has tool, redacted "
            "arguments, outcome, duration_ms, and correlation_id. The UI trace is the "
            "human-facing subset. Production would add an audit store, OpenTelemetry across "
            "chat → MCP → SQL, and alerts on error rate, loop-limit hits, and P95 latency.",
            sty["body"],
        ),
        Paragraph("9. Future improvements", sty["h"]),
        bullets(
            [
                "Stream tokens and tool events over SSE (perceived latency).",
                "Entitlements for which products/KPIs a customer may see.",
                "Materialized latest-QTD view if snapshots grow past daily.",
                "KPI aliases in the database rather than Python.",
                "Eval set of investor questions with golden tool traces.",
                "Rate limits and per-tenant quotas on MCP.",
            ],
            sty,
        ),
        Paragraph("10. AI use versus deliberate decisions", sty["h"]),
        Paragraph(
            "AI was used as a coding assistant: scaffolding FastAPI/Vite files, drafting tests, "
            "and shaping README prose. Installed library APIs were checked rather than guessed "
            "(FastMCP 4 Client.call_tool, OpenAI 3.x nested tools[].function, SQLAlchemy "
            "postgresql_nulls_not_distinct). The engineering exercise recommended this and "
            "asked for this section. This packet does not claim that AI was unused.",
            sty["body"],
        ),
        Paragraph(
            "Deliberate choices: tool schemas; latest QTD is not “today”; structured recoverable "
            "errors; KpiService as the only SQL owner; chat as an MCP client with loop caps "
            "and no silent LLM fallback; uniqueness and historical/QTD check constraints; "
            "log redaction without putting secrets in tool arguments.",
            sty["body"],
        ),
        Paragraph("11. Limits and verification", sty["h"]),
        bullets(
            [
                "24 automated tests passed (CSV import, latest QTD, history, suggestions, MCP tools, mocked LLM chat flow).",
                "Independent MCP client listed tools and returned IGC 627.45 $MM for 2026Q1 as of 2026-03-15.",
                "Without an API key, chat returns 503 llm_not_configured and does not fabricate data.",
                "Chat wait time is dominated by sequential OpenAI rounds, not Postgres. The UI shows model vs tool timings.",
                "Sample coverage is 20 fictional companies and five KPIs.",
            ],
            sty,
        ),
        Paragraph(
            "See RUNBOOK.pdf for the full local-run and troubleshooting text. "
            "See DATA-NOTES.pdf for the calculation/source-of-truth note requested alongside code.",
            sty["body"],
        ),
    ]
    return s


def runbook_pdf(sty):
    s = [
        Paragraph("PUBLIC INVESTOR EXERCISE", sty["kicker"]),
        Paragraph("Investor KPI Assistant — Runbook", sty["title"]),
        Paragraph(
            "Anonymous run instructions. Keep three processes open. Closing a terminal "
            "stops that process and, on Windows, deactivates the virtualenv. Installed "
            "packages remain on disk.",
            sty["body"],
        ),
        Paragraph("Prerequisites", sty["h"]),
        table(
            [
                ["Tool", "Why"],
                ["Git", "Obtain the source"],
                ["Python 3.12+", "Backend, MCP, seed, tests"],
                ["Node.js 18+ and npm", "React / Vite UI"],
                ["Docker Desktop or Postgres 16", "kpi/kpi/kpi on port 5432"],
                ["OpenAI API key", "Live chat only; not required for tests"],
            ],
            sty,
            [2.4 * inch, 4.1 * inch],
        ),
        Paragraph("One-time setup (PowerShell, repo root)", sty["h"]),
        Preformatted(
            "docker compose up -d postgres\n"
            "python -m venv backend\\.venv\n"
            "backend\\.venv\\Scripts\\Activate.ps1\n"
            "pip install -r backend\\requirements.txt\n"
            "copy .env.example .env\n"
            "# set OPENAI_API_KEY in .env, then:\n"
            "cd backend\n"
            "python -m app.seed",
            sty["code"],
        ),
        Paragraph(
            "If scripts are disabled: Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass. "
            "Seed success: Imported 2000 KPI records. Wrong command: python -m seed. "
            "Correct: python -m app.seed from backend\\.",
            sty["body"],
        ),
        Paragraph("Every session (three terminals)", sty["h"]),
        Preformatted(
            "backend\\.venv\\Scripts\\Activate.ps1\n"
            "cd backend && python -m app.mcp_server --transport http\n"
            "cd backend && python -m app.main\n"
            "cd frontend && npm run dev\n"
            "Browser: http://127.0.0.1:5173/",
            sty["code"],
        ),
        Paragraph("macOS / Linux", sty["h"]),
        Preformatted(
            "python3 -m venv backend/.venv\n"
            "source backend/.venv/bin/activate\n"
            "pip install -r backend/requirements.txt\n"
            "cp .env.example .env && cd backend && python -m app.seed",
            sty["code"],
        ),
        Paragraph("Troubleshooting", sty["h"]),
        table(
            [
                ["Symptom", "Fix"],
                ["No module named seed", "cd backend; python -m app.seed"],
                ["No module named app", "Current directory must be backend"],
                ["No module named sqlalchemy", "Activate backend\\.venv"],
                ["Postgres connection refused", "docker compose up -d postgres"],
                ["ERR_CONNECTION_REFUSED :5173", "Start npm run dev; use 127.0.0.1"],
                ["LLM key missing", "Set OPENAI_API_KEY and restart app.main"],
                ["MCP unavailable", "Start app.mcp_server on :8001"],
            ],
            sty,
            [2.6 * inch, 3.9 * inch],
        ),
        Paragraph("Tests and demo client", sty["h"]),
        Preformatted(
            "cd backend\n"
            "python -m pytest -q\n"
            "python -m app.demo_mcp_client\n"
            "python -m app.demo_mcp_client --in-process",
            sty["code"],
        ),
        Paragraph("External MCP", sty["h"]),
        Paragraph(
            "HTTP URL: http://127.0.0.1:8001/mcp. stdio command: the venv python with "
            "args -m app.mcp_server --transport stdio and cwd=backend. "
            "Optional local speed: MCP_IN_PROCESS=true on the chat API only.",
            sty["body"],
        ),
        Paragraph("Latency", sty["h"]),
        Paragraph(
            "Tool calls are milliseconds. Sequential OpenAI rounds are seconds. "
            "Ask with ticker + KPI to skip catalog lookup. Keep OPENAI_MODEL=gpt-4o-mini.",
            sty["body"],
        ),
    ]
    return s


def data_notes_pdf(sty):
    s = [
        Paragraph("PUBLIC INVESTOR EXERCISE", sty["kicker"]),
        Paragraph("Data and calculation notes", sty["title"]),
        Paragraph(
            "The submission email asked for calculation files (Excel and/or code). "
            "This exercise publishes estimates from a cleaned sample dataset. "
            "The calculation artifact is the CSV plus the seed/query code, not a workbook "
            "of invented forecasts.",
            sty["body"],
        ),
        Paragraph("Source file", sty["h"]),
        Paragraph(
            "data/kpi_sample_2000.csv — 2,000 records, columns: company_name, ticker, "
            "sector, kpi, period_start, period_end, period, estimate_type, value, unit, as_of.",
            sty["body"],
        ),
        Paragraph("How numbers are produced", sty["h"]),
        bullets(
            [
                "Repeatable load: python -m app.seed (reset + insert all 2,000 rows).",
                "No derived growth rate is stored. Net-added subscribers stay a count (unit: subs).",
                "Latest QTD selection is SQL window/order by as_of descending, not calendar “today”.",
                "Reviewers can recompute any figure by filtering the CSV on ticker, kpi, period, estimate_type, as_of.",
            ],
            sty,
        ),
        Paragraph("Reference figures used in tests (from the CSV)", sty["h"]),
        table(
            [
                ["Ticker / KPI", "Period", "Type", "as_of", "Value", "Unit"],
                ["IGC Total Revenue", "2026Q1", "qtd latest", "2026-03-15", "627.45", "$MM"],
                ["IGC Total Revenue", "2026Q1", "qtd", "2026-01-31", "263.09", "$MM"],
                ["IGC Total Revenue", "2026Q1", "qtd", "2026-02-15", "395.67", "$MM"],
                ["IGC Total Revenue", "2026Q1", "qtd", "2026-02-28", "503.52", "$MM"],
                ["IGC Total Revenue", "2022Q1", "historical", "—", "519.63", "$MM"],
                ["IGC Total Revenue", "2025Q4", "historical", "—", "945.3", "$MM"],
                ["ACME ASP", "2026Q1", "qtd latest", "2026-03-15", "164.22", "$"],
            ],
            sty,
            [1.6 * inch, 0.85 * inch, 1.05 * inch, 1.05 * inch, 0.85 * inch, 0.6 * inch],
        ),
        Spacer(1, 8),
        Paragraph(
            "These values are copied from the sample, not computed by extrapolation. "
            "A reviewer can open the CSV and match the same rows. Code that selects "
            "latest QTD is backend/app/services/kpi.py (latest as_of). Import is "
            "backend/app/seed.py. Tests in backend/tests/ lock these figures.",
            sty["body"],
        ),
        Paragraph("Central Data Team context (as applied)", sty["h"]),
        Paragraph(
            "The accompanying team overview was treated as background, not as a second "
            "spec. Applied assumptions: customers are public investors who need a short "
            "answer with units and dates; datasets are already cleaned and land in "
            "Postgres; QTD snapshots update at most daily; the assistant should reduce "
            "portal digging, not replace the warehouse; authentication is out of scope "
            "for this build but tenancy must be designed for later. No team member names "
            "or internal org details are repeated here.",
            sty["body"],
        ),
        Paragraph("What is intentionally absent", sty["h"]),
        bullets(
            [
                "No Excel forecast file — inventing one would contradict “do not extrapolate QTD”.",
                "No candidate name, resume, or personal metadata on this document.",
                "No API keys. .env is excluded from the ZIP; .env.example is included.",
            ],
            sty,
        ),
    ]
    return s


def main():
    sty = styles()
    OUT.mkdir(parents=True, exist_ok=True)
    build_doc(OUT / "DESIGN.pdf", design_pdf(sty))
    build_doc(OUT / "RUNBOOK.pdf", runbook_pdf(sty))
    build_doc(OUT / "DATA-NOTES.pdf", data_notes_pdf(sty))
    print("wrote", OUT / "DESIGN.pdf")
    print("wrote", OUT / "RUNBOOK.pdf")
    print("wrote", OUT / "DATA-NOTES.pdf")


if __name__ == "__main__":
    main()
