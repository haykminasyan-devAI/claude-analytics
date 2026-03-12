"""
Streamlit dashboard for the Claude Code Usage Analytics Platform.

Run with:
    cd claude_analytics
    streamlit run dashboard/app.py

Layout:
    Sidebar   — date range filter
    Tab 1     — Overview          (KPIs, daily cost, cost by practice, tokens by model)
    Tab 2     — User Analytics    (top users table, hourly heatmap)
    Tab 3     — Tool & Error      (tool usage + rejection rate, daily errors)
    Tab 4     — Anomaly Detection (IsolationForest, scatter plot, flagged users table)
"""

import sys
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

# Make sure the project root is on the path when running from any directory
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from analytics.queries import (
    get_cost_by_practice,
    get_cost_efficiency,
    get_daily_active_users,
    get_daily_cost,
    get_error_rate,
    get_hourly_heatmap,
    get_kpi_summary,
    get_model_by_practice,
    get_prompt_length_over_time,
    get_session_length_distribution,
    get_token_by_model,
    get_tool_usage,
    get_top_users,
)
from config.settings import DASHBOARD_PAGE_ICON, DASHBOARD_TITLE, DB_PATH
from ml.anomaly import detect_cost_anomalies, get_anomaly_summary
from ml.forecasting import forecast_daily_cost

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title=DASHBOARD_TITLE,
    page_icon=DASHBOARD_PAGE_ICON,
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# Guard — show friendly error if DB not yet built
# ---------------------------------------------------------------------------

if not DB_PATH.exists():
    st.error(
        "Database not found. Please run the ingestion pipeline first:\n\n"
        "```bash\npython run_pipeline.py\n```"
    )
    st.stop()

# ---------------------------------------------------------------------------
# Sidebar — date range filter
# ---------------------------------------------------------------------------

st.sidebar.title("Filters")
st.sidebar.markdown("---")

st.sidebar.subheader("Date Range")
date_from = st.sidebar.date_input("From", value=pd.Timestamp("2025-12-03"))
date_to   = st.sidebar.date_input("To",   value=pd.Timestamp("2026-01-31"))

date_from_str = str(date_from)
date_to_str   = str(date_to)

st.sidebar.markdown("---")
st.sidebar.caption("Claude Code Usage Analytics Platform")

# ---------------------------------------------------------------------------
# Title
# ---------------------------------------------------------------------------

st.title(f"{DASHBOARD_PAGE_ICON} {DASHBOARD_TITLE}")
st.caption(f"Showing data from **{date_from_str}** to **{date_to_str}**")
st.markdown("---")

# ---------------------------------------------------------------------------
# Tabs
# ---------------------------------------------------------------------------

tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "📊 Overview",
    "👥 User Analytics",
    "🔧 Tool & Error Analytics",
    "🚨 Anomaly Detection",
    "📈 Advanced Analytics",
])


# ===========================================================================
# TAB 1 — Overview
# ===========================================================================

with tab1:

    # --- KPI Cards ---
    kpi_df = get_kpi_summary(date_from_str, date_to_str)

    if kpi_df.empty or kpi_df["total_cost"].iloc[0] is None:
        st.warning("No data found for the selected date range.")
    else:
        row = kpi_df.iloc[0]

        col1, col2, col3, col4, col5 = st.columns(5)
        col1.metric("💰 Total Cost",     f"${row['total_cost']:,.2f}")
        col2.metric("🔁 Total Sessions", f"{int(row['total_sessions']):,}")
        col3.metric("👤 Active Users",   f"{int(row['total_users']):,}")
        col4.metric("📥 Input Tokens",   f"{int(row['total_input_tokens']):,}")
        col5.metric("📤 Output Tokens",  f"{int(row['total_output_tokens']):,}")

    st.markdown("---")

    # --- Daily Cost Line Chart ---
    st.subheader("Daily API Cost Over Time")
    daily_df = get_daily_cost(date_from_str, date_to_str)

    if not daily_df.empty:
        fig_daily = go.Figure()
        fig_daily.add_trace(go.Scatter(
            x=daily_df["date"],
            y=daily_df["daily_cost"],
            mode="lines+markers",
            name="Daily Cost",
            line=dict(color="#636EFA", width=2),
            fill="tozeroy",
            fillcolor="rgba(99,110,250,0.1)",
        ))
        fig_daily.add_trace(go.Scatter(
            x=daily_df["date"],
            y=daily_df["cumulative_cost"],
            mode="lines",
            name="Cumulative Cost",
            line=dict(color="#EF553B", width=2, dash="dot"),
            yaxis="y2",
        ))
        fig_daily.update_layout(
            yaxis=dict(title="Daily Cost (USD)"),
            yaxis2=dict(title="Cumulative Cost (USD)", overlaying="y", side="right"),
            legend=dict(orientation="h", yanchor="bottom", y=1.02),
            hovermode="x unified",
            height=380,
            margin=dict(t=30),
        )
        st.plotly_chart(fig_daily, use_container_width=True)

    st.markdown("---")

    # --- 14-Day Cost Forecast ---
    st.subheader("📉 14-Day Cost Forecast")
    st.caption(
        "Uses a 7-day rolling average to capture the weekly usage cycle "
        "(high weekdays, low weekends). The shaded band shows ± 1 std deviation of historical residuals."
    )

    with st.spinner("Generating forecast ..."):
        forecast_df = forecast_daily_cost(date_from=date_from_str, date_to=date_to_str)

    if forecast_df.empty:
        st.warning("Not enough data to generate a forecast.")
    else:
        # split into historical (actual_cost known) and future (actual_cost is NaN)
        hist_mask   = forecast_df["actual_cost"].notna()
        future_mask = forecast_df["actual_cost"].isna()

        hist_fc   = forecast_df[hist_mask]
        future_fc = forecast_df[future_mask]

        last_actual_date = str(hist_fc["date"].iloc[-1].date()) if not hist_fc.empty else ""

        fig_fc = go.Figure()

        # confidence band — draw first so lines appear on top
        fig_fc.add_trace(go.Scatter(
            x=pd.concat([forecast_df["date"], forecast_df["date"][::-1]]),
            y=pd.concat([forecast_df["upper_bound"], forecast_df["lower_bound"][::-1]]),
            fill="toself",
            fillcolor="rgba(239,85,59,0.12)",
            line=dict(color="rgba(255,255,255,0)"),
            hoverinfo="skip",
            name="Confidence Band",
            showlegend=True,
        ))

        # predicted line — full range (historical + future)
        fig_fc.add_trace(go.Scatter(
            x=forecast_df["date"],
            y=forecast_df["predicted_cost"],
            mode="lines",
            name="Predicted (7-day rolling avg)",
            line=dict(color="#EF553B", width=2, dash="dash"),
        ))

        # actual cost line — historical only
        fig_fc.add_trace(go.Scatter(
            x=hist_fc["date"],
            y=hist_fc["actual_cost"],
            mode="lines",
            name="Actual Cost",
            line=dict(color="#636EFA", width=2),
        ))

        # future predicted line — highlighted separately
        if not future_fc.empty:
            fig_fc.add_trace(go.Scatter(
                x=future_fc["date"],
                y=future_fc["predicted_cost"],
                mode="lines+markers",
                name="Forecast (next 14 days)",
                line=dict(color="#FF6692", width=2.5, dash="dot"),
                marker=dict(size=5),
            ))

        # vertical divider line between past and future
        if last_actual_date:
            fig_fc.add_shape(
                type="line",
                x0=last_actual_date,
                x1=last_actual_date,
                y0=0,
                y1=1,
                xref="x",
                yref="paper",
                line=dict(color="gray", width=1.5, dash="dash"),
            )
            fig_fc.add_annotation(
                x=last_actual_date,
                y=1,
                xref="x",
                yref="paper",
                text="Today",
                showarrow=False,
                font=dict(color="gray", size=12),
                xanchor="left",
                yanchor="top",
            )

        fig_fc.update_layout(
            yaxis=dict(title="Daily Cost (USD)"),
            legend=dict(orientation="h", yanchor="bottom", y=1.02),
            hovermode="x unified",
            height=400,
            margin=dict(t=40),
        )
        st.plotly_chart(fig_fc, use_container_width=True)
        st.caption(
            f"Vertical dashed line marks the last day of actual data ({last_actual_date}). "
            "Everything to the right is forecasted."
        )

    st.markdown("---")

    # --- Cost by Practice & Token by Model (side by side) ---
    col_left, col_right = st.columns(2)

    with col_left:
        st.subheader("Cost by Engineering Practice")
        practice_df = get_cost_by_practice(date_from_str, date_to_str)

        if not practice_df.empty:
            fig_practice = px.bar(
                practice_df,
                x="total_cost",
                y="practice",
                orientation="h",
                color="total_cost",
                color_continuous_scale="Blues",
                labels={"total_cost": "Cost (USD)", "practice": "Practice"},
                text=practice_df["total_cost"].apply(lambda x: f"${x:,.2f}"),
            )
            fig_practice.update_traces(textposition="outside")
            fig_practice.update_layout(
                height=360,
                margin=dict(t=20, b=20),
                coloraxis_showscale=False,
                yaxis=dict(categoryorder="total ascending"),
            )
            st.plotly_chart(fig_practice, use_container_width=True)

    with col_right:
        st.subheader("Token Usage by Model")
        model_df = get_token_by_model(date_from_str, date_to_str)

        if not model_df.empty:
            fig_model = px.pie(
                model_df,
                names="model",
                values="total_tokens",
                hole=0.45,
                color_discrete_sequence=px.colors.qualitative.Plotly,
            )
            fig_model.update_traces(
                textposition="inside",
                textinfo="percent+label",
            )
            fig_model.update_layout(
                height=360,
                margin=dict(t=20, b=20),
                showlegend=True,
                legend=dict(orientation="v"),
            )
            st.plotly_chart(fig_model, use_container_width=True)


# ===========================================================================
# TAB 2 — User Analytics
# ===========================================================================

with tab2:

    # --- Top Users Table ---
    st.subheader("Top Users by API Cost")
    top_users_df = get_top_users(n=15, date_from=date_from_str, date_to=date_to_str)

    if not top_users_df.empty:
        display_df = top_users_df.copy()
        display_df["total_cost"]   = display_df["total_cost"].apply(lambda x: f"${x:,.4f}")
        display_df["total_tokens"] = display_df["total_tokens"].apply(lambda x: f"{int(x):,}")
        display_df.columns = [
            "Email", "Name", "Practice", "Level", "Location",
            "Total Cost", "Sessions", "Total Tokens", "API Calls",
        ]
        st.dataframe(display_df, use_container_width=True, hide_index=True)

    st.markdown("---")

    # --- Hourly Heatmap ---
    st.subheader("Usage Heatmap — Hour of Day × Day of Week")
    heatmap_df = get_hourly_heatmap(date_from_str, date_to_str)

    if not heatmap_df.empty:
        day_labels = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

        pivot = heatmap_df.pivot_table(
            index="day_of_week",
            columns="hour",
            values="event_count",
            fill_value=0,
        )
        # ensure all 24 hours present
        pivot = pivot.reindex(columns=range(24), fill_value=0)
        pivot = pivot.reindex(index=range(7), fill_value=0)

        fig_heat = go.Figure(data=go.Heatmap(
            z=pivot.values,
            x=[f"{h:02d}:00" for h in range(24)],
            y=day_labels,
            colorscale="YlOrRd",
            hoverongaps=False,
            hovertemplate="Day: %{y}<br>Hour: %{x}<br>API Calls: %{z}<extra></extra>",
        ))
        fig_heat.update_layout(
            xaxis=dict(title="Hour of Day", tickangle=-45),
            yaxis=dict(title="Day of Week"),
            height=350,
            margin=dict(t=20),
        )
        st.plotly_chart(fig_heat, use_container_width=True)
        st.caption("Shows number of API calls per hour. Reveals peak usage times and working patterns.")


# ===========================================================================
# TAB 3 — Tool & Error Analytics
# ===========================================================================

with tab3:

    # --- Tool Usage Bar Chart ---
    st.subheader("Tool Usage & Rejection Rate")
    tool_df = get_tool_usage(date_from_str, date_to_str)

    if not tool_df.empty:
        col_tl, col_tr = st.columns(2)

        with col_tl:
            fig_tool = px.bar(
                tool_df,
                x="tool_name",
                y="total_calls",
                color="total_calls",
                color_continuous_scale="Teal",
                labels={"tool_name": "Tool", "total_calls": "Total Calls"},
                text="total_calls",
            )
            fig_tool.update_traces(textposition="outside")
            fig_tool.update_layout(
                height=380,
                margin=dict(t=20),
                coloraxis_showscale=False,
                xaxis=dict(tickangle=-35),
            )
            st.plotly_chart(fig_tool, use_container_width=True)
            st.caption("Total number of times Claude used each tool.")

        with col_tr:
            fig_reject = px.bar(
                tool_df.sort_values("rejection_rate", ascending=False),
                x="tool_name",
                y="rejection_rate",
                color="rejection_rate",
                color_continuous_scale="Reds",
                labels={"tool_name": "Tool", "rejection_rate": "Rejection Rate (%)"},
                text=tool_df.sort_values("rejection_rate", ascending=False)["rejection_rate"].apply(
                    lambda x: f"{x:.1f}%"
                ),
            )
            fig_reject.update_traces(textposition="outside")
            fig_reject.update_layout(
                height=380,
                margin=dict(t=20),
                coloraxis_showscale=False,
                xaxis=dict(tickangle=-35),
            )
            st.plotly_chart(fig_reject, use_container_width=True)
            st.caption("Percentage of times developers rejected the tool suggestion.")

    st.markdown("---")

    # --- Daily Error Line Chart ---
    st.subheader("Daily API Errors Over Time")
    error_df = get_error_rate(date_from_str, date_to_str)

    if not error_df.empty:
        fig_err = px.line(
            error_df,
            x="date",
            y="error_count",
            markers=True,
            labels={"date": "Date", "error_count": "Error Count"},
            color_discrete_sequence=["#EF553B"],
        )
        fig_err.update_traces(fill="tozeroy", fillcolor="rgba(239,85,59,0.1)")
        fig_err.update_layout(
            height=340,
            margin=dict(t=20),
            hovermode="x unified",
        )
        st.plotly_chart(fig_err, use_container_width=True)
        st.caption("Daily count of API errors (rate limits, server errors, aborted requests).")
    else:
        st.info("No API errors found in the selected date range.")


# ===========================================================================
# TAB 4 — Anomaly Detection
# ===========================================================================

with tab4:

    st.subheader("Cost Anomaly Detection — IsolationForest")
    st.caption(
        "Uses an unsupervised ML model (IsolationForest) trained on daily cost, "
        "sessions, and API calls per user. The most unusual 5% of user-days are flagged."
    )
    st.markdown("---")

    with st.spinner("Running anomaly detection model ..."):
        all_anomaly_df = detect_cost_anomalies(
            date_from=date_from_str,
            date_to=date_to_str,
            db_path=DB_PATH,
        )
        flagged_df = get_anomaly_summary(
            date_from=date_from_str,
            date_to=date_to_str,
            db_path=DB_PATH,
        )

    if all_anomaly_df.empty:
        st.warning("No data available for the selected date range.")
    else:
        total_rows     = len(all_anomaly_df)
        total_flagged  = int(all_anomaly_df["is_anomaly"].sum())
        flagged_users  = flagged_df["user_email"].nunique() if not flagged_df.empty else 0

        # --- Warning metric cards ---
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("🔍 User-Days Analysed", f"{total_rows:,}")
        m2.metric("🚨 Anomalous User-Days", f"{total_flagged:,}")
        m3.metric("👤 Flagged Unique Users", f"{flagged_users:,}")
        m4.metric(
            "📊 Anomaly Rate",
            f"{100 * total_flagged / total_rows:.1f}%",
        )

        st.markdown("---")

        # --- Scatter plot: daily_cost vs date, coloured by is_anomaly ---
        st.subheader("Daily Cost per User — Normal vs Anomalous")

        plot_df = all_anomaly_df.copy()
        plot_df["status"] = plot_df["is_anomaly"].map(
            {True: "🚨 Anomaly", False: "✅ Normal"}
        )

        fig_scatter = px.scatter(
            plot_df,
            x="date",
            y="daily_cost",
            color="status",
            color_discrete_map={
                "🚨 Anomaly": "#EF553B",
                "✅ Normal":  "#636EFA",
            },
            hover_data=["user_email", "daily_sessions", "daily_calls", "anomaly_score"],
            labels={"date": "Date", "daily_cost": "Daily Cost (USD)", "status": ""},
            opacity=0.7,
        )
        fig_scatter.update_traces(marker=dict(size=6))
        fig_scatter.update_layout(
            height=420,
            margin=dict(t=20),
            hovermode="closest",
            legend=dict(orientation="h", yanchor="bottom", y=1.02),
        )
        st.plotly_chart(fig_scatter, use_container_width=True)
        st.caption(
            "Red dots = flagged anomalies. These user-days have unusually high cost "
            "relative to their session and API call volume."
        )

        st.markdown("---")

        # --- Flagged users table ---
        st.subheader(f"Flagged Users ({total_flagged} anomalous user-days)")

        if flagged_df.empty:
            st.success("No anomalies detected in the selected date range.")
        else:
            display_flagged = flagged_df.copy()
            display_flagged["daily_cost"] = display_flagged["daily_cost"].apply(
                lambda x: f"${x:,.4f}"
            )
            display_flagged["anomaly_score"] = display_flagged["anomaly_score"].apply(
                lambda x: f"{x:.4f}"
            )
            display_flagged.columns = [
                "Email", "Name", "Practice", "Level", "Location",
                "Date", "Daily Cost", "Sessions", "API Calls", "Anomaly Score",
            ]
            st.dataframe(display_flagged, use_container_width=True, hide_index=True)
            st.caption(
                "Anomaly Score: more negative = more anomalous. "
                "Sorted by daily cost descending."
            )


# ===========================================================================
# TAB 5 — Advanced Analytics
# ===========================================================================

with tab5:

    # --- Row 1: Session length + Daily active users ---
    col_a, col_b = st.columns(2)

    with col_a:
        st.subheader("Avg API Calls per Session by Practice")
        session_df = get_session_length_distribution(date_from_str, date_to_str)

        if not session_df.empty:
            fig_session = px.bar(
                session_df,
                x="practice",
                y="avg_calls_per_session",
                color="avg_calls_per_session",
                color_continuous_scale="Purples",
                text=session_df["avg_calls_per_session"].apply(lambda x: f"{x:.1f}"),
                labels={
                    "practice": "Engineering Practice",
                    "avg_calls_per_session": "Avg API Calls / Session",
                },
            )
            fig_session.update_traces(textposition="outside")
            fig_session.update_layout(
                height=380,
                margin=dict(t=20, b=20),
                coloraxis_showscale=False,
                xaxis=dict(tickangle=-20),
            )
            st.plotly_chart(fig_session, use_container_width=True)
            st.caption("Practices with higher values tend to use Claude for longer, more complex tasks.")

    with col_b:
        st.subheader("Daily Active Users Over Time")
        dau_df = get_daily_active_users(date_from_str, date_to_str)

        if not dau_df.empty:
            fig_dau = go.Figure()
            fig_dau.add_trace(go.Scatter(
                x=dau_df["date"],
                y=dau_df["active_users"],
                mode="lines+markers",
                name="Active Users",
                line=dict(color="#00CC96", width=2),
                fill="tozeroy",
                fillcolor="rgba(0,204,150,0.1)",
            ))
            fig_dau.add_trace(go.Scatter(
                x=dau_df["date"],
                y=dau_df["total_sessions"],
                mode="lines",
                name="Total Sessions",
                line=dict(color="#AB63FA", width=2, dash="dot"),
                yaxis="y2",
            ))
            fig_dau.update_layout(
                yaxis=dict(title="Active Users"),
                yaxis2=dict(title="Sessions", overlaying="y", side="right"),
                legend=dict(orientation="h", yanchor="bottom", y=1.02),
                hovermode="x unified",
                height=380,
                margin=dict(t=30),
            )
            st.plotly_chart(fig_dau, use_container_width=True)
            st.caption("Green = unique users active that day. Purple = total sessions (right axis).")

    st.markdown("---")

    # --- Row 2: Prompt length trend ---
    st.subheader("Average Prompt Length Over Time")
    prompt_df = get_prompt_length_over_time(date_from_str, date_to_str)

    if not prompt_df.empty:
        fig_prompt = go.Figure()
        fig_prompt.add_trace(go.Scatter(
            x=prompt_df["date"],
            y=prompt_df["avg_prompt_length"],
            mode="lines+markers",
            name="Avg Prompt Length",
            line=dict(color="#FFA15A", width=2),
            fill="tozeroy",
            fillcolor="rgba(255,161,90,0.1)",
        ))
        fig_prompt.add_trace(go.Scatter(
            x=prompt_df["date"],
            y=prompt_df["max_prompt_length"],
            mode="lines",
            name="Max Prompt Length",
            line=dict(color="#EF553B", width=1, dash="dash"),
            yaxis="y2",
        ))
        fig_prompt.update_layout(
            yaxis=dict(title="Avg Prompt Length (chars)"),
            yaxis2=dict(title="Max Prompt Length (chars)", overlaying="y", side="right"),
            legend=dict(orientation="h", yanchor="bottom", y=1.02),
            hovermode="x unified",
            height=340,
            margin=dict(t=30),
        )
        st.plotly_chart(fig_prompt, use_container_width=True)
        st.caption("Rising avg prompt length may indicate developers tackling more complex tasks over time.")

    st.markdown("---")

    # --- Row 3: Model preference by practice + Cost efficiency ---
    col_c, col_d = st.columns(2)

    with col_c:
        st.subheader("Model Preference by Engineering Practice")
        model_prac_df = get_model_by_practice(date_from_str, date_to_str)

        if not model_prac_df.empty:
            # shorten model names for readability
            model_prac_df["model_short"] = model_prac_df["model"].str.replace(
                r"claude-", "", regex=True
            ).str.replace(r"-\d{8,}", "", regex=True)

            fig_model_prac = px.bar(
                model_prac_df,
                x="practice",
                y="api_calls",
                color="model_short",
                barmode="stack",
                labels={
                    "practice": "Engineering Practice",
                    "api_calls": "API Calls",
                    "model_short": "Model",
                },
                color_discrete_sequence=px.colors.qualitative.Plotly,
            )
            fig_model_prac.update_layout(
                height=380,
                margin=dict(t=20, b=20),
                xaxis=dict(tickangle=-20),
                legend=dict(orientation="h", yanchor="bottom", y=1.02),
            )
            st.plotly_chart(fig_model_prac, use_container_width=True)
            st.caption("Which models each practice team prefers — stacked by number of API calls.")

    with col_d:
        st.subheader("Cost Efficiency Leaderboard")
        st.caption("Output tokens produced per dollar spent — higher = more efficient")
        efficiency_df = get_cost_efficiency(n=15, date_from=date_from_str, date_to=date_to_str)

        if not efficiency_df.empty:
            fig_eff = px.bar(
                efficiency_df,
                x="efficiency_score",
                y="full_name",
                orientation="h",
                color="efficiency_score",
                color_continuous_scale="Greens",
                hover_data=["practice", "level", "total_cost", "total_output_tokens"],
                labels={
                    "efficiency_score": "Output Tokens / Dollar",
                    "full_name": "Engineer",
                },
                text=efficiency_df["efficiency_score"].apply(lambda x: f"{x:,.0f}"),
            )
            fig_eff.update_traces(textposition="outside")
            fig_eff.update_layout(
                height=420,
                margin=dict(t=20, b=20),
                coloraxis_showscale=False,
                yaxis=dict(categoryorder="total ascending"),
            )
            st.plotly_chart(fig_eff, use_container_width=True)
