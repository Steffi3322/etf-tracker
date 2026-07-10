import os
import sqlite3
from pathlib import Path

import pandas as pd

SUPPORTED_ETFS = {
    "00400A": "國泰動能高息主動",
    "00403A": "統一升級50主動",
    "00981A": "統一台股增長主動",
    "00992A": "群益台灣科技創新主動",
}

_DEFAULT_DB = Path(__file__).resolve().parent / "etf_tracker.db"


def _get_secret(key: str, default: str | None = None) -> str | None:
    try:
        import streamlit as st

        if hasattr(st, "secrets") and key in st.secrets:
            return str(st.secrets[key])
    except Exception:
        pass
    return os.environ.get(key, default)


def get_db_path() -> str:
    return _get_secret("DATABASE_PATH", str(_DEFAULT_DB)) or str(_DEFAULT_DB)


def _turso_credentials() -> tuple[str | None, str | None]:
    url = _get_secret("TURSO_DATABASE_URL")
    token = _get_secret("TURSO_AUTH_TOKEN")
    return url, token


def using_turso() -> bool:
    url, token = _turso_credentials()
    return bool(url and token)


def get_connection():
    """回傳 DB-API 連線。本機用 SQLite；若設定 Turso 則連雲端。"""
    url, token = _turso_credentials()
    if url and token:
        try:
            import libsql

            return libsql.connect(database=url, auth_token=token)
        except ImportError as exc:
            raise ImportError(
                "已設定 TURSO_DATABASE_URL，但尚未安裝 libsql。"
                "請執行：pip install libsql"
            ) from exc

    db_path = get_db_path()
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path, check_same_thread=False)
    return conn


def init_db():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
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
        )
        """
    )
    conn.commit()
    conn.close()


def save_to_db(date_str, etf_code, holdings_list):
    conn = get_connection()
    cursor = conn.cursor()
    for code, name, weight, shares in holdings_list:
        cursor.execute(
            """
            INSERT OR REPLACE INTO etf_holdings
            (date, etf_code, stock_code, stock_name, weight, shares)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (date_str, etf_code, code, name, weight, shares),
        )
    conn.commit()
    conn.close()


def clear_all_data():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM etf_holdings")
    conn.commit()
    conn.close()


def get_saved_dates(conn, etf_code):
    try:
        df = pd.read_sql_query(
            "SELECT DISTINCT date FROM etf_holdings WHERE etf_code = ? ORDER BY date ASC",
            conn,
            params=[etf_code],
        )
        return df["date"].tolist()
    except Exception:
        return []


def get_all_dates(conn):
    try:
        df = pd.read_sql_query(
            "SELECT DISTINCT date FROM etf_holdings ORDER BY date ASC",
            conn,
        )
        return df["date"].tolist()
    except Exception:
        return []


def get_holdings(conn, date_str, etf_code):
    return pd.read_sql_query(
        """
        SELECT stock_code, stock_name, weight, shares
        FROM etf_holdings
        WHERE date = ? AND etf_code = ?
        ORDER BY weight DESC
        """,
        conn,
        params=[date_str, etf_code],
    )


def get_holdings_for_dates(conn, etf_code, dates):
    if not dates:
        return pd.DataFrame(columns=["date", "stock_code", "stock_name", "shares", "weight"])
    placeholders = ",".join(["?"] * len(dates))
    params = [etf_code, *dates]
    return pd.read_sql_query(
        f"""
        SELECT date, stock_code, stock_name, shares, weight
        FROM etf_holdings
        WHERE etf_code = ? AND date IN ({placeholders})
        """,
        conn,
        params=params,
    )


def get_coverage_matrix(conn, supported_etfs, recent_n=15):
    """回傳 ETF × 日期 的有無資料矩陣（1=有、0=無）。"""
    all_dates = get_all_dates(conn)
    if not all_dates:
        return pd.DataFrame()

    dates = all_dates[-recent_n:]
    rows = []
    for code, name in supported_etfs.items():
        saved = set(get_saved_dates(conn, code))
        row = {"ETF": f"{code} {name}"}
        for d in dates:
            row[d] = 1 if d in saved else 0
        rows.append(row)
    return pd.DataFrame(rows)
