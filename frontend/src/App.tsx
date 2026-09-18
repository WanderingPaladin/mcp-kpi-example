import { FormEvent, useEffect, useMemo, useState } from "react";

type TraceEvent = {
  tool: string;
  arguments: Record<string, unknown>;
  ok: boolean;
  duration_ms: number;
  error?: string;
};

type ChatMessage = {
  role: "user" | "assistant";
  content: string;
  trace?: TraceEvent[];
  error?: boolean;
};

type Health = {
  status: string;
  database: boolean;
  llm_configured: boolean;
  mcp_url: string;
};

const EXAMPLES = [
  "What is IGC's QTD total revenue for 2026Q1?",
  "Show CloudNine SaaS historical subscribers versus the latest QTD snapshot.",
  "How did IGC's QTD revenue change across as_of dates in 2026Q1?",
  "What KPIs does YipitData cover for the Software sector?",
];

function errorMessage(payload: unknown, fallback: string): string {
  if (payload && typeof payload === "object") {
    const record = payload as Record<string, unknown>;
    if (typeof record.message === "string") return record.message;
    if (typeof record.detail === "string") return record.detail;
    if (record.detail && typeof record.detail === "object") {
      const detail = record.detail as Record<string, unknown>;
      if (typeof detail.message === "string") return detail.message;
    }
  }
  return fallback;
}

export default function App() {
  const [health, setHealth] = useState<Health | null>(null);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      role: "assistant",
      content:
        "Ask about a company or KPI. Answers are grounded in MCP tool results and include fiscal period, units, and as_of dates. QTD in this sample is 2026Q1, latest snapshot 2026-03-15 — not “current” relative to today.",
    },
  ]);

  useEffect(() => {
    fetch("/api/health")
      .then(async (response) => {
        const payload = (await response.json()) as Health;
        setHealth(payload);
      })
      .catch(() => {
        setHealth({
          status: "down",
          database: false,
          llm_configured: false,
          mcp_url: "unreachable",
        });
      });
  }, []);

  const llmReady = Boolean(health?.llm_configured);
  const statusPills = useMemo(
    () => [
      { label: `DB ${health?.database ? "ok" : "down"}`, ok: Boolean(health?.database) },
      { label: health?.llm_configured ? "LLM configured" : "LLM key missing", ok: llmReady },
      { label: "MCP via chat API", ok: health?.status !== "down" },
    ],
    [health, llmReady],
  );

  async function send(text: string) {
    const question = text.trim();
    if (!question || busy) return;
    setBusy(true);
    setInput("");
    setMessages((current) => [...current, { role: "user", content: question }]);
    try {
      const response = await fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: question }),
      });
      const payload = await response.json();
      if (!response.ok) {
        setMessages((current) => [
          ...current,
          {
            role: "assistant",
            error: true,
            content: errorMessage(payload, "The chat API returned an error."),
            trace: Array.isArray(payload.trace) ? payload.trace : undefined,
          },
        ]);
        return;
      }
      setMessages((current) => [
        ...current,
        {
          role: "assistant",
          content: payload.answer || "No answer returned.",
          trace: payload.trace,
        },
      ]);
    } catch (error) {
      setMessages((current) => [
        ...current,
        {
          role: "assistant",
          error: true,
          content:
            error instanceof Error
              ? error.message
              : "Network error talking to the chat API. Is the FastAPI server running?",
        },
      ]);
    } finally {
      setBusy(false);
    }
  }

  function onSubmit(event: FormEvent) {
    event.preventDefault();
    void send(input);
  }

  return (
    <div className="shell">
      <header className="header">
        <div>
          <p className="kicker">YipitData portal</p>
          <h1>Investor KPI Assistant</h1>
          <p className="lede">
            Natural-language questions for public-investor estimates. The model can only
            answer by calling read-only MCP tools against PostgreSQL.
          </p>
        </div>
        <div className="status">
          {statusPills.map((pill) => (
            <span key={pill.label} className={pill.ok ? "pill ok" : "pill warn"}>
              {pill.label}
            </span>
          ))}
        </div>
      </header>

      {!llmReady && (
        <div className="banner">
          OPENAI_API_KEY is not configured. Copy <code>.env.example</code> to{" "}
          <code>.env</code>, add a key, and restart the chat API. The app will not
          fabricate KPI answers without a model.
        </div>
      )}

      <div className="examples">
        {EXAMPLES.map((example) => (
          <button key={example} className="chip" type="button" onClick={() => void send(example)}>
            {example}
          </button>
        ))}
      </div>

      <div className="transcript">
        {messages.map((message, index) => (
          <article
            key={`${message.role}-${index}`}
            className={`msg ${message.role}${message.error ? " error" : ""}`}
          >
            {message.content}
            {message.trace && message.trace.length > 0 && (
              <details className="trace">
                <summary>Tool trace ({message.trace.length})</summary>
                <ol>
                  {message.trace.map((event, eventIndex) => (
                    <li key={`${event.tool}-${eventIndex}`}>
                      <strong>{event.tool}</strong> {event.ok ? "ok" : event.error} ·{" "}
                      {event.duration_ms} ms
                      <pre>{JSON.stringify(event.arguments, null, 2)}</pre>
                    </li>
                  ))}
                </ol>
              </details>
            )}
          </article>
        ))}
      </div>

      <form className="composer" onSubmit={onSubmit}>
        <textarea
          value={input}
          onChange={(event) => setInput(event.target.value)}
          placeholder="Ask about a ticker, KPI, or 2026Q1 QTD snapshot…"
          onKeyDown={(event) => {
            if (event.key === "Enter" && !event.shiftKey) {
              event.preventDefault();
              void send(input);
            }
          }}
        />
        <button type="submit" disabled={busy || !input.trim()}>
          {busy ? "Working" : "Send"}
        </button>
      </form>
    </div>
  );
}
