from core.models import OrderRow, CitySummary, StoreSummary
from db.database import get_connection


class OrderRepository:

    def get_store_rows(self, store: str, date: str) -> list[OrderRow]:
        with get_connection() as con:
            rows = con.execute(
                "SELECT * FROM orders WHERE LOWER(store) LIKE LOWER(?) AND charge_date = ? ORDER BY hour",
                [f"%{store}%", date]
            ).fetchdf().to_dict(orient="records")
        return [OrderRow(**r) for r in rows]

    def get_problem_hours(self, date: str, city: str = "", store: str = "") -> list[OrderRow]:
        conditions = ["is_problem_hour = 1", "charge_date = ?"]
        params: list = [date]
        if city:
            conditions.append("LOWER(city) LIKE LOWER(?)")
            params.append(f"%{city}%")
        if store:
            conditions.append("LOWER(store) LIKE LOWER(?)")
            params.append(f"%{store}%")

        query = f"SELECT * FROM orders WHERE {' AND '.join(conditions)} ORDER BY store, hour"
        with get_connection() as con:
            rows = con.execute(query, params).fetchdf().to_dict(orient="records")
        return [OrderRow(**r) for r in rows]

    def get_city_summary(self, city: str, date: str) -> CitySummary | None:
        with get_connection() as con:
            rows = con.execute("""
                SELECT
                    city,
                    SUM(total_orders)                                                      AS total_orders,
                    SUM(breached_count)                                                    AS total_breached,
                    ROUND(SUM(breached_count) * 100.0 / NULLIF(SUM(total_orders), 0), 1)  AS breach_rate,
                    ROUND(SUM(avg_or2a * total_orders) / NULLIF(SUM(total_orders), 0), 1) AS avg_or2a,
                    SUM(CASE WHEN is_problem_hour = 1 THEN 1 ELSE 0 END)                  AS problem_hours,
                    COUNT(*)                                                                AS total_store_hours
                FROM orders
                WHERE LOWER(city) LIKE LOWER(?) AND charge_date = ?
                GROUP BY city
            """, [f"%{city}%", date]).fetchdf().to_dict(orient="records")

        if not rows:
            return None
        r = rows[0]
        return CitySummary(
            city=r["city"],
            date=date,
            total_orders=int(r["total_orders"] or 0),
            weighted_breach_rate_pct=float(r["breach_rate"] or 0),
            weighted_avg_or2a=float(r["avg_or2a"] or 0),
            problem_hours=int(r["problem_hours"]),
            total_store_hours=int(r["total_store_hours"]),
        )

    def list_cities(self, date: str) -> list[str]:
        with get_connection() as con:
            rows = con.execute(
                "SELECT DISTINCT city FROM orders WHERE charge_date = ? ORDER BY city", [date]
            ).fetchall()
        return [r[0] for r in rows]

    def list_stores(self, city: str, date: str) -> list[StoreSummary]:
        with get_connection() as con:
            rows = con.execute("""
                SELECT store, city,
                       SUM(CASE WHEN is_problem_hour = 1 THEN 1 ELSE 0 END) AS problem_hours,
                       SUM(total_orders) AS total_orders
                FROM orders
                WHERE LOWER(city) LIKE LOWER(?) AND charge_date = ?
                GROUP BY store, city
                ORDER BY problem_hours DESC
            """, [f"%{city}%", date]).fetchdf().to_dict(orient="records")
        return [
            StoreSummary(
                store=r["store"],
                city=r["city"],
                problem_hours=int(r["problem_hours"]),
                total_orders=int(r["total_orders"]),
            )
            for r in rows
        ]


repository = OrderRepository()
