"""
ML layer: 14-day cost forecasting using 7-day rolling average.

Why 7-day rolling average?
    Daily API cost follows a weekly cycle — high on weekdays, low on weekends.
    A 7-day rolling average smooths short-term noise while preserving this pattern.
    Forecasting by repeating the last full 7-day window respects the cycle.

How it works:
    1. Query daily total cost from SQLite
    2. Compute 7-day rolling average on historical data
    3. Calculate residuals (actual - rolling avg) → get their std deviation
    4. Forecast next 14 days by cycling the last 7-day window
    5. Apply ± 1 std dev as confidence bounds
    6. Return combined historical + forecast DataFrame
"""

import logging
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

from config.settings import DB_PATH
from storage.db import get_connection

logger = logging.getLogger(__name__)

FORECAST_DAYS   = 14
ROLLING_WINDOW  = 7


# ---------------------------------------------------------------------------
# Helper: fetch daily cost from SQLite
# ---------------------------------------------------------------------------

def _fetch_daily_cost(
    date_from: Optional[str],
    date_to:   Optional[str],
    db_path:   Path,
) -> pd.DataFrame:
    """Query daily total cost, return DataFrame with columns: date, actual_cost."""
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
            DATE(event_timestamp)       AS date,
            ROUND(SUM(cost_usd), 6)     AS actual_cost
        FROM api_requests
        WHERE 1=1 {where}
        GROUP BY DATE(event_timestamp)
        ORDER BY date
    """

    with get_connection(db_path) as conn:
        df = pd.read_sql_query(sql, conn, params=params)

    df["date"] = pd.to_datetime(df["date"])
    return df


# ---------------------------------------------------------------------------
# Main forecast function
# ---------------------------------------------------------------------------

def forecast_daily_cost(
    date_from:     Optional[str] = None,
    date_to:       Optional[str] = None,
    forecast_days: int  = FORECAST_DAYS,
    rolling_window: int = ROLLING_WINDOW,
    db_path:       Path = DB_PATH,
) -> pd.DataFrame:
    """
    Forecast daily API cost for the next `forecast_days` days.

    Algorithm:
        - Compute 7-day rolling average on historical daily cost
        - Extract the last full 7-day window as the repeating cycle
        - Forecast by tiling that window over the forecast horizon
        - Confidence bounds = rolling avg ± 1 std dev of residuals

    Args:
        date_from:      optional start date filter 'YYYY-MM-DD'
        date_to:        optional end date filter 'YYYY-MM-DD'
        forecast_days:  how many future days to predict (default 14)
        rolling_window: window size for rolling average (default 7)
        db_path:        path to SQLite database

    Returns:
        DataFrame with columns:
            date, actual_cost, predicted_cost, lower_bound, upper_bound

        actual_cost is NaN for future dates.
    """
    hist_df = _fetch_daily_cost(date_from, date_to, db_path)

    if hist_df.empty:
        logger.warning("No historical cost data found for forecasting.")
        return pd.DataFrame(columns=[
            "date", "actual_cost", "predicted_cost", "lower_bound", "upper_bound"
        ])

    if len(hist_df) < rolling_window:
        logger.warning(
            "Not enough data for a %d-day rolling window (only %d days).",
            rolling_window, len(hist_df),
        )
        return pd.DataFrame(columns=[
            "date", "actual_cost", "predicted_cost", "lower_bound", "upper_bound"
        ])

    # --- Step 1: compute rolling average on historical data ---
    hist_df = hist_df.copy()
    hist_df["predicted_cost"] = (
        hist_df["actual_cost"]
        .rolling(window=rolling_window, min_periods=rolling_window)
        .mean()
        .round(4)
    )

    # --- Step 2: compute residuals and their std deviation ---
    valid_mask = hist_df["predicted_cost"].notna()
    residuals  = hist_df.loc[valid_mask, "actual_cost"] - hist_df.loc[valid_mask, "predicted_cost"]
    residual_std = float(residuals.std())

    logger.info(
        "Residual std dev: $%.4f | Last rolling avg: $%.4f",
        residual_std,
        hist_df["predicted_cost"].iloc[-1],
    )

    # --- Step 3: extract the last full 7-day window as the forecast cycle ---
    last_window = hist_df["actual_cost"].iloc[-rolling_window:].values
    # Use the rolling avg of the window as the base cycle
    last_rolling_avg = hist_df["predicted_cost"].dropna().iloc[-rolling_window:].values

    if len(last_rolling_avg) < rolling_window:
        last_rolling_avg = last_window   # fallback

    # --- Step 4: build forecast rows by tiling the 7-day cycle ---
    last_date = hist_df["date"].iloc[-1]
    future_dates   = [last_date + pd.Timedelta(days=i + 1) for i in range(forecast_days)]
    future_preds   = []

    for i in range(forecast_days):
        cycle_idx = i % rolling_window
        future_preds.append(round(float(last_rolling_avg[cycle_idx]), 4))

    future_df = pd.DataFrame({
        "date":           future_dates,
        "actual_cost":    np.nan,
        "predicted_cost": future_preds,
    })

    # --- Step 5: apply confidence bounds to ALL rows ---
    hist_df["lower_bound"] = (hist_df["predicted_cost"] - residual_std).round(4)
    hist_df["upper_bound"] = (hist_df["predicted_cost"] + residual_std).round(4)

    future_df["lower_bound"] = (future_df["predicted_cost"] - residual_std).round(4)
    future_df["upper_bound"] = (future_df["predicted_cost"] + residual_std).round(4)

    # clip lower bound at 0 (cost can't be negative)
    hist_df["lower_bound"]   = hist_df["lower_bound"].clip(lower=0)
    future_df["lower_bound"] = future_df["lower_bound"].clip(lower=0)

    # --- Step 6: combine historical + forecast ---
    combined = pd.concat(
        [hist_df[["date", "actual_cost", "predicted_cost", "lower_bound", "upper_bound"]],
         future_df],
        ignore_index=True,
    )

    logger.info(
        "Forecast complete — %d historical days + %d forecast days",
        len(hist_df),
        forecast_days,
    )

    return combined
