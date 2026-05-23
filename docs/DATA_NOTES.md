# Data notes — what's actually in the workbook

Before writing a line of engine code I read every cell of
`Runix_Logistics_Engine_Scenario_Dataset.xlsx` (values *and* formulas). This file
records what I found, the two genuine data-quality issues, and the decisions I
made because of them. Everything the engine computes traces back to a cell named
here.

## The three sheets

**`Scenario Summary`** — two key/value blocks.
- *Engine Constants* (columns B/C): the named parameters below.
- *Active Scenario Context* (columns F/G): what's happening this shift.

| Constant (cell) | Value | Meaning |
|---|---|---|
| `SHIFT_HOURS` (C6) | 8 | hours per driver shift |
| `DELIVERIES_PER_DRIVER_PER_SHIFT` (C7) | 8 | deliveries one driver completes in a clear-weather shift |
| `EXPRESS_SLA_HOURS` (C8) | 2 | express delivery window |
| `STANDARD_SLA_HOURS` (C9) | 8 | standard delivery window |
| `DRIVER_SHIFT_COST` (C10) | 120 | $ to put one extra driver on shift |
| `EXPRESS_PENALTY` (C11) | 25 | $ penalty for a breached express order |
| `STANDARD_PENALTY` (C12) | 8 | $ penalty for a breached standard order |
| `WEATHER_MULTIPLIER (heavy_snow)` (C13) | 0.6 | capacity multiplier under snow |
| `TRAFFIC_RISK_SCORE (major)` (C14) | 75 | 0–100 risk index for the event |
| `WEATHER_RISK_SCORE (heavy_snow)` (C15) | 90 | 0–100 risk index for the weather |
| `RISK_WEIGHTS` (C16) | 40% / 30% / 30% | weather / traffic / load blend |

Context (F/G): weather `heavy_snow`, severity `major`, target volume `50`, base
drivers `10`, express mix `40%`, primary affected zone `central`, affected-zone
share `40%`.

**`Orders Data`** — 50 orders, `ORD-000…ORD-049`. Hand-entered, reliable columns:
Order ID (B), Service Tier (C), Destination Zone (D). Computed from the rows:

- 20 express / 30 standard → **40% express** (matches the stated mix exactly).
- Zones: central 21, south 8, west 7, north 7, east 7 → **central is 42%** (the
  workbook *states* 40% — a small drift, flagged at load time).
- 13 of the 20 express orders are in the central (affected) zone.

**`Integrated Drivers`** — 10 drivers, `DRV-000…DRV-009`, all `ACTIVE`. Only the
ID (B) and Status (C) columns are hand-entered; the rest are formulas.

## Finding 1 — the per-row penalty/SLA columns are mis-referenced

The Orders sheet has two formula columns, "SLA Delivery Window (Hrs)" (E) and
"Breach Penalty Risk" (F). Both point at the wrong cells:

```
E5 = IF(C5="express", 'Scenario Summary'!C6, 'Scenario Summary'!C7)   # C6/C7 = 8/8 → always 8, ignores tier
F5 = IF(C5="express", 'Scenario Summary'!C8, 'Scenario Summary'!C9)   # C8/C9 = SLA HOURS (2/8), not penalties
```

The real penalties live two rows lower, at `C11`/`C12` ($25 / $8). So the
"penalty" column actually contains *SLA hours*, and the "SLA window" column is
constant. Classic row-insertion drift in a hand-built spreadsheet.

**Decision:** trust the *named constants* and derive each order's SLA window and
penalty from its tier (`EXPRESS_*` for express, `STANDARD_*` otherwise). The
loader records this on every run as a data-quality note. (`test_data_loader.py`
asserts every express order carries a $25 penalty, not $2.)

## Finding 2 — every formula cell reads back as `None`

The workbook was saved without a recalculation pass, so openpyxl's `data_only`
read returns `None` for *all* formula cells — the entire Drivers economics block
(shift cost, degraded capacity), the fleet totals (`H16`, `F15`), and the
"Live Sheet Aggregations" on the summary sheet.

**Decision:** never read a value from a formula cell. Driver economics come from
the constants block (`DRIVER_SHIFT_COST`), driver *count* comes from counting
`ACTIVE` rows, and any aggregate (orders, express share, zone share) is computed
here from the rows. This is also why the workbook's own fleet-capacity total is
re-derived rather than read.

For the record, the workbook's intended fleet capacity *formula* is
`H16 = Σ (DELIVERIES_PER_DRIVER_PER_SHIFT × WEATHER_MULTIPLIER) = 10 × (8 × 0.6) = 48`.
Note it keeps the fractional 4.8/driver — it does **not** floor per driver. The
engine matches this (see `DECISION_LOGIC.md` → capacity).

## Finding 3 — small stated-vs-actual drifts (flagged, not fatal)

- Affected-zone share: rows say 42% central, the config says 40%. The engine
  uses the **actual row counts** for capacity/prioritisation and notes the drift.
- A mislabeled summary cell (`G16` "Total Drivers On Shift") actually references
  the fleet *cost* total, not a head-count. We ignore the live-aggregation cells
  entirely and compute our own.

None of these are errors in *our* output — they're observations about the source
that travel with the data (`scenario.data_quality_notes`) so a reviewer can see
exactly what we did and why.
