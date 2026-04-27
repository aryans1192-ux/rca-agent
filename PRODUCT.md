# RCA Agent — Product Overview

## The Problem

When a delivery store misses its SLA — riders aren't assigned fast enough — an operations analyst has to manually pull SQL reports and work through a diagnostic checklist to figure out why. This takes time, requires SQL skills, and happens after the damage is done.

## What This Agent Does

It replaces that manual process with a conversation. An ops user types a question in plain English. The agent queries the data, runs the diagnostic checks, and returns a structured root cause analysis — in seconds.

**Before:** Analyst opens SQL editor → writes 4 queries → cross-references a playbook → writes a summary report.  
**After:** Analyst types *"Why did STORE_003 underperform this morning?"* and gets the answer.

---

## What You Can Ask

The agent understands questions at three levels of detail:

**City level**
> *"How did Bangalore do on 2026-04-22?"*  
> *"Which city had the worst SLA breach rate today?"*  
> *"Were there any sustained pileups across all cities?"*

**Store level**
> *"Why did STORE_177 underperform?"*  
> *"List all stores in Mumbai North with problem hours"*  
> *"Run RCA for STORE_003"*

**Hour level**
> *"Walk me through the morning hours at STORE_003"*  
> *"What happened at STORE_177 at 8 PM?"*

It also understands follow-up questions and context switches mid-conversation:
> *"What about Chennai?"* — switches city without you re-explaining the date  
> *"Now drill into the worst store there"* — agent remembers what was just discussed

---

## What the RCA Checks

For every problem hour, the agent independently checks three possible root causes:

| Root Cause | What it means in plain language |
|------------|--------------------------------|
| **Demand Spike** | More orders arrived than forecasted (>10% above projection) — supply couldn't keep up |
| **Pileup** | Unassigned orders carried over from the previous hour, compounding the delay |
| **Sustained Pileup** | Pileup lasted 3+ consecutive hours — a systemic backlog, not a one-off |
| **Booking Gap (L1)** | Less than 90% of rider slots were filled — not enough riders showed up |
| **Utilization Gap (L2)** | Riders were booked but not working — no-show or early departure issue |

Multiple causes can apply to the same hour — the agent reports all of them.

---

## Sample Output

```
### STORE_177 — Hour 20:00 — avg OR2A: 883 min

1. Demand Spike: NO — 40 orders vs 42 projected (-4.8%)
2. Pileup: YES — 10 orders carried from previous hour [SUSTAINED: 5 consecutive hours]
3. Supply:
   a. Booking: 21 of 35 slots booked (60.0%) — GAP
   b. Utilization: man_hour ratio 0.71 (4 no-shows) — GAP

Summary: OR2A 883 min (breach 100%) — Sustained pileup from 16:00; booking gap 60% vs 90% required
```

---

## Coverage

- **Date:** 2026-04-22
- **Cities:** Bangalore, Chennai, Faridabad, Gurgaon, Hyderabad, Mumbai North, New Delhi, Noida, Pune City East
- **Stores:** 200+ stores across all cities
- **Data:** Pre-aggregated store × hour table (3,800+ records)
