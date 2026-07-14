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
        return "新進"
    if start > 0 and end == 0:
        return "清倉"
    if diff > 0:
        return "加碼"
    if diff < 0:
        return "減碼"
    return "持平"


def compute_period_diff(df_start, df_end):
    df_period = pd.merge(df_end, df_start, on="stock_code", how="outer")
    df_period["股票名稱"] = (
        df_period["stock_name_x"]
        .fillna(df_period["stock_name_y"])
        .fillna(df_period["stock_code"])
    )
    df_period = df_period.fillna(0)
    df_period["區間淨增減(張)"] = ((df_period["s_end"] - df_period["s_start"]) / 1000).round(1)
    return df_period


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
        top_buy = {
            "name": top_buy_row["股票名稱"],
            "code": top_buy_row["stock_code"],
            "lots": top_buy_row["區間淨增減(張)"],
        }
        top_sell_row = changes.sort_values("區間淨增減(張)", ascending=True).iloc[0]
        if top_sell_row["區間淨增減(張)"] < 0:
            top_sell = {
                "name": top_sell_row["股票名稱"],
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
