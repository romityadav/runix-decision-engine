"""Runix decision dashboard (Streamlit).

A hub manager's cockpit. It does three things a static report cannot:

1. Shows the WhatsApp alert exactly as it would arrive.
2. Lets the manager drag the two judgement calls the data cannot make —
   congestion severity (beta) and how much a breach really costs (M) — and
   watch the recommendation, the cost curve, and the risk move live.
3. Puts the decision in context with a sensitivity heatmap, so the manager can
   see whether tonight's call sits deep inside a stable region or right on a
   knife-edge.

Run with:  make dashboard   (or)   streamlit run app/dashboard.py
"""

from __future__ import annotations

from pathlib import Path

import plotly.graph_objects as go
import streamlit as st

from runix.config import EngineConfig
from runix.data_loader import load_scenario
from runix.pipeline import run
from runix.sensitivity import sweep

_DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DATASET = _DATA_DIR / "Runix_Logistics_Engine_Scenario_Dataset.xlsx"

RISK_COLOUR = {"Low": "#16a34a", "Medium": "#d97706", "High": "#dc2626"}

st.set_page_config(page_title="Runix Decision Engine", page_icon="🚚", layout="wide")


@st.cache_resource
def _scenario(path: str):
    return load_scenario(path)


@st.cache_data
def _sweep(path: str, betas: tuple[float, ...], mults: tuple[float, ...]):
    sc = load_scenario(path)
    grid = sweep(sc, EngineConfig(), list(betas), list(mults))
    return grid.betas, grid.multipliers, grid.recommended_drivers


# ---------------------------------------------------------------------------
# Charts
# ---------------------------------------------------------------------------


def risk_gauge(score: float, level: str) -> go.Figure:
    fig = go.Figure(
        go.Indicator(
            mode="gauge+number",
            value=score,
            number={"suffix": " / 100", "font": {"size": 34}},
            title={"text": f"Composite risk — <b>{level}</b>"},
            gauge={
                "axis": {"range": [0, 100]},
                "bar": {"color": RISK_COLOUR[level]},
                "steps": [
                    {"range": [0, 40], "color": "#dcfce7"},
                    {"range": [40, 70], "color": "#fef3c7"},
                    {"range": [70, 100], "color": "#fee2e2"},
                ],
                "threshold": {
                    "line": {"color": "black", "width": 3},
                    "value": score,
                },
            },
        )
    )
    fig.update_layout(height=260, margin=dict(t=60, b=10, l=20, r=20))
    return fig


def capacity_waterfall(cap) -> go.Figure:
    fig = go.Figure(
        go.Waterfall(
            orientation="v",
            measure=["absolute", "relative", "relative", "total"],
            x=["Nominal", "Snow impact", "Congestion", "Effective"],
            text=[
                f"{cap.nominal_capacity:.0f}",
                f"−{cap.nominal_capacity - cap.weather_capacity:.0f}",
                f"−{cap.weather_capacity - cap.effective_capacity:.1f}",
                f"{cap.effective_capacity:.1f}",
            ],
            y=[
                cap.nominal_capacity,
                -(cap.nominal_capacity - cap.weather_capacity),
                -(cap.weather_capacity - cap.effective_capacity),
                cap.effective_capacity,
            ],
            connector={"line": {"color": "#94a3b8"}},
            decreasing={"marker": {"color": "#dc2626"}},
            totals={"marker": {"color": "#2563eb"}},
        )
    )
    fig.add_hline(
        y=cap.demand,
        line_dash="dash",
        line_color="#111827",
        annotation_text=f"Demand = {cap.demand} orders",
        annotation_position="top left",
    )
    fig.update_layout(
        title="Where the capacity goes (deliveries/shift)",
        height=360,
        margin=dict(t=50, b=10, l=10, r=10),
    )
    return fig


def cost_curve_chart(decision) -> go.Figure:
    xs = [p.extra_drivers for p in decision.cost_curve]
    deploy = [p.deployment_cost for p in decision.cost_curve]
    breach = [p.weighted_penalty for p in decision.cost_curve]
    total = [p.total_cost for p in decision.cost_curve]

    fig = go.Figure()
    fig.add_bar(x=xs, y=deploy, name="Driver cost", marker_color="#2563eb")
    fig.add_bar(x=xs, y=breach, name="Breach cost (×M)", marker_color="#f59e0b")
    fig.add_scatter(
        x=xs, y=total, name="Total cost", mode="lines+markers",
        line=dict(color="#111827", width=3),
    )
    rec = decision.recommended_extra_drivers
    fig.add_scatter(
        x=[rec],
        y=[next(p.total_cost for p in decision.cost_curve if p.extra_drivers == rec)],
        name="Recommended",
        mode="markers",
        marker=dict(color="#16a34a", size=18, symbol="star"),
    )
    fig.update_layout(
        barmode="stack",
        title="Total cost vs. extra drivers (lower is better)",
        xaxis_title="Extra drivers deployed",
        yaxis_title="Cost ($)",
        height=360,
        margin=dict(t=50, b=10, l=10, r=10),
        legend=dict(orientation="h", y=1.12),
    )
    return fig


def baselines_chart(baselines, engine_cost: float, engine_drivers: int) -> go.Figure:
    labels = [b.label for b in baselines] + ["→ Engine"]
    costs = [b.total_cost for b in baselines] + [engine_cost]
    colours = ["#94a3b8"] * len(baselines) + ["#16a34a"]
    fig = go.Figure(go.Bar(x=costs, y=labels, orientation="h", marker_color=colours,
                           text=[f"${c:,.0f}" for c in costs], textposition="auto"))
    fig.update_layout(
        title="Engine vs. naive strategies (total cost at current M)",
        xaxis_title="Total cost ($)",
        height=300,
        margin=dict(t=50, b=10, l=10, r=10),
    )
    return fig


def sensitivity_heatmap(betas, mults, grid, cur_beta, cur_m) -> go.Figure:
    fig = go.Figure(
        go.Heatmap(
            z=grid,
            x=mults,
            y=betas,
            colorscale="YlOrRd",
            colorbar=dict(title="Drivers"),
            hovertemplate="M=%{x}, β=%{y}: deploy %{z}<extra></extra>",
        )
    )
    fig.add_scatter(
        x=[cur_m], y=[cur_beta], mode="markers",
        marker=dict(color="#2563eb", size=16, symbol="x", line=dict(width=2, color="white")),
        name="You are here",
    )
    fig.update_layout(
        title="Recommended drivers across both assumptions",
        xaxis_title="Breach aversion M  (cost of a breach vs its penalty)",
        yaxis_title="Congestion sensitivity β",
        height=360,
        margin=dict(t=50, b=10, l=10, r=10),
    )
    return fig


# ---------------------------------------------------------------------------
# Layout
# ---------------------------------------------------------------------------


def main() -> None:
    st.title("🚚 Runix Decision Engine")
    st.caption(
        "Operational risk, capacity, and a costed staffing decision for tonight's shift — "
        "with the two business assumptions on the table, not buried in the code."
    )

    if not DATASET.exists():
        st.error(f"Dataset not found at {DATASET}")
        st.stop()

    # --- sidebar: the two knobs ---
    st.sidebar.header("Assumptions")
    st.sidebar.caption("These are the calls the data can't make for you.")
    beta = st.sidebar.slider(
        "Congestion sensitivity β",
        0.0, 1.0, 0.5, 0.05,
        help="How hard the road event erodes throughput. 0 = no capacity impact.",
    )
    m = st.sidebar.slider(
        "Breach aversion M",
        0.5, 10.0, 1.0, 0.25,
        help="What a missed SLA truly costs vs its contractual penalty. 1 = trust the contract.",
    )
    st.sidebar.divider()
    st.sidebar.caption(
        "Defaults: β = 0.5 (a moderate event drag), M = 1.0 (contractual economics)."
    )

    scenario = _scenario(str(DATASET))
    config = EngineConfig(congestion_sensitivity=beta, breach_aversion=m)
    result = run(scenario, config=config)
    alert, cap, risk, dec = result.alert, result.capacity, result.risk, result.decision

    # --- top row: alert card + gauge + headline metrics ---
    left, right = st.columns([1.25, 1])
    with left:
        _render_alert_card(alert)
    with right:
        st.plotly_chart(risk_gauge(risk.composite_score, risk.level), width="stretch")
        c1, c2, c3 = st.columns(3)
        c1.metric("Recommended drivers", f"+{dec.recommended_extra_drivers}")
        c2.metric("Total cost tonight", f"${dec.total_cost:,.0f}")
        c3.metric("Confidence", f"{dec.confidence}%")

    # --- the decision in one sentence ---
    _render_decision_banner(dec)

    st.divider()

    # --- capacity + cost curve ---
    a, b = st.columns(2)
    with a:
        st.plotly_chart(capacity_waterfall(cap), width="stretch")
    with b:
        st.plotly_chart(cost_curve_chart(dec), width="stretch")

    # --- baselines + sensitivity ---
    c, d = st.columns(2)
    with c:
        st.plotly_chart(
            baselines_chart(result.baselines, dec.total_cost, dec.recommended_extra_drivers),
            width="stretch",
        )
    with d:
        betas, mults, grid = _sweep(
            str(DATASET),
            tuple(round(0.05 * i, 2) for i in range(0, 21)),
            tuple(round(0.5 * i, 2) for i in range(1, 21)),
        )
        st.plotly_chart(
            sensitivity_heatmap(betas, mults, grid, beta, m), width="stretch"
        )

    # --- detail expanders ---
    with st.expander("Capacity & risk detail"):
        _render_detail(cap, risk)
    with st.expander("Data-quality notes (what we caught in the workbook)"):
        for note in scenario.data_quality_notes:
            st.markdown(f"- {note}")
    with st.expander("Full machine-readable report (JSON)"):
        st.json(result.report())


def _render_alert_card(alert) -> None:
    a = alert.to_dict()
    colour = RISK_COLOUR.get(a["risk_level"], "#334155")
    st.markdown(
        f"""
        <div style="background:#e7f7ec;border-radius:14px;padding:18px 20px;
                    box-shadow:0 1px 4px rgba(0,0,0,0.12);max-width:560px;">
          <div style="font-size:13px;color:#475569;margin-bottom:6px;">
            📲 <b>Runix Ops Alert</b> · WhatsApp
          </div>
          <div style="font-size:20px;font-weight:700;color:{colour};margin-bottom:8px;">
            ⚠️ Risk: {a["risk_level"]} &nbsp;·&nbsp; Confidence {a["confidence_score"]}
          </div>
          <div style="font-size:15px;color:#0f172a;line-height:1.5;">
            <p style="margin:6px 0;"><b>Why:</b> {a["risk_summary"]}</p>
            <p style="margin:6px 0;"><b>Impact:</b> {a["estimated_impact"]}</p>
            <p style="margin:6px 0;"><b>Do this:</b> {a["prescription"]}</p>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_decision_banner(dec) -> None:
    be = dec.break_even_to_deploy
    if dec.recommended_extra_drivers == 0:
        full = dec.cost_curve[-1]
        msg = (
            f"**Hold and prioritise.** Spending ${full.deployment_cost:,.0f} on "
            f"{full.extra_drivers} drivers to avoid ${dec.raw_penalty_exposure:,.0f} of "
            f"standard-order penalties is a losing trade at this breach valuation. It only flips "
            f"to deploying once a breach is worth **>{be:g}×** its contractual penalty."
        )
        st.success(msg)
    else:
        st.warning(
            f"**Deploy {dec.recommended_extra_drivers} extra driver(s)** "
            f"(${dec.deployment_cost:,.0f}) and prioritise express + affected-zone orders — at "
            f"this breach valuation the spend beats ${dec.weighted_breach_cost:,.0f} of "
            f"projected penalties."
        )


def _render_detail(cap, risk) -> None:
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("**Capacity**")
        st.table(
            {
                "Stage": [
                    "Nominal", "After snow", "Congestion factor",
                    "Effective", "Servable", "Shortfall",
                ],
                "Value": [
                    f"{cap.nominal_capacity:.0f}",
                    f"{cap.weather_capacity:.0f}",
                    f"{cap.congestion_factor:.3f}",
                    f"{cap.effective_capacity:.1f}",
                    f"{cap.servable}",
                    f"{cap.shortfall}",
                ],
            }
        )
    with col2:
        st.markdown("**Risk sub-scores** (weighted 40/30/30)")
        st.table(
            {
                "Factor": ["Weather", "Traffic", "Load", "Composite"],
                "Score": [
                    f"{risk.weather_sub_score:.0f}",
                    f"{risk.traffic_sub_score:.0f}",
                    f"{risk.load_sub_score:.0f}",
                    f"{risk.composite_score:.1f} ({risk.level})",
                ],
            }
        )


if __name__ == "__main__":
    main()
