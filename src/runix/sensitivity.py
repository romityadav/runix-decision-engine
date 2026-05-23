"""Sensitivity analysis over the two assumptions the data cannot pin down.

A point recommendation is only as trustworthy as its robustness to the things we
guessed. We sweep the two free knobs —

* congestion sensitivity ``beta`` (how badly the event erodes throughput), and
* breach aversion ``M`` (how much a missed SLA really costs) —

and report the recommended number of extra drivers across the grid. The result
is the honest headline: "the recommendation is stable across most of the
plausible region, and only flips to deploying drivers when you believe BOTH the
congestion is severe AND a breach costs several times its contractual penalty."
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from .capacity import CapacityModel
from .config import EngineConfig
from .decision import DecisionEngine
from .models import Scenario


@dataclass(frozen=True, slots=True)
class SensitivityGrid:
    betas: list[float]               # rows (congestion sensitivity)
    multipliers: list[float]         # columns (breach aversion M)
    recommended_drivers: list[list[int]]  # grid[i][j] for betas[i], multipliers[j]


def sweep(
    scenario: Scenario,
    base_config: EngineConfig,
    betas: list[float] | None = None,
    multipliers: list[float] | None = None,
) -> SensitivityGrid:
    """Recommend extra drivers across a ``beta`` x ``M`` grid."""
    betas = betas if betas is not None else [round(0.1 * i, 2) for i in range(0, 11)]  # 0.0..1.0
    multipliers = (
        multipliers if multipliers is not None else [round(0.5 * i, 2) for i in range(1, 21)]
    )  # 0.5..10.0

    grid: list[list[int]] = []
    for beta in betas:
        row: list[int] = []
        for m in multipliers:
            cfg = replace(base_config, congestion_sensitivity=beta, breach_aversion=m)
            capacity = CapacityModel(cfg).compute(scenario)
            decision = DecisionEngine(cfg).decide(scenario, capacity)
            row.append(decision.recommended_extra_drivers)
        grid.append(row)

    return SensitivityGrid(betas=betas, multipliers=multipliers, recommended_drivers=grid)
