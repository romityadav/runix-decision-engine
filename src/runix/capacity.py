"""Capacity model: how many deliveries the fleet can actually complete tonight.

The chain is deliberately a transparent product of named factors, each with a
source, so a manager can read it like a sentence:

    nominal     = drivers x deliveries/driver                 (from the data)
    weather     = nominal x weather_multiplier                (from the data: 0.6)
    effective   = weather x congestion_factor                 (one stated assumption)

``congestion_factor`` is the only modelled term. The workbook gives the road
event as a 0-100 *risk index*, not a capacity multiplier, so we translate it
transparently:

    congestion_factor = 1 - (traffic_risk/100) * affected_zone_share * beta

where ``beta`` (config) is how sharply congestion erodes throughput. We do NOT
floor capacity per-driver: the workbook's own fleet total (``H16``) is
10 * (8 * 0.6) = 48, i.e. it keeps the fractional 4.8/driver. We match that and
floor only once, at the fleet level, when converting a delivery *rate* into a
whole number of *orders we can serve*.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from .config import EngineConfig
from .models import Scenario


@dataclass(frozen=True, slots=True)
class CapacityResult:
    """The capacity picture for the active scenario."""

    active_drivers: int
    deliveries_per_driver: float
    nominal_capacity: float          # before any degradation
    weather_capacity: float          # after weather only (data-grounded)
    congestion_factor: float         # in (0, 1]; 1.0 = no event impact
    effective_capacity: float        # after weather AND congestion
    per_driver_effective: float      # marginal capacity an extra driver adds
    demand: int                      # number of orders
    servable: int                    # whole orders the base fleet can serve
    shortfall: int                   # orders beyond base-fleet capacity (>= 0)

    @property
    def weather_reduction_pct(self) -> int:
        """Headline 'snow cuts capacity by ~X%' figure (weather only)."""
        if self.nominal_capacity == 0:
            return 0
        return round((1 - self.weather_capacity / self.nominal_capacity) * 100)

    @property
    def effective_reduction_pct(self) -> int:
        """Capacity reduction from weather AND congestion combined."""
        if self.nominal_capacity == 0:
            return 0
        return round((1 - self.effective_capacity / self.nominal_capacity) * 100)

    def servable_with(self, extra_drivers: int) -> int:
        """Whole orders servable if ``extra_drivers`` are added to the base fleet."""
        capacity = self.effective_capacity + extra_drivers * self.per_driver_effective
        return min(self.demand, math.floor(capacity))

    def unserved_with(self, extra_drivers: int) -> int:
        """Orders left unserved (at SLA risk) with ``extra_drivers`` added."""
        return max(0, self.demand - self.servable_with(extra_drivers))


class CapacityModel:
    """Computes effective fleet capacity from a scenario + config."""

    def __init__(self, config: EngineConfig) -> None:
        self._config = config

    def compute(self, scenario: Scenario) -> CapacityResult:
        const = scenario.constants
        drivers = scenario.active_driver_count
        per_driver = const.deliveries_per_driver_per_shift

        nominal = drivers * per_driver
        weather = nominal * const.weather_multiplier

        congestion_factor = self._congestion_factor(scenario)
        effective = weather * congestion_factor
        per_driver_effective = per_driver * const.weather_multiplier * congestion_factor

        demand = scenario.order_count
        servable = min(demand, math.floor(effective))
        shortfall = max(0, demand - servable)

        return CapacityResult(
            active_drivers=drivers,
            deliveries_per_driver=per_driver,
            nominal_capacity=nominal,
            weather_capacity=weather,
            congestion_factor=congestion_factor,
            effective_capacity=effective,
            per_driver_effective=per_driver_effective,
            demand=demand,
            servable=servable,
            shortfall=shortfall,
        )

    def _congestion_factor(self, scenario: Scenario) -> float:
        """Translate the event's risk index into a throughput multiplier in (0, 1]."""
        traffic_frac = scenario.constants.traffic_risk_score / 100.0
        zone_share = scenario.context.affected_zone_share
        drag = traffic_frac * zone_share * self._config.congestion_sensitivity
        return max(0.0, 1.0 - drag)
