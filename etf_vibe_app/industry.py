"""台股代號 → 產業別對照（靜態表，未知則歸「其他」）。"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

_MAP_PATH = Path(__file__).resolve().parent / "industry_map.json"


@lru_cache(maxsize=1)
def _load_map() -> dict[str, dict]:
    if not _MAP_PATH.exists():
        return {}
    return json.loads(_MAP_PATH.read_text(encoding="utf-8"))


def industry_for(stock_code: str) -> str:
    code = str(stock_code).split(".")[0].strip()
    entry = _load_map().get(code)
    if not entry:
        return "其他"
    return entry.get("industry") or "其他"


def attach_industry(df, code_col: str = "stock_code"):
    """在 DataFrame 加上 industry 欄。"""
    out = df.copy()
    out["industry"] = out[code_col].map(industry_for)
    return out
