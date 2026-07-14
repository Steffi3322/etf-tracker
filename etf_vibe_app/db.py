import json
import os
import re
import sqlite3
import urllib.error
import urllib.request
from pathlib import Path

import pandas as pd

SUPPORTED_ETFS = {
    "00400A": "國泰動能高息主動",
    "00403A": "統一升級50主動",
    "00981A": "統一台股增長主動",
    "00992A": "群益台灣科技創新主動",
}

_DEFAULT_DB = Path(__file__).resolve().parent / "etf_tracker.db"

_CREATE_TABLE_SQL = """
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


def _normalize_secret(key: str, value: str | None) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if key == "TURSO_AUTH_TOKEN":
        # Tokens must be a single line; pasted wraps often insert spaces/newlines.
        text = re.sub(r"\s+", "", text)
    return text or None


def _get_secret(key: str, default: str | None = None) -> str | None:
    try:
        import streamlit as st

        if hasattr(st, "secrets") and key in st.secrets:
            return _normalize_secret(key, str(st.secrets[key]))
    except Exception:
        pass
    return _normalize_secret(key, os.environ.get(key, default))


def get_db_path() -> str:
    return _get_secret("DATABASE_PATH", str(_DEFAULT_DB)) or str(_DEFAULT_DB)


def _turso_credentials() -> tuple[str | None, str | None]:
    url = _get_secret("TURSO_DATABASE_URL")
    token = _get_secret("TURSO_AUTH_TOKEN")
    return url, token


def using_turso() -> bool:
    url, token = _turso_credentials()
    return bool(url and token)


def _turso_http_base(url: str) -> str:
    base = url.strip().rstrip("/")
    if base.startswith("libsql://"):
        base = "https://" + base[len("libsql://") :]
    elif base.startswith("wss://"):
        base = "https://" + base[len("wss://") :]
    elif base.startswith("ws://"):
        base = "http://" + base[len("ws://") :]
    return base


def _to_hrana_arg(value):
    if value is None:
        return {"type": "null"}
    if isinstance(value, bool):
        return {"type": "integer", "value": "1" if value else "0"}
    if isinstance(value, int):
        return {"type": "integer", "value": str(value)}
    if isinstance(value, float):
        return {"type": "float", "value": value}
    return {"type": "text", "value": str(value)}


def _from_hrana_value(cell):
    if cell is None:
        return None
    kind = cell.get("type")
    if kind == "null":
        return None
    if kind == "integer":
        raw = cell.get("value")
        return int(raw) if raw is not None else None
    if kind == "float":
        return float(cell.get("value"))
    if kind == "text":
        return cell.get("value")
    if kind == "blob":
        return cell.get("base64")
    return cell.get("value")


class _TursoCursor:
    def __init__(self, conn: "TursoHttpConnection"):
        self._conn = conn
        self._rows: list[tuple] = []
        self._index = 0
        self.description = None
        self.rowcount = -1

    def execute(self, sql, params=None):
        result = self._conn._execute(sql, params or [])
        cols = result.get("cols") or []
        self.description = tuple((c.get("name"), None, None, None, None, None, None) for c in cols)
        self._rows = [
            tuple(_from_hrana_value(cell) for cell in row) for row in (result.get("rows") or [])
        ]
        self._index = 0
        self.rowcount = int(result.get("affected_row_count") or 0)
        return self

    def fetchone(self):
        if self._index >= len(self._rows):
            return None
        row = self._rows[self._index]
        self._index += 1
        return row

    def fetchall(self):
        rows = self._rows[self._index :]
        self._index = len(self._rows)
        return rows

    def close(self):
        return None


class TursoHttpConnection:
    """DB-API-ish connection over Turso SQL-over-HTTP (stable on Streamlit Cloud)."""

    def __init__(self, url: str, token: str):
        self._base = _turso_http_base(url)
        self._token = token.strip()

    def cursor(self):
        return _TursoCursor(self)

    def execute(self, sql, params=None):
        cur = self.cursor()
        return cur.execute(sql, params)

    def commit(self):
        return None

    def close(self):
        return None

    def _execute(self, sql: str, params) -> dict:
        stmt: dict = {"sql": sql}
        if params:
            stmt["args"] = [_to_hrana_arg(p) for p in params]

        payload = {
            "requests": [
                {"type": "execute", "stmt": stmt},
                {"type": "close"},
            ]
        }
        req = urllib.request.Request(
            f"{self._base}/v2/pipeline",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self._token}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                body = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            raise RuntimeError(
                f"Turso HTTP {exc.code}：請確認 Secrets 的 URL/Token 是否正確。"
            ) from None
        except Exception as exc:
            raise RuntimeError(
                f"無法連線 Turso（{type(exc).__name__}）。請確認網路與 Secrets。"
            ) from None

        results = body.get("results") or []
        if not results:
            raise RuntimeError("Turso 回傳空結果。")

        first = results[0]
        if first.get("type") == "error":
            err = first.get("error") or {}
            msg = err.get("message") or "unknown error"
            raise RuntimeError(f"Turso SQL 錯誤：{msg}")

        response = first.get("response") or {}
        if response.get("type") != "execute":
            raise RuntimeError("Turso 回應格式異常。")
        return response.get("result") or {}


def get_connection():
    """回傳 DB-API 連線。本機用 SQLite；若設定 Turso 則走 HTTP。"""
    url, token = _turso_credentials()
    if url and token:
        return TursoHttpConnection(url, token)

    db_path = get_db_path()
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    return sqlite3.connect(db_path, check_same_thread=False)


def init_db():
    conn = get_connection()
    conn.execute(_CREATE_TABLE_SQL)
    conn.commit()
    conn.close()


def save_to_db(date_str, etf_code, holdings_list):
    conn = get_connection()
    for code, name, weight, shares in holdings_list:
        conn.execute(
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
    conn.execute("DELETE FROM etf_holdings")
    conn.commit()
    conn.close()


def _read_sql(conn, sql, params=None) -> pd.DataFrame:
    cur = conn.execute(sql, params or [])
    cols = [d[0] for d in (cur.description or [])]
    return pd.DataFrame(cur.fetchall(), columns=cols)


def get_saved_dates(conn, etf_code):
    try:
        df = _read_sql(
            conn,
            "SELECT DISTINCT date FROM etf_holdings WHERE etf_code = ? ORDER BY date ASC",
            [etf_code],
        )
        return df["date"].tolist()
    except Exception:
        return []


def get_all_dates(conn):
    try:
        df = _read_sql(conn, "SELECT DISTINCT date FROM etf_holdings ORDER BY date ASC")
        return df["date"].tolist()
    except Exception:
        return []


def get_holdings(conn, date_str, etf_code):
    return _read_sql(
        conn,
        """
        SELECT stock_code, stock_name, weight, shares
        FROM etf_holdings
        WHERE date = ? AND etf_code = ?
        ORDER BY weight DESC
        """,
        [date_str, etf_code],
    )


def get_holdings_for_dates(conn, etf_code, dates):
    if not dates:
        return pd.DataFrame(columns=["date", "stock_code", "stock_name", "shares", "weight"])
    placeholders = ",".join(["?"] * len(dates))
    params = [etf_code, *dates]
    return _read_sql(
        conn,
        f"""
        SELECT date, stock_code, stock_name, shares, weight
        FROM etf_holdings
        WHERE etf_code = ? AND date IN ({placeholders})
        """,
        params,
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
