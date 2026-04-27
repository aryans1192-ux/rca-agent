# Delivery Operations RCA Agent

An AI agent that performs Root Cause Analysis on OR2A (Order Ready to Assignment) SLA breaches across Loadshare's Amazon quick-commerce network. Ops users ask questions in plain English; the agent queries real data, runs the diagnostic playbook, and returns structured root cause analysis — in seconds, without any SQL.

---

## The Problem

When a delivery store misses its OR2A SLA, an analyst has to:
1. Open a SQL editor and run 4+ queries across different tables
2. Cross-reference results against a diagnostic playbook (demand spike? pileup? supply gap?)
3. Write a summary report — for each store, for each problem hour

This takes 20–40 minutes per store, requires SQL skills, and happens *after* the damage is done. On a bad day there are dozens of stores with problem hours across 9 cities.

**This agent replaces that entire flow with a conversation.**

---

## What the Agent Does

The agent receives a plain-English question, decides which data to fetch, runs the RCA checks, and returns a structured answer. It supports multi-turn conversations — drill-downs, follow-ups, city/store context switches — all within one session.

```
User: "How did Bangalore do today?"
Agent: [calls get_city_summary] → weighted breach rate, avg OR2A, problem hour count

User: "Which stores were worst?"
Agent: [calls list_stores_in_city] → store list ranked by problem hours

User: "Run RCA for STORE_003"
Agent: [calls run_rca_for_store] → demand spike, pileup, supply checks per hour

User: "Walk me through just the morning hours"
Agent: filters the already-fetched data, explains hours 6–12
```

No query rewriting. No SQL. No re-explaining context on each turn.

---

## System Design

### Full stack

```
┌─────────────────────────────────────────────────────────┐
│  Browser                                                │
│  Streamlit UI  (frontend/app.py)                        │
│  port 8501                                              │
└────────────────────┬────────────────────────────────────┘
                     │ POST /chat  {session_id, message}
                     ▼
┌─────────────────────────────────────────────────────────┐
│  FastAPI  (api/)                                        │
│  port 8000                                              │
│  • Session store   (_sessions: dict[uuid → messages])   │
│  • History trim    (_trim: last 6 msgs, 300 char cap)   │
│  • Retry + timeout (75s per attempt, 2 retries on 429)  │
└────────────────────┬────────────────────────────────────┘
                     │ graph.ainvoke({messages})
                     ▼
┌─────────────────────────────────────────────────────────┐
│  LangGraph ReAct Loop  (agent/)                         │
│                                                         │
│   ┌──────────┐   tool_calls?   ┌──────────────────────┐ │
│   │  agent   │ ──────────────► │  ToolNode            │ │
│   │  node    │ ◄────────────── │  (MCP or direct)     │ │
│   └────┬─────┘   ToolMessage   └──────────────────────┘ │
│        │ no tool_calls                                  │
│        ▼                                               │
│      END                                               │
└────────────────────┬────────────────────────────────────┘
                     │
          ┌──────────┴──────────┐
          │                     │
          ▼                     ▼
┌──────────────────┐   ┌─────────────────────────────────┐
│  Direct tools    │   │  MCP server  (mcp_server/)       │
│  (agent/graph.py)│   │  FastMCP, port 8001              │
│  5 @tool fns     │   │  HTTP transport                  │
└────────┬─────────┘   └──────────────┬──────────────────┘
         │                            │
         └──────────┬─────────────────┘
                    │ both call
                    ▼
┌─────────────────────────────────────────────────────────┐
│  RCA Service  (services/rca_service.py)                 │
│  Composes repository queries + engine checks            │
└──────────────┬─────────────────────────────────────────┘
               │
     ┌─────────┴──────────┐
     ▼                    ▼
┌──────────────┐   ┌─────────────────────────────────────┐
│  Repository  │   │  RCA Engine  (core/rca_engine.py)   │
│  (db/)       │   │  Pure functions, zero I/O            │
│  DuckDB SQL  │   │  demand + pileup + supply checks     │
└──────────────┘   └─────────────────────────────────────┘
```

### Startup sequence (`run.py`)

1. `setup()` — reads CSV from `data/`, creates `db/orders.db` (DuckDB)
2. Spawns `mcp_server/server.py` as a subprocess on port 8001
3. 3-second sleep, then starts FastAPI on port 8000
4. FastAPI lifespan: `MultiServerMCPClient` connects to MCP, loads 5 tools, wires them into the LangGraph graph

---

## Directory Layout

```
rca-agent/
│
├── run.py                        # Entrypoint: DB setup → MCP subprocess → FastAPI
│
├── data/
│   └── amazon_orders_gold_20260422.csv   # Source data: store × hour grain
│
├── db/
│   ├── database.py               # DuckDB connect/setup (CSV → orders table)
│   └── repository.py             # All SQL queries, returns typed Pydantic models
│
├── core/
│   ├── models.py                 # Pydantic: OrderRow, RCAResult, CitySummary, etc.
│   ├── rca_engine.py             # Pure RCA logic: demand/pileup/supply checks
│   └── prompts.py                # System prompt for the LLM
│
├── services/
│   └── rca_service.py            # Orchestrates repo + engine, formats string output
│
├── mcp_server/
│   └── server.py                 # FastMCP HTTP server, delegates to rca_service
│
├── agent/
│   ├── state.py                  # AgentState (TypedDict wrapping messages list)
│   └── graph.py                  # LangGraph graph: tool defs, ReAct loop, debug logging
│
├── api/
│   ├── app.py                    # FastAPI app factory, MCP client init, lifespan
│   ├── routes.py                 # /chat, /session/new, /health + _trim()
│   └── schemas.py                # ChatRequest, ChatResponse, NewSessionResponse
│
├── frontend/
│   └── app.py                    # Streamlit chat UI with session sidebar
│
├── langgraph.json                # LangGraph Cloud / Studio manifest
└── Procfile                      # For Railway deployment
```

---

## The RCA Logic

### Data model

The source table is `store × hour` grain. One row = one store, one hour of one day. Key columns:

| Column | Meaning |
|--------|---------|
| `store`, `city`, `charge_date`, `hour` | Identity |
| `total_orders` | Actual order volume that hour |
| `order_projection` | Forecasted volume |
| `is_problem_hour` | 1 if OR2A SLA was breached |
| `avg_or2a` | Average order-ready-to-assignment time (minutes) |
| `breached_rate` | Fraction of orders that missed SLA |
| `pileup_flag` | 1 if unassigned orders carried over from prior hour |
| `pileup_count` | Number of carried-over orders |
| `current_size` | Total rider slots available |
| `booked_size` | Slots actually filled |
| `man_hour` | Ratio: actual rider-hours worked / booked-hours |
| `noshow_count` | Riders who didn't show or left early |

### Three independent checks (per problem hour)

**1. Demand Spike** — Did more orders arrive than forecasted?

```python
# core/rca_engine.py
DEMAND_SPIKE_THRESHOLD = 1.10

def check_demand_spike(row: OrderRow) -> DemandSpikeResult:
    if row.order_projection > 0 and row.total_orders > row.order_projection * 1.10:
        excess_pct = round(((row.total_orders / row.order_projection) - 1) * 100, 1)
        return DemandSpikeResult(triggered=True,
            reason=f"{int(row.total_orders)} orders vs {int(row.order_projection)} projected (+{excess_pct}%)")
    return DemandSpikeResult(triggered=False)
```

**2. Pileup** — Did unassigned orders carry over? If so, was it sustained?

```python
SUSTAINED_PILEUP_MIN_HOURS = 3

def check_pileup(row: OrderRow, store_rows: list[OrderRow]) -> PileupResult:
    if not row.pileup_flag:
        return PileupResult(triggered=False)

    # Find the longest consecutive run of pileup hours for the whole store-day
    pileup_hours = sorted(r.hour for r in store_rows if r.pileup_flag)
    max_consecutive = max run of consecutive integers in pileup_hours

    if max_consecutive >= 3:
        return PileupResult(triggered=True, sustained=True,
            reason=f"... [SUSTAINED: {max_consecutive} consecutive hours]")
    return PileupResult(triggered=True, sustained=False, ...)
```

The sustained check looks at *all* pileup hours for the store that day, not just the current row. This is why `store_rows` (the full day's data) is passed alongside the single `row`.

**3. Supply** — Were enough riders available and working?

```python
BOOKING_GAP_THRESHOLD  = 0.90   # L1: < 90% of slots filled
UTILIZATION_GAP_THRESHOLD = 0.85  # L2: rider-hours ratio < 0.85

def check_supply(row: OrderRow) -> SupplyResult:
    if row.current_size > 0:
        booking_ratio = row.booked_size / row.current_size
        if booking_ratio < 0.90:
            return SupplyResult(triggered=True, level="L1", ...)  # Not enough riders booked
    if 0 < row.man_hour < 0.85:
        return SupplyResult(triggered=True, level="L2", ...)  # Riders booked but not working
    return SupplyResult(triggered=False)
```

L1 and L2 are mutually exclusive in one call — L1 is checked first. But across multiple hours, both can appear.

**All three checks are independent** — a single problem hour can trigger demand spike + pileup + supply L2 simultaneously. `run_rca` aggregates all triggered reasons into `root_causes`.

### Output format (from `format_rca_report`)

```
### STORE_003 — Hour 8:00 — avg OR2A: 883 min

1. Demand Spike: NO — 40 orders vs 42 projected (-4.8%)
2. Pileup: YES — 10 orders carried from previous hour [SUSTAINED: 5 consecutive hours]
3. Supply:
   a. Booking: 21 of 35 slots booked (60.0%) — GAP
   b. Utilization: man_hour ratio 0.71 (4 no-shows) — GAP

**Summary**: OR2A 883 min (breach 100%) — Sustained pileup from prior hour; booking gap 60% vs 90% required
```

---

## The 5 Tools

Both the direct tools (`agent/graph.py`) and MCP tools (`mcp_server/server.py`) expose the same 5 operations. Both call the same `rca_service`. The MCP server is purely a transport wrapper.

| Tool | What it does | When the agent uses it |
|------|-------------|------------------------|
| `list_cities` | Lists all cities in the dataset | First turn, broad queries |
| `get_city_summary` | Weighted breach rate, avg OR2A, problem hour count for a city | City-level "how did X do?" questions |
| `list_stores_in_city` | All stores in a city, ranked by problem hours | "Which stores were worst?" |
| `get_problem_hours` | Problem hours for a city/store (broad = city aggregate, filtered = row-level) | Scoping before running RCA |
| `run_rca_for_store` | Full demand/pileup/supply RCA for all problem hours at a store | "Run RCA for STORE_003" |

### Token-safe query design

`get_problem_hours` with no city/store filter returns a **9-line city aggregate** (not all 3,800 rows). With a filter it returns individual rows capped at 50. `run_rca_for_store` returns the **5 worst hours** (by breach rate), not all problem hours. This keeps tool results under ~500 tokens so history doesn't overflow the LLM's context.

---

## API Reference

Base URL: `http://localhost:8000`

### `POST /session/new`
Creates a new conversation session. Returns a UUID.

```json
// Response
{ "session_id": "a3f1..." }
```

### `POST /chat`
Send a message. Session history is maintained server-side.

```json
// Request
{ "session_id": "a3f1...", "message": "Run RCA for STORE_003" }

// Response
{ "session_id": "a3f1...", "response": "### STORE_003 — Hour 8:00...", "turn": 3 }
```

### `DELETE /session/{session_id}`
Clears session history.

### `GET /health`
Returns `{"status": "ok"}`.

---

## Technology Choices and Tradeoffs

### LLM: Groq + Llama 4 Scout

**Chose:** `meta-llama/llama-4-scout-17b-16e-instruct` via Groq API

**Why Groq over OpenAI/Anthropic:** Groq's free tier runs at ~500 tokens/sec — fast enough for a real conversation. OpenAI and Anthropic free tiers are either slower or require credit. For an ops tool that needs sub-5s response time, latency matters.

**Why Llama 4 Scout:** Strong instruction-following and reliable tool-call JSON generation. The 16e mixture-of-experts architecture gives GPT-4-class reasoning at a fraction of the compute cost. Available on Groq free tier.

**Tradeoff:** 6,000 TPM rate limit on free tier. Handled via history trimming + retry with 70s backoff on 429.

---

### Orchestration: LangGraph

**Chose:** LangGraph `StateGraph` with a ReAct (Reason + Act) loop

**Why LangGraph over plain LangChain AgentExecutor:** AgentExecutor is deprecated and gives less control. LangGraph makes the loop explicit: `agent → tools → agent → END`. We can add a `recursion_limit`, inspect state at any node, and extend to multi-agent graphs later without rewriting.

**Why not a simple while loop with manual tool dispatch:** That works for one tool call. For multi-step plans ("list cities → list stores → run RCA → summarize"), you'd be rebuilding the ReAct loop manually. LangGraph gives this for free plus observability via LangGraph Studio.

**The graph:**
```
entry → agent_node
agent_node → tools (if tool_calls in last message)
agent_node → END  (if no tool_calls)
tools → agent_node
```

`ToolNode` handles dispatching to whichever tool the LLM named, catching exceptions, and wrapping the result in a `ToolMessage`.

---

### Tool Protocol: MCP (Model Context Protocol)

**Chose:** FastMCP server on HTTP transport (port 8001), loaded via `langchain-mcp-adapters`

**Why MCP at all:** MCP is becoming the standard interface for exposing tools to AI agents — Claude Desktop, VS Code Copilot, and LangGraph Cloud all speak it. Building to MCP now means the same tool server can be plugged into any MCP-compatible client without changes to the tool logic.

**Why HTTP transport over stdio:** Stdio transport spawns a subprocess and communicates over stdin/stdout pipes. On Windows, Python's `asyncio` subprocess implementation has a known issue with `ProactorEventLoop` and pipe streams — it raises `ExceptionGroup` on any async error. HTTP transport sidesteps this entirely: the MCP server is a normal web server, and the client calls it like any HTTP API.

**Why not skip MCP and just use direct tools:** Direct tools (the `@tool` decorated functions in `agent/graph.py`) are simpler and equally correct. The MCP path exists so the agent is compatible with external tooling (LangGraph Studio, Claude Desktop). Both paths call `rca_service` — zero logic duplication.

---

### Database: DuckDB

**Chose:** DuckDB with a persistent `.db` file, read-only connections per query

**Why DuckDB over SQLite:** DuckDB is column-oriented and built for analytical queries — `SUM`, `GROUP BY`, window functions. The city summary query uses weighted averages over hundreds of rows; DuckDB runs these ~10× faster than SQLite on analytical workloads. It also reads CSV natively with `read_csv_auto` — no schema definition needed.

**Why not PostgreSQL:** Requires a running server process, credentials, and a migration. DuckDB is file-based — `duckdb.connect("orders.db")` is all the setup. For a read-heavy analytical tool with one data file, there is no benefit to Postgres.

**Why not Pandas in-memory DataFrame:** Pandas would work at this data size (~3,800 rows). DuckDB gives us SQL — which is the right language for "give me all rows where `is_problem_hour = 1` and `city LIKE ?`". SQL expresses those filters more clearly than Pandas boolean indexing. It also makes it easy to add new queries without learning a new API.

**Thread safety:** Every query opens a fresh `read_only=True` connection and closes it via context manager. DuckDB allows multiple simultaneous read-only connections to the same file. `setup()` at startup writes the table using a write connection that is immediately closed — after that, everything is read-only.

---

### API: FastAPI

**Chose:** FastAPI with async handlers and a lifespan context

**Why FastAPI over Flask:** FastAPI is async-native. The LangGraph `graph.ainvoke()` call is async — in Flask you'd need threading hacks to not block the server. FastAPI also generates OpenAPI docs automatically at `/docs`, useful for debugging tool payloads.

**Why not Django:** Django is a full-stack web framework. We need an API server that exposes 4 endpoints. Django's ORM, admin, templates, and middleware stack add zero value here.

**Session management:** Session history is stored in a plain `dict[session_id → list[messages]]` in memory. No Redis, no database. This is intentional: sessions are short-lived (one ops investigation), and the history is already bounded to 6 messages by `_trim()`. If the server restarts, sessions reset — acceptable for an ops tool.

---

### History Trimming: `_trim()` in `api/routes.py`

This is the most operationally critical piece of the API layer.

```python
MAX_HISTORY = 6           # keep last 6 messages
TOOL_RESULT_MAX_CHARS = 300  # truncate tool results to 300 chars in history

def _trim(messages: list) -> list:
    recent = messages[-MAX_HISTORY:]
    result = []
    for m in recent:
        if isinstance(m, ToolMessage):
            content = m.content
            # MCP tools return list[{'type': 'text', 'text': '...'}]
            # Direct tools return plain str
            if isinstance(content, list):
                text = " ".join(c.get("text", "") for c in content if isinstance(c, dict))
            else:
                text = str(content)
            if len(text) > TOOL_RESULT_MAX_CHARS:
                m = m.model_copy(update={"content": text[:TOOL_RESULT_MAX_CHARS] + "…"})
        result.append(m)
    return result
```

**Why this matters:** On turn 1 the agent calls `list_stores_in_city("Bangalore")` and gets back ~97 stores (~3,000 tokens). On turn 4 ("walk me through morning hours"), that full store list is still in history. Without trimming, Groq receives a 6,000+ token context, hits the TPM limit, and returns a 400 error.

**The MCP content format bug:** MCP tool results have `content` as `list[{'type': 'text', 'text': '...'}]`, not a plain string. The original `len(m.content) > 300` check returned `len(list) = 1`, so truncation never fired. The fix extracts the text string first, then measures length.

---

### Frontend: Streamlit

**Chose:** Streamlit with `st.chat_message`, sidebar session controls

**Why Streamlit over React:** This is an internal ops tool, not a consumer product. Streamlit gives a usable, production-quality chat UI in ~75 lines of Python. A React frontend would need a separate JS build pipeline, npm dependencies, CORS configuration, and a deploy step — for the same end result.

**Why not Gradio:** Gradio's `ChatInterface` abstracts away session management in a way that doesn't compose cleanly with server-side session IDs. Streamlit gives full control over the `st.session_state` lifecycle and what gets sent to the backend.

---

## Setup

### Prerequisites
- Python 3.10+
- A [Groq](https://console.groq.com) API key (free tier)

### Install

```bash
git clone https://github.com/aryans1192-ux/rca-agent.git
cd rca-agent
pip install -r requirements.txt
```

### Configure

```bash
# .env
GROQ_API_KEY=your_groq_api_key_here
```

### Run

**Terminal 1** — backend + MCP server:
```bash
python run.py
```

**Terminal 2** — frontend:
```bash
streamlit run frontend/app.py
```

Open **http://localhost:8501**.

### Debug mode

```bash
python run.py --debug
# or
RCA_DEBUG=1 python run.py
```

Prints every tool call, tool result (first 200 chars), and final answer length to the terminal. Useful for diagnosing why the agent made a particular decision.

---

## Sample Test Sequence

Run in a single session to exercise all layers:

```
1. Which cities are in the dataset?
   → calls list_cities

2. What's the overall summary for Bangalore?
   → calls get_city_summary

3. Which stores in Bangalore had problem hours?
   → calls list_stores_in_city

4. Run RCA for STORE_003.
   → calls run_rca_for_store

5. Walk me through just the morning hours there.
   → no new tool call; agent filters from turn 4's result

6. Was there a sustained pileup at that store?
   → agent answers from existing context

7. Which city had the worst breach rate?
   → calls get_city_summary for multiple cities

8. List all stores in Delhi and run RCA on the one with the most problem hours.
   → chains list_stores_in_city → run_rca_for_store in one turn

9. Is STORE_999 having issues today?
   → graceful "no data found" handling
```

Questions 5–6 test multi-turn history (the `_trim()` fix). Question 8 tests multi-step tool chaining.

---

## AI Tools Used

**Claude Code (Anthropic)** was used throughout development as a coding assistant.

What it helped with:
- Debugging the `_trim()` function — the MCP list-format content bug that caused 400 errors on turn 4 of multi-turn conversations
- Adding debug logging to `agent/graph.py` and the `--debug` flag in `run.py`
- Removing the `hour` parameter from the MCP `run_rca_for_store` tool after it caused invalid tool call errors
- Writing and iterating on the README

What I wrote myself:
- The core architecture decisions — layered design, separation of `core/`, `db/`, `services/`, `agent/`, `api/`
- The RCA engine logic (`core/rca_engine.py`) — all three checks, thresholds, sustained pileup detection
- The Pydantic data models (`core/models.py`)
- The DuckDB repository and SQL queries (`db/repository.py`)
- The LangGraph graph structure and tool definitions (`agent/graph.py`)
- The MCP server setup and FastMCP tool wiring (`mcp_server/server.py`)
- The FastAPI app, session management, and `_trim()` design (`api/`)
- The Streamlit frontend (`frontend/app.py`)
- The system prompt (`core/prompts.py`)

What I discarded:
- An earlier version of the MCP server that had its own DuckDB instance and raw SQL — duplicating all the logic from `rca_service`. Replaced it with a thin wrapper that delegates to the service layer.
- stdio transport for MCP — caused `ExceptionGroup` crashes on Windows. Switched to HTTP transport.
- The `hour` parameter on `run_rca_for_store` — the model kept passing string values like `"morning"`, causing 400 errors. Removed it entirely.

---

## Coverage

- **Date:** 2026-04-22
- **Cities:** Bangalore, Chennai, Faridabad, Gurgaon, Hyderabad, Mumbai North, New Delhi, Noida, Pune City East
- **Stores:** 200+ across all cities
- **Records:** 3,800+ store × hour rows
