"""Alert assembly: exactly five fields, valid JSON, confidence formatting."""

from __future__ import annotations

import json

import pytest

from runix.alert import WhatsAppAlert, build_alert
from runix.narrative import Narrative


def _alert() -> WhatsAppAlert:
    return WhatsAppAlert(
        risk_level="High",
        risk_summary="summary",
        estimated_impact="impact",
        prescription="do the thing",
        confidence_score="79%",
    )


def test_alert_has_exactly_five_fields():
    d = _alert().to_dict()
    assert set(d) == {
        "risk_level",
        "risk_summary",
        "estimated_impact",
        "prescription",
        "confidence_score",
    }


def test_alert_json_round_trips():
    d = _alert().to_dict()
    assert json.loads(_alert().to_json()) == d


def test_missing_field_raises():
    bad = WhatsAppAlert("High", "", "impact", "rx", "79%")
    with pytest.raises(ValueError, match="risk_summary"):
        bad.to_dict()


def test_confidence_is_percent_string():
    class _D:
        confidence = 79

    class _R:
        level = "High"

    alert = build_alert(_R(), Narrative("s", "i", "p"), _D())
    assert alert.confidence_score == "79%"
