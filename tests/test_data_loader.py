"""DataLoader: real-dataset truth, the spreadsheet-bug workaround, and validation."""

from __future__ import annotations

import pytest

from runix.data_loader import DataLoaderError, load_scenario
from runix.models import ServiceTier


def test_loads_real_scenario_counts(scenario):
    assert scenario.order_count == 50
    assert len(scenario.express_orders) == 20  # 40% express
    assert len(scenario.standard_orders) == 30
    assert scenario.active_driver_count == 10
    assert scenario.context.primary_affected_zone == "central"


def test_real_constants_traceable_to_cells(scenario):
    c = scenario.constants
    assert c.deliveries_per_driver_per_shift == 8
    assert c.weather_multiplier == 0.6
    assert c.driver_shift_cost == 120
    assert c.express_penalty == 25
    assert c.standard_penalty == 8
    assert c.weather_risk_score == 90
    assert c.traffic_risk_score == 75
    assert c.risk_weights == {"weather": 0.4, "traffic": 0.3, "load": 0.3}


def test_penalties_derived_from_constants_not_buggy_columns(scenario):
    # The workbook's per-row penalty column is buggy (points at SLA-hours cells).
    # Every express order must carry the *named* EXPRESS_PENALTY ($25), not $2.
    for order in scenario.express_orders:
        assert order.breach_penalty == 25
        assert order.sla_hours == 2
    for order in scenario.standard_orders:
        assert order.breach_penalty == 8
        assert order.sla_hours == 8


def test_data_quality_note_records_the_spreadsheet_bug(scenario):
    joined = " ".join(scenario.data_quality_notes).lower()
    assert "breach penalty" in joined and "bug" in joined


def test_zone_share_drift_is_noted(scenario):
    # Rows are 42% central but the workbook states 40%; that drift must be flagged.
    joined = " ".join(scenario.data_quality_notes).lower()
    assert "affected-zone" in joined or "affected zone" in joined


def test_tiers_parse_to_enum(scenario):
    assert all(o.tier in (ServiceTier.EXPRESS, ServiceTier.STANDARD) for o in scenario.orders)


def test_missing_file_raises_filenotfound():
    with pytest.raises(FileNotFoundError):
        load_scenario("does/not/exist.xlsx")


def test_missing_sheet_raises(tmp_path, make_workbook):
    path = make_workbook(tmp_path / "no_orders.xlsx", omit_sheet="Orders Data")
    with pytest.raises(DataLoaderError, match="Orders Data"):
        load_scenario(path)


def test_missing_constant_raises_named_error(tmp_path, make_workbook):
    path = make_workbook(tmp_path / "no_mult.xlsx", omit_param="WEATHER_MULTIPLIER (heavy_snow)")
    with pytest.raises(DataLoaderError, match="WEATHER_MULTIPLIER"):
        load_scenario(path)


def test_synthetic_workbook_loads_cleanly(tmp_path, make_workbook):
    path = make_workbook(tmp_path / "ok.xlsx", n_orders=6, n_drivers=2)
    sc = load_scenario(path)
    assert sc.order_count == 6
    assert sc.active_driver_count == 2
