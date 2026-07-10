#!/usr/bin/env python3
"""將本機 etf_tracker.db 匯出為 SQL，方便匯入 Turso。

用法：
  python export_sql.py > holdings_seed.sql
  turso db shell <db-name> < holdings_seed.sql
"""

from __future__ import annotations

from pathlib import Path

from db import get_db_path, get_connection, init_db


def main():
    init_db()
    db_path = Path(get_db_path())
    if not db_path.exists():
        raise SystemExit(f"找不到資料庫：{db_path}")

    conn = get_connection()
    print("BEGIN;")
    print(
        """
CREATE TABLE IF NOT EXISTS etf_holdings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL,
    etf_code TEXT NOT NULL,
    stock_code TEXT NOT NULL,
    stock_name TEXT NOT NULL,
    weight REAL,
    shares INTEGER,
    UNIQUE(date, etf_code, stock_code)
);
""".strip()
    )
    rows = conn.execute(
        "SELECT date, etf_code, stock_code, stock_name, weight, shares FROM etf_holdings ORDER BY date, etf_code, stock_code"
    ).fetchall()
    for date, etf_code, stock_code, stock_name, weight, shares in rows:
        name = str(stock_name).replace("'", "''")
        print(
            "INSERT OR REPLACE INTO etf_holdings "
            "(date, etf_code, stock_code, stock_name, weight, shares) VALUES ("
            f"'{date}', '{etf_code}', '{stock_code}', '{name}', {float(weight or 0)}, {int(shares or 0)}"
            ");"
        )
    print("COMMIT;")
    conn.close()
    print(f"-- exported {len(rows)} rows from {db_path}", file=__import__("sys").stderr)


if __name__ == "__main__":
    main()
