"""
Central configuration for the Claude Analytics Platform.
All paths, constants, and tunable parameters live here.
"""

from pathlib import Path

# ---------------------------------------------------------------------------
# Project root  (claude_analytics/)
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent.parent

# ---------------------------------------------------------------------------
# Data paths
# ---------------------------------------------------------------------------
DATA_DIR        = BASE_DIR / "data"
TELEMETRY_JSONL = DATA_DIR / "telemetry_logs.jsonl"
EMPLOYEES_CSV   = DATA_DIR / "employees.csv"
DB_PATH         = DATA_DIR / "analytics.db"

# ---------------------------------------------------------------------------
# Event type constants
# ---------------------------------------------------------------------------
EVENT_API_REQUEST   = "claude_code.api_request"
EVENT_TOOL_DECISION = "claude_code.tool_decision"
EVENT_TOOL_RESULT   = "claude_code.tool_result"
EVENT_USER_PROMPT   = "claude_code.user_prompt"
EVENT_API_ERROR     = "claude_code.api_error"

ALL_EVENT_TYPES = [
    EVENT_API_REQUEST,
    EVENT_TOOL_DECISION,
    EVENT_TOOL_RESULT,
    EVENT_USER_PROMPT,
    EVENT_API_ERROR,
]

# ---------------------------------------------------------------------------
# Ingestion
# ---------------------------------------------------------------------------
JSONL_BATCH_SIZE = 1_000   # number of events flushed to DB at a time

# ---------------------------------------------------------------------------
# ML / Anomaly detection
# ---------------------------------------------------------------------------
ANOMALY_CONTAMINATION = 0.05   # expected fraction of anomalies (5%)
ANOMALY_RANDOM_STATE  = 42

# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------
DASHBOARD_TITLE     = "Claude Code Usage Analytics"
DASHBOARD_PAGE_ICON = "🤖"
TOP_N_USERS         = 15   # users shown in leaderboard charts
