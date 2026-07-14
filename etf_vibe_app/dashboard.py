import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from analysis import summarize_etf_changes
from db import get_coverage_matrix, get_holdings, get_holdings_for_dates, get_saved_dates
from ui import COLORS, plotly_layout, render_etf_status_card, render_section


def _has_any_data(conn, supported_etfs):
    for code in supported_etfs:
        if get_saved_dates(conn, code):
            return True
    return False


def _collect_all_summaries(conn, supported_etfs):
    summaries = {}
    for code, name in supported_etfs.items():
        dates = get_saved_dates(conn, code)
        summaries[code] = {
            "name": name,
            "dates": dates,
            "summary": summarize_etf_changes(conn, code, dates, get_holdings),
        }
    return summaries


def _render_status_cards(summaries):
    cols = st.columns(4)
    for col, (code, info) in zip(cols, summaries.items()):
        summary = info["summary"]
        with col:
            if summary is None:
                render_etf_status_card(code, info["name"], empty=True)
                continue
            if summary["prev_date"]:
                top_buy = None
                top_sell = None
                if summary["top_buy"]:
                    top_buy = (
                        f"{summary['top_buy']['name']} "
                        f"+{summary['top_buy']['lots']:.0f}張"
                    )
                if summary["top_sell"]:
                    top_sell = (
                        f"{summary['top_sell']['name']} "
                        f"{summary['top_sell']['lots']:.0f}張"
                    )
                render_etf_status_card(
                    code,
                    info["name"],
                    latest_date=summary["latest_date"],
                    change_count=summary["change_count"],
                    add_count=summary["add_count"],
                    reduce_count=summary["reduce_count"],
                    top_buy=top_buy,
                    top_sell=top_sell,
                )
            else:
                render_etf_status_card(
                    code,
                    info["name"],
                    latest_date=summary["latest_date"],
                    holding_count=summary["holding_count"],
                )


def _render_cross_etf_table(summaries):
    rows = []
    for code, info in summaries.items():
        summary = info["summary"]
        if summary is None or summary["changes"].empty:
            continue
        for _, row in summary["changes"].iterrows():
            rows.append(
                {
                    "ETF": code,
                    "股票代號": row["stock_code"],
                    "股票名稱": row["股票名稱"],
                    "操作": row["操作"],
                    "淨增減(張)": row["區間淨增減(張)"],
                    "權重變動(%)": round(row["w_end"] - row["w_start"], 2),
                }
            )
    if not rows:
        st.info("各 ETF 最新區間內無持股異動。")
        return

    df = pd.DataFrame(rows).sort_values("淨增減(張)", ascending=False)
    st.dataframe(df, use_container_width=True, hide_index=True)

    overlap = (
        df[df["淨增減(張)"] > 0]
        .groupby(["股票代號", "股票名稱"])
        .agg(加碼ETF數=("ETF", "nunique"), ETF清單=("ETF", lambda x: "、".join(sorted(x))))
        .reset_index()
    )
    overlap = overlap[overlap["加碼ETF數"] >= 2].sort_values("加碼ETF數", ascending=False)
    if not overlap.empty:
        render_section("多檔同步加碼", "兩檔以上主動 ETF 同日加碼的標的。")
        st.dataframe(overlap, use_container_width=True, hide_index=True)


def _render_change_bar_chart(summaries):
    rows = []
    for code, info in summaries.items():
        summary = info["summary"]
        if summary is None or summary["changes"].empty:
            continue
        for _, row in summary["changes"].iterrows():
            rows.append(
                {
                    "ETF": code,
                    "標籤": f"{row['股票名稱']} ({code})",
                    "淨增減(張)": row["區間淨增減(張)"],
                }
            )
    if not rows:
        return

    df = pd.DataFrame(rows)
    df["顏色"] = df["淨增減(張)"].apply(lambda x: "加碼" if x > 0 else "減碼")
    top = pd.concat(
        [
            df.nlargest(8, "淨增減(張)"),
            df.nsmallest(8, "淨增減(張)"),
        ]
    ).drop_duplicates()
    fig = px.bar(
        top.sort_values("淨增減(張)"),
        x="淨增減(張)",
        y="標籤",
        color="顏色",
        orientation="h",
        color_discrete_map={"加碼": COLORS["buy"], "減碼": COLORS["sell"]},
        title="最新異動 Top 加減碼",
    )
    fig.update_layout(
        **plotly_layout(
            height=420,
            yaxis={"categoryorder": "total ascending"},
            showlegend=False,
        )
    )
    st.plotly_chart(fig, use_container_width=True)


def _render_treemap(conn, summaries, supported_etfs):
    options = {
        f"{code} {info['name']}": code
        for code, info in summaries.items()
        if info["summary"] is not None
    }
    if not options:
        return

    selected = st.selectbox("選擇 ETF 檢視持股權重", list(options.keys()), key="dash_treemap_etf")
    code = options[selected]
    summary = summaries[code]["summary"]
    holdings = get_holdings(conn, summary["latest_date"], code)
    if holdings.empty:
        return

    fig = px.treemap(
        holdings.head(20),
        path=["stock_name"],
        values="weight",
        color="weight",
        color_continuous_scale=["#e8f3ee", "#1f7a5c", "#0f2744"],
        title=f"{code} 持股權重 Top 20（{summary['latest_date']}）",
    )
    fig.update_traces(textinfo="label+percent parent")
    fig.update_layout(**plotly_layout(coloraxis_showscale=False, height=420))
    st.plotly_chart(fig, use_container_width=True)


def _render_heatmap(conn, summaries, supported_etfs):
    """跨日權重變動熱力圖（Δ 百分點），與 Treemap 的「當日權重切面」互補。"""
    options = {
        f"{code} {info['name']}": code
        for code, info in summaries.items()
        if len(info["dates"]) >= 2
    }
    if not options:
        st.info("權重變動熱力圖需要至少兩個交易日資料。")
        return

    selected = st.selectbox(
        "選擇 ETF 檢視權重變動熱力圖", list(options.keys()), key="dash_heatmap_etf"
    )
    code = options[selected]
    dates = summaries[code]["dates"][-7:]
    if len(dates) < 2:
        st.info("此 ETF 資料不足兩個交易日，無法計算權重變動。")
        return

    df_raw = get_holdings_for_dates(conn, code, dates)
    if df_raw.empty:
        return

    weight_pivot = (
        df_raw.pivot_table(
            index="stock_name", columns="date", values="weight", aggfunc="first"
        )
        .reindex(columns=dates)
        .fillna(0.0)
    )
    # 相對前一個有資料交易日的權重變動（百分點）
    delta = weight_pivot.diff(axis=1).iloc[:, 1:]
    change_dates = dates[1:]
    if delta.empty or not change_dates:
        return

    # Top 15：區間內絕對變動總和最大者
    abs_move = delta.abs().sum(axis=1).sort_values(ascending=False)
    top_names = abs_move.head(15).index.tolist()
    delta_top = delta.reindex(index=top_names)
    # 由小到大（底部減碼紅 → 頂部加碼綠）
    cum = delta_top.sum(axis=1)
    name_order = cum.sort_values(ascending=True).index.tolist()
    delta_plot = delta_top.reindex(index=name_order)
    y_labels = [f"{name}  累計{cum[name]:+.2f}pt" for name in name_order]

    zmax = float(delta_plot.abs().to_numpy().max()) if not delta_plot.empty else 1.0
    zmax = max(zmax, 0.1)

    fig = go.Figure(
        data=go.Heatmap(
            z=delta_plot.values,
            x=[str(d) for d in change_dates],
            y=y_labels,
            colorscale=[
                [0.0, COLORS["sell"]],
                [0.5, "#f7f6f2"],
                [1.0, COLORS["buy"]],
            ],
            zmid=0,
            zmin=-zmax,
            zmax=zmax,
            colorbar={
                "title": {"text": "權重變動", "side": "right"},
                "ticksuffix": " pt",
                "thickness": 14,
                "len": 0.9,
            },
            hovertemplate="%{y}<br>相對前一交易日 %{x}<br>權重變動 %{z:+.2f} pt<extra></extra>",
        )
    )
    fig.update_layout(
        **plotly_layout(
            title=f"{code} 權重變動熱力圖（Top 15）",
            height=520,
            margin=dict(l=20, r=90, t=48, b=16),
            xaxis_title="交易日",
            yaxis_title="",
            xaxis={
                "type": "category",
                "categoryorder": "array",
                "categoryarray": [str(d) for d in change_dates],
            },
        )
    )
    st.caption(
        "顏色＝權重變動（百分點，pt），不是張數、也不是當日權重本身。"
        "綠＝相對前一交易日加碼、紅＝減碼；與上方 Treemap（當日權重結構）互補。"
        "左側累計數字為所選區間內每日變動加總。"
    )
    st.plotly_chart(fig, use_container_width=True)


def _render_coverage_calendar(conn, supported_etfs):
    render_section("資料覆蓋日曆", "綠＝已上傳，紅＝缺資料。")
    matrix = get_coverage_matrix(conn, supported_etfs, recent_n=15)
    if matrix.empty:
        return

    date_cols = [c for c in matrix.columns if c != "ETF"]
    z = matrix[date_cols].values
    fig = go.Figure(
        data=go.Heatmap(
            z=z,
            x=date_cols,
            y=matrix["ETF"].tolist(),
            colorscale=[[0, "#c45c26"], [1, COLORS["buy"]]],
            zmin=0,
            zmax=1,
            showscale=False,
            hovertemplate="%{y}<br>%{x}<br>%{customdata}<extra></extra>",
            customdata=[["有資料" if v == 1 else "缺資料" for v in row] for row in z],
            xgap=2,
            ygap=2,
        )
    )
    fig.update_layout(
        **plotly_layout(height=220, margin=dict(l=10, r=10, t=10, b=10), title=None)
    )
    st.plotly_chart(fig, use_container_width=True)

    missing = []
    for _, row in matrix.iterrows():
        gaps = [d for d in date_cols if row[d] == 0]
        if gaps:
            missing.append(f"{row['ETF']}：缺 {len(gaps)} 日（最近缺：{gaps[-1]}）")
    if missing:
        st.warning(" / ".join(missing))
    else:
        st.success("近期待追蹤區間內四檔資料齊全。")


def render_dashboard(conn, supported_etfs):
    render_section("四檔操盤總覽", "最新異動、跨檔加碼與持股結構。")

    if not _has_any_data(conn, supported_etfs):
        st.info("尚無任何 ETF 資料。請由管理員上傳持股明細。")
        return

    summaries = _collect_all_summaries(conn, supported_etfs)
    _render_status_cards(summaries)

    _render_coverage_calendar(conn, supported_etfs)

    render_section("最新異動明細", "四檔合併檢視。")
    _render_cross_etf_table(summaries)

    chart_col1, chart_col2 = st.columns(2)
    with chart_col1:
        render_section("加減碼排行")
        _render_change_bar_chart(summaries)
    with chart_col2:
        render_section("持股權重結構")
        _render_treemap(conn, summaries, supported_etfs)

    render_section("權重變動熱力圖", "相對前一交易日的權重變化（百分點）。")
    _render_heatmap(conn, summaries, supported_etfs)
