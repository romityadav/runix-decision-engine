"""CapacityModel: the degradation chain and the servable/shortfall helpers."""

from __future__ import annotations

import math

from runix.capacity import CapacityModel
from runix.config import EngineConfig


def test_real_scenario_capacity_chain(scenario):
    cap = CapacityModel(EngineConfig()).compute(scenario)
    assert cap.nominal_capacity == 80  # 10 drivers x 8
    assert cap.weather_capacity == 48  # x0.6 (matches the workbook's own H16)
    assert cap.congestion_factor == 0.85  # 1 - 0.75*0.40*0.5
    assert cap.effective_capacity == 40.8
    assert cap.servable == 40
    assert cap.shortfall == 10


def test_no_per_driver_flooring(scenario):
    # We must NOT floor per-driver (that would give 4*10=40, not 48).
    cap = CapacityModel(EngineConfig()).compute(scenario)
    assert cap.weather_capacity == 48
    assert cap.per_driver_effective == 8 * 0.6 * 0.85  # 4.08, fractional preserved


def test_reduction_percentages(scenario):
    cap = CapacityModel(EngineConfig()).compute(scenario)
    assert cap.weather_reduction_pct == 40       # snow alone
    assert cap.effective_reduction_pct == 49     # snow + congestion (1 - 40.8/80)


def test_beta_zero_means_weather_only(scenario):
    cap = CapacityModel(EngineConfig(congestion_sensitivity=0.0)).compute(scenario)
    assert cap.congestion_factor == 1.0
    assert cap.effective_capacity == cap.weather_capacity == 48


def test_servable_and_unserved_with_extra_drivers(scenario):
    cap = CapacityModel(EngineConfig()).compute(scenario)
    # per_driver_effective = 4.08
    assert cap.servable_with(0) == 40
    assert cap.servable_with(1) == math.floor(40.8 + 4.08)   # 44
    assert cap.servable_with(2) == math.floor(40.8 + 8.16)   # 48
    assert cap.servable_with(3) == 50                         # capped at demand
    assert cap.unserved_with(0) == 10
    assert cap.unserved_with(3) == 0


def test_servable_never_exceeds_demand(scenario):
    cap = CapacityModel(EngineConfig()).compute(scenario)
    assert cap.servable_with(99) == cap.demand
