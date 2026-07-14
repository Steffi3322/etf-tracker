"""持股明細檔案解析、檔名推斷與品質檢查。"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import BinaryIO

import pandas as pd

from db import SUPPORTED_ETFS

WEIGHT_SUM_TOLERANCE = 5.0  # 主動 ETF 常有現金部位，股票權重加總常低於 100%

# 統一檔名：{ETF代號}_{YYYYMMDD}.xlsx  → 自動歸檔到正確 ETF × 交易日
# 例：00400A_20260709.xlsx
_STANDARD_NAME_RE = re.compile(
    r"(?P<code>00400A|00403A|00981A|00992A)[_-](?P<ymd>20\d{6})",
    re.IGNORECASE,
)

# 檔名關鍵字 → ETF 代號（較長關鍵字優先；標準格式優先於關鍵字）
_ETF_FILENAME_HINTS: list[tuple[str, str]] = [
    ("00400A", "00400A"),
    ("00403A", "00403A"),
    ("00981A", "00981A"),
    ("00992A", "00992A"),
    ("國泰動能", "00400A"),
    ("動能高息", "00400A"),
    ("統一升級", "00403A"),
    ("升級50", "00403A"),
    ("台股增長", "00981A"),
    ("統一增長", "00981A"),
    ("群益台灣科技", "00992A"),
    ("科技創新", "00992A"),
]

_ISSUER_BY_ETF = {
    "00400A": "cathay",
    "00403A": "unified",
    "00981A": "unified",
    "00992A": "capital",
}


@dataclass
class ParseResult:
    holdings: list[tuple]
    sheet_name: str | None = None
    inferred_date: str | None = None
    inferred_etf: str | None = None
    issuer: str | None = None
    parser_used: str = "heuristic"
    warnings: list[str] = field(default_factory=list)


def suggested_filename_stem(etf_code: str, trade_date: date | str) -> str:
    """回傳統一檔名（不含副檔名），例如 00400A_20260709。"""
    if isinstance(trade_date, str):
        trade_date = datetime.strptime(trade_date, "%Y-%m-%d").date()
    return f"{etf_code}_{trade_date.strftime('%Y%m%d')}"


def suggested_filename(etf_code: str, trade_date: date | str, ext: str = "xlsx") -> str:
    """回傳統一檔名（含副檔名），例如 00400A_20260709.xlsx。"""
    ext = ext.lstrip(".") or "xlsx"
    return f"{suggested_filename_stem(etf_code, trade_date)}.{ext}"


def parse_standard_filename(filename: str) -> tuple[str | None, str | None]:
    """若符合統一檔名，回傳 (etf_code, YYYY-MM-DD)。"""
    stem = filename.rsplit("/", 1)[-1]
    match = _STANDARD_NAME_RE.search(stem)
    if not match:
        return None, None
    code = match.group("code").upper()
    ymd = match.group("ymd")
    try:
        return code, date(int(ymd[:4]), int(ymd[4:6]), int(ymd[6:8])).isoformat()
    except ValueError:
        return code, None


def infer_date_from_filename(filename: str) -> str | None:
    """從檔名推斷 YYYY-MM-DD。優先統一格式，其次 2026-07-09 / 20260709 等。"""
    _, standard_date = parse_standard_filename(filename)
    if standard_date:
        return standard_date

    stem = filename.rsplit("/", 1)[-1]
    patterns = [
        r"(20\d{2})[-_./](\d{1,2})[-_./](\d{1,2})",
        r"(20\d{2})(\d{2})(\d{2})",
    ]
    for pattern in patterns:
        match = re.search(pattern, stem)
        if not match:
            continue
        y, m, d = int(match.group(1)), int(match.group(2)), int(match.group(3))
        try:
            return date(y, m, d).isoformat()
        except ValueError:
            continue
    return None


def infer_etf_from_filename(filename: str) -> str | None:
    standard_etf, _ = parse_standard_filename(filename)
    if standard_etf:
        return standard_etf

    upper = filename.upper()
    for hint, code in _ETF_FILENAME_HINTS:
        if hint.isascii():
            if hint.upper() in upper:
                return code
        elif hint in filename:
            return code
    return None


def issuer_for_etf(etf_code: str | None) -> str | None:
    if not etf_code:
        return None
    return _ISSUER_BY_ETF.get(etf_code)


def _read_raw_table(uploaded_file: BinaryIO, filename: str) -> tuple[pd.DataFrame, str | None]:
    name = filename.lower()
    if name.endswith(".csv"):
        return pd.read_csv(uploaded_file, header=None).fillna(""), None

    excel_file = pd.ExcelFile(uploaded_file)
    sheet_names = excel_file.sheet_names
    target_sheet = None
    for s in sheet_names:
        if any(k in s for k in ["股", "明細", "清單", "Portfolio", "Sheet", "Table"]):
            target_sheet = s
            break
    if not target_sheet:
        target_sheet = sheet_names[0]

    df_raw = pd.read_excel(uploaded_file, sheet_name=target_sheet, header=None).fillna("")
    return df_raw, target_sheet


def _is_stock_code(val: str) -> bool:
    clean = val.split(".")[0].strip()
    return clean.isdigit() and 4 <= len(clean) <= 5


def _find_header_map(df_raw: pd.DataFrame) -> dict[str, int] | None:
    """若前幾列出現表頭關鍵字，回傳欄位對應。"""
    keywords = {
        "code": ["股票代號", "證券代號", "代號", "股票代碼", "標的代號", "Code"],
        "name": ["股票名稱", "證券名稱", "名稱", "標的名稱", "Name"],
        "weight": ["權重", "持股比重", "比重", "佔比", "Weight", "%"],
        "shares": ["股數", "持股數", "單位數", "張數", "Shares", "數量"],
    }
    for row_idx in range(min(15, len(df_raw))):
        cells = [str(c).strip() for c in df_raw.iloc[row_idx].tolist()]
        mapping: dict[str, int] = {}
        for col_idx, cell in enumerate(cells):
            for field_name, keys in keywords.items():
                if field_name in mapping:
                    continue
                if any(k.lower() in cell.lower() for k in keys if k != "%"):
                    mapping[field_name] = col_idx
                elif field_name == "weight" and cell.strip() in ("%", "％"):
                    mapping[field_name] = col_idx
        if "code" in mapping and ("shares" in mapping or "weight" in mapping):
            mapping["_header_row"] = row_idx
            return mapping
    return None


def _parse_number(val: str) -> float | None:
    clean = str(val).replace("%", "").replace("％", "").replace(",", "").strip()
    if not clean or clean in ("-", "—", "－"):
        return None
    try:
        return float(clean)
    except ValueError:
        return None


def _parse_with_headers(df_raw: pd.DataFrame, header_map: dict[str, int]) -> list[tuple]:
    header_row = header_map["_header_row"]
    holdings: list[tuple] = []
    for row_idx in range(header_row + 1, len(df_raw)):
        cells = [str(c).strip() for c in df_raw.iloc[row_idx].tolist()]
        code_raw = cells[header_map["code"]] if header_map["code"] < len(cells) else ""
        code = code_raw.split(".")[0].strip()
        if not _is_stock_code(code):
            continue

        name = ""
        if "name" in header_map and header_map["name"] < len(cells):
            name = cells[header_map["name"]]
        if not name or "合計" in name or "總計" in name:
            continue

        weight = 0.0
        if "weight" in header_map and header_map["weight"] < len(cells):
            w = _parse_number(cells[header_map["weight"]])
            if w is not None:
                weight = w

        shares = 0
        if "shares" in header_map and header_map["shares"] < len(cells):
            s = _parse_number(cells[header_map["shares"]])
            if s is not None:
                shares = int(s)

        if shares <= 0:
            continue

        holdings.append(_normalize_holding_row(code, name, weight, shares))

    return _dedupe(holdings)


def _parse_heuristic_rows(df_raw: pd.DataFrame) -> list[tuple]:
    parsed_portfolio: list[tuple] = []

    for _, row in df_raw.iterrows():
        row_cells = [str(cell).strip() for cell in row.tolist()]

        for col_idx, cell_val in enumerate(row_cells):
            clean_code = cell_val.split(".")[0].strip()
            if not (clean_code.isdigit() and 4 <= len(clean_code) <= 5):
                continue

            stock_code = clean_code
            stock_name = ""

            for offset in [1, 2, -1]:
                if 0 <= col_idx + offset < len(row_cells):
                    val = row_cells[col_idx + offset]
                    if (
                        val
                        and not val.replace(".", "", 1).isdigit()
                        and len(val) <= 10
                        and "代號" not in val
                        and "碼" not in val
                    ):
                        stock_name = val
                        break

            numbers = []
            for val in row_cells:
                clean_num = val.replace("%", "").replace(",", "").strip()
                try:
                    num_float = float(clean_num)
                    if num_float > 0 and clean_num.split(".")[0] != stock_code:
                        numbers.append(num_float)
                except ValueError:
                    continue

            weight = 0.0
            shares = 0
            if len(numbers) >= 2:
                sorted_nums = sorted(numbers)
                weight = sorted_nums[0]
                shares = int(sorted_nums[-1])
            elif len(numbers) == 1:
                weight = numbers[0]

            if (
                stock_name
                and "合計" not in stock_name
                and "總計" not in stock_name
                and shares > 0
            ):
                parsed_portfolio.append(
                    _normalize_holding_row(stock_code, stock_name, weight, shares)
                )
                break

    return _dedupe(parsed_portfolio)


def _dedupe(holdings: list[tuple]) -> list[tuple]:
    seen = set()
    unique = []
    for item in holdings:
        if item[0] not in seen:
            seen.add(item[0])
            unique.append(item)
    return unique


def normalize_stock_code(code: str | None) -> str:
    """統一股票代號格式。"""
    return str(code or "").split(".")[0].strip()


def normalize_stock_name(name: str | None) -> str:
    """整理名稱空白；保留投信原檔註記（如 國巨*）。"""
    # pandas/numpy 缺值在布林判斷上是 truthy，不可用 `name or ""`
    try:
        if name is None or pd.isna(name):
            return ""
    except (TypeError, ValueError):
        pass
    text = str(name).strip()
    if text.lower() in {"", "nan", "none", "null", "<na>"}:
        return ""
    text = re.sub(r"\s+", "", text)
    return text


def pick_display_name(names) -> str:
    """同代號多個名稱時，優先顯示帶 * 註記的最新名稱。"""
    cleaned = []
    for n in names or []:
        text = normalize_stock_name(n)
        if text:
            cleaned.append(text)
    if not cleaned:
        return ""
    starred = [n for n in cleaned if ("*" in n) or ("＊" in n) or ("※" in n)]
    pool = starred or cleaned
    return pool[-1]


def _normalize_holding_row(code, name, weight, shares) -> tuple:
    return (
        normalize_stock_code(code),
        normalize_stock_name(name),
        weight,
        shares,
    )

def parse_holdings_file(
    uploaded_file: BinaryIO,
    filename: str,
    etf_code: str | None = None,
) -> ParseResult:
    """
    解析投信持股明細。優先表頭對應，失敗則啟發式掃描。
    同時從檔名推斷日期與 ETF。
    """
    inferred_date = infer_date_from_filename(filename)
    inferred_etf = etf_code or infer_etf_from_filename(filename)
    issuer = issuer_for_etf(inferred_etf)
    warnings: list[str] = []

    df_raw, sheet_name = _read_raw_table(uploaded_file, filename)

    header_map = _find_header_map(df_raw)
    holdings: list[tuple] = []
    parser_used = "heuristic"

    if header_map:
        holdings = _parse_with_headers(df_raw, header_map)
        if holdings:
            parser_used = f"header:{issuer or 'generic'}"
        else:
            warnings.append("偵測到表頭但解析為空，改用啟發式掃描。")

    if not holdings:
        holdings = _parse_heuristic_rows(df_raw)
        parser_used = f"heuristic:{issuer or 'generic'}"

    if not inferred_date:
        warnings.append("檔名無法推斷交易日，請手動選擇。")
    if not inferred_etf:
        warnings.append("檔名無法推斷 ETF，請手動選擇。")

    return ParseResult(
        holdings=holdings,
        sheet_name=sheet_name,
        inferred_date=inferred_date,
        inferred_etf=inferred_etf,
        issuer=issuer,
        parser_used=parser_used,
        warnings=warnings,
    )


def validate_holdings(holdings: list[tuple]) -> dict:
    warnings: list[str] = []
    if not holdings:
        return {
            "count": 0,
            "weight_sum": 0.0,
            "weight_ok": False,
            "warnings": ["未解析到任何成分股"],
        }

    weight_sum = sum(h[2] for h in holdings)
    weight_ok = abs(weight_sum - 100.0) <= WEIGHT_SUM_TOLERANCE or (
        90.0 <= weight_sum <= 100.0 + WEIGHT_SUM_TOLERANCE
    )
    if not weight_ok:
        warnings.append(
            f"權重加總為 {weight_sum:.2f}%（偏離合理區間），"
            "請確認是否解析到完整清單或權重欄位是否正確。"
        )
    elif weight_sum < 99.0:
        warnings.append(
            f"權重加總為 {weight_sum:.2f}%（通常因現金／其他資產未列入股票清單）。"
        )

    zero_share = [h[0] for h in holdings if h[3] <= 0]
    if zero_share:
        warnings.append(f"有 {len(zero_share)} 檔股數為 0，已排除或請檢查。")

    return {
        "count": len(holdings),
        "weight_sum": round(weight_sum, 2),
        "weight_ok": weight_ok,
        "warnings": warnings,
    }


def holdings_to_dataframe(holdings: list[tuple]) -> pd.DataFrame:
    df = pd.DataFrame(holdings, columns=["股票代號", "股票名稱", "權重(%)", "總股數"])
    df["預覽張數"] = (df["總股數"] / 1000).round(1)
    return df


def parse_to_save_rows(holdings: list[tuple]) -> list[tuple]:
    df = holdings_to_dataframe(holdings)
    rows = []
    for code, name, weight, shares in df[
        ["股票代號", "股票名稱", "權重(%)", "總股數"]
    ].itertuples(index=False, name=None):
        rows.append(_normalize_holding_row(code, name, weight, shares))
    return rows


def etf_label(code: str) -> str:
    name = SUPPORTED_ETFS.get(code, "")
    return f"{code} {name}".strip()


def default_trade_date(inferred: str | None) -> date:
    if inferred:
        try:
            return datetime.strptime(inferred, "%Y-%m-%d").date()
        except ValueError:
            pass
    return date.today()
