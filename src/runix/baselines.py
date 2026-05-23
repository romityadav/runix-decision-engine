"""Naive baselines, so the engine has to *earn* its complexity.

Before trusting a marginal cost optimiser, we check it against the dumbest
strategies a manager might use:

* ``do_nothing`` — serve in arbitrary order, deploy nobody. Breaches fall across
  tiers in proportion to the order mix (so some express orders fail).
* ``always_cover`` — panic-hire enough drivers to leave zero breaches, whatever
  it costs. (This is essentially what one of the earlier prototypes always did.)
* ``prioritise_only`` — protect express/affected-zone first, but never deploy.

The engine's decision is the lower envelope of every driver count at every M, so
it can never do worse than any of these — and the gap is the value it adds. The
do-nothing-vs-prioritise gap in particular quantifies the ROI of the single
free decision: re-sequencing the route sheet.
"""

from __future__ import annotations

from dataclasses import dataclass

from .capacity import CapacityResult
from .config import EngineConfig
from .decision import _priority_sorted
from .models import Scenario


@dataclass(frozen=True, slots=True)
class BaselineResult:
    name: str
    label: str
    description: str
    extra_drivers: int
    raw_penalty: float
    total_cost: float  # at the active breach-aversion M


def compare_baselines(
    scenario: Scenario, capacity: CapacityResult, config: EngineConfig
) -> list[BaselineResult]:
    """Return the cost of each naive strategy at the active M, for comparison."""
    m = config.breach_aversion
    driver_cost = scenario.constants.driver_shift_cost
    orders = scenario.orders
    demand = capacity.demand

    # --- do_nothing: no drivers, no prioritisation ---
    unserved = capacity.unserved_with(0)
    avg_penalty = (sum(o.breach_penalty for o in orders) / demand) if demand else 0.0
    do_nothing_penalty = unserved * avg_penalty

    # --- always_cover: deploy until zero breaches ---
    d_full = next(
        (d for d in range(config.max_additional_drivers + 1) if capacity.unserved_with(d) == 0),
        config.max_additional_drivers,
    )

    # --- prioritise_only: protect high-value orders, no drivers ---
    priority = _priority_sorted(orders, scenario.context.primary_affected_zone)
    servable0 = capacity.servable_with(0)
    prioritise_penalty = sum(o.breach_penalty for o in priority[servable0:])

    return [
        BaselineResult(
            name="do_nothing",
            label="Do nothing (no prioritisation)",
            description="Serve in arbitrary order, deploy nobody. Breaches hit tiers by mix.",
            extra_drivers=0,
            raw_penalty=do_nothing_penalty,
            total_cost=do_nothing_penalty * m,
        ),
        BaselineResult(
            name="always_cover",
            label="Panic-hire to zero breaches",
            description="Deploy enough drivers to leave no order unserved, whatever the cost.",
            extra_drivers=d_full,
            raw_penalty=0.0,
            total_cost=d_full * driver_cost,
        ),
        BaselineResult(
            name="prioritise_only",
            label="Prioritise only (no drivers)",
            description="Protect express + affected-zone first, deploy nobody.",
            extra_drivers=0,
            raw_penalty=prioritise_penalty,
            total_cost=prioritise_penalty * m,
        ),
    ]
