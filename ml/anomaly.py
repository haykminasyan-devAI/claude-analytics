"""
ML layer: anomaly detection for unusual API cost patterns.

Uses scikit-learn's IsolationForest — an unsupervised algorithm that
isolates outliers by randomly partitioning data. Points that are easy
to isolate (require fewer splits) are flagged as anomalies.

Main functions:
    detect_cost_anomalies()  — runs IsolationForest, returns all rows with scores
    get_anomaly_summary()    — returns only flagged rows joined with employee info
"""

import logging
from pathlib import Path
from typing import Optional

import pandas as pd
from sklearn.ensemble import IsolationForest

from config.settings import (
    ANOMALY_CONTAMINATION,
    ANOMALY_RANDOM_STATE,
    DB_PATH,
)
from storage.db import get_connection

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helper: fetch daily cost per user from SQLite
# ---------------------------------------------------------------------------

def _get_daily_cost_per_user(
    date_from: Optional[str],
    date_to:   Optional[str],
    db_path:   Path,
) -> pd.DataFrame:
    """
    Query daily API cost aggregated per user per day.

    Returns columns: user_email, date, daily_cost, daily_sessions, daily_calls
    """
    clauses = []
    params  = []

    if date_from:
        clauses.append("event_timestamp >= ?")
        params.append(date_from)
    if date_to:
        clauses.append("event_timestamp <= ?")
        params.append(date_to + " 23:59:59")

    where = ("AND " + " AND ".join(clauses)) if clauses else ""

    sql = f"""
        SELECT
            user_email,
            DATE(event_timestamp)           AS date,
            ROUND(SUM(cost_usd), 6)         AS daily_cost,
            COUNT(DISTINCT session_id)       AS daily_sessions,
            COUNT(*)                         AS daily_calls
        FROM api_requests
        WHERE user_email != '' {where}
        GROUP BY user_email, DATE(event_timestamp)
        ORDER BY user_email, date
    """

    with get_connection(db_path) as conn:
        df = pd.read_sql_query(sql, conn, params=params)

    return df


# ---------------------------------------------------------------------------
# Core: detect anomalies with IsolationForest
# ---------------------------------------------------------------------------

def detect_cost_anomalies(
    date_from: Optional[str] = None,
    date_to:   Optional[str] = None,
    contamination: float = ANOMALY_CONTAMINATION,
    random_state:  int   = ANOMALY_RANDOM_STATE,
    db_path:   Path = DB_PATH,
) -> pd.DataFrame:
    """
    Detect users with abnormally high daily API cost using IsolationForest.

    The model is trained on three features per user-day:
        - daily_cost      (USD spent that day)
        - daily_sessions  (number of sessions)
        - daily_calls     (number of API calls)

    Args:
        date_from:     optional start date 'YYYY-MM-DD'
        date_to:       optional end date 'YYYY-MM-DD'
        contamination: expected fraction of anomalies (default 5%)
        random_state:  for reproducibility
        db_path:       path to SQLite database

    Returns:
        DataFrame with columns:
            user_email, date, daily_cost, daily_sessions, daily_calls,
            anomaly_score, is_anomaly
    """
    df = _get_daily_cost_per_user(date_from, date_to, db_path)

    if df.empty:
        logger.warning("No data available for anomaly detection.")
        return df

    # Features used for anomaly detection
    features = ["daily_cost", "daily_sessions", "daily_calls"]
    X = df[features].values

    logger.info(
        "Running IsolationForest on %d user-day rows (contamination=%.2f)",
        len(df),
        contamination,
    )

    model = IsolationForest(
        contamination=contamination,
        random_state=random_state,
        n_estimators=100,
    )
    model.fit(X)

    # score_samples: more negative = more anomalous
    # predict:       -1 = anomaly, 1 = normal
    df["anomaly_score"] = model.score_samples(X).round(6)
    df["is_anomaly"]    = model.predict(X) == -1

    anomaly_count = df["is_anomaly"].sum()
    logger.info(
        "Anomaly detection complete — %d / %d rows flagged (%.1f%%)",
        anomaly_count,
        len(df),
        100 * anomaly_count / len(df),
    )

    return df


# ---------------------------------------------------------------------------
# Summary: flagged rows joined with employee info
# ---------------------------------------------------------------------------

def get_anomaly_summary(
    date_from: Optional[str] = None,
    date_to:   Optional[str] = None,
    contamination: float = ANOMALY_CONTAMINATION,
    db_path:   Path = DB_PATH,
) -> pd.DataFrame:
    """
    Return only the anomalous rows, enriched with employee metadata.

    Returns columns:
        user_email, full_name, practice, level, location,
        date, daily_cost, daily_sessions, daily_calls,
        anomaly_score, is_anomaly
    Sorted by daily_cost descending.
    """
    all_df = detect_cost_anomalies(
        date_from=date_from,
        date_to=date_to,
        contamination=contamination,
        db_path=db_path,
    )

    if all_df.empty:
        return all_df

    # keep only flagged rows
    anomalies = all_df[all_df["is_anomaly"]].copy()

    if anomalies.empty:
        logger.info("No anomalies found in the selected date range.")
        return anomalies

    # join with employees table for human-readable info
    with get_connection(db_path) as conn:
        employees = pd.read_sql_query(
            "SELECT email, full_name, practice, level, location FROM employees",
            conn,
        )

    anomalies = anomalies.merge(
        employees,
        left_on="user_email",
        right_on="email",
        how="left",
    ).drop(columns=["email"])

    # reorder columns for readability
    cols = [
        "user_email", "full_name", "practice", "level", "location",
        "date", "daily_cost", "daily_sessions", "daily_calls",
        "anomaly_score",
    ]
    anomalies = anomalies[cols].sort_values("daily_cost", ascending=False)

    return anomalies.reset_index(drop=True)
