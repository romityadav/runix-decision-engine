"""DecisionEngine: the cost curve, the argmin, break-evens, and confidence.

This is the module that actually *uses* the financial trade-off, so it gets the
most scrutiny.
"""

from __future__ import annotations

import pytest

from runix.capacity import CapacityModel
from runix.config import EngineConfig
from runix.decision import DecisionEngine


def _decide(scenario, **overrides):
    cfg = EngineConfig(**overrides)
    cap = CapacityModel(cfg).compute(scenario)
    return DecisionEngine(cfg).decide(scenario, cap)


def test_default_recommendation_is_hold(scenario):
    # At contractual economics (M=1), $360 of drivers to avoid $80 of standard
    # breaches is wrong: the optimum is to hold and prioritise.
    d = _decide(scenario)
    assert d.recommended_extra_drivers == 0
    assert d.action == "hold_and_prioritise"
    assert d.total_cost == 80
    assert d.raw_penalty_exposure == 80


def test_cost_curve_values(scenario):
    d = _decide(scenario)
    curve = {p.extra_drivers: p for p in d.cost_curve}
    assert curve[0].total_cost == 80
    assert curve[1].total_cost == 168
    assert curve[2].total_cost == 256
    assert curve[3].total_cost == 360
    assert curve[3].unserved == 0  # curve stops at full coverage


def test_prioritisation_protects_all_express(scenario):
    d = _decide(scenario)
    assert d.express_protected is True
    assert d.unserved_express == 0
    assert d.unserved_standard == d.unserved == 10


def test_break_even_values(scenario):
    d = _decide(scenario)
    assert d.break_even_to_deploy == 3.75
    assert d.break_even_full_cover == 7.5


@pytest.mark.parametrize(
    "m,expected_drivers",
    [(1.0, 0), (3.0, 0), (3.75, 0), (4.0, 2), (5.0, 2), (7.5, 2), (8.0, 3), (10.0, 3)],
)
def test_recommendation_tracks_breach_aversion(scenario, m, expected_drivers):
    d = _decide(scenario, breach_aversion=m)
    assert d.recommended_extra_drivers == expected_drivers


def test_decision_regions_partition_M(scenario):
    d = _decide(scenario)
    # Regions must be contiguous and cover [0, 20].
    regions = d.decision_regions
    assert regions[0][0] == 0.0
    assert regions[-1][1] == 20.0
    for (_lo1, hi1, _), (lo2, _hi2, _) in zip(regions, regions[1:], strict=False):
        assert hi1 == lo2  # contiguous
    # And they encode the same break-evens.
    drivers_by_region = [d for _, _, d in regions]
    assert drivers_by_region == [0, 2, 3]


def test_more_congestion_raises_recommendation(scenario):
    # Higher beta -> less capacity -> at a fixed high M, more drivers warranted.
    low = _decide(scenario, congestion_sensitivity=0.0, breach_aversion=6.0)
    high = _decide(scenario, congestion_sensitivity=1.0, breach_aversion=6.0)
    assert high.recommended_extra_drivers >= low.recommended_extra_drivers


def test_confidence_in_range_and_lower_near_boundary(scenario):
    decisive = _decide(scenario, breach_aversion=1.0)   # far from break-even
    borderline = _decide(scenario, breach_aversion=5.0)  # near a flip
    assert 50 <= borderline.confidence <= 99
    assert 50 <= decisive.confidence <= 99
    assert decisive.confidence > borderline.confidence


def test_total_cost_matches_components(scenario):
    d = _decide(scenario, breach_aversion=5.0)
    assert d.total_cost == pytest.approx(d.deployment_cost + d.weighted_breach_cost)
