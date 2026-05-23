# Decision logic — how the engine thinks

This is the reasoning the dashboard and the alert sit on top of. It is
deliberately written so you can follow every number by hand.

## 1. The problem, stated plainly

A regional hub has 50 orders to deliver tonight and 10 drivers. Two things go
wrong at once: heavy snow from 6 PM, and a major football match congesting the
central zone. The manager has to decide, in minutes, **whether to pay for extra
drivers, whether to reprioritise, and what to tell the team.** Express orders
have a tight 2-hour SLA and a higher breach penalty; standard orders have an
8-hour window.

The output is a five-field WhatsApp alert. The hard part isn't the JSON — it's
making the *right* call and being able to defend it.

## 2. The design principle: estimate, then decide

The engine has two cleanly separated halves:

- **The model estimates reality** — how much capacity we actually have, how many
  orders are at risk, how dangerous the shift is. It knows nothing about money.
- **The decision layer trades off costs** — it takes the estimate and the
  business's cost appetite and picks an action.

This separation matters because the same risk picture should drive *different*
decisions for different cost appetites, and because the one genuinely subjective
input (how much a missed SLA really costs) belongs in the open, not hard-coded
inside a risk score.

## 3. Capacity — a chain of named factors

```
nominal     = drivers × deliveries/driver        = 10 × 8            = 80
weather     = nominal × weather_multiplier        = 80 × 0.6          = 48
congestion  = 1 − (traffic/100) × zone_share × β  = 1 − 0.75×0.40×0.5 = 0.85
effective   = weather × congestion                = 48 × 0.85         = 40.8
```

- `weather = 48` is exactly the workbook's own fleet total (no per-driver
  flooring; see `DATA_NOTES.md`).
- `β` (congestion sensitivity) is the **one modelled assumption**. The workbook
  gives the event only as a 0–100 *risk index*, not a capacity multiplier, so we
  translate it transparently and expose β rather than burying a magic number.
  Default β = 0.5 ("a worst-case event in a fully-congested network halves
  throughput"); here that's a 15% drag.

We floor only once, at the fleet level: **40 whole orders servable, 10 short.**

## 4. Risk — a 0–100 composite

```
composite = 0.40×weather + 0.30×traffic + 0.30×load
          = 0.40×90      + 0.30×75      + 0.30×100   = 88.5  → High
```

Weather (90) and traffic (75) are read straight from the data. **Load** is demand
pressure against *realistic* (snow-degraded) capacity: `100 × 50/48 → capped at
100`. We use the degraded capacity, not the clear-weather 80, because pretending
we have 80 deliveries of headroom in a snowstorm understates the pressure — at 50
orders against 48 realistic deliveries, the load genuinely *is* maxed, and the
score should say so. Thresholds: Low < 40 ≤ Medium < 70 ≤ High.

## 5. The decision — a threshold call under asymmetric costs

We don't ask "how many drivers cover the shortfall?" We ask "what's the cheapest
action?" For each number of extra drivers `d`:

```
cost(d) = d × $120  +  M × penalty(orders left unserved | d)
```

where `M` (breach aversion) is how much a missed SLA truly costs versus its
contractual penalty, and we always **serve express + central orders first**, so a
driver is only ever bought for the low-value tail.

With prioritisation, all 20 express orders fit inside the first 40 of capacity —
so **express is fully protected for free**, and every breach falls on cheap
standard orders. The cost curve at the default `M = 1`:

| Extra drivers | Driver cost | Unserved (all standard) | Breach $ | **Total** |
|--:|--:|--:|--:|--:|
| **0** | $0 | 10 | $80 | **$80** ✅ |
| 1 | $120 | 6 | $48 | $168 |
| 2 | $240 | 2 | $16 | $256 |
| 3 | $360 | 0 | $0 | $360 |

The optimum is **deploy nobody, reprioritise, accept ~10 standard breaches
($80)**. Spending $360 to avoid $80 is a losing trade.

### The break-even (the real lever)

Because everything is linear in `M`, the optimal `d` as a function of `M` is a
clean set of regions:

- `M < 3.75` → **0 drivers** (hold)
- `3.75 ≤ M < 7.5` → **2 drivers**
- `M ≥ 7.5` → **3 drivers** (full cover)

So the recommendation is robust: across *any* plausible breach valuation up to
3.75× the contractual penalty, holding is optimal. That single number —
"how much is protecting a standard customer in a storm worth to you?" — is the
only thing that flips the decision, and the engine hands it to the manager
instead of guessing it.

## 6. Baselines — earning the complexity

| Strategy | Action | Total cost (M=1) |
|---|---|--:|
| Do nothing (no prioritisation) | breaches hit tiers by mix | **$148** |
| Panic-hire to zero breaches | +3 drivers | **$360** |
| Prioritise only (no drivers) | reprioritise, +0 | **$80** |
| **Engine** | reprioritise, +0 | **$80** |

Two takeaways: (1) the engine ties the best static strategy at `M=1` and strictly
beats all of them elsewhere, because its decision is the lower envelope of every
driver count at every `M`; (2) **just reprioritising the route sheet saves $68
(148 → 80) at zero spend** — the single highest-ROI action available, and it's
free.

## 7. Confidence

Confidence reflects how *decisively* the chosen action beats its runner-up
(scaled by data completeness), not how scared we are. At `M=1` the best option
($80) is far cheaper than the next ($168) → **79%**. Near a break-even the two
options are close and confidence honestly drops (e.g. ~60% at `M=5`).

## 8. What this engine does NOT know (and what would fix it)

- **No per-order geography or routing.** Capacity is an aggregate rate, not a
  routed plan. A real router (travel times per zone under snow) would replace the
  single `β` with measured zone-level throughput — the highest-value next step.
- **`β` and `M` are assumptions, not measurements.** That's exactly why they're
  exposed and swept in the sensitivity grid rather than hidden. Historical
  delivery logs under past snow/events would let us *fit* β instead of assuming
  it.
- **Penalties are contractual, not behavioural.** The true churn cost of failing
  a customer is what `M` stands in for; a retention model would let us set it
  from data rather than judgement.
- **The scenario is a single snapshot.** No intra-shift dynamics (the snow
  worsening, drivers finishing early). A time-stepped version would let the
  manager re-run the call at 7 PM with what actually happened by 6:30.

Knowing where the information *isn't* is the point: no amount of tuning extracts a
zone-level routing decision from a workbook that doesn't contain travel times.
The engine is honest about that line.
