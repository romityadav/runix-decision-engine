"""Typed domain model for the Runix logistics scenario.

These dataclasses are the lingua franca between pipeline stages. They are
``frozen`` because a scenario, once loaded, is an immutable description of the
world — every downstream number is *derived*, never mutated in place. Using real
types here (rather than passing bare dicts around) is what lets the type checker
and the reader follow the data from the workbook all the way to the alert.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class ServiceTier(str, Enum):
    """Order service tier. Express has a tighter SLA and a higher breach penalty."""

    EXPRESS = "express"
    STANDARD = "standard"


@dataclass(frozen=True, slots=True)
class Order:
    """A single pending delivery.

    ``sla_hours`` and ``breach_penalty`` are derived from the named scenario
    constants by tier — deliberately NOT read from the workbook's per-row
    formula columns, which contain a cell-reference bug (see ``data_loader``).
    """

    order_id: str
    tier: ServiceTier
    zone: str
    sla_hours: float
    breach_penalty: float

    @property
    def is_express(self) -> bool:
        return self.tier is ServiceTier.EXPRESS


@dataclass(frozen=True, slots=True)
class Driver:
    """A fleet driver. The workbook only carries id + status reliably; all driver
    economics (shift cost, capacity) come from the scenario constants."""

    driver_id: str
    status: str

    @property
    def is_active(self) -> bool:
        return self.status.strip().upper() == "ACTIVE"


@dataclass(frozen=True, slots=True)
class ScenarioConstants:
    """The engine constants block from the workbook's ``Scenario Summary`` sheet.

    Every field maps to exactly one named cell, so each number is traceable to
    the source of truth (see ``docs/DATA_NOTES.md``).
    """

    shift_hours: int
    deliveries_per_driver_per_shift: float
    express_sla_hours: float
    standard_sla_hours: float
    driver_shift_cost: float
    express_penalty: float
    standard_penalty: float
    weather_multiplier: float  # capacity multiplier for the active weather, e.g. 0.6
    traffic_risk_score: float  # 0-100 risk index for the active event severity
    weather_risk_score: float  # 0-100 risk index for the active weather
    risk_weights: dict[str, float]  # {"weather":0.4,"traffic":0.3,"load":0.3}


@dataclass(frozen=True, slots=True)
class ScenarioContext:
    """The 'Active Scenario Context' block — what is actually happening this shift."""

    weather_condition: str
    traffic_severity: str
    target_order_volume: int
    base_shift_drivers_available: int
    express_tier_share: float
    primary_affected_zone: str
    affected_zone_share: float


@dataclass(frozen=True, slots=True)
class Scenario:
    """Everything the engine needs to make a decision, fully typed."""

    constants: ScenarioConstants
    context: ScenarioContext
    orders: list[Order]
    drivers: list[Driver]
    data_quality_notes: list[str] = field(default_factory=list)

    @property
    def active_drivers(self) -> list[Driver]:
        return [d for d in self.drivers if d.is_active]

    @property
    def active_driver_count(self) -> int:
        return len(self.active_drivers)

    @property
    def order_count(self) -> int:
        return len(self.orders)

    @property
    def express_orders(self) -> list[Order]:
        return [o for o in self.orders if o.is_express]

    @property
    def standard_orders(self) -> list[Order]:
        return [o for o in self.orders if not o.is_express]
