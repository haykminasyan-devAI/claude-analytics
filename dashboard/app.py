"""
Streamlit dashboard — Claude Code Usage Analytics Platform.

Run with:
    cd claude_analytics
    streamlit run dashboard/app.py
"""

import sys
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

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
# Global CSS — palette, cards, header, sidebar, tabs
# ---------------------------------------------------------------------------

PALETTE = {
    "primary":   "#7C3AED",   # violet
    "secondary": "#06B6D4",   # cyan
    "accent":    "#F59E0B",   # amber
    "success":   "#10B981",   # emerald
    "danger":    "#EF4444",   # red
    "bg_card":   "#1E1E2E",   # dark card
    "text_muted":"#94A3B8",
}

st.markdown("""
<style>
/* ── Base font ── */
html, body, [class*="css"] {
    font-family: 'Inter', 'Segoe UI', sans-serif;
}

/* ── Main background ── */
.stApp {
    background: linear-gradient(135deg, #0F0F1A 0%, #1A1A2E 50%, #16213E 100%);
    color: #E2E8F0;
}

/* ── Sidebar ── */
section[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #1A1A2E 0%, #16213E 100%);
    border-right: 1px solid rgba(124,58,237,0.3);
}
section[data-testid="stSidebar"] * { color: #CBD5E1 !important; }
section[data-testid="stSidebar"] .stDateInput label { color: #94A3B8 !important; }

/* ── Hero header banner ── */
.hero-banner {
    background: linear-gradient(135deg, #7C3AED 0%, #2563EB 50%, #06B6D4 100%);
    border-radius: 16px;
    padding: 28px 36px;
    margin-bottom: 24px;
    box-shadow: 0 8px 32px rgba(124,58,237,0.35);
}
.hero-banner h1 {
    color: #FFFFFF !important;
    font-size: 2rem;
    font-weight: 800;
    margin: 0 0 6px 0;
    letter-spacing: -0.5px;
}
.hero-banner p {
    color: rgba(255,255,255,0.75) !important;
    font-size: 0.95rem;
    margin: 0;
}

/* ── KPI cards ── */
.kpi-grid {
    display: grid;
    grid-template-columns: repeat(5, 1fr);
    gap: 16px;
    margin-bottom: 28px;
}
.kpi-card {
    background: rgba(255,255,255,0.05);
    border: 1px solid rgba(255,255,255,0.08);
    border-radius: 14px;
    padding: 20px 18px;
    text-align: center;
    backdrop-filter: blur(8px);
    transition: transform .2s, box-shadow .2s;
}
.kpi-card:hover {
    transform: translateY(-3px);
    box-shadow: 0 8px 24px rgba(0,0,0,0.3);
}
.kpi-icon  { font-size: 1.8rem; line-height: 1; margin-bottom: 8px; }
.kpi-value { font-size: 1.5rem; font-weight: 700; color: #FFFFFF; line-height: 1.1; }
.kpi-label { font-size: 0.72rem; color: #94A3B8; text-transform: uppercase;
             letter-spacing: .06em; margin-top: 4px; }

/* Accent top-border colours */
.kpi-card.violet  { border-top: 3px solid #7C3AED; }
.kpi-card.cyan    { border-top: 3px solid #06B6D4; }
.kpi-card.emerald { border-top: 3px solid #10B981; }
.kpi-card.amber   { border-top: 3px solid #F59E0B; }
.kpi-card.rose    { border-top: 3px solid #F43F5E; }

/* ── Section headings ── */
.section-title {
    font-size: 1.05rem;
    font-weight: 700;
    color: #E2E8F0;
    margin: 0 0 12px 0;
    padding-left: 10px;
    border-left: 4px solid #7C3AED;
}
.section-caption {
    font-size: 0.78rem;
    color: #64748B;
    margin-top: -8px;
    margin-bottom: 12px;
    padding-left: 14px;
}

/* ── Tabs ── */
button[data-baseweb="tab"] {
    background: transparent !important;
    color: #94A3B8 !important;
    border-radius: 8px 8px 0 0 !important;
    font-weight: 600 !important;
    font-size: 0.88rem !important;
}
button[data-baseweb="tab"][aria-selected="true"] {
    background: rgba(124,58,237,0.15) !important;
    color: #A78BFA !important;
    border-bottom: 2px solid #7C3AED !important;
}

/* ── DataFrames ── */
.stDataFrame { border-radius: 10px; overflow: hidden; }
.stDataFrame thead tr th {
    background: rgba(124,58,237,0.2) !important;
    color: #C4B5FD !important;
    font-size: 0.78rem !important;
}

/* ── Divider ── */
.fancy-divider {
    height: 1px;
    background: linear-gradient(90deg, transparent, rgba(124,58,237,0.5), transparent);
    margin: 24px 0;
    border: none;
}

/* ── Info / warning boxes ── */
.stAlert { border-radius: 10px !important; }

/* ── Plotly chart containers ── */
.js-plotly-plot .plotly .main-svg { background: transparent !important; }
</style>
""", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Guard
# ---------------------------------------------------------------------------

if not DB_PATH.exists():
    st.error(
        "Database not found. Please run the ingestion pipeline first:\n\n"
        "```bash\npython run_pipeline.py\n```"
    )
    st.stop()

# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------

with st.sidebar:
    st.markdown("""
    <div style='text-align:center; padding: 12px 0 20px;'>
        <span style='font-size:2.4rem;'>🤖</span>
        <p style='font-size:0.9rem; font-weight:700; color:#A78BFA; margin:4px 0 0;'>
            Claude Analytics
        </p>
        <p style='font-size:0.7rem; color:#475569; margin:0;'>Usage Intelligence Platform</p>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("---")
    st.markdown("**📅 Date Range**")
    date_from = st.date_input("From", value=pd.Timestamp("2025-12-03"))
    date_to   = st.date_input("To",   value=pd.Timestamp("2026-01-31"))
    st.markdown("---")

    st.markdown("""
    <div style='font-size:0.7rem; color:#475569; text-align:center; padding-top:8px;'>
        Built for Provectus Internship<br>
        Powered by Streamlit + Plotly
    </div>
    """, unsafe_allow_html=True)

date_from_str = str(date_from)
date_to_str   = str(date_to)

# ---------------------------------------------------------------------------
# Hero Header
# ---------------------------------------------------------------------------

st.markdown(f"""
<div class="hero-banner">
    <h1>🤖 {DASHBOARD_TITLE}</h1>
    <p>Real-time analytics for Claude Code usage across all engineering practices &nbsp;·&nbsp;
       <strong style="color:rgba(255,255,255,0.9)">{date_from_str}</strong>
       &nbsp;→&nbsp;
       <strong style="color:rgba(255,255,255,0.9)">{date_to_str}</strong>
    </p>
</div>
""", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Tabs
# ---------------------------------------------------------------------------

tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "📊  Overview",
    "👥  User Analytics",
    "🔧  Tool & Error",
    "🚨  Anomaly Detection",
    "📈  Advanced Analytics",
])

# shared chart theme
CHART_LAYOUT = dict(
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    font=dict(color="#94A3B8", family="Inter, Segoe UI, sans-serif", size=11),
    margin=dict(t=36, b=16, l=8, r=8),
)

_AXIS_STYLE = dict(gridcolor="rgba(255,255,255,0.05)", linecolor="rgba(255,255,255,0.1)")


def apply_theme(fig, height=380, **extra):
    fig.update_layout(**CHART_LAYOUT, height=height, **extra)
    fig.update_xaxes(**_AXIS_STYLE)
    fig.update_yaxes(**_AXIS_STYLE)
    return fig


# ===========================================================================
# TAB 1 — Overview
# ===========================================================================

with tab1:

    kpi_df = get_kpi_summary(date_from_str, date_to_str)

    if kpi_df.empty or kpi_df["total_cost"].iloc[0] is None:
        st.warning("No data found for the selected date range.")
    else:
        row = kpi_df.iloc[0]
        st.markdown(f"""
        <div class="kpi-grid">
            <div class="kpi-card violet">
                <div class="kpi-icon">💰</div>
                <div class="kpi-value">${row['total_cost']:,.2f}</div>
                <div class="kpi-label">Total API Cost</div>
            </div>
            <div class="kpi-card cyan">
                <div class="kpi-icon">🔁</div>
                <div class="kpi-value">{int(row['total_sessions']):,}</div>
                <div class="kpi-label">Sessions</div>
            </div>
            <div class="kpi-card emerald">
                <div class="kpi-icon">👤</div>
                <div class="kpi-value">{int(row['total_users']):,}</div>
                <div class="kpi-label">Active Users</div>
            </div>
            <div class="kpi-card amber">
                <div class="kpi-icon">📥</div>
                <div class="kpi-value">{int(row['total_input_tokens']):,}</div>
                <div class="kpi-label">Input Tokens</div>
            </div>
            <div class="kpi-card rose">
                <div class="kpi-icon">📤</div>
                <div class="kpi-value">{int(row['total_output_tokens']):,}</div>
                <div class="kpi-label">Output Tokens</div>
            </div>
        </div>
        """, unsafe_allow_html=True)

    st.markdown('<hr class="fancy-divider">', unsafe_allow_html=True)

    # --- Daily Cost ---
    st.markdown('<p class="section-title">Daily API Cost Over Time</p>', unsafe_allow_html=True)
    daily_df = get_daily_cost(date_from_str, date_to_str)

    if not daily_df.empty:
        fig_daily = go.Figure()
        fig_daily.add_trace(go.Scatter(
            x=daily_df["date"], y=daily_df["daily_cost"],
            mode="lines", name="Daily Cost",
            line=dict(color="#7C3AED", width=2.5),
            fill="tozeroy", fillcolor="rgba(124,58,237,0.12)",
        ))
        fig_daily.add_trace(go.Scatter(
            x=daily_df["date"], y=daily_df["cumulative_cost"],
            mode="lines", name="Cumulative Cost",
            line=dict(color="#06B6D4", width=2, dash="dot"),
            yaxis="y2",
        ))
        fig_daily.update_layout(
            **CHART_LAYOUT,
            height=340,
            yaxis=dict(title="Daily Cost (USD)", gridcolor="rgba(255,255,255,0.05)"),
            yaxis2=dict(title="Cumulative (USD)", overlaying="y", side="right",
                        gridcolor="rgba(0,0,0,0)"),
            legend=dict(orientation="h", yanchor="bottom", y=1.02,
                        bgcolor="rgba(0,0,0,0)", font=dict(color="#CBD5E1")),
            hovermode="x unified",
        )
        st.plotly_chart(fig_daily, use_container_width=True)

    st.markdown('<hr class="fancy-divider">', unsafe_allow_html=True)

    # --- 14-Day Forecast ---
    st.markdown('<p class="section-title">📉 14-Day Cost Forecast</p>', unsafe_allow_html=True)
    st.markdown(
        '<p class="section-caption">7-day rolling average captures weekday/weekend cycles. '
        'Shaded band = ±1 std deviation of historical residuals.</p>',
        unsafe_allow_html=True,
    )

    with st.spinner("Generating forecast …"):
        forecast_df = forecast_daily_cost(date_from=date_from_str, date_to=date_to_str)

    if forecast_df.empty:
        st.warning("Not enough data to generate a forecast.")
    else:
        hist_mask   = forecast_df["actual_cost"].notna()
        future_mask = forecast_df["actual_cost"].isna()
        hist_fc     = forecast_df[hist_mask]
        future_fc   = forecast_df[future_mask]
        last_actual_date = str(hist_fc["date"].iloc[-1].date()) if not hist_fc.empty else ""

        fig_fc = go.Figure()

        fig_fc.add_trace(go.Scatter(
            x=pd.concat([forecast_df["date"], forecast_df["date"][::-1]]),
            y=pd.concat([forecast_df["upper_bound"], forecast_df["lower_bound"][::-1]]),
            fill="toself", fillcolor="rgba(244,63,94,0.10)",
            line=dict(color="rgba(0,0,0,0)"),
            hoverinfo="skip", name="Confidence Band",
        ))
        fig_fc.add_trace(go.Scatter(
            x=forecast_df["date"], y=forecast_df["predicted_cost"],
            mode="lines", name="Predicted (rolling avg)",
            line=dict(color="#F43F5E", width=2, dash="dash"),
        ))
        fig_fc.add_trace(go.Scatter(
            x=hist_fc["date"], y=hist_fc["actual_cost"],
            mode="lines", name="Actual Cost",
            line=dict(color="#7C3AED", width=2.5),
        ))
        if not future_fc.empty:
            fig_fc.add_trace(go.Scatter(
                x=future_fc["date"], y=future_fc["predicted_cost"],
                mode="lines+markers", name="Forecast (next 14 days)",
                line=dict(color="#FB923C", width=2.5, dash="dot"),
                marker=dict(size=5, color="#FB923C"),
            ))
        if last_actual_date:
            fig_fc.add_shape(
                type="line", x0=last_actual_date, x1=last_actual_date,
                y0=0, y1=1, xref="x", yref="paper",
                line=dict(color="rgba(148,163,184,0.6)", width=1.5, dash="dash"),
            )
            fig_fc.add_annotation(
                x=last_actual_date, y=1, xref="x", yref="paper",
                text="Today", showarrow=False,
                font=dict(color="#94A3B8", size=11),
                xanchor="left", yanchor="top",
            )

        fig_fc.update_layout(
            **CHART_LAYOUT, height=380,
            yaxis=dict(title="Daily Cost (USD)", gridcolor="rgba(255,255,255,0.05)"),
            legend=dict(orientation="h", yanchor="bottom", y=1.02,
                        bgcolor="rgba(0,0,0,0)", font=dict(color="#CBD5E1")),
            hovermode="x unified",
        )
        st.plotly_chart(fig_fc, use_container_width=True)
        st.markdown(
            f'<p class="section-caption">Vertical line = last actual data day ({last_actual_date}). '
            'Everything right is forecasted.</p>',
            unsafe_allow_html=True,
        )

    st.markdown('<hr class="fancy-divider">', unsafe_allow_html=True)

    # --- Practice & Model side by side ---
    col_left, col_right = st.columns(2)

    with col_left:
        st.markdown('<p class="section-title">Cost by Engineering Practice</p>', unsafe_allow_html=True)
        practice_df = get_cost_by_practice(date_from_str, date_to_str)

        if not practice_df.empty:
            fig_practice = px.bar(
                practice_df, x="total_cost", y="practice", orientation="h",
                color="total_cost",
                color_continuous_scale=[[0, "#3B0764"], [0.5, "#7C3AED"], [1, "#A78BFA"]],
                text=practice_df["total_cost"].apply(lambda x: f"${x:,.0f}"),
            )
            fig_practice.update_traces(textposition="outside", textfont_color="#CBD5E1")
            fig_practice.update_layout(
                **CHART_LAYOUT, height=380,
                coloraxis_showscale=False,
                yaxis=dict(categoryorder="total ascending", gridcolor="rgba(255,255,255,0.04)"),
                xaxis=dict(
                    title="Cost (USD)",
                    gridcolor="rgba(255,255,255,0.04)",
                    range=[0, practice_df["total_cost"].max() * 1.35],
                ),
            )
            st.plotly_chart(fig_practice, use_container_width=True)

    with col_right:
        st.markdown('<p class="section-title">Token Usage by Model</p>', unsafe_allow_html=True)
        model_df = get_token_by_model(date_from_str, date_to_str)

        if not model_df.empty:
            fig_model = px.pie(
                model_df, names="model", values="total_tokens", hole=0.52,
                color_discrete_sequence=["#7C3AED", "#06B6D4", "#10B981", "#F59E0B", "#F43F5E"],
            )
            fig_model.update_traces(
                textposition="inside", textinfo="percent+label",
                textfont=dict(color="#FFFFFF", size=11),
                marker=dict(line=dict(color="#1A1A2E", width=2)),
            )
            fig_model.update_layout(
                **CHART_LAYOUT, height=340,
                showlegend=True,
                legend=dict(orientation="v", font=dict(color="#CBD5E1", size=10)),
            )
            st.plotly_chart(fig_model, use_container_width=True)


# ===========================================================================
# TAB 2 — User Analytics
# ===========================================================================

with tab2:

    st.markdown('<p class="section-title">Top 15 Users by API Cost</p>', unsafe_allow_html=True)
    top_users_df = get_top_users(n=15, date_from=date_from_str, date_to=date_to_str)

    if not top_users_df.empty:
        PRACTICE_BADGE = {
            "ML Engineering":       ("#7C3AED", "#EDE9FE"),
            "Frontend Engineering": ("#0891B2", "#CFFAFE"),
            "Backend Engineering":  ("#059669", "#D1FAE5"),
            "DevOps":               ("#D97706", "#FEF3C7"),
            "Platform Engineering": ("#E11D48", "#FFE4E6"),
            "Data Engineering":     ("#EA580C", "#FFEDD5"),
        }
        LEVEL_BADGE = {
            "Junior":   ("#6EE7B7", "#064E3B"),
            "Mid":      ("#93C5FD", "#1E3A5F"),
            "Senior":   ("#C4B5FD", "#2E1065"),
            "Lead":     ("#FCD34D", "#78350F"),
            "Director": ("#F9A8D4", "#831843"),
        }

        rows_html = ""
        for i, row in enumerate(top_users_df.itertuples(index=False)):
            practice     = str(row[2]) if len(row) > 2 else ""
            level        = str(row[3]) if len(row) > 3 else ""
            p_bg, p_txt  = PRACTICE_BADGE.get(practice, ("#475569", "#E2E8F0"))
            l_bg, l_txt  = LEVEL_BADGE.get(level, ("#475569", "#1E293B"))
            row_bg = "rgba(255,255,255,0.04)" if i % 2 == 0 else "rgba(255,255,255,0.01)"
            rows_html += f"""
            <tr style="background:{row_bg}; transition: background .15s;">
                <td style="color:#94A3B8; font-size:0.73rem; padding:8px 10px;">{row[0]}</td>
                <td style="color:#F1F5F9; font-weight:600; padding:8px 10px;">{row[1]}</td>
                <td style="padding:8px 10px;">
                    <span style="background:{p_bg}22; color:{p_bg}; border:1px solid {p_bg}55;
                                 border-radius:20px; padding:2px 9px; font-size:0.72rem; font-weight:600;">
                        {practice}
                    </span>
                </td>
                <td style="padding:8px 10px;">
                    <span style="background:{l_bg}; color:{l_txt};
                                 border-radius:20px; padding:2px 9px; font-size:0.72rem; font-weight:700;">
                        {level}
                    </span>
                </td>
                <td style="color:#94A3B8; font-size:0.78rem; padding:8px 10px;">{row[4]}</td>
                <td style="color:#34D399; font-weight:700; padding:8px 10px;">${row[5]:,.4f}</td>
                <td style="color:#A5B4FC; padding:8px 10px;">{int(row[6]):,}</td>
                <td style="color:#CBD5E1; padding:8px 10px;">{int(row[7]):,}</td>
                <td style="color:#CBD5E1; padding:8px 10px;">{int(row[8]):,}</td>
            </tr>"""

        st.markdown(f"""
        <div style="overflow-x:auto; border-radius:12px; border:1px solid rgba(255,255,255,0.08);">
        <table style="width:100%; border-collapse:collapse; font-size:0.82rem;">
            <thead>
                <tr style="background:linear-gradient(90deg,#2E1065,#1E3A5F);
                            color:#A78BFA; font-size:0.73rem; text-transform:uppercase;
                            letter-spacing:.06em;">
                    <th style="padding:11px 10px; text-align:left;">Email</th>
                    <th style="padding:11px 10px; text-align:left;">Name</th>
                    <th style="padding:11px 10px; text-align:left;">Practice</th>
                    <th style="padding:11px 10px; text-align:left;">Level</th>
                    <th style="padding:11px 10px; text-align:left;">Location</th>
                    <th style="padding:11px 10px; text-align:left;">Total Cost</th>
                    <th style="padding:11px 10px; text-align:left;">Sessions</th>
                    <th style="padding:11px 10px; text-align:left;">Tokens</th>
                    <th style="padding:11px 10px; text-align:left;">API Calls</th>
                </tr>
            </thead>
            <tbody>{rows_html}</tbody>
        </table>
        </div>
        """, unsafe_allow_html=True)

    st.markdown('<hr class="fancy-divider">', unsafe_allow_html=True)

    st.markdown('<p class="section-title">Usage Heatmap — Hour of Day × Day of Week</p>',
                unsafe_allow_html=True)
    st.markdown('<p class="section-caption">Shows API call volume by time slot — reveals peak engineering hours.</p>',
                unsafe_allow_html=True)
    heatmap_df = get_hourly_heatmap(date_from_str, date_to_str)

    if not heatmap_df.empty:
        day_labels = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
        pivot = heatmap_df.pivot_table(
            index="day_of_week", columns="hour",
            values="event_count", fill_value=0,
        )
        pivot = pivot.reindex(columns=range(24), fill_value=0)
        pivot = pivot.reindex(index=range(7), fill_value=0)

        fig_heat = go.Figure(data=go.Heatmap(
            z=pivot.values,
            x=[f"{h:02d}:00" for h in range(24)],
            y=day_labels,
            colorscale=[
                [0,   "#0F0F1A"],
                [0.2, "#3B0764"],
                [0.5, "#7C3AED"],
                [0.8, "#A78BFA"],
                [1,   "#EDE9FE"],
            ],
            hoverongaps=False,
            hovertemplate="Day: %{y}<br>Hour: %{x}<br>API Calls: %{z}<extra></extra>",
        ))
        fig_heat.update_layout(
            **CHART_LAYOUT, height=320,
            xaxis=dict(title="Hour of Day", tickangle=-45,
                       gridcolor="rgba(255,255,255,0.04)"),
            yaxis=dict(title="Day of Week", gridcolor="rgba(255,255,255,0.04)"),
        )
        st.plotly_chart(fig_heat, use_container_width=True)


# ===========================================================================
# TAB 3 — Tool & Error Analytics
# ===========================================================================

with tab3:

    st.markdown('<p class="section-title">Tool Usage & Rejection Rate</p>', unsafe_allow_html=True)
    tool_df = get_tool_usage(date_from_str, date_to_str)

    if not tool_df.empty:
        col_tl, col_tr = st.columns(2)

        with col_tl:
            fig_tool = px.bar(
                tool_df, x="tool_name", y="total_calls",
                color="total_calls",
                color_continuous_scale=[[0, "#164E63"], [0.5, "#0891B2"], [1, "#67E8F9"]],
                text="total_calls",
            )
            fig_tool.update_traces(textposition="outside", textfont_color="#CBD5E1")
            fig_tool.update_layout(
                **CHART_LAYOUT, height=420,
                coloraxis_showscale=False,
                xaxis=dict(tickangle=-35, title="Tool"),
                yaxis=dict(
                    title="Total Calls",
                    range=[0, tool_df["total_calls"].max() * 1.3],
                ),
                title=dict(text="Total Calls per Tool", font=dict(color="#CBD5E1", size=13)),
            )
            st.plotly_chart(fig_tool, use_container_width=True)
            st.markdown('<p class="section-caption">Total times Claude used each tool.</p>',
                        unsafe_allow_html=True)

        with col_tr:
            sorted_tool = tool_df.sort_values("rejection_rate", ascending=False)
            fig_reject = px.bar(
                sorted_tool, x="tool_name", y="rejection_rate",
                color="rejection_rate",
                color_continuous_scale=[[0, "#7F1D1D"], [0.5, "#DC2626"], [1, "#FCA5A5"]],
                text=sorted_tool["rejection_rate"].apply(lambda x: f"{x:.1f}%"),
            )
            fig_reject.update_traces(textposition="outside", textfont_color="#CBD5E1")
            fig_reject.update_layout(
                **CHART_LAYOUT, height=420,
                coloraxis_showscale=False,
                xaxis=dict(tickangle=-35, title="Tool"),
                yaxis=dict(
                    title="Rejection Rate (%)",
                    range=[0, sorted_tool["rejection_rate"].max() * 1.35],
                ),
                title=dict(text="Developer Rejection Rate", font=dict(color="#CBD5E1", size=13)),
            )
            st.plotly_chart(fig_reject, use_container_width=True)
            st.markdown('<p class="section-caption">% of times developers rejected the suggestion.</p>',
                        unsafe_allow_html=True)

    st.markdown('<hr class="fancy-divider">', unsafe_allow_html=True)

    st.markdown('<p class="section-title">Daily API Errors Over Time</p>', unsafe_allow_html=True)
    error_df = get_error_rate(date_from_str, date_to_str)

    if not error_df.empty:
        fig_err = go.Figure()
        fig_err.add_trace(go.Scatter(
            x=error_df["date"], y=error_df["error_count"],
            mode="lines+markers", name="Error Count",
            line=dict(color="#EF4444", width=2.5),
            fill="tozeroy", fillcolor="rgba(239,68,68,0.10)",
            marker=dict(size=5, color="#EF4444"),
        ))
        fig_err.update_layout(
            **CHART_LAYOUT, height=320,
            yaxis=dict(title="Error Count", gridcolor="rgba(255,255,255,0.05)"),
            hovermode="x unified",
        )
        st.plotly_chart(fig_err, use_container_width=True)
        st.markdown('<p class="section-caption">Daily API errors — rate limits, server errors, aborted requests.</p>',
                    unsafe_allow_html=True)
    else:
        st.info("No API errors found in the selected date range.")


# ===========================================================================
# TAB 4 — Anomaly Detection
# ===========================================================================

with tab4:

    st.markdown('<p class="section-title">Cost Anomaly Detection — IsolationForest</p>',
                unsafe_allow_html=True)
    st.markdown(
        '<p class="section-caption">Unsupervised ML trained on daily cost, sessions, '
        'and API calls per user. Most unusual 5% of user-days are flagged.</p>',
        unsafe_allow_html=True,
    )
    st.markdown('<hr class="fancy-divider">', unsafe_allow_html=True)

    with st.spinner("Running anomaly detection model …"):
        all_anomaly_df = detect_cost_anomalies(
            date_from=date_from_str, date_to=date_to_str, db_path=DB_PATH,
        )
        flagged_df = get_anomaly_summary(
            date_from=date_from_str, date_to=date_to_str, db_path=DB_PATH,
        )

    if all_anomaly_df.empty:
        st.warning("No data available for the selected date range.")
    else:
        total_rows    = len(all_anomaly_df)
        total_flagged = int(all_anomaly_df["is_anomaly"].sum())
        flagged_users = flagged_df["user_email"].nunique() if not flagged_df.empty else 0
        anomaly_rate  = 100 * total_flagged / total_rows if total_rows else 0

        st.markdown(f"""
        <div class="kpi-grid" style="grid-template-columns: repeat(4, 1fr);">
            <div class="kpi-card cyan">
                <div class="kpi-icon">🔍</div>
                <div class="kpi-value">{total_rows:,}</div>
                <div class="kpi-label">User-Days Analysed</div>
            </div>
            <div class="kpi-card rose">
                <div class="kpi-icon">🚨</div>
                <div class="kpi-value">{total_flagged:,}</div>
                <div class="kpi-label">Anomalous User-Days</div>
            </div>
            <div class="kpi-card amber">
                <div class="kpi-icon">👤</div>
                <div class="kpi-value">{flagged_users:,}</div>
                <div class="kpi-label">Flagged Unique Users</div>
            </div>
            <div class="kpi-card violet">
                <div class="kpi-icon">📊</div>
                <div class="kpi-value">{anomaly_rate:.1f}%</div>
                <div class="kpi-label">Anomaly Rate</div>
            </div>
        </div>
        """, unsafe_allow_html=True)

        st.markdown('<hr class="fancy-divider">', unsafe_allow_html=True)
        st.markdown('<p class="section-title">Daily Cost per User — Normal vs Anomalous</p>',
                    unsafe_allow_html=True)

        plot_df = all_anomaly_df.copy()
        plot_df["status"] = plot_df["is_anomaly"].map(
            {True: "🚨 Anomaly", False: "✅ Normal"}
        )

        fig_scatter = px.scatter(
            plot_df, x="date", y="daily_cost", color="status",
            color_discrete_map={"🚨 Anomaly": "#EF4444", "✅ Normal": "#7C3AED"},
            hover_data=["user_email", "daily_sessions", "daily_calls", "anomaly_score"],
            opacity=0.75,
            size_max=10,
        )
        fig_scatter.update_traces(marker=dict(size=7))
        fig_scatter.update_layout(
            **CHART_LAYOUT, height=400,
            yaxis=dict(title="Daily Cost (USD)"),
            legend=dict(orientation="h", yanchor="bottom", y=1.02,
                        bgcolor="rgba(0,0,0,0)", font=dict(color="#CBD5E1")),
            hovermode="closest",
        )
        st.plotly_chart(fig_scatter, use_container_width=True)
        st.markdown(
            '<p class="section-caption">Red = anomaly. '
            'These user-days have unusually high cost relative to session/API call volume.</p>',
            unsafe_allow_html=True,
        )

        st.markdown('<hr class="fancy-divider">', unsafe_allow_html=True)
        st.markdown(f'<p class="section-title">Flagged Users ({total_flagged} anomalous user-days)</p>',
                    unsafe_allow_html=True)

        if flagged_df.empty:
            st.success("No anomalies detected in the selected date range.")
        else:
            anomaly_rows_html = ""
            for i, row in enumerate(flagged_df.itertuples(index=False)):
                score = float(row[9])
                if score < -0.15:
                    row_bg    = "rgba(239,68,68,0.14)"
                    score_col = "#FCA5A5"
                    badge_bg  = "#7F1D1D"
                    badge_txt = "#FCA5A5"
                    badge_lbl = "🔴 High"
                elif score < -0.05:
                    row_bg    = "rgba(245,158,11,0.12)"
                    score_col = "#FCD34D"
                    badge_bg  = "#78350F"
                    badge_txt = "#FCD34D"
                    badge_lbl = "🟠 Medium"
                else:
                    row_bg    = "rgba(124,58,237,0.10)"
                    score_col = "#C4B5FD"
                    badge_bg  = "#2E1065"
                    badge_txt = "#C4B5FD"
                    badge_lbl = "🟣 Low"

                practice = str(row[2])
                PRACTICE_BADGE = {
                    "ML Engineering":       "#7C3AED",
                    "Frontend Engineering": "#0891B2",
                    "Backend Engineering":  "#059669",
                    "DevOps":               "#D97706",
                    "Platform Engineering": "#E11D48",
                    "Data Engineering":     "#EA580C",
                }
                p_col = PRACTICE_BADGE.get(practice, "#475569")

                anomaly_rows_html += f"""
                <tr style="background:{row_bg};">
                    <td style="color:#94A3B8; font-size:0.72rem; padding:8px 10px;">{row[0]}</td>
                    <td style="color:#F1F5F9; font-weight:600; padding:8px 10px;">{row[1]}</td>
                    <td style="padding:8px 10px;">
                        <span style="background:{p_col}22; color:{p_col};
                                     border:1px solid {p_col}55; border-radius:20px;
                                     padding:2px 8px; font-size:0.7rem; font-weight:600;">
                            {practice}
                        </span>
                    </td>
                    <td style="color:#CBD5E1; font-size:0.78rem; padding:8px 10px;">{row[3]}</td>
                    <td style="color:#94A3B8; font-size:0.75rem; padding:8px 10px;">{row[5]}</td>
                    <td style="color:#34D399; font-weight:700; padding:8px 10px;">${float(row[6]):,.4f}</td>
                    <td style="color:#A5B4FC; padding:8px 10px;">{int(row[7]):,}</td>
                    <td style="color:#A5B4FC; padding:8px 10px;">{int(row[8]):,}</td>
                    <td style="padding:8px 10px;">
                        <span style="background:{badge_bg}; color:{badge_txt};
                                     border-radius:20px; padding:3px 10px;
                                     font-size:0.72rem; font-weight:700;">
                            {badge_lbl}
                        </span>
                        <span style="color:{score_col}; font-size:0.75rem; margin-left:6px;">{score:.4f}</span>
                    </td>
                </tr>"""

            st.markdown(f"""
            <div style="max-height:420px; overflow-y:auto; overflow-x:auto; border-radius:12px; border:1px solid rgba(239,68,68,0.25);">

            <table style="width:100%; border-collapse:collapse; font-size:0.82rem;">
                <thead>
                    <tr>
                        <th style="padding:11px 10px; text-align:left; position:sticky; top:0; background:linear-gradient(90deg,#7F1D1D,#2E1065); color:#FCA5A5; font-size:0.72rem; text-transform:uppercase; letter-spacing:.06em; z-index:2;">Email</th>
                        <th style="padding:11px 10px; text-align:left; position:sticky; top:0; background:linear-gradient(90deg,#7F1D1D,#2E1065); color:#FCA5A5; font-size:0.72rem; text-transform:uppercase; letter-spacing:.06em; z-index:2;">Name</th>
                        <th style="padding:11px 10px; text-align:left; position:sticky; top:0; background:linear-gradient(90deg,#7F1D1D,#2E1065); color:#FCA5A5; font-size:0.72rem; text-transform:uppercase; letter-spacing:.06em; z-index:2;">Practice</th>
                        <th style="padding:11px 10px; text-align:left; position:sticky; top:0; background:linear-gradient(90deg,#7F1D1D,#2E1065); color:#FCA5A5; font-size:0.72rem; text-transform:uppercase; letter-spacing:.06em; z-index:2;">Level</th>
                        <th style="padding:11px 10px; text-align:left; position:sticky; top:0; background:linear-gradient(90deg,#7F1D1D,#2E1065); color:#FCA5A5; font-size:0.72rem; text-transform:uppercase; letter-spacing:.06em; z-index:2;">Date</th>
                        <th style="padding:11px 10px; text-align:left; position:sticky; top:0; background:linear-gradient(90deg,#7F1D1D,#2E1065); color:#FCA5A5; font-size:0.72rem; text-transform:uppercase; letter-spacing:.06em; z-index:2;">Daily Cost</th>
                        <th style="padding:11px 10px; text-align:left; position:sticky; top:0; background:linear-gradient(90deg,#7F1D1D,#2E1065); color:#FCA5A5; font-size:0.72rem; text-transform:uppercase; letter-spacing:.06em; z-index:2;">Sessions</th>
                        <th style="padding:11px 10px; text-align:left; position:sticky; top:0; background:linear-gradient(90deg,#7F1D1D,#2E1065); color:#FCA5A5; font-size:0.72rem; text-transform:uppercase; letter-spacing:.06em; z-index:2;">API Calls</th>
                        <th style="padding:11px 10px; text-align:left; position:sticky; top:0; background:linear-gradient(90deg,#7F1D1D,#2E1065); color:#FCA5A5; font-size:0.72rem; text-transform:uppercase; letter-spacing:.06em; z-index:2;">Severity</th>
                    </tr>
                </thead>
                <tbody>{anomaly_rows_html}</tbody>
            </table>
            </div>
            """, unsafe_allow_html=True)
            st.markdown(
                '<p class="section-caption">Anomaly Score: more negative = more anomalous.</p>',
                unsafe_allow_html=True,
            )


# ===========================================================================
# TAB 5 — Advanced Analytics
# ===========================================================================

with tab5:

    col_a, col_b = st.columns(2)

    with col_a:
        st.markdown('<p class="section-title">Avg API Calls per Session by Practice</p>',
                    unsafe_allow_html=True)
        session_df = get_session_length_distribution(date_from_str, date_to_str)

        if not session_df.empty:
            fig_session = px.bar(
                session_df, x="practice", y="avg_calls_per_session",
                color="avg_calls_per_session",
                color_continuous_scale=[[0, "#2E1065"], [0.5, "#7C3AED"], [1, "#C4B5FD"]],
                text=session_df["avg_calls_per_session"].apply(lambda x: f"{x:.1f}"),
            )
            fig_session.update_traces(textposition="outside", textfont_color="#CBD5E1")
            fig_session.update_layout(
                **CHART_LAYOUT, height=420,
                coloraxis_showscale=False,
                xaxis=dict(tickangle=-30, title="Engineering Practice"),
                yaxis=dict(
                    title="Avg API Calls / Session",
                    range=[0, session_df["avg_calls_per_session"].max() * 1.3],
                ),
            )
            st.plotly_chart(fig_session, use_container_width=True)
            st.markdown(
                '<p class="section-caption">Higher = longer, more complex tasks.</p>',
                unsafe_allow_html=True,
            )

    with col_b:
        st.markdown('<p class="section-title">Daily Active Users Over Time</p>',
                    unsafe_allow_html=True)
        dau_df = get_daily_active_users(date_from_str, date_to_str)

        if not dau_df.empty:
            fig_dau = go.Figure()
            fig_dau.add_trace(go.Scatter(
                x=dau_df["date"], y=dau_df["active_users"],
                mode="lines+markers", name="Active Users",
                line=dict(color="#10B981", width=2.5),
                fill="tozeroy", fillcolor="rgba(16,185,129,0.10)",
            ))
            fig_dau.add_trace(go.Scatter(
                x=dau_df["date"], y=dau_df["total_sessions"],
                mode="lines", name="Total Sessions",
                line=dict(color="#A78BFA", width=2, dash="dot"),
                yaxis="y2",
            ))
            fig_dau.update_layout(
                **CHART_LAYOUT, height=360,
                yaxis=dict(title="Active Users"),
                yaxis2=dict(title="Sessions", overlaying="y", side="right",
                            gridcolor="rgba(0,0,0,0)"),
                legend=dict(orientation="h", yanchor="bottom", y=1.02,
                            bgcolor="rgba(0,0,0,0)", font=dict(color="#CBD5E1")),
                hovermode="x unified",
            )
            st.plotly_chart(fig_dau, use_container_width=True)
            st.markdown(
                '<p class="section-caption">Green = unique users. Purple = total sessions (right axis).</p>',
                unsafe_allow_html=True,
            )

    st.markdown('<hr class="fancy-divider">', unsafe_allow_html=True)

    st.markdown('<p class="section-title">Average Prompt Length Over Time</p>',
                unsafe_allow_html=True)
    prompt_df = get_prompt_length_over_time(date_from_str, date_to_str)

    if not prompt_df.empty:
        fig_prompt = go.Figure()
        fig_prompt.add_trace(go.Scatter(
            x=prompt_df["date"], y=prompt_df["avg_prompt_length"],
            mode="lines+markers", name="Avg Prompt Length",
            line=dict(color="#F59E0B", width=2.5),
            fill="tozeroy", fillcolor="rgba(245,158,11,0.10)",
        ))
        fig_prompt.add_trace(go.Scatter(
            x=prompt_df["date"], y=prompt_df["max_prompt_length"],
            mode="lines", name="Max Prompt Length",
            line=dict(color="#F43F5E", width=1.5, dash="dash"),
            yaxis="y2",
        ))
        fig_prompt.update_layout(
            **CHART_LAYOUT, height=320,
            yaxis=dict(title="Avg Length (chars)"),
            yaxis2=dict(title="Max Length (chars)", overlaying="y", side="right",
                        gridcolor="rgba(0,0,0,0)"),
            legend=dict(orientation="h", yanchor="bottom", y=1.02,
                        bgcolor="rgba(0,0,0,0)", font=dict(color="#CBD5E1")),
            hovermode="x unified",
        )
        st.plotly_chart(fig_prompt, use_container_width=True)
        st.markdown(
            '<p class="section-caption">Rising trend = developers tackling more complex tasks over time.</p>',
            unsafe_allow_html=True,
        )

    st.markdown('<hr class="fancy-divider">', unsafe_allow_html=True)

    col_c, col_d = st.columns(2)

    with col_c:
        st.markdown('<p class="section-title">Model Preference by Engineering Practice</p>',
                    unsafe_allow_html=True)
        model_prac_df = get_model_by_practice(date_from_str, date_to_str)

        if not model_prac_df.empty:
            model_prac_df["model_short"] = (
                model_prac_df["model"]
                .str.replace(r"claude-", "", regex=True)
                .str.replace(r"-\d{8,}", "", regex=True)
            )
            fig_model_prac = px.bar(
                model_prac_df, x="practice", y="api_calls",
                color="model_short", barmode="stack",
                color_discrete_sequence=["#7C3AED", "#06B6D4", "#10B981", "#F59E0B", "#F43F5E"],
            )
            fig_model_prac.update_layout(
                **CHART_LAYOUT, height=420,
                xaxis=dict(tickangle=-35, title="", tickfont=dict(size=10)),
                yaxis=dict(title="API Calls"),
                legend=dict(orientation="h", yanchor="bottom", y=1.02,
                            bgcolor="rgba(0,0,0,0)", font=dict(color="#CBD5E1", size=10)),
            )
            st.plotly_chart(fig_model_prac, use_container_width=True)
            st.markdown(
                '<p class="section-caption">Which models each practice prefers — stacked by API calls.</p>',
                unsafe_allow_html=True,
            )

    with col_d:
        st.markdown('<p class="section-title">Cost Efficiency Leaderboard</p>',
                    unsafe_allow_html=True)
        st.markdown('<p class="section-caption">Output tokens per dollar — higher is better.</p>',
                    unsafe_allow_html=True)
        efficiency_df = get_cost_efficiency(n=15, date_from=date_from_str, date_to=date_to_str)

        if not efficiency_df.empty:
            fig_eff = px.bar(
                efficiency_df, x="efficiency_score", y="full_name", orientation="h",
                color="efficiency_score",
                color_continuous_scale=[[0, "#064E3B"], [0.5, "#059669"], [1, "#6EE7B7"]],
                hover_data=["practice", "level", "total_cost", "total_output_tokens"],
                text=efficiency_df["efficiency_score"].apply(lambda x: f"{x:,.0f}"),
            )
            fig_eff.update_traces(textposition="outside", textfont_color="#CBD5E1")
            fig_eff.update_layout(
                **CHART_LAYOUT, height=460,
                coloraxis_showscale=False,
                yaxis=dict(categoryorder="total ascending", title=""),
                xaxis=dict(
                    title="Output Tokens / Dollar",
                    range=[0, efficiency_df["efficiency_score"].max() * 1.3],
                ),
            )
            st.plotly_chart(fig_eff, use_container_width=True)
