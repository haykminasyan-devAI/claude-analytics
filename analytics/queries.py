"""
Analytics layer: SQL queries that return pandas DataFrames.

Every function accepts optional date-range filters (date_from, date_to)
so the dashboard can apply them from sidebar controls.

All functions follow the same pattern:
    1. Build SQL with optional WHERE clauses
    2. Execute via get_connection()
    3. Return result as a pandas DataFrame
"""

import logging
from pathlib import Path
from typing import Optional

import pandas as pd

from config.settings import DB_PATH, TOP_N_USERS
from storage.db import get_connection

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _date_filter(
    date_from: Optional[str],
    date_to: Optional[str],
    col: str = "event_timestamp",
) -> tuple[str, list]:
    """
    Build a SQL WHERE clause fragment and param list for date filtering.

    Args:
        date_from: 'YYYY-MM-DD' string or None
        date_to:   'YYYY-MM-DD' string or None
        col:       column name to filter on

    Returns:
        (sql_fragment, params)
        e.g. ("AND event_timestamp >= ? AND event_timestamp <= ?", ["2025-12-01", "2026-01-31"])
    """
    clauses = []
    params  = []
    if date_from:
        clauses.append(f"{col} >= ?")
        params.append(date_from)
    if date_to:
        clauses.append(f"{col} <= ?")
        params.append(date_to + " 23:59:59")
    fragment = ("AND " + " AND ".join(clauses)) if clauses else ""
    return fragment, params


def _query(sql: str, params: list = None, db_path: Path = DB_PATH) -> pd.DataFrame:
    """Execute a SELECT query and return a DataFrame."""
    with get_connection(db_path) as conn:
        return pd.read_sql_query(sql, conn, params=params or [])


# ---------------------------------------------------------------------------
# 1. KPI Summary  (single-row DataFrame with headline numbers)
# ---------------------------------------------------------------------------

def get_kpi_summary(
    date_from: Optional[str] = None,
    date_to:   Optional[str] = None,
    db_path:   Path = DB_PATH,
) -> pd.DataFrame:
    """
    Returns one row with:
        total_cost, total_sessions, total_users,
        total_input_tokens, total_output_tokens, total_api_calls
    """
    date_sql, params = _date_filter(date_from, date_to)
    sql = f"""
        SELECT
            ROUND(SUM(cost_usd), 4)          AS total_cost,
            COUNT(DISTINCT session_id)        AS total_sessions,
            COUNT(DISTINCT user_email)        AS total_users,
            SUM(input_tokens)                 AS total_input_tokens,
            SUM(output_tokens)                AS total_output_tokens,
            COUNT(*)                          AS total_api_calls
        FROM api_requests
        WHERE 1=1 {date_sql}
    """
    return _query(sql, params, db_path)


# ---------------------------------------------------------------------------
# 2. Daily cost trend
# ---------------------------------------------------------------------------

def get_daily_cost(
    date_from: Optional[str] = None,
    date_to:   Optional[str] = None,
    db_path:   Path = DB_PATH,
) -> pd.DataFrame:
    """
    Returns columns: date, daily_cost, cumulative_cost
    Sorted ascending by date.
    """
    date_sql, params = _date_filter(date_from, date_to)
    sql = f"""
        SELECT
            DATE(event_timestamp)        AS date,
            ROUND(SUM(cost_usd), 4)      AS daily_cost
        FROM api_requests
        WHERE 1=1 {date_sql}
        GROUP BY DATE(event_timestamp)
        ORDER BY date
    """
    df = _query(sql, params, db_path)
    if not df.empty:
        df["cumulative_cost"] = df["daily_cost"].cumsum()
    return df


# ---------------------------------------------------------------------------
# 3. Cost by engineering practice
# ---------------------------------------------------------------------------

def get_cost_by_practice(
    date_from: Optional[str] = None,
    date_to:   Optional[str] = None,
    db_path:   Path = DB_PATH,
) -> pd.DataFrame:
    """
    Returns columns: practice, total_cost, total_tokens, api_calls
    Sorted by total_cost descending.
    """
    date_sql, params = _date_filter(date_from, date_to)
    sql = f"""
        SELECT
            practice,
            ROUND(SUM(cost_usd), 4)              AS total_cost,
            SUM(input_tokens + output_tokens)     AS total_tokens,
            COUNT(*)                              AS api_calls
        FROM api_requests
        WHERE practice != '' {date_sql}
        GROUP BY practice
        ORDER BY total_cost DESC
    """
    return _query(sql, params, db_path)


# ---------------------------------------------------------------------------
# 4. Token usage by model
# ---------------------------------------------------------------------------

def get_token_by_model(
    date_from: Optional[str] = None,
    date_to:   Optional[str] = None,
    db_path:   Path = DB_PATH,
) -> pd.DataFrame:
    """
    Returns columns: model, input_tokens, output_tokens, total_tokens,
                     total_cost, api_calls
    Sorted by total_tokens descending.
    """
    date_sql, params = _date_filter(date_from, date_to)
    sql = f"""
        SELECT
            model,
            SUM(input_tokens)                    AS input_tokens,
            SUM(output_tokens)                   AS output_tokens,
            SUM(input_tokens + output_tokens)    AS total_tokens,
            ROUND(SUM(cost_usd), 4)              AS total_cost,
            COUNT(*)                             AS api_calls
        FROM api_requests
        WHERE model != '' {date_sql}
        GROUP BY model
        ORDER BY total_tokens DESC
    """
    return _query(sql, params, db_path)


# ---------------------------------------------------------------------------
# 5. Hourly usage heatmap  (hour-of-day × day-of-week)
# ---------------------------------------------------------------------------

def get_hourly_heatmap(
    date_from: Optional[str] = None,
    date_to:   Optional[str] = None,
    db_path:   Path = DB_PATH,
) -> pd.DataFrame:
    """
    Returns columns: day_of_week (0=Mon … 6=Sun), hour (0-23), event_count
    Used to build a 7×24 heatmap in the dashboard.
    """
    date_sql, params = _date_filter(date_from, date_to)
    sql = f"""
        SELECT
            CAST(strftime('%w', event_timestamp) AS INTEGER) AS day_of_week,
            CAST(strftime('%H', event_timestamp) AS INTEGER) AS hour,
            COUNT(*)                                         AS event_count
        FROM api_requests
        WHERE 1=1 {date_sql}
        GROUP BY day_of_week, hour
        ORDER BY day_of_week, hour
    """
    df = _query(sql, params, db_path)
    # SQLite %w: 0=Sunday … 6=Saturday — remap to 0=Monday … 6=Sunday
    if not df.empty:
        df["day_of_week"] = (df["day_of_week"] - 1) % 7
    return df


# ---------------------------------------------------------------------------
# 6. Top N users by cost
# ---------------------------------------------------------------------------

def get_top_users(
    n:         int = TOP_N_USERS,
    date_from: Optional[str] = None,
    date_to:   Optional[str] = None,
    db_path:   Path = DB_PATH,
) -> pd.DataFrame:
    """
    Returns columns: user_email, full_name, practice, level, location,
                     total_cost, total_sessions, total_tokens, api_calls
    Sorted by total_cost descending, limited to top n.
    """
    date_sql, params = _date_filter(date_from, date_to)
    sql = f"""
        SELECT
            r.user_email,
            e.full_name,
            e.practice,
            e.level,
            e.location,
            ROUND(SUM(r.cost_usd), 4)             AS total_cost,
            COUNT(DISTINCT r.session_id)           AS total_sessions,
            SUM(r.input_tokens + r.output_tokens)  AS total_tokens,
            COUNT(*)                               AS api_calls
        FROM api_requests r
        LEFT JOIN employees e ON r.user_email = e.email
        WHERE r.user_email != '' {date_sql}
        GROUP BY r.user_email
        ORDER BY total_cost DESC
        LIMIT ?
    """
    return _query(sql, params + [n], db_path)


# ---------------------------------------------------------------------------
# 7. Tool usage counts
# ---------------------------------------------------------------------------

def get_tool_usage(
    date_from: Optional[str] = None,
    date_to:   Optional[str] = None,
    db_path:   Path = DB_PATH,
) -> pd.DataFrame:
    """
    Returns columns: tool_name, total_calls, accepted, rejected, rejection_rate
    Sorted by total_calls descending.
    """
    date_sql, params = _date_filter(date_from, date_to)
    sql = f"""
        SELECT
            tool_name,
            COUNT(*)                                         AS total_calls,
            SUM(CASE WHEN decision = 'accept' THEN 1 ELSE 0 END) AS accepted,
            SUM(CASE WHEN decision = 'reject' THEN 1 ELSE 0 END) AS rejected,
            ROUND(
                100.0 * SUM(CASE WHEN decision = 'reject' THEN 1 ELSE 0 END)
                / COUNT(*), 2
            )                                                AS rejection_rate
        FROM tool_decisions
        WHERE tool_name != '' {date_sql}
        GROUP BY tool_name
        ORDER BY total_calls DESC
    """
    return _query(sql, params, db_path)


# ---------------------------------------------------------------------------
# 8. Daily API error counts
# ---------------------------------------------------------------------------

def get_error_rate(
    date_from: Optional[str] = None,
    date_to:   Optional[str] = None,
    db_path:   Path = DB_PATH,
) -> pd.DataFrame:
    """
    Returns columns: date, error_count, top_error
    Sorted ascending by date.
    """
    date_sql, params = _date_filter(date_from, date_to)
    sql = f"""
        SELECT
            DATE(event_timestamp)   AS date,
            COUNT(*)                AS error_count,
            error                   AS top_error
        FROM api_errors
        WHERE 1=1 {date_sql}
        GROUP BY DATE(event_timestamp)
        ORDER BY date
    """
    return _query(sql, params, db_path)


# ---------------------------------------------------------------------------
# 9. Session length distribution (avg events per session by practice)
# ---------------------------------------------------------------------------

def get_session_length_distribution(
    date_from: Optional[str] = None,
    date_to:   Optional[str] = None,
    db_path:   Path = DB_PATH,
) -> pd.DataFrame:
    """
    Returns the average number of API calls per session, grouped by practice.

    Columns: practice, avg_calls_per_session, avg_cost_per_session,
             avg_tokens_per_session, total_sessions
    """
    date_sql, params = _date_filter(date_from, date_to)
    sql = f"""
        SELECT
            practice,
            COUNT(DISTINCT session_id)                           AS total_sessions,
            ROUND(COUNT(*) * 1.0 / COUNT(DISTINCT session_id), 2)
                                                                 AS avg_calls_per_session,
            ROUND(SUM(cost_usd) / COUNT(DISTINCT session_id), 4)
                                                                 AS avg_cost_per_session,
            ROUND(
                SUM(input_tokens + output_tokens) * 1.0
                / COUNT(DISTINCT session_id), 0
            )                                                    AS avg_tokens_per_session
        FROM api_requests
        WHERE practice != '' {date_sql}
        GROUP BY practice
        ORDER BY avg_calls_per_session DESC
    """
    return _query(sql, params, db_path)


# ---------------------------------------------------------------------------
# 10. Prompt length trend over time (daily average)
# ---------------------------------------------------------------------------

def get_prompt_length_over_time(
    date_from: Optional[str] = None,
    date_to:   Optional[str] = None,
    db_path:   Path = DB_PATH,
) -> pd.DataFrame:
    """
    Returns daily average and median prompt length.

    Columns: date, avg_prompt_length, max_prompt_length, total_prompts
    """
    date_sql, params = _date_filter(date_from, date_to)
    sql = f"""
        SELECT
            DATE(event_timestamp)              AS date,
            ROUND(AVG(prompt_length), 1)       AS avg_prompt_length,
            MAX(prompt_length)                 AS max_prompt_length,
            COUNT(*)                           AS total_prompts
        FROM user_prompts
        WHERE 1=1 {date_sql}
        GROUP BY DATE(event_timestamp)
        ORDER BY date
    """
    return _query(sql, params, db_path)


# ---------------------------------------------------------------------------
# 11. Model preference by engineering practice (stacked bar data)
# ---------------------------------------------------------------------------

def get_model_by_practice(
    date_from: Optional[str] = None,
    date_to:   Optional[str] = None,
    db_path:   Path = DB_PATH,
) -> pd.DataFrame:
    """
    Returns API call counts broken down by practice × model.

    Columns: practice, model, api_calls, total_cost
    """
    date_sql, params = _date_filter(date_from, date_to)
    sql = f"""
        SELECT
            practice,
            model,
            COUNT(*)                    AS api_calls,
            ROUND(SUM(cost_usd), 4)     AS total_cost
        FROM api_requests
        WHERE practice != '' AND model != '' {date_sql}
        GROUP BY practice, model
        ORDER BY practice, api_calls DESC
    """
    return _query(sql, params, db_path)


# ---------------------------------------------------------------------------
# 12. Cost efficiency score (output tokens per dollar, top N users)
# ---------------------------------------------------------------------------

def get_cost_efficiency(
    n:         int = TOP_N_USERS,
    date_from: Optional[str] = None,
    date_to:   Optional[str] = None,
    db_path:   Path = DB_PATH,
) -> pd.DataFrame:
    """
    Ranks users by cost efficiency: output tokens produced per dollar spent.
    Higher = more value extracted from the API budget.

    Columns: user_email, full_name, practice, level,
             total_cost, total_output_tokens, efficiency_score
    """
    date_sql, params = _date_filter(date_from, date_to)
    sql = f"""
        SELECT
            r.user_email,
            e.full_name,
            e.practice,
            e.level,
            ROUND(SUM(r.cost_usd), 4)       AS total_cost,
            SUM(r.output_tokens)             AS total_output_tokens,
            ROUND(
                CASE
                    WHEN SUM(r.cost_usd) > 0
                    THEN SUM(r.output_tokens) * 1.0 / SUM(r.cost_usd)
                    ELSE 0
                END, 1
            )                                AS efficiency_score
        FROM api_requests r
        LEFT JOIN employees e ON r.user_email = e.email
        WHERE r.user_email != '' {date_sql}
        GROUP BY r.user_email
        HAVING SUM(r.cost_usd) > 0
        ORDER BY efficiency_score DESC
        LIMIT ?
    """
    return _query(sql, params + [n], db_path)


# ---------------------------------------------------------------------------
# 13. Daily active users over time
# ---------------------------------------------------------------------------

def get_daily_active_users(
    date_from: Optional[str] = None,
    date_to:   Optional[str] = None,
    db_path:   Path = DB_PATH,
) -> pd.DataFrame:
    """
    Returns the number of unique users active each day.

    Columns: date, active_users, total_sessions, total_api_calls
    """
    date_sql, params = _date_filter(date_from, date_to)
    sql = f"""
        SELECT
            DATE(event_timestamp)           AS date,
            COUNT(DISTINCT user_email)      AS active_users,
            COUNT(DISTINCT session_id)      AS total_sessions,
            COUNT(*)                        AS total_api_calls
        FROM api_requests
        WHERE user_email != '' {date_sql}
        GROUP BY DATE(event_timestamp)
        ORDER BY date
    """
    return _query(sql, params, db_path)
