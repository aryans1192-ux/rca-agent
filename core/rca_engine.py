from core.models import (
    OrderRow, RCAResult, DemandSpikeResult, PileupResult, SupplyResult
)

DEMAND_SPIKE_THRESHOLD = 1.10
BOOKING_GAP_THRESHOLD = 0.90
UTILIZATION_GAP_THRESHOLD = 0.85
SUSTAINED_PILEUP_MIN_HOURS = 3


def check_demand_spike(row: OrderRow) -> DemandSpikeResult:
    if row.order_projection > 0 and row.total_orders > row.order_projection * DEMAND_SPIKE_THRESHOLD:
        excess_pct = round(((row.total_orders / row.order_projection) - 1) * 100, 1)
        return DemandSpikeResult(
            triggered=True,
            reason=f"{int(row.total_orders)} orders vs {int(row.order_projection)} projected (+{excess_pct}%)",
        )
    return DemandSpikeResult(triggered=False)


def check_pileup(row: OrderRow, store_rows: list[OrderRow]) -> PileupResult:
    if not row.pileup_flag:
        return PileupResult(triggered=False)

    pileup_hours = sorted(r.hour for r in store_rows if r.pileup_flag)

    max_consecutive = 1
    current_run = 1
    for i in range(1, len(pileup_hours)):
        if pileup_hours[i] == pileup_hours[i - 1] + 1:
            current_run += 1
            max_consecutive = max(max_consecutive, current_run)
        else:
            current_run = 1

    pileup_count = int(row.pileup_count)
    if max_consecutive >= SUSTAINED_PILEUP_MIN_HOURS:
        return PileupResult(
            triggered=True,
            sustained=True,
            reason=f"{pileup_count} orders carried from previous hour [SUSTAINED: {max_consecutive} consecutive hours]",
        )
    return PileupResult(
        triggered=True,
        sustained=False,
        reason=f"{pileup_count} orders carried from previous hour",
    )


def check_supply(row: OrderRow) -> SupplyResult:
    if row.current_size > 0:
        booking_ratio = row.booked_size / row.current_size
        if booking_ratio < BOOKING_GAP_THRESHOLD:
            return SupplyResult(
                triggered=True,
                level="L1",
                reason=(
                    f"Booking gap: {int(row.booked_size)} of {int(row.current_size)} slots booked "
                    f"({round(booking_ratio * 100, 1)}% vs 90% required)"
                ),
            )

    if 0 < row.man_hour < UTILIZATION_GAP_THRESHOLD:
        return SupplyResult(
            triggered=True,
            level="L2",
            reason=f"Utilization gap: man_hour ratio {round(row.man_hour, 2)} ({int(row.noshow_count)} no-shows, below 0.85 threshold)",
        )

    return SupplyResult(triggered=False)


def run_rca(row: OrderRow, store_rows: list[OrderRow]) -> RCAResult:
    demand = check_demand_spike(row)
    pileup = check_pileup(row, store_rows)
    supply = check_supply(row)

    root_causes = [
        r.reason for r in [demand, pileup, supply]
        if r.triggered and r.reason
    ]
    if not root_causes:
        root_causes = ["No clear root cause identified from available signals"]

    return RCAResult(
        store=row.store,
        city=row.city,
        hour=row.hour,
        avg_or2a=round(row.avg_or2a, 2),
        breached_rate_pct=round(row.breached_rate * 100, 1),
        total_orders=int(row.total_orders),
        order_projection=int(row.order_projection),
        booked_size=int(row.booked_size),
        current_size=int(row.current_size),
        man_hour=round(row.man_hour, 2),
        noshow_count=int(row.noshow_count),
        root_causes=root_causes,
        demand_spike=demand,
        pileup=pileup,
        supply=supply,
    )


def format_rca_report(results: list[RCAResult]) -> str:
    if not results:
        return "No problem hours found."

    blocks = []
    for r in results:
        # Demand line
        if r.demand_spike.triggered:
            demand_line = f"YES — {r.demand_spike.reason}"
        else:
            if r.order_projection > 0:
                pct = round(((r.total_orders / r.order_projection) - 1) * 100, 1)
                demand_line = f"NO — {r.total_orders} orders vs {r.order_projection} projected ({pct:+.1f}%)"
            else:
                demand_line = f"NO — {r.total_orders} orders (no projection available)"

        # Pileup line
        if r.pileup.triggered:
            pileup_line = f"YES — {r.pileup.reason}"
        else:
            pileup_line = "NO"

        # Supply lines
        booking_pct = round((r.booked_size / r.current_size) * 100, 1) if r.current_size > 0 else 0
        booking_ok = booking_pct >= 90
        booking_line = f"{r.booked_size} of {r.current_size} slots booked ({booking_pct}%) — {'OK' if booking_ok else 'GAP'}"

        util_ok = r.man_hour >= UTILIZATION_GAP_THRESHOLD or r.man_hour == 0
        util_line = f"man_hour ratio {r.man_hour} ({r.noshow_count} no-shows) — {'OK' if util_ok else 'GAP'}"

        summary = "; ".join(r.root_causes)

        block = (
            f"### {r.store} — Hour {r.hour}:00 — avg OR2A: {r.avg_or2a} min\n\n"
            f"1. Demand Spike: {demand_line}\n"
            f"2. Pileup: {pileup_line}\n"
            f"3. Supply:\n"
            f"   a. Booking: {booking_line}\n"
            f"   b. Utilization: {util_line}\n\n"
            f"**Summary**: OR2A {r.avg_or2a} min (breach {r.breached_rate_pct}%) — {summary}"
        )
        blocks.append(block)

    header = f"RCA for {results[0].store} — {len(results)} problem hour(s) shown:\n\n"
    return header + "\n\n---\n\n".join(blocks)
