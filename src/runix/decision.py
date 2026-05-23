"""Decision layer: turn the capacity/risk estimate into a costed staffing action.

This is where the brief's "financial trade-off" actually *decides* something —
unlike a model that computes two costs and then ignores them. The job is a
threshold decision under asymmetric costs, so we treat it as one:

    For each possible number of extra drivers d, total cost is
        cost(d) = d * driver_shift_cost  +  M * penalty(orders left unserved | d)
    and we pick the d that minimises it.

Two things make this honest rather than reflexive:

* **Prioritisation comes first, and it's free.** We always serve express and
  affected-zone orders first, so a driver is only ever "worth it" for the
  low-value tail. On this scenario prioritisation alone protects all 20 express
  orders, which is why throwing drivers at the problem is usually wrong.

* **The breach-aversion multiplier M is explicit.** The contractual penalties
  make breaches look cheap; whether they really are is a business call. So we
  don't bury M — we report the *break-even* M at which the recommendation flips,
  and expose the whole decision curve. The manager owns that one judgement.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .capacity import CapacityResult
from .config import EngineConfig
from .models import Order, Scenario


@dataclass(frozen=True, slots=True)
class CostPoint:
    """One point on the cost-vs-drivers curve, at the active M."""

    extra_drivers: int
    deployment_cost: float
    unserved: int
    unserved_express: int
    unserved_standard: int
    raw_penalty: float       # contractual penalty of the unserved tail (M = 1)
    weighted_penalty: float  # raw_penalty * M
    total_cost: float        # deployment_cost + weighted_penalty


@dataclass(frozen=True, slots=True)
class DecisionResult:
    recommended_extra_drivers: int
    action: str  # "hold_and_prioritise" | "deploy_and_prioritise"
    breach_aversion: float

    deployment_cost: float
    raw_penalty_exposure: float   # contractual $ of breaches we accept (at recommendation)
    weighted_breach_cost: float
    total_cost: float

    express_protected: bool
    served: int
    unserved: int
    unserved_express: int
    unserved_standard: int

    break_even_to_deploy: float | None   # M at which adding drivers first beats holding
    break_even_full_cover: float | None  # M at which covering everyone becomes optimal
    confidence: int                      # 0-100, how decisively the choice beats the runner-up

    cost_curve: list[CostPoint] = field(default_factory=list)
    decision_regions: list[tuple[float, float, int]] = field(default_factory=list)


class DecisionEngine:
    """Marginal, asymmetric-cost optimiser over the number of extra drivers."""

    def __init__(self, config: EngineConfig) -> None:
        self._config = config

    def decide(self, scenario: Scenario, capacity: CapacityResult) -> DecisionResult:
        const = scenario.constants
        m = self._config.breach_aversion
        driver_cost = const.driver_shift_cost

        # Orders in the order we would protect them: express first, then the
        # congested affected-zone, then by id for determinism.
        priority = _priority_sorted(scenario.orders, scenario.context.primary_affected_zone)

        # Build the cost curve from 0 extra drivers up to the point where the
        # whole demand is covered (more drivers past that only add cost).
        curve = self._cost_curve(priority, capacity, driver_cost, m)

        # Choose the cheapest option at the active M.
        best = min(curve, key=lambda p: (p.total_cost, p.extra_drivers))

        regions = self._decision_regions(priority, capacity, driver_cost)
        be_deploy = self._break_even_to_deploy(regions)
        be_full = self._break_even_full_cover(priority, capacity, driver_cost)

        served = capacity.demand - best.unserved
        confidence = self._confidence(curve, best, scenario)

        return DecisionResult(
            recommended_extra_drivers=best.extra_drivers,
            action="deploy_and_prioritise" if best.extra_drivers > 0 else "hold_and_prioritise",
            breach_aversion=m,
            deployment_cost=best.deployment_cost,
            raw_penalty_exposure=best.raw_penalty,
            weighted_breach_cost=best.weighted_penalty,
            total_cost=best.total_cost,
            express_protected=best.unserved_express == 0,
            served=served,
            unserved=best.unserved,
            unserved_express=best.unserved_express,
            unserved_standard=best.unserved_standard,
            break_even_to_deploy=be_deploy,
            break_even_full_cover=be_full,
            confidence=confidence,
            cost_curve=curve,
            decision_regions=regions,
        )

    # -- curve construction --------------------------------------------------

    def _cost_curve(
        self,
        priority: list[Order],
        capacity: CapacityResult,
        driver_cost: float,
        m: float,
    ) -> list[CostPoint]:
        points: list[CostPoint] = []
        for d in range(self._config.max_additional_drivers + 1):
            point = self._cost_point(priority, capacity, driver_cost, m, d)
            points.append(point)
            if point.unserved == 0:
                break  # full coverage reached; further drivers are strictly worse
        return points

    def _cost_point(
        self,
        priority: list[Order],
        capacity: CapacityResult,
        driver_cost: float,
        m: float,
        d: int,
    ) -> CostPoint:
        servable = capacity.servable_with(d)
        unserved_orders = priority[servable:]
        raw_penalty = sum(o.breach_penalty for o in unserved_orders)
        unserved_express = sum(1 for o in unserved_orders if o.is_express)
        deployment = d * driver_cost
        weighted = raw_penalty * m
        return CostPoint(
            extra_drivers=d,
            deployment_cost=deployment,
            unserved=len(unserved_orders),
            unserved_express=unserved_express,
            unserved_standard=len(unserved_orders) - unserved_express,
            raw_penalty=raw_penalty,
            weighted_penalty=weighted,
            total_cost=deployment + weighted,
        )

    # -- break-even / decision-region analysis -------------------------------

    def _raw_penalty_for_drivers(
        self, priority: list[Order], capacity: CapacityResult, d: int
    ) -> float:
        servable = capacity.servable_with(d)
        return sum(o.breach_penalty for o in priority[servable:])

    def _decision_regions(
        self, priority: list[Order], capacity: CapacityResult, driver_cost: float
    ) -> list[tuple[float, float, int]]:
        """Optimal number of drivers as a function of M, as ``(M_lo, M_hi, d)`` bands.

        Each option d is a line in M: ``cost = d*driver_cost + raw(d)*M``. The
        optimum over d is the lower envelope of those lines. With only a handful
        of candidate d, we find it exactly by evaluating at the midpoints between
        all pairwise line intersections.
        """
        ds: list[int] = []
        intercept: dict[int, float] = {}
        slope: dict[int, float] = {}
        for d in range(self._config.max_additional_drivers + 1):
            raw = self._raw_penalty_for_drivers(priority, capacity, d)
            ds.append(d)
            intercept[d] = d * driver_cost
            slope[d] = raw
            if raw == 0:
                break

        m_max = 20.0
        breakpoints = {0.0, m_max}
        for i in ds:
            for j in ds:
                if i < j and slope[i] != slope[j]:
                    m = (intercept[j] - intercept[i]) / (slope[i] - slope[j])
                    if 0.0 < m < m_max:
                        breakpoints.add(m)
        ordered = sorted(breakpoints)

        regions: list[tuple[float, float, int]] = []
        for lo, hi in zip(ordered, ordered[1:], strict=False):
            mid = (lo + hi) / 2.0
            d_opt = min(ds, key=lambda d: intercept[d] + slope[d] * mid)
            if regions and regions[-1][2] == d_opt:
                regions[-1] = (regions[-1][0], hi, d_opt)
            else:
                regions.append((lo, hi, d_opt))
        return regions

    def _break_even_to_deploy(
        self, regions: list[tuple[float, float, int]]
    ) -> float | None:
        """The smallest M at which the optimal action stops being 'hold' (d=0)."""
        for lo, _hi, d in regions:
            if d > 0:
                return round(lo, 4)
        return None

    def _break_even_full_cover(
        self, priority: list[Order], capacity: CapacityResult, driver_cost: float
    ) -> float | None:
        """The M at which covering *everyone* becomes the optimal action."""
        # full-cover d = smallest d with zero unserved
        d_full = None
        for d in range(self._config.max_additional_drivers + 1):
            if capacity.unserved_with(d) == 0:
                d_full = d
                break
        if d_full is None or d_full == 0:
            return 0.0 if d_full == 0 else None
        # Find the region whose optimal d is d_full; its lower bound is the break-even.
        regions = self._decision_regions(priority, capacity, driver_cost)
        for lo, _hi, d in regions:
            if d == d_full:
                return round(lo, 4)
        return None

    # -- confidence ----------------------------------------------------------

    def _confidence(
        self, curve: list[CostPoint], best: CostPoint, scenario: Scenario
    ) -> int:
        """How decisively the recommended option beats its runner-up.

        High when the best option is much cheaper than the next-best (a clear
        call), lower when they are close (the decision is sensitive). Scaled by a
        data-completeness factor so missing inputs honestly lower confidence.
        """
        others = [p.total_cost for p in curve if p.extra_drivers != best.extra_drivers]
        runner_up = min(others) if others else best.total_cost
        rel_margin = (runner_up - best.total_cost) / runner_up if runner_up > 0 else 1.0
        rel_margin = max(0.0, min(1.0, rel_margin))

        completeness = _data_completeness(scenario)
        score = (0.55 + 0.45 * rel_margin) * 100.0 * completeness
        return int(max(50, min(99, round(score))))


def _priority_sorted(orders: list[Order], affected_zone: str) -> list[Order]:
    """Protect express first, then the congested affected zone, then by id."""
    return sorted(
        orders,
        key=lambda o: (
            0 if o.is_express else 1,
            0 if o.zone == affected_zone else 1,
            o.order_id,
        ),
    )


def _data_completeness(scenario: Scenario) -> float:
    const = scenario.constants
    signals = [
        bool(scenario.orders),
        bool(scenario.active_drivers),
        0.0 < const.weather_multiplier <= 1.0,
        const.traffic_risk_score > 0,
        const.express_penalty > 0 and const.standard_penalty > 0,
    ]
    return sum(signals) / len(signals)
