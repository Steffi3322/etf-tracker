"""單檔深度分析 UI（viewer / admin 共用）。"""

import datetime

import pandas as pd
import streamlit as st

from analysis import (
    align_end_date,
    align_inventory_date,
    align_start_date,
    compute_period_diff,
    label_action,
)
from db import SUPPORTED_ETFS, get_holdings, get_holdings_for_dates, get_saved_dates
from ui import render_section


def render_detail_analysis(conn):
    render_section("單檔深度分析", "自訂區間、移動矩陣與原始持股明細。")

    etf_options = [f"{code} {name}" for code, name in SUPPORTED_ETFS.items()]
    # 從總覽點進來時，session_state 已帶好 view_etf_select
    if "view_etf_select" not in st.session_state:
        st.session_state["view_etf_select"] = etf_options[0]
    elif st.session_state["view_etf_select"] not in etf_options:
        st.session_state["view_etf_select"] = etf_options[0]

    selected_view_etf_str = st.selectbox(
        "選擇主動式 ETF", etf_options, key="view_etf_select"
    )
    view_etf_code = selected_view_etf_str.split(" ")[0]
    valid_dates_list = get_saved_dates(conn, view_etf_code)

    if not valid_dates_list:
        st.info(
            f"💡 目前資料庫內尚無 `{selected_view_etf_str}` 的歷史數據。"
            "請由管理員上傳持股明細。"
        )
        return

    tab1, tab2, tab3 = st.tabs(
        [
            "⏳ 區間波段操盤總結",
            "📊 一週操盤大查表 (移動矩陣)",
            "📄 原始持股明細庫存",
        ]
    )

    with tab1:
        st.write("### ⏳ 自訂任意時間段：波段調倉大統整")
        st.caption("預設自動鎖定最新兩個交易日，日曆具備開盤日自動對齊。")

        default_start_dt = datetime.datetime.strptime(valid_dates_list[0], "%Y-%m-%d").date()
        default_end_dt = datetime.datetime.strptime(valid_dates_list[-1], "%Y-%m-%d").date()
        if len(valid_dates_list) >= 2:
            default_start_dt = datetime.datetime.strptime(valid_dates_list[-2], "%Y-%m-%d").date()

        col_start, col_end = st.columns(2)
        with col_start:
            input_start_date = st.date_input(
                "📌 請選擇區間【起點日期】(舊)", default_start_dt, key="p_start_date"
            )
        with col_end:
            input_end_date = st.date_input(
                "📌 請選擇區間【終點日期】(新)", default_end_dt, key="p_end_date"
            )

        start_str = input_start_date.strftime("%Y-%m-%d")
        end_str = input_end_date.strftime("%Y-%m-%d")

        actual_start_str, start_msg = align_start_date(start_str, valid_dates_list)
        actual_end_str, end_msg = align_end_date(end_str, valid_dates_list)
        if start_msg:
            st.warning(f"💡 {start_msg}")
        if end_msg:
            st.warning(f"💡 {end_msg}")

        if actual_start_str == actual_end_str and len(valid_dates_list) >= 2:
            st.error(
                f"❌ 校正後日期重疊，起點 `{actual_start_str}` 未能早於終點 `{actual_end_str}`，請拉開區間。"
            )
        else:
            st.info(f"📊 分析區間：`{actual_start_str}` → `{actual_end_str}`")

            df_start = get_holdings(conn, actual_start_str, view_etf_code).rename(
                columns={"weight": "w_start", "shares": "s_start"}
            )
            df_end = get_holdings(conn, actual_end_str, view_etf_code).rename(
                columns={"weight": "w_end", "shares": "s_end"}
            )
            df_period = compute_period_diff(df_start, df_end)
            df_period = df_period[df_period["區間淨增減(張)"] != 0.0]

            if df_period.empty:
                st.warning("💡 此區間內經理人未調整任何成分股。")
            else:
                df_period["期初持股(張)"] = (df_period["s_start"] / 1000).round(1)
                df_period["期末持股(張)"] = (df_period["s_end"] / 1000).round(1)
                df_period["區間權重變動(%)"] = (df_period["w_end"] - df_period["w_start"]).round(2)
                df_period = df_period.sort_values(by="區間淨增減(張)", ascending=False)
                df_period["動向"] = df_period.apply(label_action, axis=1)

                df_period_show = pd.DataFrame(
                    {
                        "股票代號": df_period["stock_code"],
                        "股票名稱": df_period["股票名稱"],
                        "動向": df_period["動向"],
                        "區間淨增減(張)": df_period["區間淨增減(張)"],
                        "區間權重變動(pt)": df_period["區間權重變動(%)"],
                        f"{actual_start_str}張數": df_period["期初持股(張)"],
                        f"{actual_end_str}張數": df_period["期末持股(張)"],
                        "期初權重(%)": df_period["w_start"].round(2),
                        "期末權重(%)": df_period["w_end"].round(2),
                    }
                )
                df_period_show.index = range(1, len(df_period_show) + 1)
                st.caption("動向＝一眼定性；右側數字為實際張數與權重變化（pt＝百分點）。")
                st.dataframe(
                    df_period_show,
                    use_container_width=True,
                    column_config={
                        "動向": st.column_config.TextColumn(
                            "動向",
                            help="新進／清倉／加碼／減碼（依持股變化事實判斷）",
                            width="small",
                        ),
                        "區間淨增減(張)": st.column_config.NumberColumn(
                            "區間淨增減(張)",
                            format="%+.1f",
                        ),
                        "區間權重變動(pt)": st.column_config.NumberColumn(
                            "區間權重變動(pt)",
                            format="%+.2f",
                        ),
                    },
                )

                csv_period = df_period_show.to_csv(index=False).encode("utf-8-sig")
                st.download_button(
                    f"📥 匯出 {actual_start_str}～{actual_end_str} 精華操作報告",
                    csv_period,
                    f"{view_etf_code}_period_report.csv",
                    "text/csv",
                )

    with tab2:
        st.write("### 📅 一週操盤大查表 (歷史持股張數移動矩陣)")
        st.caption("移動矩陣數字統一為整數張數（千分位、零位小數）。")
        recent_dates = valid_dates_list[-7:]

        if not recent_dates:
            st.info("💡 目前尚無歷史數據。")
        else:
            df_matrix_raw = get_holdings_for_dates(conn, view_etf_code, recent_dates)
            df_matrix_raw["張數_float"] = df_matrix_raw["shares"] / 1000

            df_pivot = (
                df_matrix_raw.pivot(
                    index=["stock_code", "stock_name"], columns="date", values="張數_float"
                )
                .reset_index()
                .fillna(0.0)
            )
            df_pivot.columns.name = None

            time_cols = [col for col in df_pivot.columns if col not in ["stock_code", "stock_name"]]
            for col in time_cols:
                df_pivot[col] = df_pivot[col].apply(lambda x: "{:,.0f}".format(x))

            df_pivot_for_sort = (
                df_matrix_raw.pivot(
                    index=["stock_code", "stock_name"], columns="date", values="張數_float"
                )
                .reset_index()
                .fillna(0.0)
            )
            df_pivot_for_sort.columns.name = None
            latest_date_col = recent_dates[-1]
            df_pivot_for_sort["sort_key"] = df_pivot_for_sort[latest_date_col]

            df_final_merged = pd.merge(
                df_pivot_for_sort[["stock_code", "sort_key"]], df_pivot, on="stock_code", how="right"
            )
            df_matrix_sorted = df_final_merged.sort_values(by="sort_key", ascending=False).drop(
                columns=["sort_key"]
            )
            df_matrix_final = df_matrix_sorted.rename(
                columns={"stock_code": "股票代號", "stock_name": "股票名稱"}
            )
            df_matrix_final.index = range(1, len(df_matrix_final) + 1)

            st.dataframe(df_matrix_final, use_container_width=True, height=500)
            csv_matrix = df_matrix_final.to_csv(index=False).encode("utf-8-sig")
            st.download_button(
                "📥 匯出此核心操盤總覽大表為 CSV",
                csv_matrix,
                f"{view_etf_code}_weekly_matrix.csv",
                "text/csv",
            )

    with tab3:
        st.write("### 📄 完整真實持股明細庫存")
        st.caption("日曆具備開盤交易日自動校正對齊。")

        default_inventory_dt = datetime.datetime.strptime(valid_dates_list[-1], "%Y-%m-%d").date()
        input_inv_date = st.date_input(
            "📅 請選擇要檢視原始持股庫存的日期", default_inventory_dt, key="p_inv_date"
        )
        inv_date_str = input_inv_date.strftime("%Y-%m-%d")

        actual_inv_str, inv_msg = align_inventory_date(inv_date_str, valid_dates_list)
        if inv_msg:
            st.warning(f"💡 {inv_msg}")

        st.write(f"#### 📅 {actual_inv_str} 當日完整持股庫存清單")

        df_raw_tab3 = get_holdings(conn, actual_inv_str, view_etf_code)
        df_raw_tab3 = df_raw_tab3.rename(
            columns={
                "stock_code": "股票代號",
                "stock_name": "股票名稱",
                "weight": "持股權重(%)",
            }
        )
        df_raw_tab3["持股張數"] = (df_raw_tab3["shares"] / 1000).round(1)
        df_raw_tab3 = df_raw_tab3[["股票代號", "股票名稱", "持股權重(%)", "持股張數"]]
        df_raw_tab3.index = range(1, len(df_raw_tab3) + 1)

        st.dataframe(df_raw_tab3, use_container_width=True)

        csv_tab3 = df_raw_tab3.to_csv(index=False).encode("utf-8-sig")
        st.download_button(
            "📥 下載此日數據為 CSV",
            csv_tab3,
            f"{view_etf_code}_holdings_{actual_inv_str}.csv",
            "text/csv",
        )
