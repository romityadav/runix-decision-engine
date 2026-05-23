"""RiskModel: sub-scores, the weighted composite, and classification boundaries."""

from __future__ import annotations

import pytest

from runix.capacity import CapacityModel
from runix.config import EngineConfig
from runix.risk import RiskModel


def test_real_scenario_composite_and_level(scenario):
    cfg = EngineConfig()
    cap = CapacityModel(cfg).compute(scenario)
    risk = RiskModel(cfg).compute(scenario, cap)
    assert risk.weather_sub_score == 90
    assert risk.traffic_sub_score == 75
    assert risk.load_sub_score == 100  # 50 orders vs 48 realistic deliveries -> saturated
    assert risk.composite_score == 88.5  # 0.4*90 + 0.3*75 + 0.3*100
    assert risk.level == "High"
    assert risk.primary_factor == "weather"


@pytest.mark.parametrize(
    "score,expected",
    [(0, "Low"), (39.99, "Low"), (40, "Medium"), (69.99, "Medium"), (70, "High"), (100, "High")],
)
def test_classification_boundaries(score, expected):
    assert RiskModel(EngineConfig()).classify(score) == expected


def test_load_sub_score_uses_weather_capacity_not_nominal(scenario):
    # Honesty check: load pressure is measured against realistic (snow) capacity,
    # so 50 vs 48 saturates to 100 rather than 50/80 = 62.5.
    cfg = EngineConfig()
    cap = CapacityModel(cfg).compute(scenario)
    risk = RiskModel(cfg).compute(scenario, cap)
    assert risk.load_sub_score == 100
    assert risk.load_sub_score != 62.5
