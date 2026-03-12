# LLM Usage Log

## Tools Used

| Tool | Role |
|---|---|
| **Claude (via Cursor)** | Primary tool — code generation, architecture design, debugging, documentation |
| **Cursor IDE** | AI-assisted editing, inline suggestions, and context-aware completions |

---

## How I Used AI

I used Claude as a pair programmer throughout the project. My approach:
1. Ask exploratory questions to understand concepts before asking for code
2. Review every generated output, test it manually, and ask follow-up questions when something didn't work or I didn't understand it
3. Iterate — most modules went through 2–3 rounds of refinement

The prompts below reflect real conversations, including follow-ups and debugging sessions.

---

## Prompts, Iterations & Validation

### 1 — Project Architecture

**My prompt:**
> *"I need to build an analytics platform from a JSONL telemetry file and a CSV of employees. What's a good Python project structure? I want separate folders for reading data, storing it, analysing it, and showing a dashboard. Also what packages do I need?"*

**Follow-up:**
> *"Can you also add a folder for ML stuff like anomaly detection?"*

**What I built:** Full project skeleton — `config/`, `ingestion/`, `processing/`, `storage/`, `analytics/`, `ml/`, `dashboard/`, `api/`, `requirements.txt`

**What I validated:** Checked that all `__init__.py` files were empty with no logic in them, confirmed the folder naming made sense for the responsibility of each module, verified `requirements.txt` contained all needed packages by cross-checking with the import statements I planned to use.

---

### 2 — Config File

**My prompt:**
> *"How do I set up a config file in Python with all my file paths so I don't hardcode them everywhere? I want to use pathlib and make it work from any directory."*

**Follow-up:**
> *"Also add constants for the 5 event type names so I don't have to type the strings everywhere and avoid typos."*

**What I built:** `config/settings.py` with `BASE_DIR`, `DB_PATH`, `TELEMETRY_JSONL`, `EMPLOYEES_CSV`, all 5 event type constants, batch size, and dashboard config.

**What I validated:** Imported `settings.py` in a Python REPL from a different directory and confirmed `BASE_DIR` resolved correctly. Checked `TELEMETRY_JSONL.exists()` returned `True` after placing the file.

---

### 3 — JSONL Ingestion

**My prompt:**
> *"I have a big JSONL file where each line is a JSON batch containing a list of log events, and each event's message is itself a JSON string. How do I read this without loading the whole thing into memory? What does `yield` do exactly?"*

**Follow-up:**
> *"Some lines are blank or have empty message fields and it crashes — how do I skip those safely?"*

**What I built:** `ingestion/jsonl_reader.py` — memory-efficient generator using `yield`, two-level JSON parsing (batch → message), with error handling for malformed lines and empty messages.

**What I validated:** Ran the reader on the first 100 lines using `itertools.islice`, printed event count, monitored memory usage with Activity Monitor — no spike. Manually added a broken JSON line to the file and confirmed it was skipped with a warning log.

---

### 4 — Event Parser

**My prompt:**
> *"I need a function that takes a raw event dict and returns a flat dict ready for a database row. The event has body, attributes, scope, resource fields. There are 5 different event types with different fields each. How do I structure this cleanly without a giant if-else block?"*

**Follow-up:**
> *"The tokens come as strings like '420' not integers — how do I handle that safely without crashing on bad values?"*

**What I built:** `processing/event_parser.py` — one parser per event type, `_common_fields()` shared helper, `_to_int()` / `_to_float()` / `_to_bool()` safe casting helpers, `parse_event()` dispatcher using a dict of parsers.

**What I validated:** Passed a sample event of each type and inspected the output dict with `type()` checks on every field. Verified that passing `None` and `""` to the casting helpers returned the correct default, and that a missing timestamp returns `None` from the parser.

---

### 5 — Database Schema

**My prompt:**
> *"How do I write SQLite CREATE TABLE statements in Python? I have 6 tables — 5 for events and 1 for employees. What columns should each have?"*

**Follow-up:**
> *"Which columns should I index? I know indexes speed up queries but I'm not sure which ones to pick for an analytics workload."*

**What I built:** `storage/schema.py` — DDL for 6 tables with `AUTOINCREMENT` PKs, all common columns, event-specific columns, and `CREATE INDEX IF NOT EXISTS` on `event_timestamp`, `user_email`, `session_id` for each event table. `ALL_DDL` list for iteration.

**What I validated:** Called `init_db()` twice and confirmed it ran without errors both times (testing `IF NOT EXISTS` idempotency). Opened the DB in SQLite CLI with `.schema` and verified all tables and indexes existed.

---

### 6 — Database Layer

**My prompt:**
> *"I need a Python function that opens a SQLite connection, runs some inserts, and always closes it even if something crashes mid-way. I heard context managers can help — how do those work?"*

**Follow-up:**
> *"Also, how do I insert 1000 rows at once efficiently instead of calling execute() in a loop?"*

**What I built:** `storage/db.py` — `get_connection()` context manager with WAL mode, `init_db()`, `load_employees()`, `bulk_insert_events()` using `executemany`.

**What I validated:** Inserted 10 test rows, read them back with a SELECT to confirm data integrity. Timed `executemany` vs a loop of `execute()` on 1000 rows — `executemany` was about 8x faster.

---

### 7 — Run Pipeline

**My prompt:**
> *"How do I write an entry point script that ties together: initialise DB, load CSV, read JSONL events one by one, parse them, buffer them, and flush to DB every 1000 events? I want progress logs while it runs."*

**Follow-up:**
> *"The script runs but some events have an unknown body field and I get a KeyError in bulk_insert_events — how do I handle unknown event types gracefully?"*

**What I built:** `run_pipeline.py` — logging setup, sequential pipeline steps, `defaultdict` buffer, batch flush every `JSONL_BATCH_SIZE`, final summary with per-table row counts.

**What I validated:** Ran the full pipeline on the real dataset. Final row counts matched the totals I computed when exploring the raw file earlier (118,014 api_requests, 151,461 tool_decisions, etc.). Checked `analytics.db` file size was reasonable (~150MB).

---

### 8 — Analytics Queries

**My prompt:**
> *"I have a SQLite DB with an api_requests table. How do I write Python functions that query it and return pandas DataFrames? I need total cost, daily cost over time, and cost grouped by a 'practice' column."*

**Follow-up:**
> *"How do I add optional date range parameters so the dashboard can filter everything by date without changing the query logic?"*

**What I built:** `analytics/queries.py` — 13 query functions each returning a DataFrame, shared `_date_filter()` helper, `_query()` wrapper using `pd.read_sql_query`.

**What I validated:** Ran each function in isolation and compared totals against the raw-file statistics I computed at the start. `get_kpi_summary()` total cost matched the $6,001.43 figure from the initial data exploration.

---

### 9 — Streamlit Dashboard (initial)

**My prompt:**
> *"How do I build a Streamlit dashboard with multiple tabs and a sidebar date filter? I want KPI number cards at the top, then Plotly charts below."*

**Follow-up:**
> *"How do I make two charts appear side by side in Streamlit instead of stacking them vertically?"*

**What I built:** `dashboard/app.py` — 3-tab layout (Overview, User Analytics, Tool & Error), `st.columns()` for side-by-side charts, Plotly figures for all visualisations, sidebar `date_input` filter passed to all queries.

**What I validated:** Launched dashboard and clicked through every tab. Changed the date range in the sidebar and confirmed all charts updated. Checked that the KPI numbers matched what the query functions returned when called directly.

---

### 10 — Anomaly Detection

**My prompt:**
> *"I want to detect users who had an abnormally high daily API cost. I heard IsolationForest can find outliers — what is it and how do I apply it to my data?"*

**Follow-up:**
> *"What does the contamination parameter actually mean? Is 0.05 a good starting value for this use case?"*

**What I built:** `ml/anomaly.py` — `detect_cost_anomalies()` with IsolationForest trained on daily_cost, daily_sessions, daily_calls. `get_anomaly_summary()` joining flagged rows with employee info.

**What I validated:** Manually inspected the top 10 flagged rows and confirmed they had noticeably higher cost than the dataset average. Verified the flagging rate was close to the expected 5% (contamination=0.05). Checked that `is_anomaly=False` rows had scores near 0 and flagged rows had scores below -0.3.

---

### 11 — Anomaly Tab in Dashboard

**My prompt:**
> *"How do I add a 4th tab to the Streamlit dashboard showing anomaly results? I want a scatter plot where anomalous points are red and normal ones are blue, plus a table of flagged users."*

**Follow-up:**
> *"The model reruns every time I interact with the dashboard — is there a way to avoid that?"*

**What I built:** Tab 4 in `dashboard/app.py` — 4 metric cards, scatter plot with colour mapping, flagged users table with formatted columns.

**What I validated:** Cross-checked scatter plot colours against the `is_anomaly` column in the raw DataFrame. Verified the flagged user count in the metric cards matched the number of rows in the table below.

---

### 12 — Advanced Analytics Queries

**My prompt:**
> *"I want deeper insights — which engineering practices run the longest Claude sessions? How do I calculate average API calls per session when I have session_id in the data?"*

**Follow-up:**
> *"Also can you add an 'efficiency score' — like how many output tokens each user gets per dollar spent? I want to see who gets the most value."*

**What I built:** 5 new functions in `analytics/queries.py` — `get_session_length_distribution()`, `get_prompt_length_over_time()`, `get_model_by_practice()`, `get_cost_efficiency()`, `get_daily_active_users()`.

**What I validated:** Spot-checked session length calculation by manually counting events for one session_id in the DB. Verified efficiency score for one user by dividing their total_output_tokens by total_cost manually.

---

### 13 — Advanced Analytics Tab

**My prompt:**
> *"How do I make a stacked bar chart in Plotly where each bar represents an engineering practice and the segments are different Claude models? My data has columns: practice, model, api_calls."*

**Follow-up:**
> *"The model names like 'claude-opus-4-5-20251101' are too long and overlap on the chart — how do I shorten them?"*

**What I built:** Tab 5 in `dashboard/app.py` — session length bar chart, dual-line active users chart, prompt length trend, stacked model-by-practice bar chart, cost efficiency horizontal bar chart.

**What I validated:** Verified that the stacked totals per practice in the model chart matched the individual practice totals from the simpler cost-by-practice chart in Tab 1.

---

### 14 — Cost Forecasting

**My prompt:**
> *"I want to forecast the next 2 weeks of daily API cost. The problem is my data has a clear weekday/weekend pattern — weekdays are much higher. I tried asking about linear regression but it doesn't capture that. What's a better approach?"*

**Follow-up:**
> *"You mentioned residual standard deviation for the confidence bands — can you explain what that actually means in simple terms and how wide the bands should be?"*

**What I built:** `ml/forecasting.py` — `forecast_daily_cost()` using 7-day rolling average, last-window cycling for forecast, ±1 std dev confidence bounds, lower bound clipped at 0.

**What I validated:** Visually inspected the forecast chart — weekend dips appeared correctly in the predicted future days. Checked that the confidence band width was proportional to the volatility of historical costs (wider when daily costs varied a lot).

---

### 15 — Forecast Chart in Dashboard

**My prompt:**
> *"How do I add a vertical dashed line in Plotly to separate the historical part of a chart from the forecast part? And how do I draw a shaded area between two lines for a confidence band?"*

**Follow-up:**
> *"The shaded confidence area wasn't showing up — after debugging I found I had the x-values in the wrong order when constructing the filled polygon."*

**What I built:** Forecast section in Tab 1 of `dashboard/app.py` — actual cost line (blue), predicted line (red dashed), confidence band (shaded), vertical "Today" divider, future forecast highlighted separately.

**What I validated:** Confirmed the vertical line appeared at the correct last data date. Checked that the shaded band was visible and that upper/lower bounds were symmetrically placed around the predicted line.

---

### 16 — Real-time Stream Simulator

**My prompt:**
> *"How would a real production system handle Claude Code events arriving continuously in real time? I want to at least demonstrate the concept — can I simulate it using my existing JSONL file?"*

**Follow-up:**
> *"How do I yield progress updates from inside the loop so the caller can print them as the loop runs, rather than waiting for it to finish?"*

**What I built:** `ingestion/realtime_simulator.py` — `simulate_live_stream()` generator that reads in configurable batches, inserts to SQLite, sleeps between batches, and yields a status dict after each batch.

**What I validated:** Ran the simulator with `batch_size=50, sleep_seconds=0.5` and watched status dicts print one by one in real time. After completion, confirmed the total events processed matched the full pipeline count.

---

### 17 — REST API

**My prompt:**
> *"I want to make my analytics data accessible to other tools, not just the dashboard. How do I create a simple REST API in Python? I heard FastAPI is popular for this."*

**Follow-up:**
> *"What is CORS and why would I need it? My API worked fine with curl but when I tried to call it from JavaScript in a browser it was blocked."*

**What I built:** `api/main.py` — FastAPI app with CORS middleware, 4 GET endpoints (`/api/kpi`, `/api/daily-cost`, `/api/top-users`, `/api/anomalies`), optional `date_from`/`date_to` query params, auto-generated Swagger docs.

**What I validated:** Opened `http://localhost:8000/docs` and tested all 4 endpoints interactively. Verified the JSON response structure matched the DataFrame columns. Tested date filter params by comparing filtered totals against known values.

---

### 18 — Debugging

**My prompt:**
> *"I'm getting this error when running the dashboard: `ImportError: cannot import name 'ANOMALY_CONTAMINATION' from 'config.settings'`. What does this mean and how do I fix it?"*

**Follow-up:** *(none needed — single fix)*

**What I built:** Added `ANOMALY_CONTAMINATION = 0.05` and `ANOMALY_RANDOM_STATE = 42` to `config/settings.py`.

**What I validated:** Re-ran the dashboard after the fix, confirmed the import error was gone, and that the anomaly tab loaded correctly.

---

### 19 — Documentation

**My prompt:**
> *"How should I write a README for a data engineering project? What sections should it have? I want to include something visual like an architecture diagram."*

**Follow-up:**
> *"For the LLM usage log — should I paste the exact technical prompts I used or write them more naturally the way I actually thought about the problems?"*

**What I built:** `README.md` with project overview, ASCII architecture diagram, setup instructions, run commands, API table, dashboard features table, and this LLM log as a separate file.

**What I validated:** Followed the setup instructions from scratch in a clean terminal session to confirm they work end-to-end. Had a colleague read the README and flag anything unclear.
