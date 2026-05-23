# Runix Decision Engine

It's 5 PM. Heavy snow is forecast from six, and there's a major football match
snarling traffic in the central zone. You're the hub manager: 50 orders on the
board, 10 drivers, and a few minutes to decide whether to pay for more drivers,
reprioritise the route sheet, or accept that some deliveries will slip.

This is a small engine that makes that call — and, more importantly, shows its
working. It reads the scenario workbook, estimates how much delivery capacity the
storm and the match actually leave you, scores the risk, runs the money, and
emits a WhatsApp-ready alert with a clear recommendation and a confidence level.

```json
{
  "risk_level": "High",
  "risk_summary": "High risk: heavy snow (severity 90/100) plus a major event congesting the central zone (75/100). 50 orders against ~41 effective deliveries — load pressure 100/100.",
  "estimated_impact": "Snow cuts fleet capacity ~40% (80→48 deliveries); with central-zone congestion, effective capacity ~41. ~10 of 50 orders at SLA risk, all standard — every express order stays protected.",
  "prescription": "Prioritise all 20 express + central-zone orders now — current capacity covers them. Hold extra drivers: covering the 10 at-risk standard orders ($80 exposure) would cost $360 (3 drivers). Deploy only if a breach is worth >3.75× its penalty, or congestion worsens.",
  "confidence_score": "79%"
}
```

## The interesting part

The obvious move in a snowstorm is to throw drivers at the problem. The engine
says **don't** — and that's the whole point.

Once you simply **serve express and central-zone orders first**, all 20 express
orders fit inside the capacity you have left. Every order that ends up at risk is
a cheap standard one. Paying for 3 extra drivers ($360) to rescue ~$80 of
standard-order penalties is a bad trade. So the recommendation is: reprioritise
(free), hold the drivers, and accept a handful of standard slips.

But "is $80 of penalties really only worth $80?" is a *business* question — a
failed delivery in a storm costs goodwill the contract doesn't price. So instead
of pretending to know that number, the engine reports the **break-even**: you
should only start deploying drivers once you believe a missed SLA is worth more
than **3.75×** its contractual penalty. That one judgement call is handed to the
manager, out in the open, with a sensitivity map showing exactly where tonight's
decision sits.

That's the difference between a tool that computes a number and one that helps a
human make a decision.

## Quick start

Requires Python 3.10+. The Makefile is the interface.

```bash
make install     # create a venv and install the package (uses uv if present)
make run         # print the WhatsApp alert for the bundled scenario
make dashboard   # launch the interactive decision dashboard
make test        # run the test suite (60 tests)
```

`make run` gives you the JSON above. To watch the engine reason:

```bash
make run-verbose
```

```
[Capacity]
  nominal              : 80
  after weather (x0.6) : 48
  congestion factor    : 0.850
  effective            : 40.80
  demand vs servable   : 50 vs 40  (shortfall 10)
[Decision]  (breach-aversion M = 1.00)
  cost curve:
    +0 drivers: deploy $    0 + breach $   80 = $    80  (unserved 10)  ←recommended
    +1 drivers: deploy $  120 + breach $   48 = $   168  (unserved 6)
    +2 drivers: deploy $  240 + breach $   16 = $   256  (unserved 2)
    +3 drivers: deploy $  360 + breach $    0 = $   360  (unserved 0)
  break-even to deploy : M > 3.75
[Baselines]  (total cost at active M)
    Do nothing (no prioritisation)  : $    148
    Prioritise only (no drivers)    : $     80
    → ENGINE                        : $     80
```

You can challenge the assumptions straight from the command line:

```bash
runix -M 5            # if a breach is worth 5× its penalty → engine deploys 2 drivers
runix --beta 1.0      # if you think the match is worse → deeper shortfall
runix --report --pretty   # full machine-readable report (every intermediate number)
```

## The dashboard

`make dashboard` opens a manager's cockpit (Streamlit + Plotly):

- the **WhatsApp alert** exactly as it would arrive;
- a **risk gauge** and the headline metrics;
- a **capacity waterfall** (80 → 48 → 40.8 vs the 50-order demand line);
- the **cost-vs-drivers curve** with the recommended point starred;
- the engine vs. the **naive baselines**;
- a **sensitivity heatmap** over the two assumptions, with a marker for where your
  current settings land — so you can see whether the call is robust or borderline.

Two sliders — congestion sensitivity (β) and breach aversion (M) — recompute the
entire decision live.

## How it thinks

The pipeline is a series of small, separately testable stages:

```
load → capacity → risk → decide → baselines → narrate → alert
```

The design splits cleanly into a **model** (estimates reality: capacity, risk,
who's at risk) and a **decision layer** (trades off costs to pick an action). The
full reasoning — every formula, the break-even maths, the baseline comparison,
and an honest list of what the engine can't know — is in
[`docs/DECISION_LOGIC.md`](docs/DECISION_LOGIC.md).

### A note on the data

I read every cell of the workbook before trusting it, and found two real issues:
the per-order "penalty" column is mis-referenced (it points at the SLA-hours
cells, not the penalty cells), and the file was saved without recalculating, so
every formula cell reads back empty. The engine works around both by trusting the
named constants and deriving the rest, and it logs what it caught on every run.
The full audit is in [`docs/DATA_NOTES.md`](docs/DATA_NOTES.md).

## The two knobs (and why they're knobs)

Everything else comes from the data. These two don't, so they're explicit,
documented, and swept in the sensitivity analysis rather than hidden:

| Knob | What it means | Default | Because |
|---|---|---|---|
| `β` congestion sensitivity | how hard the road event erodes throughput | 0.5 | the workbook gives the event as a risk *index*, not a capacity multiplier |
| `M` breach aversion | a missed SLA's true cost vs its contractual penalty | 1.0 | the $25/$8 penalties are contractual; real churn cost is a business call |

## Project layout

```
src/runix/
  data_loader.py   workbook → typed scenario (+ data-quality findings)
  models.py        frozen domain dataclasses
  capacity.py      nominal → weather → congestion → effective
  risk.py          the 0–100 composite risk index
  decision.py      the asymmetric-cost optimiser + break-even analysis
  baselines.py     naive strategies the engine must beat
  sensitivity.py   the β × M sweep behind the heatmap
  narrative.py     deterministic prose (+ optional, fall-back LLM narrator)
  alert.py         the five-field WhatsApp payload + full report
  pipeline.py      wires the stages together
  cli.py           command-line interface
app/dashboard.py   the Streamlit cockpit
tests/             60 tests: unit, boundaries, baselines, and an end-to-end golden
docs/              the data audit and the decision-logic deep-dive
```

## Testing

```bash
make test      # 60 tests
make lint      # ruff, clean
```

The suite covers each component's contract and edge cases, asserts the engine
never loses to a naive baseline at any M, checks the break-even maths, and ends
with a **golden test** that runs the whole pipeline on the real workbook and
pins the exact five-field alert. If any number or any word changes, that test
fails on purpose.

## What I'd build next

The honest limitations are written up in `docs/DECISION_LOGIC.md`, but the short
version: the biggest unlock is **per-zone routing with real travel times** under
snow/events — that would replace the single β assumption with measured throughput
and turn this from a staffing call into a routed plan. Second is **fitting M from
retention data** instead of leaving it a slider. Both need data the workbook
doesn't contain, which is exactly why the engine surfaces them as assumptions
today rather than faking precision it doesn't have.

## Optional: LLM-phrased alerts

The brief allows an LLM to assist with the prose. The default narrator is
deterministic (so the output is reproducible and testable), but an optional one
will rephrase the alert via the Anthropic API if you want richer wording:

```bash
pip install -e ".[llm]"
export ANTHROPIC_API_KEY=...
runix --narrator llm        # falls back to the template offline or on any error
```

It only rephrases prose from numbers the engine already decided — it never
changes the recommendation.
