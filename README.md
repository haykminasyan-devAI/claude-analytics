# Claude Code Usage Analytics Platform

An end-to-end analytics platform that ingests, processes, and visualises
telemetry data from Claude Code sessions. Transforms raw CloudWatch event
streams into actionable insights through an interactive multi-tab dashboard,
a REST API, ML-powered anomaly detection, and a 14-day cost forecast.

---

## Table of Contents

1. [Project Overview](#project-overview)
2. [Architecture](#architecture)
3. [Project Structure](#project-structure)
4. [Setup Instructions](#setup-instructions)
5. [Running the Pipeline](#running-the-pipeline)
6. [Running the Dashboard](#running-the-dashboard)
7. [Running the API](#running-the-api)
8. [API Endpoints](#api-endpoints)
9. [Dashboard Features](#dashboard-features)
10. [LLM Usage Log](#llm-usage-log)

---

## Project Overview

### Dataset
| File | Description |
|---|---|
| `telemetry_logs.jsonl` | 82,661 CloudWatch log batches → 454,428 individual events |
| `employees.csv` | 201 engineers with practice, level, and location |

### Event Types Processed
| Event | What it captures |
|---|---|
| `claude_code.api_request` | Token usage, cost, model, duration |
| `claude_code.tool_decision` | Which tool Claude chose and whether it was accepted |
| `claude_code.tool_result` | Tool execution outcome and duration |
| `claude_code.user_prompt` | Prompt length per developer interaction |
| `claude_code.api_error` | Error messages, status codes, retry attempts |

### Key Numbers (full dataset)
- **Date range:** Dec 3 2025 → Jan 31 2026 (60 days)
- **Total simulated cost:** $6,001.43
- **Total tokens:** 103M input + output combined
- **Sessions:** 5,000 across 100 engineers

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        RAW DATA                             │
│   telemetry_logs.jsonl          employees.csv               │
└──────────────┬──────────────────────────┬───────────────────┘
               │                          │
               ▼                          ▼
┌──────────────────────┐    ┌─────────────────────────┐
│  ingestion/           │    │  storage/db.py           │
│  jsonl_reader.py      │    │  load_employees()        │
│                       │    └───────────┬─────────────┘
│  iter_events()        │                │
│  ─ reads line by line │                │
│  ─ unwraps batches    │                │
│  ─ yields event dicts │                │
└──────────┬───────────┘                │
           │                            │
           ▼                            │
┌──────────────────────┐                │
│  processing/          │                │
│  event_parser.py      │                │
│                       │                │
│  parse_event()        │                │
│  ─ dispatches by body │                │
│  ─ casts types        │                │
│  ─ returns flat dict  │                │
└──────────┬───────────┘                │
           │                            │
           ▼                            ▼
┌──────────────────────────────────────────────────────────┐
│                   storage/                               │
│   schema.py  ──→  db.py  ──→  data/analytics.db         │
│                                                          │
│   Tables: api_requests, tool_decisions, tool_results,    │
│           user_prompts, api_errors, employees            │
└──────┬───────────────────────────────────────────────────┘
       │
       ├─────────────────────┬──────────────────────┐
       ▼                     ▼                      ▼
┌────────────┐   ┌─────────────────────┐  ┌──────────────┐
│ analytics/ │   │ ml/                 │  │ api/         │
│ queries.py │   │ anomaly.py          │  │ main.py      │
│            │   │ forecasting.py      │  │              │
│ 13 SQL     │   │ IsolationForest     │  │ FastAPI      │
│ functions  │   │ 7-day rolling avg   │  │ 4 endpoints  │
└─────┬──────┘   └────────┬────────────┘  └──────┬───────┘
      │                   │                       │
      └───────────────────▼───────────────────────┘
                          │
                          ▼
            ┌─────────────────────────┐
            │   dashboard/app.py      │
            │                         │
            │   Streamlit + Plotly    │
            │   5 interactive tabs    │
            │   Sidebar date filter   │
            └─────────────────────────┘
```

---

## Project Structure

```
claude_analytics/
│
├── config/
│   └── settings.py          # All paths, constants, config values
│
├── ingestion/
│   ├── jsonl_reader.py       # Memory-efficient JSONL reader (generator)
│   └── realtime_simulator.py # Live stream simulation
│
├── processing/
│   └── event_parser.py       # Per-event-type parsers + dispatcher
│
├── storage/
│   ├── schema.py             # SQLite DDL (CREATE TABLE + indexes)
│   └── db.py                 # Connection manager, init, bulk insert
│
├── analytics/
│   └── queries.py            # 13 SQL analytics functions → DataFrames
│
├── ml/
│   ├── anomaly.py            # IsolationForest anomaly detection
│   └── forecasting.py        # 7-day rolling average cost forecast
│
├── api/
│   └── main.py               # FastAPI REST endpoints
│
├── dashboard/
│   └── app.py                # Streamlit dashboard (5 tabs)
│
├── data/                     # Put data files here (gitignored)
│   ├── telemetry_logs.jsonl
│   ├── employees.csv
│   └── analytics.db          # Created by run_pipeline.py
│
├── run_pipeline.py           # Entry point: ingest → process → store
└── requirements.txt
```

---

## Setup Instructions

### 1. Clone / download the project
```bash
cd /path/to/your/workspace
```

### 2. Create and activate a virtual environment
```bash
python3 -m venv venv
source venv/bin/activate        # macOS / Linux
# venv\Scripts\activate         # Windows
```

### 3. Install dependencies
```bash
pip install -r requirements.txt
```

### 4. Copy data files into the `data/` folder
```
data/
├── telemetry_logs.jsonl    ← copy from claude_code_telemetry/output/
└── employees.csv           ← copy from claude_code_telemetry/output/
```

---

## Running the Pipeline

Run once to parse all events and populate the SQLite database:

```bash
python run_pipeline.py
```

Expected output:
```
2026-01-01 10:00:00 | INFO | pipeline | ===== Claude Analytics Pipeline =====
2026-01-01 10:00:00 | INFO | pipeline | Initialising database ...
2026-01-01 10:00:01 | INFO | pipeline | Loaded 201 employees
2026-01-01 10:00:01 | INFO | pipeline | Starting event ingestion ...
2026-01-01 10:00:12 | INFO | pipeline | Pipeline complete in 11.4 seconds
2026-01-01 10:00:12 | INFO | pipeline | Total events parsed:  454428
2026-01-01 10:00:12 | INFO | pipeline | claude_code.api_request      118014
2026-01-01 10:00:12 | INFO | pipeline | claude_code.tool_decision    151461
2026-01-01 10:00:12 | INFO | pipeline | claude_code.tool_result      148418
2026-01-01 10:00:12 | INFO | pipeline | claude_code.user_prompt       35173
2026-01-01 10:00:12 | INFO | pipeline | claude_code.api_error          1362
```

---

## Running the Dashboard

```bash
streamlit run dashboard/app.py
```

Opens at: **http://localhost:8501**

> The pipeline must be run first to create `data/analytics.db`.

---

## Running the API

```bash
uvicorn api.main:app --reload --port 8000
```

- API base URL: **http://localhost:8000**
- Interactive docs: **http://localhost:8000/docs**
- ReDoc: **http://localhost:8000/redoc**

---

## API Endpoints

| Method | Endpoint | Description | Query Params |
|---|---|---|---|
| `GET` | `/` | Health check | — |
| `GET` | `/api/kpi` | Headline KPIs (cost, sessions, users, tokens) | `date_from`, `date_to` |
| `GET` | `/api/daily-cost` | Daily cost time series with cumulative total | `date_from`, `date_to` |
| `GET` | `/api/top-users` | Top N users ranked by API cost | `date_from`, `date_to`, `n` |
| `GET` | `/api/anomalies` | Anomalous user-days from IsolationForest | `date_from`, `date_to`, `contamination` |

### Example requests

```bash
# All-time KPIs
curl http://localhost:8000/api/kpi

# December only
curl "http://localhost:8000/api/kpi?date_from=2025-12-01&date_to=2025-12-31"

# Top 5 users in January
curl "http://localhost:8000/api/top-users?n=5&date_from=2026-01-01"

# Anomalies with 10% contamination
curl "http://localhost:8000/api/anomalies?contamination=0.10"
```

---

## Dashboard Features

| Tab | Visualisations |
|---|---|
| 📊 Overview | KPI cards, daily cost line chart, 14-day forecast, cost by practice, token by model donut |
| 👥 User Analytics | Top 15 users table, hourly usage heatmap (7×24) |
| 🔧 Tool & Error | Tool usage counts, rejection rate per tool, daily error trend |
| 🚨 Anomaly Detection | Anomaly metrics, scatter plot (normal vs flagged), flagged users table |
| 📈 Advanced Analytics | Session length by practice, daily active users, prompt length trend, model by practice stacked bar, cost efficiency leaderboard |

---

## LLM Usage Log

All AI prompts, follow-ups, and validation steps are documented in a dedicated file:

👉 **[LLM_USAGE_LOG.md](./LLM_USAGE_LOG.md)**

### Summary

| Tool | Usage |
|---|---|
| Claude (via Cursor) | Primary — code generation, architecture, debugging, docs |
| Cursor IDE | AI-assisted editing and inline completions |

19 prompts documented across: Architecture, Config, Ingestion, Processing, Schema, Storage, Pipeline, Analytics, Dashboard, ML, Forecasting, Real-time, API, and Debugging.

---

## Dependencies

| Package | Version | Purpose |
|---|---|---|
| `pandas` | 2.2.2 | Data manipulation and DataFrame operations |
| `numpy` | 1.26.4 | Numerical operations for ML modules |
| `streamlit` | 1.35.0 | Interactive dashboard framework |
| `plotly` | 5.22.0 | Interactive charts and visualisations |
| `scikit-learn` | 1.5.0 | IsolationForest anomaly detection |
| `fastapi` | 0.111.0 | REST API framework |
| `uvicorn` | 0.30.1 | ASGI server for FastAPI |
| `tqdm` | 4.66.4 | Progress bars |
| `python-dotenv` | 1.0.1 | Environment variable management |
| `sqlite3` | built-in | Database storage (no install needed) |
