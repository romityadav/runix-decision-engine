"""Assemble the final WhatsApp alert and the full machine-readable report.

The alert is exactly the five fields the brief specifies. The report is a
superset for dashboards / audits / debugging: it carries every intermediate
number so a reviewer can trace the recommendation end to end.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from .baselines import BaselineResult
from .capacity import CapacityResult
from .decision import DecisionResult
from .models import Scenario
from .narrative import Narrative
from .risk import RiskResult

_ALERT_FIELDS = (
    "risk_level",
    "risk_summary",
    "estimated_impact",
    "prescription",
    "confidence_score",
)


@dataclass(frozen=True, slots=True)
class WhatsAppAlert:
    """The five-field alert payload from the brief."""

    risk_level: str
    risk_summary: str
    estimated_impact: str
    prescription: str
    confidence_score: str  # e.g. "79%"

    def to_dict(self) -> dict[str, str]:
        d = {
            "risk_level": self.risk_level,
            "risk_summary": self.risk_summary,
            "estimated_impact": self.estimated_impact,
            "prescription": self.prescription,
            "confidence_score": self.confidence_score,
        }
        missing = [f for f in _ALERT_FIELDS if not d.get(f)]
        if missing:
            raise ValueError(f"Alert is missing required field(s): {missing}")
        return d

    def to_json(self, pretty: bool = False) -> str:
        return json.dumps(self.to_dict(), indent=2 if pretty else None, ensure_ascii=False)


def build_alert(risk: RiskResult, narrative: Narrative, decision: DecisionResult) -> WhatsAppAlert:
    return WhatsAppAlert(
        risk_level=risk.level,
        risk_summary=narrative.risk_summary,
        estimated_impact=narrative.estimated_impact,
        prescription=narrative.prescription,
        confidence_score=f"{decision.confidence}%",
    )


def build_report(
    scenario: Scenario,
    capacity: CapacityResult,
    risk: RiskResult,
    decision: DecisionResult,
    baselines: list[BaselineResult],
    alert: WhatsAppAlert,
) -> dict:
    """A fully JSON-serialisable view of the entire decision."""
    return {
        "alert": alert.to_dict(),
        "scenario": {
            "weather_condition": scenario.context.weather_condition,
            "traffic_severity": scenario.context.traffic_severity,
            "primary_affected_zone": scenario.context.primary_affected_zone,
            "orders": scenario.order_count,
            "express_orders": len(scenario.express_orders),
            "standard_orders": len(scenario.standard_orders),
            "active_drivers": scenario.active_driver_count,
        },
        "capacity": {
            "nominal": capacity.nominal_capacity,
            "weather_degraded": capacity.weather_capacity,
            "congestion_factor": round(capacity.congestion_factor, 4),
            "effective": round(capacity.effective_capacity, 2),
            "per_driver_effective": round(capacity.per_driver_effective, 2),
            "demand": capacity.demand,
            "servable": capacity.servable,
            "shortfall": capacity.shortfall,
            "weather_reduction_pct": capacity.weather_reduction_pct,
            "effective_reduction_pct": capacity.effective_reduction_pct,
        },
        "risk": {
            "weather_sub_score": risk.weather_sub_score,
            "traffic_sub_score": risk.traffic_sub_score,
            "load_sub_score": risk.load_sub_score,
            "composite_score": risk.composite_score,
            "level": risk.level,
            "primary_factor": risk.primary_factor,
        },
        "decision": {
            "breach_aversion_M": decision.breach_aversion,
            "recommended_extra_drivers": decision.recommended_extra_drivers,
            "action": decision.action,
            "deployment_cost": decision.deployment_cost,
            "raw_penalty_exposure": decision.raw_penalty_exposure,
            "weighted_breach_cost": decision.weighted_breach_cost,
            "total_cost": decision.total_cost,
            "express_protected": decision.express_protected,
            "served": decision.served,
            "unserved": decision.unserved,
            "unserved_express": decision.unserved_express,
            "unserved_standard": decision.unserved_standard,
            "break_even_to_deploy_M": decision.break_even_to_deploy,
            "break_even_full_cover_M": decision.break_even_full_cover,
            "confidence": decision.confidence,
            "cost_curve": [
                {
                    "extra_drivers": p.extra_drivers,
                    "deployment_cost": p.deployment_cost,
                    "unserved": p.unserved,
                    "raw_penalty": p.raw_penalty,
                    "total_cost": p.total_cost,
                }
                for p in decision.cost_curve
            ],
            "decision_regions_by_M": [
                {"m_low": round(lo, 3), "m_high": round(hi, 3), "drivers": d}
                for (lo, hi, d) in decision.decision_regions
            ],
        },
        "baselines": [
            {
                "name": b.name,
                "label": b.label,
                "extra_drivers": b.extra_drivers,
                "raw_penalty": b.raw_penalty,
                "total_cost": b.total_cost,
            }
            for b in baselines
        ],
        "data_quality_notes": scenario.data_quality_notes,
    }
