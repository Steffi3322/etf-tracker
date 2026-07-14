import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from analysis import summarize_etf_changes
from db import get_holdings, get_saved_dates
from industry import attach_industry
from ui import CHART_PALETTE, COLORS, plotly_layout, render_section


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


def _open_etf_detail(code: str, name: str) -> None:
    """從總覽卡片跳到單檔分析。"""
    st.session_state["view_etf_select"] = f"{code} {name}"
    st.session_state["main_nav"] = "單檔分析"
    st.rerun()


def _render_status_cards(summaries):
    """四欄等結構卡片；可點擊進入該檔分析。"""
    cols = st.columns(4, gap="medium")
    for col, (code, info) in zip(cols, summaries.items()):
        summary = info["summary"]
        with col:
            with st.container(border=True):
                st.markdown(f"**{code}**")
                st.caption(info["name"])

                if summary is None:
                    st.error("尚無資料")
                    st.button(
                        "查看分析",
                        key=f"open_{code}",
                        disabled=True,
                        use_container_width=True,
                    )
                    continue

                st.caption(f"最新 {summary['latest_date']}")

                if summary["prev_date"]:
                    st.metric("今日異動", f"{summary['change_count']} 檔")
                    a, b = st.columns(2)
                    a.metric("加碼", summary["add_count"])
                    b.metric("減碼", summary["reduce_count"])
                    if summary["top_buy"]:
                        st.caption(
                            f"最大加碼 {summary['top_buy']['name']} "
                            f"+{summary['top_buy']['lots']:.0f} 張"
                        )
                    else:
                        st.caption("最大加碼 —")
                    if summary["top_sell"]:
                        st.caption(
                            f"最大減碼 {summary['top_sell']['name']} "
                            f"{summary['top_sell']['lots']:.0f} 張"
                        )
                    else:
                        st.caption("最大減碼 —")
                else:
                    st.metric("持股檔數", summary["holding_count"])
                    st.caption("僅單日資料，尚無異動可比對")
                    st.caption(" ")
                    st.caption(" ")

                if st.button(
                    "查看分析 →",
                    key=f"open_{code}",
                    use_container_width=True,
                    type="secondary",
                ):
                    _open_etf_detail(code, info["name"])


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
        title=f"{code} 持股權重 Top 20（{summary['latest_date']}）",
    )
    fig.update_traces(
        textinfo="label+percent parent",
        marker=dict(line=dict(width=1, color="rgba(255,255,255,0.85)")),
    )
    fig.update_layout(height=420, margin=dict(l=10, r=10, t=48, b=10))
    st.plotly_chart(fig, use_container_width=True)


def _render_industry_donut(conn, summaries, supported_etfs):
    """最新交易日產業權重甜甜圈圖（右側圖例顯示百分比）。"""
    options = {
        f"{code} {info['name']}": code
        for code, info in summaries.items()
        if info["summary"] is not None
    }
    if not options:
        return

    selected = st.selectbox(
        "選擇 ETF 檢視產業配置", list(options.keys()), key="dash_industry_etf"
    )
    code = options[selected]
    latest = summaries[code]["summary"]["latest_date"]
    holdings = get_holdings(conn, latest, code)
    if holdings.empty:
        return

    df_ind = attach_industry(holdings)
    weights = (
        df_ind.groupby("industry", as_index=False)["weight"]
        .sum()
        .sort_values("weight", ascending=False)
    )
    # 過小產業合併，避免圖例過長
    major = weights[weights["weight"] >= 0.5].copy()
    other = weights[weights["weight"] < 0.5]["weight"].sum()
    if other > 0:
        major = pd.concat(
            [major, pd.DataFrame([{"industry": "其他（合計）", "weight": other}])],
            ignore_index=True,
        )

    labels = major["industry"].tolist()
    values = major["weight"].tolist()
    colors = [CHART_PALETTE[i % len(CHART_PALETTE)] for i in range(len(labels))]
    legend_text = [f"{lab}    {val:.2f}%" for lab, val in zip(labels, values)]

    fig = go.Figure(
        data=[
            go.Pie(
                labels=legend_text,
                values=values,
                hole=0.62,
                sort=False,
                direction="clockwise",
                marker=dict(colors=colors, line=dict(color="#ffffff", width=2)),
                textinfo="none",
                hovertemplate="%{label}<extra></extra>",
                showlegend=True,
            )
        ]
    )
    fig.update_layout(
        **plotly_layout(
            title=f"{code} 產業配置（{latest}）",
            height=460,
            margin=dict(l=10, r=10, t=56, b=10),
            showlegend=True,
            legend=dict(
                orientation="v",
                yanchor="middle",
                y=0.5,
                xanchor="left",
                x=1.02,
                font=dict(size=13, color=COLORS["ink"]),
                bgcolor="rgba(0,0,0,0)",
                traceorder="normal",
            ),
            annotations=[
                dict(
                    text=f"<b>{code}</b><br><span style='font-size:12px;color:#6b7a88'>產業配置</span>",
                    x=0.5,
                    y=0.5,
                    xref="paper",
                    yref="paper",
                    showarrow=False,
                    font=dict(size=15, color=COLORS["ink"], family="Fraunces, Georgia, serif"),
                )
            ],
        )
    )
    # 讓甜甜圈偏左，右側留給圖例
    fig.update_traces(domain=dict(x=[0.0, 0.55], y=[0.05, 0.95]))
    st.plotly_chart(fig, use_container_width=True)
    st.caption("依上市櫃產業別加總最新持股權重；淡色區段為主要配置，右側為產業與占比。")


def render_dashboard(conn, supported_etfs):
    render_section("四檔操盤總覽", "點卡片下方「查看分析」可進入該檔詳情。")

    if not _has_any_data(conn, supported_etfs):
        st.info("尚無任何 ETF 資料。請由管理員上傳持股明細。")
        return

    summaries = _collect_all_summaries(conn, supported_etfs)
    _render_status_cards(summaries)

    render_section("最新異動明細", "四檔合併檢視。")
    _render_cross_etf_table(summaries)

    chart_col1, chart_col2 = st.columns(2)
    with chart_col1:
        render_section("加減碼排行")
        _render_change_bar_chart(summaries)
    with chart_col2:
        render_section("持股權重結構")
        _render_treemap(conn, summaries, supported_etfs)

    render_section("產業分析", "最新交易日產業配置占比。")
    _render_industry_donut(conn, summaries, supported_etfs)
