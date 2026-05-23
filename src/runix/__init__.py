"""Runix Decision Engine.

A decision-intelligence pipeline that turns a logistics disruption scenario
(weather, a road event, orders, drivers, costs) into a costed, prescriptive
operational decision and a WhatsApp-ready alert.

Public entry points:

    from runix import run_from_path, EngineConfig
    result = run_from_path("data/Runix_Logistics_Engine_Scenario_Dataset.xlsx")
    print(result.alert.to_json(pretty=True))
"""

from __future__ import annotations

from .config import EngineConfig
from .pipeline import PipelineResult, run, run_from_path

__version__ = "1.0.0"
__all__ = ["EngineConfig", "PipelineResult", "run", "run_from_path", "__version__"]
