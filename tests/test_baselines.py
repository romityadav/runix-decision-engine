"""Baselines: the engine must never lose to a naive strategy (it's their envelope)."""

from __future__ import annotations

import pytest

from runix.baselines import compare_baselines
from runix.capacity import CapacityModel
from runix.config import EngineConfig
from runix.decision import DecisionEngine


def _baselines(scenario, **overrides):
    cfg = EngineConfig(**overrides)
    cap = CapacityModel(cfg).compute(scenario)
    return {b.name: b for b in compare_baselines(scenario, cap, cfg)}


def test_baseline_costs_at_M1(scenario):
    b = _baselines(scenario)
    assert b["do_nothing"].total_cost == pytest.approx(148.0)       # 10 * mean penalty 14.8
    assert b["prioritise_only"].total_cost == 80                    # 10 standard breaches
    assert b["always_cover"].total_cost == 360                      # 3 drivers
    assert b["always_cover"].extra_drivers == 3


def test_prioritisation_value_is_quantified(scenario):
    # Re-sequencing the route sheet (free) saves $68 vs doing nothing.
    b = _baselines(scenario)
    assert b["do_nothing"].total_cost - b["prioritise_only"].total_cost == pytest.approx(68.0)


@pytest.mark.parametrize("m", [0.5, 1.0, 2.0, 3.75, 5.0, 7.5, 10.0])
def test_engine_never_worse_than_any_baseline(scenario, m):
    cfg = EngineConfig(breach_aversion=m)
    cap = CapacityModel(cfg).compute(scenario)
    engine_cost = DecisionEngine(cfg).decide(scenario, cap).total_cost
    for b in compare_baselines(scenario, cap, cfg):
        assert engine_cost <= b.total_cost + 1e-9, f"engine lost to {b.name} at M={m}"
