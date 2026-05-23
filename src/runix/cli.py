"""Command-line interface.

Design choices:
* The five-field alert (or the full report with ``--report``) goes to **stdout**
  as clean JSON, so it pipes into ``jq`` or a webhook.
* The human reasoning trace (``--verbose``) goes to **stderr**, so it never
  pollutes the JSON on stdout.
* The two business knobs (``--beta``, ``--breach-aversion``) are first-class
  flags, because they are exactly the assumptions a manager should be able to
  challenge from the command line.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .config import EngineConfig
from .logging_setup import configure_logging
from .narrative import get_narrator
from .pipeline import PipelineResult, run_from_path

_DEFAULT_DATASET = "data/Runix_Logistics_Engine_Scenario_Dataset.xlsx"


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="runix",
        description="Turn a logistics disruption scenario into a costed, prescriptive decision.",
    )
    p.add_argument(
        "--dataset",
        type=Path,
        default=Path(_DEFAULT_DATASET),
        help=f"Path to the Excel scenario workbook (default: {_DEFAULT_DATASET}).",
    )
    p.add_argument("--pretty", action="store_true", help="Pretty-print the JSON output.")
    p.add_argument(
        "--report",
        action="store_true",
        help="Emit the full decision report (alert + all intermediates) instead of just the alert.",
    )
    p.add_argument(
        "--verbose",
        action="store_true",
        help="Print the full reasoning trace to stderr.",
    )
    p.add_argument(
        "--output", type=Path, default=None, help="Write JSON to a file instead of stdout."
    )
    p.add_argument(
        "--beta",
        type=float,
        default=None,
        metavar="0..2",
        help="Congestion sensitivity assumption (how hard the event erodes throughput).",
    )
    p.add_argument(
        "--breach-aversion",
        "-M",
        type=float,
        default=None,
        metavar="M",
        help="How much a missed SLA truly costs vs its contractual penalty (default 1.0).",
    )
    p.add_argument(
        "--narrator",
        choices=("template", "llm"),
        default="template",
        help="Prose generator. 'llm' is optional and falls back to 'template' offline.",
    )
    return p


def _print_trace(result: PipelineResult) -> None:
    """Human-readable reasoning trace, to stderr."""
    cap, risk, dec = result.capacity, result.risk, result.decision
    w = sys.stderr.write
    w("\n──────── REASONING TRACE ────────\n")
    w(
        f"\n[Scenario]   {result.scenario.context.weather_condition} + "
        f"{result.scenario.context.traffic_severity} event in "
        f"{result.scenario.context.primary_affected_zone}; "
        f"{result.scenario.order_count} orders, {result.scenario.active_driver_count} drivers\n"
    )
    mult = result.scenario.constants.weather_multiplier
    w("\n[Capacity]\n")
    w(f"  nominal              : {cap.nominal_capacity:.0f}\n")
    w(f"  after weather (x{mult}) : {cap.weather_capacity:.0f}\n")
    w(f"  congestion factor    : {cap.congestion_factor:.3f}\n")
    w(f"  effective            : {cap.effective_capacity:.2f}\n")
    w(f"  demand vs servable   : {cap.demand} vs {cap.servable}  (shortfall {cap.shortfall})\n")
    w("\n[Risk]\n")
    w(
        f"  weather/traffic/load : {risk.weather_sub_score}/"
        f"{risk.traffic_sub_score}/{risk.load_sub_score}\n"
    )
    w(f"  composite            : {risk.composite_score}  → {risk.level}\n")
    w(f"\n[Decision]  (breach-aversion M = {dec.breach_aversion:.2f})\n")
    w("  cost curve:\n")
    for pt in dec.cost_curve:
        marker = "  ←recommended" if pt.extra_drivers == dec.recommended_extra_drivers else ""
        w(
            f"    +{pt.extra_drivers} drivers: deploy ${pt.deployment_cost:>5,.0f} + "
            f"breach ${pt.weighted_penalty:>5,.0f} = ${pt.total_cost:>6,.0f}"
            f"  (unserved {pt.unserved}){marker}\n"
        )
    be = dec.break_even_to_deploy
    bf = dec.break_even_full_cover
    if be is not None:
        w(f"  break-even to deploy : M > {be}\n")
    else:
        w("  break-even to deploy : none in range\n")
    if bf is not None:
        w(f"  break-even full cover: M ≥ {bf}\n")
    w(f"  confidence           : {dec.confidence}%\n")
    w("\n[Baselines]  (total cost at active M)\n")
    for b in result.baselines:
        w(f"    {b.label:<32}: ${b.total_cost:>7,.0f}  (+{b.extra_drivers} drivers)\n")
    engine_row = f"${dec.total_cost:>7,.0f}  (+{dec.recommended_extra_drivers} drivers)"
    w(f"    {'→ ENGINE':<32}: {engine_row}\n")
    if result.scenario.data_quality_notes:
        w("\n[Data-quality notes]\n")
        for note in result.scenario.data_quality_notes:
            w(f"    • {note}\n")
    w("\n─────────────────────────────────\n\n")


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    configure_logging(verbose=args.verbose)

    overrides: dict[str, float] = {}
    if args.beta is not None:
        overrides["congestion_sensitivity"] = args.beta
    if args.breach_aversion is not None:
        overrides["breach_aversion"] = args.breach_aversion
    config = EngineConfig(**overrides)

    try:
        result = run_from_path(args.dataset, config=config, narrator=get_narrator(args.narrator))
    except FileNotFoundError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:  # noqa: BLE001
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    if args.verbose:
        _print_trace(result)

    payload = result.report() if args.report else result.alert.to_dict()
    text = json.dumps(payload, indent=2 if args.pretty else None, ensure_ascii=False)

    if args.output:
        args.output.write_text(text + "\n", encoding="utf-8")
        print(f"Wrote {args.output}", file=sys.stderr)
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
