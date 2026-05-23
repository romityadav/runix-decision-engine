"""Risk model: a 0-100 composite index describing how dangerous this shift is.

This layer's only job is to *estimate the state of the world* — it deliberately
knows nothing about driver costs or what to do. (Keeping the estimate separate
from the action is what lets the same risk read drive different decisions for
different cost appetites; see ``decision.py``.)

The composite is the workbook's own weighted blend of three 0-100 sub-scores:

    composite = 0.40*weather + 0.30*traffic + 0.30*load

* weather and traffic sub-scores are read straight from the data
  (heavy_snow -> 90, major -> 75).
* load is demand pressure against *realistic* (weather-degraded) capacity:
  100 * demand / weather_capacity, capped at 100. We use the weather-degraded
  capacity, not the sunny-day nominal, because pretending we have 80 deliveries
  of capacity in a snowstorm understates the pressure — at 50 orders vs 48
  realistic deliveries the load is genuinely maxed, and the score should say so.
"""

from __future__ import annotations

from dataclasses import dataclass

from .capacity import CapacityResult
from .config import EngineConfig
from .models import Scenario


@dataclass(frozen=True, slots=True)
class RiskResult:
    weather_sub_score: float
    traffic_sub_score: float
    load_sub_score: float
    composite_score: float
    level: str  # "Low" | "Medium" | "High"
    primary_factor: str  # largest *weighted* contributor to the composite


class RiskModel:
    """Computes the composite operational risk index."""

    def __init__(self, config: EngineConfig) -> None:
        self._config = config

    def compute(self, scenario: Scenario, capacity: CapacityResult) -> RiskResult:
        const = scenario.constants
        weights = const.risk_weights

        weather = const.weather_risk_score
        traffic = const.traffic_risk_score
        load = self._load_sub_score(capacity)

        composite = (
            weather * weights["weather"]
            + traffic * weights["traffic"]
            + load * weights["load"]
        )
        composite = round(composite, 2)
        # Primary factor = largest *weighted* contribution, not largest raw
        # sub-score: weather (0.4*90=36) drives this composite more than the
        # saturated load term (0.3*100=30) does.
        contributions = {
            "weather": weather * weights["weather"],
            "traffic": traffic * weights["traffic"],
            "load": load * weights["load"],
        }
        primary = max(contributions, key=contributions.__getitem__)
        return RiskResult(
            weather_sub_score=weather,
            traffic_sub_score=traffic,
            load_sub_score=round(load, 2),
            composite_score=composite,
            level=self.classify(composite),
            primary_factor=primary,
        )

    def _load_sub_score(self, capacity: CapacityResult) -> float:
        denom = capacity.weather_capacity or 1.0
        return min(100.0, 100.0 * capacity.demand / denom)

    def classify(self, composite_score: float) -> str:
        if composite_score >= self._config.risk_high_threshold:
            return "High"
        if composite_score >= self._config.risk_medium_threshold:
            return "Medium"
        return "Low"
