"""Engine configuration — the assumptions we *chose*, kept apart from the data.

A core principle of this project (see the README) is the separation of the
**model** (which estimates reality from data) from the **decision** (which trades
off business costs). The two judgement calls the data cannot make for us live
here, at the surface, tunable, each with a documented default and a "because":

* ``congestion_sensitivity`` (beta) — how much a road event actually erodes
  delivery throughput. The workbook gives a 0-100 *risk index* for the event but
  no capacity multiplier, so this is an explicit assumption, surfaced in the
  sensitivity analysis rather than buried as a magic number.

* ``breach_aversion`` (M) — how much a missed SLA truly costs relative to its
  contractual penalty. The $25/$8 penalties in the data are contractual; the real
  cost of failing a customer in a snowstorm (re-delivery, support, churn) is
  higher and is a business call. M=1 means "trust the contract literally".

Both are deliberately the *only* free knobs. Risk thresholds and weights come
from the data; nothing else is hand-tuned.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class EngineConfig:
    """Tunable assumptions for the capacity, risk, and decision layers."""

    # --- Capacity assumption ------------------------------------------------
    # Throughput lost in a *fully* affected network under a *maximal* severity
    # event = traffic_frac (1.0) * zone_share (1.0) * beta. Default 0.5 means a
    # worst-case event in a fully-congested network halves throughput; the
    # active scenario (0.75 severity, 0.40 of zones) loses 0.75*0.40*0.5 = 15%.
    congestion_sensitivity: float = 0.5

    # --- Decision assumption ------------------------------------------------
    # Multiplier on contractual SLA penalties to reflect their true business
    # cost. Default 1.0 = literal contract economics (the honest baseline).
    breach_aversion: float = 1.0

    # --- Risk classification (data framing: 0-100 index) --------------------
    # Conventional thirds on the 0-100 composite. Documented, not tuned to hit a
    # particular answer on this dataset.
    risk_medium_threshold: float = 40.0
    risk_high_threshold: float = 70.0

    # --- Decision search bound ----------------------------------------------
    # Upper bound on extra drivers the optimiser will consider (a hub manager is
    # not going to summon an unbounded fleet). Generous relative to a 10-driver
    # base; the optimum for this scenario is far below it.
    max_additional_drivers: int = 10

    def validate(self) -> None:
        """Fail fast on nonsensical configuration."""
        if not 0.0 <= self.congestion_sensitivity <= 2.0:
            raise ValueError(
                f"congestion_sensitivity must be in [0, 2], got {self.congestion_sensitivity}"
            )
        if self.breach_aversion < 0.0:
            raise ValueError(f"breach_aversion must be >= 0, got {self.breach_aversion}")
        if not 0 <= self.risk_medium_threshold <= self.risk_high_threshold <= 100:
            raise ValueError("risk thresholds must satisfy 0 <= medium <= high <= 100")
        if self.max_additional_drivers < 0:
            raise ValueError("max_additional_drivers must be >= 0")
