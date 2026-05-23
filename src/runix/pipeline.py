"""The orchestration layer: scenario in, decision out.

Wires the stages together in one place so the CLI, the dashboard, and the tests
all run the *exact same* computation:

    load → capacity → risk → decide → baselines → narrate → alert

Each stage is a small, separately testable object; this module just composes
them. ``run()`` returns a rich :class:`PipelineResult`; ``run_from_path()`` is
the one-call convenience for the CLI.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .alert import WhatsAppAlert, build_alert, build_report
from .baselines import BaselineResult, compare_baselines
from .capacity import CapacityModel, CapacityResult
from .config import EngineConfig
from .data_loader import load_scenario
from .decision import DecisionEngine, DecisionResult
from .logging_setup import get_logger
from .models import Scenario
from .narrative import NarrativeContext, NarrativeGenerator, TemplateNarrator
from .risk import RiskModel, RiskResult

log = get_logger("runix.pipeline")


@dataclass(frozen=True, slots=True)
class PipelineResult:
    scenario: Scenario
    capacity: CapacityResult
    risk: RiskResult
    decision: DecisionResult
    baselines: list[BaselineResult]
    alert: WhatsAppAlert

    def report(self) -> dict:
        """Full machine-readable report (alert + every intermediate)."""
        return build_report(
            self.scenario, self.capacity, self.risk, self.decision, self.baselines, self.alert
        )


def run(
    scenario: Scenario,
    config: EngineConfig | None = None,
    narrator: NarrativeGenerator | None = None,
) -> PipelineResult:
    """Run the full decision pipeline on an already-loaded scenario."""
    config = config or EngineConfig()
    config.validate()
    narrator = narrator or TemplateNarrator()

    capacity = CapacityModel(config).compute(scenario)
    log.debug(
        "capacity: effective=%.2f shortfall=%d", capacity.effective_capacity, capacity.shortfall
    )

    risk = RiskModel(config).compute(scenario, capacity)
    log.debug("risk: composite=%.2f level=%s", risk.composite_score, risk.level)

    decision = DecisionEngine(config).decide(scenario, capacity)
    log.debug(
        "decision: drivers=%d action=%s confidence=%d",
        decision.recommended_extra_drivers,
        decision.action,
        decision.confidence,
    )

    baselines = compare_baselines(scenario, capacity, config)

    narrative = narrator.compose(
        NarrativeContext(scenario=scenario, capacity=capacity, risk=risk, decision=decision)
    )
    alert = build_alert(risk, narrative, decision)

    return PipelineResult(
        scenario=scenario,
        capacity=capacity,
        risk=risk,
        decision=decision,
        baselines=baselines,
        alert=alert,
    )


def run_from_path(
    dataset: str | Path,
    config: EngineConfig | None = None,
    narrator: NarrativeGenerator | None = None,
) -> PipelineResult:
    """Load a workbook and run the pipeline. The one-call entry point."""
    scenario = load_scenario(dataset)
    return run(scenario, config=config, narrator=narrator)
