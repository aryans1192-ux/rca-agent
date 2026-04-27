from core.models import RCAResult, CitySummary, StoreSummary
from core.rca_engine import run_rca, format_rca_report
from db.repository import repository

DEFAULT_DATE = "2026-04-22"


class RCAService:

    def get_problem_hours_summary(self, date: str = DEFAULT_DATE, city: str = "", store: str = "") -> str:
        rows = repository.get_problem_hours(date=date, city=city, store=store)
        if not rows:
            return "No problem hours found for the given filters."

        # Broad query (no city/store filter) → city-level summary to avoid token bloat
        if not city and not store:
            from collections import defaultdict
            by_city: dict = defaultdict(lambda: {"total": 0, "stores": set(), "pileup": 0})
            for r in rows:
                by_city[r.city]["total"] += 1
                by_city[r.city]["stores"].add(r.store)
                if r.pileup_flag:
                    by_city[r.city]["pileup"] += 1

            total_stores = sum(len(s["stores"]) for s in by_city.values())
            lines = [
                f"Found **{total_stores} stores** with problem hours across **{len(by_city)} cities** on 2026-04-22:\n"
            ]
            for city_name, stats in sorted(by_city.items()):
                lines.append(
                    f"- **{city_name}**: {len(stats['stores'])} stores affected, "
                    f"{stats['total']} problem hours, "
                    f"{stats['pileup']} with pileup"
                )
            lines.append("\nUse get_problem_hours with a specific city to see store-level detail.")
            return "\n".join(lines)

        # Filtered query → individual rows (capped at 50)
        total = len(rows)
        shown = rows[:50]
        lines = [f"Found **{total}** problem hour(s) (showing first {len(shown)}):\n"]
        for r in shown:
            lines.append(
                f"- **{r.store}** ({r.city}) | Hour {r.hour}:00 "
                f"| OR2A: {round(r.avg_or2a, 1)} min "
                f"| Breach Rate: {round(r.breached_rate * 100, 1)}%"
                f"| Pileup: {'YES' if r.pileup_flag else 'NO'}"
            )
        return "\n".join(lines)

    def run_store_rca(self, store: str, date: str = DEFAULT_DATE, hour: int = -1) -> str:
        store_rows = repository.get_store_rows(store=store, date=date)
        if not store_rows:
            return f"No data found for store '{store}' on {date}."

        problem_rows = [r for r in store_rows if r.is_problem_hour]
        if hour >= 0:
            problem_rows = [r for r in problem_rows if r.hour == hour]

        if not problem_rows:
            return f"No problem hours found for store '{store}'."

        # Cap at 5 worst hours (highest breach rate) to keep response concise
        problem_rows = sorted(problem_rows, key=lambda r: r.breached_rate, reverse=True)[:5]
        results: list[RCAResult] = [run_rca(row, store_rows) for row in problem_rows]
        return format_rca_report(results)

    def get_city_summary(self, city: str, date: str = DEFAULT_DATE) -> str:
        summary: CitySummary | None = repository.get_city_summary(city=city, date=date)
        if not summary:
            return f"No data found for city '{city}' on {date}."

        return (
            f"**{summary.city}** — {date}\n"
            f"- Total Orders: {summary.total_orders}\n"
            f"- Weighted Breach Rate: {summary.weighted_breach_rate_pct}%\n"
            f"- Weighted Avg OR2A: {summary.weighted_avg_or2a} min\n"
            f"- Problem Hours: {summary.problem_hours} of {summary.total_store_hours} store-hours\n"
        )

    def list_cities(self, date: str = DEFAULT_DATE) -> str:
        cities = repository.list_cities(date=date)
        if not cities:
            return "No cities found."
        return "Available cities: " + ", ".join(cities)

    def list_stores(self, city: str, date: str = DEFAULT_DATE) -> str:
        stores: list[StoreSummary] = repository.list_stores(city=city, date=date)
        if not stores:
            return f"No stores found in '{city}'."

        lines = [f"Stores in **{city}**:\n"]
        for s in stores:
            flag = "PROBLEM" if s.problem_hours > 0 else "OK"
            lines.append(f"  [{flag}] {s.store} — {s.problem_hours} problem hour(s), {s.total_orders} orders")
        return "\n".join(lines)


rca_service = RCAService()
