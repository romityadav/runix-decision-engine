"""Sensitivity sweep: shape, monotonicity, and a couple of known cells."""

from __future__ import annotations

from runix.config import EngineConfig
from runix.sensitivity import sweep


def test_grid_shape(scenario):
    grid = sweep(scenario, EngineConfig(), betas=[0.0, 0.5, 1.0], multipliers=[1.0, 5.0, 10.0])
    assert len(grid.recommended_drivers) == 3
    assert all(len(row) == 3 for row in grid.recommended_drivers)


def test_monotonic_in_breach_aversion(scenario):
    # Along any beta row, recommended drivers must be non-decreasing in M.
    grid = sweep(scenario, EngineConfig(), betas=[0.0, 0.5, 1.0])
    for row in grid.recommended_drivers:
        assert row == sorted(row), f"not monotonic in M: {row}"


def test_monotonic_in_congestion(scenario):
    # Down any M column, recommended drivers must be non-decreasing in beta.
    grid = sweep(scenario, EngineConfig(), multipliers=[1.0, 5.0, 10.0])
    cols = list(zip(*grid.recommended_drivers, strict=True))
    for col in cols:
        assert list(col) == sorted(col), f"not monotonic in beta: {col}"


def test_low_M_low_beta_holds(scenario):
    grid = sweep(scenario, EngineConfig(), betas=[0.0], multipliers=[1.0])
    assert grid.recommended_drivers[0][0] == 0
