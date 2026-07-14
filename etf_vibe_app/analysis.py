import pandas as pd


def align_start_date(selected, valid_dates):
    if selected in valid_dates:
        return selected, None
    higher_dates = [d for d in valid_dates if d >= selected]
    if higher_dates:
        actual = higher_dates[0]
        return actual, f"起點 `{selected}` 無資料，已對齊至 `{actual}`"
    actual = valid_dates[0]
    return actual, f"起點 `{selected}` 超出範圍，已重設為 `{actual}`"


def align_end_date(selected, valid_dates):
    if selected in valid_dates:
        return selected, None
    lower_dates = [d for d in valid_dates if d <= selected]
    if lower_dates:
        actual = lower_dates[-1]
        return actual, f"終點 `{selected}` 無資料，已對齊至 `{actual}`"
    actual = valid_dates[-1]
    return actual, f"終點 `{selected}` 超出範圍，已重設為 `{actual}`"


def align_inventory_date(selected, valid_dates):
    if selected in valid_dates:
        return selected, None
    lower_dates = [d for d in valid_dates if d <= selected]
    if lower_dates:
        actual = lower_dates[-1]
        return actual, f"日期 `{selected}` 無資料，已對齊至 `{actual}`"
    actual = valid_dates[-1]
    return actual, f"日期 `{selected}` 超出範圍，已對齊至 `{actual}`"


def label_action(row, diff_col="區間淨增減(張)", start_col="s_start", end_col="s_end", period=False):
    """一眼定性：只描述發生什麼，不臆測經理人策略。"""
    start = float(row[start_col] or 0)
    end = float(row[end_col] or 0)
    diff = float(row[diff_col] or 0)

    if start == 0 and end > 0:
        return "＋ 新進"
    if start > 0 and end == 0:
        return "× 清倉"
    if diff > 0:
        return "▲ 加碼"
    if diff < 0:
        return "▼ 減碼"
    return "－ 持平"


def is_add_action(label: str) -> bool:
    return label in {"▲ 加碼", "＋ 新進", "加碼", "新進"}


def is_cut_action(label: str) -> bool:
    return label in {"▼ 減碼", "× 清倉", "減碼", "清倉"}


def style_action_column(df: pd.DataFrame, col: str = "動向"):
    """為動向欄加上綠／橘底色，方便掃讀。"""

    def _color(val: str) -> str:
        if is_add_action(str(val)):
            return "background-color: #e7f5ee; color: #1f6b4f; font-weight: 700"
        if is_cut_action(str(val)):
            return "background-color: #fbebe3; color: #a85a2a; font-weight: 700"
        return ""

    if col not in df.columns or df.empty:
        return df
    return df.style.map(_color, subset=[col])


def compute_period_diff(df_start, df_end):
    from parser import pick_display_name

    df_period = pd.merge(df_end, df_start, on="stock_code", how="outer")
    df_period["股票名稱"] = [
        pick_display_name([a, b])
        for a, b in zip(
            df_period.get("stock_name_x", pd.Series(dtype=object)),
            df_period.get("stock_name_y", pd.Series(dtype=object)),
        )
    ]
    # 缺名稱時回退代號；避免 float NaN 被 astype(str) 變成字面 "nan"
    df_period["股票名稱"] = df_period["股票名稱"].replace(
        {"": pd.NA, "nan": pd.NA, "None": pd.NA, "NaN": pd.NA}
    )
    df_period["股票名稱"] = (
        df_period["股票名稱"]
        .fillna(df_period["stock_code"])
        .map(lambda x: str(x) if pd.notna(x) else "")
    )
    for col in ("w_start", "w_end", "s_start", "s_end"):
        if col in df_period.columns:
            df_period[col] = pd.to_numeric(df_period[col], errors="coerce").fillna(0)
    df_period["區間淨增減(張)"] = ((df_period["s_end"] - df_period["s_start"]) / 1000).round(1)
    return df_period


def _safe_stock_label(row) -> str:
    name = row.get("股票名稱", "")
    code = str(row.get("stock_code", ""))
    text = str(name).strip()
    if text in ("", "nan", "None", "0", "0.0"):
        return code
    return text


def summarize_etf_changes(conn, etf_code, valid_dates, get_holdings_fn):
    if not valid_dates:
        return None
    latest = valid_dates[-1]
    if len(valid_dates) < 2:
        holdings = get_holdings_fn(conn, latest, etf_code)
        return {
            "latest_date": latest,
            "prev_date": None,
            "holding_count": len(holdings),
            "change_count": 0,
            "add_count": 0,
            "reduce_count": 0,
            "top_buy": None,
            "top_sell": None,
            "changes": pd.DataFrame(),
            "holdings": holdings,
        }

    prev = valid_dates[-2]
    df_start = get_holdings_fn(conn, prev, etf_code).rename(
        columns={"weight": "w_start", "shares": "s_start"}
    )
    df_end = get_holdings_fn(conn, latest, etf_code).rename(
        columns={"weight": "w_end", "shares": "s_end"}
    )
    df_period = compute_period_diff(df_start, df_end)
    changes = df_period[df_period["區間淨增減(張)"] != 0].copy()
    changes["操作"] = changes.apply(label_action, axis=1)

    top_buy = None
    top_sell = None
    if not changes.empty:
        top_buy_row = changes.sort_values("區間淨增減(張)", ascending=False).iloc[0]
        if top_buy_row["區間淨增減(張)"] > 0:
            top_buy = {
                "name": _safe_stock_label(top_buy_row),
                "code": top_buy_row["stock_code"],
                "lots": top_buy_row["區間淨增減(張)"],
            }
        top_sell_row = changes.sort_values("區間淨增減(張)", ascending=True).iloc[0]
        if top_sell_row["區間淨增減(張)"] < 0:
            top_sell = {
                "name": _safe_stock_label(top_sell_row),
                "code": top_sell_row["stock_code"],
                "lots": top_sell_row["區間淨增減(張)"],
            }

    return {
        "latest_date": latest,
        "prev_date": prev,
        "holding_count": len(df_end),
        "change_count": len(changes),
        "add_count": len(changes[changes["區間淨增減(張)"] > 0]),
        "reduce_count": len(changes[changes["區間淨增減(張)"] < 0]),
        "top_buy": top_buy,
        "top_sell": top_sell,
        "changes": changes,
        "holdings": df_end,
    }
