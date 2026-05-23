"""Human-readable narrative for the alert (the WhatsApp prose).

The brief allows an LLM "to assist with the reasoning" but evaluates the *logic*,
so the default narrator is deterministic templating: every sentence is a direct
read-out of numbers the engine already computed, which makes the alert
reproducible and unit-testable. An optional :class:`LLMNarrator` is provided
behind the same interface for richer phrasing, and it falls back to the template
on any error (missing key, no network, no package) so the engine always works
offline.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from .capacity import CapacityResult
from .decision import DecisionResult
from .logging_setup import get_logger
from .models import Scenario
from .risk import RiskResult

log = get_logger("runix.narrative")


@dataclass(frozen=True, slots=True)
class Narrative:
    """The three prose fields of the alert."""

    risk_summary: str
    estimated_impact: str
    prescription: str


@dataclass(frozen=True, slots=True)
class NarrativeContext:
    """Everything a narrator needs, already computed."""

    scenario: Scenario
    capacity: CapacityResult
    risk: RiskResult
    decision: DecisionResult


class NarrativeGenerator(Protocol):
    """Anything that can turn the decision context into prose."""

    def compose(self, ctx: NarrativeContext) -> Narrative: ...


def _money(value: float) -> str:
    return f"${value:,.0f}"


class TemplateNarrator:
    """Deterministic, dependency-free narrator. The default."""

    def compose(self, ctx: NarrativeContext) -> Narrative:
        s, cap, risk, dec = ctx.scenario, ctx.capacity, ctx.risk, ctx.decision
        weather = s.context.weather_condition.replace("_", " ")
        zone = s.context.primary_affected_zone
        n = cap.demand
        express = len(s.express_orders)

        risk_summary = (
            f"{risk.level} risk: {weather} (severity {int(risk.weather_sub_score)}/100) plus a "
            f"{s.context.traffic_severity} event congesting the {zone} zone "
            f"({int(risk.traffic_sub_score)}/100). {n} orders against "
            f"~{cap.effective_capacity:.0f} effective deliveries — "
            f"load pressure {int(risk.load_sub_score)}/100."
        )

        impact_tail = (
            ", all standard — every express order stays protected."
            if dec.express_protected and dec.unserved > 0
            else ("." if dec.unserved else " — capacity covers all orders.")
        )
        estimated_impact = (
            f"Snow cuts fleet capacity ~{cap.weather_reduction_pct}% "
            f"({cap.nominal_capacity:.0f}→{cap.weather_capacity:.0f} deliveries); with "
            f"{zone}-zone congestion, effective capacity ~{cap.effective_capacity:.0f}. "
            f"~{dec.unserved} of {n} orders at SLA risk{impact_tail}"
        )

        prescription = self._prescription(s, cap, dec, zone, express)
        return Narrative(risk_summary, estimated_impact, prescription)

    def _prescription(
        self,
        scenario: Scenario,
        cap: CapacityResult,
        dec: DecisionResult,
        zone: str,
        express: int,
    ) -> str:
        if dec.recommended_extra_drivers > 0:
            return (
                f"Deploy {dec.recommended_extra_drivers} extra "
                f"{'driver' if dec.recommended_extra_drivers == 1 else 'drivers'} "
                f"({_money(dec.deployment_cost)}) and prioritise express + {zone}-zone orders — "
                f"this clears the shortfall and beats {_money(dec.weighted_breach_cost)} in "
                f"projected SLA penalties."
            )

        # Hold-and-prioritise: lead with the free, certain win.
        full = dec.cost_curve[-1]
        be = dec.break_even_to_deploy
        be_txt = f"{be:g}× its penalty" if be is not None else "much higher"
        return (
            f"Prioritise all {express} express + {zone}-zone orders now — current "
            f"capacity covers them. Hold extra drivers: covering the {dec.unserved} "
            f"at-risk standard orders ({_money(dec.raw_penalty_exposure)} exposure) "
            f"would cost {_money(full.deployment_cost)} ({full.extra_drivers} drivers). "
            f"Deploy only if a breach is worth >{be_txt}, or congestion worsens."
        )


class LLMNarrator:
    """Optional Anthropic-backed narrator. Falls back to the template on any error.

    Off by default and never used by the tests or the standard CLI path. It only
    rephrases prose from facts the deterministic engine already decided — it is
    not allowed to change the decision.
    """

    def __init__(self, model: str = "claude-haiku-4-5", fallback: NarrativeGenerator | None = None):
        self._model = model
        self._fallback = fallback or TemplateNarrator()

    def compose(self, ctx: NarrativeContext) -> Narrative:
        base = self._fallback.compose(ctx)
        try:
            import os

            from anthropic import Anthropic  # type: ignore

            if not os.environ.get("ANTHROPIC_API_KEY"):
                log.info("LLMNarrator: no ANTHROPIC_API_KEY; using template narrative.")
                return base

            client = Anthropic()
            prompt = self._build_prompt(ctx, base)
            msg = client.messages.create(
                model=self._model,
                max_tokens=400,
                messages=[{"role": "user", "content": prompt}],
            )
            text = msg.content[0].text.strip()  # type: ignore[attr-defined]
            # Expect three lines; if the shape is off, keep the template.
            lines = [ln for ln in text.splitlines() if ln.strip()]
            if len(lines) >= 3:
                return Narrative(lines[0].strip(), lines[1].strip(), lines[2].strip())
            return base
        except Exception as exc:  # noqa: BLE001 — narrator must never break the engine
            log.warning("LLMNarrator failed (%s); using template narrative.", exc)
            return base

    def _build_prompt(self, ctx: NarrativeContext, base: Narrative) -> str:
        d = ctx.decision
        return (
            "You write terse WhatsApp ops alerts for a delivery hub manager. "
            "Rephrase the three lines below to be punchy and clear. Keep every number "
            "exactly. Do NOT change the recommendation. Return exactly three lines: "
            "risk summary, estimated impact, prescription.\n\n"
            f"1) {base.risk_summary}\n2) {base.estimated_impact}\n3) {base.prescription}\n\n"
            f"(For grounding: recommended extra drivers={d.recommended_extra_drivers}, "
            f"confidence={d.confidence}%.)"
        )


def get_narrator(kind: str = "template") -> NarrativeGenerator:
    """Factory: ``'template'`` (default, deterministic) or ``'llm'`` (optional)."""
    if kind == "llm":
        return LLMNarrator()
    return TemplateNarrator()
