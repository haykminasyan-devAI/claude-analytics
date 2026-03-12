"""
FastAPI REST API for the Claude Code Usage Analytics Platform.

Exposes processed analytics data as JSON endpoints so external tools,
scripts, or dashboards can access the data programmatically.

Run with:
    cd claude_analytics
    uvicorn api.main:app --reload --port 8000

Interactive docs available at:
    http://localhost:8000/docs        (Swagger UI)
    http://localhost:8000/redoc       (ReDoc)

Endpoints:
    GET /api/kpi             — headline KPI summary
    GET /api/daily-cost      — daily cost time series
    GET /api/top-users       — top 15 users by cost
    GET /api/anomalies       — anomaly detection results
"""

import sys
from pathlib import Path
from typing import Optional

# ensure project root is on the path when running via uvicorn
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from analytics.queries import (
    get_daily_cost,
    get_kpi_summary,
    get_top_users,
)
from config.settings import DB_PATH
from ml.anomaly import get_anomaly_summary

# ---------------------------------------------------------------------------
# App initialisation
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Claude Code Usage Analytics API",
    description=(
        "REST API for programmatic access to Claude Code telemetry analytics. "
        "All endpoints accept optional date_from / date_to query parameters "
        "in YYYY-MM-DD format."
    ),
    version="1.0.0",
)

# ---------------------------------------------------------------------------
# CORS middleware — allow requests from any origin (browser-safe)
# ---------------------------------------------------------------------------

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],        # in production, restrict to known domains
    allow_credentials=True,
    allow_methods=["GET"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _df_to_json(df):
    """Convert a DataFrame to a list of dicts, handling NaN safely."""
    return df.where(df.notna(), other=None).to_dict(orient="records")


def _check_db():
    """Raise 503 if the database has not been built yet."""
    if not DB_PATH.exists():
        raise HTTPException(
            status_code=503,
            detail=(
                "Database not found. "
                "Please run the ingestion pipeline first: python run_pipeline.py"
            ),
        )


# ---------------------------------------------------------------------------
# Root
# ---------------------------------------------------------------------------

@app.get("/", tags=["Health"])
def root():
    """Health check — confirms the API is running."""
    return {"status": "ok", "message": "Claude Analytics API is running"}


# ---------------------------------------------------------------------------
# GET /api/kpi
# ---------------------------------------------------------------------------

@app.get("/api/kpi", tags=["Analytics"])
def get_kpi(
    date_from: Optional[str] = Query(
        default=None,
        description="Start date in YYYY-MM-DD format",
        example="2025-12-01",
    ),
    date_to: Optional[str] = Query(
        default=None,
        description="End date in YYYY-MM-DD format",
        example="2026-01-31",
    ),
):
    """
    Return headline KPI metrics.

    Includes: total_cost, total_sessions, total_users,
              total_input_tokens, total_output_tokens, total_api_calls.
    """
    _check_db()
    df = get_kpi_summary(date_from=date_from, date_to=date_to)

    if df.empty:
        return JSONResponse(content={}, status_code=200)

    row = df.iloc[0].where(df.iloc[0].notna(), other=None).to_dict()
    return JSONResponse(content=row)


# ---------------------------------------------------------------------------
# GET /api/daily-cost
# ---------------------------------------------------------------------------

@app.get("/api/daily-cost", tags=["Analytics"])
def get_daily_cost_endpoint(
    date_from: Optional[str] = Query(
        default=None,
        description="Start date in YYYY-MM-DD format",
    ),
    date_to: Optional[str] = Query(
        default=None,
        description="End date in YYYY-MM-DD format",
    ),
):
    """
    Return daily API cost time series.

    Each record: date, daily_cost, cumulative_cost.
    Sorted ascending by date.
    """
    _check_db()
    df = get_daily_cost(date_from=date_from, date_to=date_to)
    return JSONResponse(content=_df_to_json(df))


# ---------------------------------------------------------------------------
# GET /api/top-users
# ---------------------------------------------------------------------------

@app.get("/api/top-users", tags=["Analytics"])
def get_top_users_endpoint(
    date_from: Optional[str] = Query(default=None),
    date_to:   Optional[str] = Query(default=None),
    n: int = Query(
        default=15,
        ge=1,
        le=100,
        description="Number of top users to return (1–100)",
    ),
):
    """
    Return top N users ranked by total API cost.

    Each record: user_email, full_name, practice, level, location,
                 total_cost, total_sessions, total_tokens, api_calls.
    """
    _check_db()
    df = get_top_users(n=n, date_from=date_from, date_to=date_to)
    return JSONResponse(content=_df_to_json(df))


# ---------------------------------------------------------------------------
# GET /api/anomalies
# ---------------------------------------------------------------------------

@app.get("/api/anomalies", tags=["ML"])
def get_anomalies_endpoint(
    date_from: Optional[str] = Query(default=None),
    date_to:   Optional[str] = Query(default=None),
    contamination: float = Query(
        default=0.05,
        ge=0.01,
        le=0.5,
        description="Expected fraction of anomalies (0.01–0.50, default 0.05)",
    ),
):
    """
    Return users with anomalous daily API cost detected by IsolationForest.

    Each record: user_email, full_name, practice, level, location,
                 date, daily_cost, daily_sessions, daily_calls, anomaly_score.
    Sorted by daily_cost descending.
    """
    _check_db()
    df = get_anomaly_summary(
        date_from=date_from,
        date_to=date_to,
        contamination=contamination,
    )
    return JSONResponse(content=_df_to_json(df))
