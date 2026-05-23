"""End-to-end golden test against the *real* dataset.

This is the characterisation test the earlier prototypes lacked: it runs the full
pipeline on the actual workbook and asserts the exact five-field alert. If any
number or any wording changes, this test fails loudly and must be updated on
purpose. It is the contract for "what the engine says about this scenario".
"""

from __future__ import annotations

import json

from runix.pipeline import run_from_path

EXPECTED_ALERT = {
    "risk_level": "High",
    "risk_summary": (
        "High risk: heavy snow (severity 90/100) plus a major event congesting the central "
        "zone (75/100). 50 orders against ~41 effective deliveries — load pressure 100/100."
    ),
    "estimated_impact": (
        "Snow cuts fleet capacity ~40% (80→48 deliveries); with central-zone congestion, "
        "effective capacity ~41. ~10 of 50 orders at SLA risk, all standard — every express "
        "order stays protected."
    ),
    "prescription": (
        "Prioritise all 20 express + central-zone orders now — current capacity covers them. "
        "Hold extra drivers: covering the 10 at-risk standard orders ($80 exposure) would cost "
        "$360 (3 drivers). Deploy only if a breach is worth >3.75× its penalty, or congestion "
        "worsens."
    ),
    "confidence_score": "79%",
}


def test_end_to_end_alert_matches_golden(dataset_path):
    result = run_from_path(dataset_path)
    assert result.alert.to_dict() == EXPECTED_ALERT


def test_report_is_json_serialisable_and_complete(dataset_path):
    report = run_from_path(dataset_path).report()
    # round-trips through JSON
    assert json.loads(json.dumps(report)) == report
    # key intermediates are present and correct
    assert report["capacity"]["effective"] == 40.8
    assert report["risk"]["composite_score"] == 88.5
    assert report["decision"]["recommended_extra_drivers"] == 0
    assert report["decision"]["break_even_to_deploy_M"] == 3.75
    assert report["baselines"][0]["name"] == "do_nothing"


def test_alert_fields_are_nonempty_strings(dataset_path):
    alert = run_from_path(dataset_path).alert.to_dict()
    assert all(isinstance(v, str) and v for v in alert.values())
