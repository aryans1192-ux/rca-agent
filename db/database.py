import os
import duckdb

DB_PATH = os.path.join(os.path.dirname(__file__), "orders.db")
CSV_PATH = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "data", "amazon_orders_gold_20260422.csv")
)


def get_connection() -> duckdb.DuckDBPyConnection:
    return duckdb.connect(DB_PATH, read_only=True)


def setup():
    if not os.path.exists(CSV_PATH):
        raise FileNotFoundError(f"CSV not found: {CSV_PATH}")

    con = duckdb.connect(DB_PATH)
    con.execute("DROP TABLE IF EXISTS orders")
    con.execute(
        f"CREATE TABLE orders AS SELECT * FROM read_csv_auto('{CSV_PATH}', header=True)"
    )
    count = con.execute("SELECT COUNT(*) FROM orders").fetchone()[0]
    con.close()
    print(f"[DB] Loaded {count} rows from CSV into orders table")
