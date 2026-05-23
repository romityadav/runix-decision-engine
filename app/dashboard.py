"""Runix decision dashboard (Streamlit) — written to be read by a busy manager.

The page tells one story, top to bottom:

    1. Set tonight's situation (two plain-English questions).
    2. THE CALL — the recommendation, big and unmissable.
    3. The alert exactly as it lands on WhatsApp.
    4. Why — three plain steps: what we can deliver, who we protect, is it worth hiring.
    5. When would the answer change? — the sensitivity map.

Jargon (beta, M, "composite", "breach aversion") is kept out of the main flow and
tucked into the detail expanders for the curious.

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

# Plain-English choices mapped to the engine's two assumptions.
EVENT_CHOICES = {
    "Not at all": 0.0,
    "A little": 0.25,
    "Moderately (likely)": 0.5,
    "Heavily": 0.75,
    "Severely": 1.0,
}
VALUE_CHOICES = {
    "Just the penalty (1×)": 1.0,
    "A bit more (2×)": 2.0,
    "Noticeably more (3×)": 3.0,
    "A lot more (5×)": 5.0,
    "Reputation-critical (8×)": 8.0,
}

st.set_page_config(page_title="Runix — Tonight's Delivery Call", page_icon="🚚", layout="wide")


@st.cache_resource
def _scenario(path: str):
    return load_scenario(path)


@st.cache_data
def _sweep(path: str, betas: tuple[float, ...], mults: tuple[float, ...]):
    sc = load_scenario(path)
    grid = sweep(sc, EngineConfig(), list(betas), list(mults))
    return grid.betas, grid.multipliers, grid.recommended_drivers


# ---------------------------------------------------------------------------
# Charts (plain titles, no jargon)
# ---------------------------------------------------------------------------


def capacity_waterfall(cap) -> go.Figure:
    fig = go.Figure(
        go.Waterfall(
            orientation="v",
            measure=["absolute", "relative", "relative", "total"],
            x=["A normal day", "Snow", "Traffic", "Tonight"],
            text=[
                f"{cap.nominal_capacity:.0f}",
                f"−{cap.nominal_capacity - cap.weather_capacity:.0f}",
                f"−{cap.weather_capacity - cap.effective_capacity:.1f}",
                f"{cap.effective_capacity:.0f}",
            ],
            y=[
                cap.nominal_capacity,
                -(cap.nominal_capacity - cap.weather_capacity),
                -(cap.weather_capacity - cap.effective_capacity),
                cap.effective_capacity,
            ],
            connector={"line": {"color": "#cbd5e1"}},
            decreasing={"marker": {"color": "#dc2626"}},
            totals={"marker": {"color": "#2563eb"}},
        )
    )
    fig.add_hline(
        y=cap.demand,
        line_dash="dash",
        line_color="#111827",
        annotation_text=f"We have {cap.demand} orders to deliver",
        annotation_position="top left",
    )
    fig.update_layout(
        yaxis_title="Deliveries we can make",
        height=340,
        margin=dict(t=20, b=10, l=10, r=10),
        showlegend=False,
    )
    return fig


def protection_chart(dec, scenario) -> go.Figure:
    express_total = len(scenario.express_orders)
    express_served = express_total - dec.unserved_express
    standard_served = dec.served - express_served
    fig = go.Figure()
    fig.add_bar(
        y=["Orders"], x=[express_served], orientation="h",
        name=f"Express — protected ({express_served})", marker_color="#16a34a",
    )
    fig.add_bar(
        y=["Orders"], x=[standard_served], orientation="h",
        name=f"Standard — on time ({standard_served})", marker_color="#3b82f6",
    )
    if dec.unserved_standard:
        fig.add_bar(
            y=["Orders"], x=[dec.unserved_standard], orientation="h",
            name=f"Standard — at risk ({dec.unserved_standard})", marker_color="#f59e0b",
        )
    if dec.unserved_express:
        fig.add_bar(
            y=["Orders"], x=[dec.unserved_express], orientation="h",
            name=f"Express — at risk ({dec.unserved_express})", marker_color="#dc2626",
        )
    fig.update_layout(
        barmode="stack",
        height=170,
        margin=dict(t=10, b=10, l=10, r=10),
        legend=dict(orientation="h", y=-0.4),
        xaxis_title="Number of orders",
    )
    return fig


def cost_curve_chart(decision) -> go.Figure:
    xs = [p.extra_drivers for p in decision.cost_curve]
    deploy = [p.deployment_cost for p in decision.cost_curve]
    breach = [p.weighted_penalty for p in decision.cost_curve]
    total = [p.total_cost for p in decision.cost_curve]

    fig = go.Figure()
    fig.add_bar(x=xs, y=deploy, name="Cost of extra drivers", marker_color="#2563eb")
    fig.add_bar(x=xs, y=breach, name="Cost of missed deliveries", marker_color="#f59e0b")
    fig.add_scatter(
        x=xs, y=total, name="Total cost", mode="lines+markers",
        line=dict(color="#111827", width=3),
    )
    rec = decision.recommended_extra_drivers
    fig.add_scatter(
        x=[rec],
        y=[next(p.total_cost for p in decision.cost_curve if p.extra_drivers == rec)],
        name="Cheapest (recommended)", mode="markers",
        marker=dict(color="#16a34a", size=20, symbol="star"),
    )
    fig.update_layout(
        barmode="stack",
        xaxis_title="Extra drivers we hire",
        yaxis_title="Total cost tonight ($)",
        height=340,
        margin=dict(t=20, b=10, l=10, r=10),
        legend=dict(orientation="h", y=1.15),
    )
    fig.update_xaxes(dtick=1)
    return fig


def sensitivity_heatmap(betas, mults, grid, cur_beta, cur_m) -> go.Figure:
    fig = go.Figure(
        go.Heatmap(
            z=grid, x=mults, y=betas, colorscale="YlOrRd",
            colorbar=dict(title="Drivers<br>to hire"),
            hovertemplate="miss costs %{x}×, traffic drag %{y} → hire %{z}<extra></extra>",
        )
    )
    fig.add_scatter(
        x=[cur_m], y=[cur_beta], mode="markers+text",
        marker=dict(color="#1d4ed8", size=18, symbol="x", line=dict(width=2, color="white")),
        text=["you"], textposition="top center", textfont=dict(color="#1d4ed8", size=13),
        name="Your setting",
    )
    fig.update_layout(
        xaxis_title="How much a missed delivery really costs (× its penalty)",
        yaxis_title="How much the match slows deliveries",
        height=360,
        margin=dict(t=20, b=10, l=10, r=10),
        showlegend=False,
    )
    return fig


def baselines_chart(baselines, engine_cost, engine_drivers) -> go.Figure:
    rows = [
        ("Hire enough to miss nothing", baselines[1].total_cost, baselines[1].extra_drivers),
        ("Do nothing, no prioritising", baselines[0].total_cost, baselines[0].extra_drivers),
        ("Runix recommendation", engine_cost, engine_drivers),
    ]
    labels = [r[0] for r in rows]
    costs = [r[1] for r in rows]
    colours = ["#94a3b8", "#94a3b8", "#16a34a"]
    fig = go.Figure(
        go.Bar(
            x=costs, y=labels, orientation="h", marker_color=colours,
            text=[f"${c:,.0f}  (+{r[2]} drivers)" for c, r in zip(costs, rows, strict=True)],
            textposition="auto",
        )
    )
    fig.update_layout(
        xaxis_title="Total cost tonight ($) — lower is better",
        height=240,
        margin=dict(t=20, b=10, l=10, r=10),
    )
    return fig


# ---------------------------------------------------------------------------
# Page
# ---------------------------------------------------------------------------


def main() -> None:
    st.title("🚚 Tonight's Delivery Call")
    st.caption(
        "Heavy snow from 6 PM and a major match snarling the central zone. "
        "50 orders, 10 drivers. Here's what to do — and why."
    )

    if not DATASET.exists():
        st.error(f"Dataset not found at {DATASET}")
        st.stop()
    scenario = _scenario(str(DATASET))

    # --- 1. Set the situation (two plain questions) -------------------------
    with st.container(border=True):
        st.markdown("#### 1 · Your read on tonight")
        q1, q2 = st.columns(2)
        with q1:
            event_label = st.select_slider(
                "How much is the football match slowing deliveries?",
                options=list(EVENT_CHOICES), value="Moderately (likely)",
            )
            beta = EVENT_CHOICES[event_label]
        with q2:
            value_label = st.select_slider(
                "How much does a missed delivery really cost you?",
                options=list(VALUE_CHOICES), value="Just the penalty (1×)",
                help="Beyond the contract penalty — think repeat-delivery, support, lost goodwill.",
            )
            m = VALUE_CHOICES[value_label]

    config = EngineConfig(congestion_sensitivity=beta, breach_aversion=m)
    result = run(scenario, config=config)
    alert, cap, risk, dec = result.alert, result.capacity, result.risk, result.decision
    std_penalty = int(scenario.constants.standard_penalty)

    # --- 2. THE CALL (hero) -------------------------------------------------
    st.markdown("#### 2 · The call")
    _render_hero(dec)
    m1, m2, m3 = st.columns(3)
    m1.metric("Risk level", risk.level, help="How dangerous tonight's conditions are.")
    m2.metric("Cost of this plan", f"${dec.total_cost:,.0f}")
    m3.metric(
        "Confidence", f"{dec.confidence}%",
        help="How clearly this option beats the next-best one. Lower = it's a close call.",
    )

    # --- 3. The alert -------------------------------------------------------
    st.markdown("#### 3 · The alert your team gets")
    _render_alert_card(alert)

    st.divider()

    # --- 4. Why (three plain steps) ----------------------------------------
    st.markdown("#### 4 · Why")

    st.markdown("**Step 1 — How many deliveries can we actually make tonight?**")
    sc1, sc2 = st.columns([1.1, 1])
    with sc1:
        st.plotly_chart(capacity_waterfall(cap), width="stretch")
    with sc2:
        st.markdown(
            f"A normal driver does {scenario.constants.deliveries_per_driver_per_shift:.0f} "
            f"deliveries a shift. Snow cuts that to 60%, and the match adds more drag. "
            f"\n\n**Result: ~{cap.effective_capacity:.0f} deliveries possible, but {cap.demand} "
            f"orders waiting → about {cap.shortfall} will be late unless we act.**"
        )

    st.markdown("**Step 2 — Who do we protect?**")
    st.plotly_chart(protection_chart(dec, scenario), width="stretch")
    if dec.express_protected:
        st.markdown(
            f"✅ **Just by delivering express + central-zone orders first, all "
            f"{len(scenario.express_orders)} premium orders are safe.** Every order at risk is a "
            f"low-value standard one — and that costs nothing to arrange."
        )
    else:
        st.markdown(
            f"⚠️ Capacity is tight enough that **{dec.unserved_express} express orders** are at "
            f"risk even after prioritising. That's why hiring is now on the table."
        )

    st.markdown("**Step 3 — Is it worth hiring extra drivers?**")
    cc1, cc2 = st.columns([1.1, 1])
    with cc1:
        st.plotly_chart(cost_curve_chart(dec), width="stretch")
    with cc2:
        _render_step3_text(dec, value_label, m, std_penalty)

    st.divider()

    # --- 5. When would the answer change? ----------------------------------
    st.markdown("#### 5 · When would the answer change?")
    hc1, hc2 = st.columns([1.2, 1])
    with hc1:
        betas, mults, grid = _sweep(
            str(DATASET),
            tuple(round(0.05 * i, 2) for i in range(0, 21)),
            tuple(round(0.5 * i, 2) for i in range(1, 21)),
        )
        st.plotly_chart(sensitivity_heatmap(betas, mults, grid, beta, m), width="stretch")
    with hc2:
        st.markdown(
            "Each square is the recommended number of drivers for a different read on the night. "
            "Pale = hire nobody; darker = hire more. The blue **✕** is where your two answers "
            "land.\n\nThe big pale region is the point: **for most reasonable beliefs, holding "
            "drivers is the right call.** It only changes if you think the event is bad *and* a "
            "missed delivery is worth several times its penalty."
        )

    # --- details for the curious -------------------------------------------
    with st.expander("Compare with the naive approaches"):
        st.plotly_chart(
            baselines_chart(result.baselines, dec.total_cost, dec.recommended_extra_drivers),
            width="stretch",
        )
        st.caption(
            "Just re-sequencing the route sheet (free) saves "
            f"${result.baselines[0].total_cost - result.baselines[2].total_cost:,.0f} versus doing "
            "nothing — the highest-return move available, at zero spend."
        )
    with st.expander("The numbers (capacity, risk, and the technical settings)"):
        _render_detail(cap, risk, beta, m)
    with st.expander("What we caught in the data file"):
        for note in scenario.data_quality_notes:
            st.markdown(f"- {note}")
    with st.expander("Raw JSON (the WhatsApp payload + full report)"):
        st.json(result.report())


def _render_hero(dec) -> None:
    if dec.recommended_extra_drivers == 0:
        st.success(
            "### ✋ Hold — don't hire extra drivers\n"
            "Re-sequence the route sheet to protect express + central orders. "
            "That's free, it covers every premium order, and hiring drivers isn't "
            "worth it at tonight's numbers."
        )
    else:
        n = dec.recommended_extra_drivers
        st.warning(
            f"### 🚚 Deploy {n} extra {'driver' if n == 1 else 'drivers'} "
            f"(${dec.deployment_cost:,.0f})\n"
            "Still protect express + central orders first — but at this valuation the extra "
            "drivers pay for themselves against the missed-delivery cost."
        )


def _render_step3_text(dec, value_label, m, std_penalty) -> None:
    full = dec.cost_curve[-1]
    be = dec.break_even_to_deploy
    if dec.recommended_extra_drivers == 0:
        st.markdown(
            f"Hiring {full.extra_drivers} drivers to miss nothing costs "
            f"**${full.deployment_cost:,.0f}** — to avoid only "
            f"**${dec.raw_penalty_exposure:,.0f}** of standard-order penalties. That's a bad "
            f"trade.\n\nYou're currently treating a missed delivery as **{value_label.lower()}** "
            f"(≈ ${m * std_penalty:,.0f} of real harm). It would only become worth hiring once "
            f"that crosses **{be:g}×** the ${std_penalty} penalty."
        )
    else:
        st.markdown(
            f"At your setting (a missed delivery worth **{value_label.lower()}**), the "
            f"${dec.deployment_cost:,.0f} for {dec.recommended_extra_drivers} drivers beats the "
            f"**${dec.weighted_breach_cost:,.0f}** those misses would cost. So hiring wins."
        )


def _render_alert_card(alert) -> None:
    a = alert.to_dict()
    colour = RISK_COLOUR.get(a["risk_level"], "#334155")
    st.markdown(
        f"""
        <div style="background:#e7f7ec;border-radius:14px;padding:18px 20px;
                    box-shadow:0 1px 4px rgba(0,0,0,0.12);max-width:620px;">
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


def _render_detail(cap, risk, beta, m) -> None:
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("**Capacity**")
        st.table(
            {
                "Stage": [
                    "Normal day", "After snow", "After traffic", "Servable", "At risk",
                ],
                "Deliveries": [
                    f"{cap.nominal_capacity:.0f}",
                    f"{cap.weather_capacity:.0f}",
                    f"{cap.effective_capacity:.1f}",
                    f"{cap.servable}",
                    f"{cap.shortfall}",
                ],
            }
        )
    with col2:
        st.markdown("**Risk (weighted 40 / 30 / 30)**")
        st.table(
            {
                "Factor": ["Weather", "Traffic", "Load", "Overall"],
                "Score": [
                    f"{risk.weather_sub_score:.0f}",
                    f"{risk.traffic_sub_score:.0f}",
                    f"{risk.load_sub_score:.0f}",
                    f"{risk.composite_score:.1f} ({risk.level})",
                ],
            }
        )
    st.caption(
        f"Technical settings behind the two sliders: congestion sensitivity β = {beta}, "
        f"breach-aversion M = {m}. See docs/DECISION_LOGIC.md."
    )


if __name__ == "__main__":
    main()
