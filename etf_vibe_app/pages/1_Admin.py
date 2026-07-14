"""管理後台 — 上傳持股與資料管理（需密碼）。"""

from __future__ import annotations

import datetime

import pandas as pd
import streamlit as st

from auth import require_admin
from db import (
    SUPPORTED_ETFS,
    clear_all_data,
    delete_snapshot,
    get_coverage_matrix,
    get_connection,
    init_db,
    list_snapshots,
    save_to_db,
    using_turso,
)
from parser import (
    etf_label,
    holdings_to_dataframe,
    parse_holdings_file,
    parse_to_save_rows,
    validate_holdings,
)

st.set_page_config(page_title="ETF 追蹤 · 管理後台", layout="wide")
init_db()

if not require_admin():
    st.stop()

st.title("管理後台")
st.caption("盤後上傳持股明細 · 檔名可自動推斷 ETF 與交易日")

if using_turso():
    st.success("已連線雲端資料庫（Turso）")
else:
    st.info("目前寫入本機 SQLite。部署多人查看前請設定 Turso secrets。")

etf_codes = list(SUPPORTED_ETFS.keys())
etf_options = [etf_label(c) for c in etf_codes]

tab_upload, tab_data = st.tabs(["上傳持股", "資料管理"])


def _render_quality_metrics(quality: dict):
    m1, m2, m3 = st.columns(3)
    m1.metric("成分股數", quality["count"])
    m2.metric("權重加總 (%)", f"{quality['weight_sum']:.2f}")
    m3.metric("權重檢查", "通過" if quality["weight_ok"] else "異常")
    for w in quality["warnings"]:
        st.warning(w)


with tab_upload:
    st.subheader("上傳持股")
    st.caption(
        "可一次拖入 1～多個檔案。建議檔名含代號與日期，例如 "
        "`00400A_20260709.xlsx`。"
    )

    c1, c2, c3 = st.columns(3)
    with c1:
        fallback_etf = st.selectbox(
            "檔名無法辨識時的預設 ETF",
            etf_options,
            key="upload_fallback_etf",
        ).split(" ")[0]
    with c2:
        fallback_date = st.date_input(
            "檔名無法辨識時的預設交易日",
            datetime.date.today(),
            key="upload_fallback_date",
        )
    with c3:
        allow_force = st.checkbox("允許權重異常仍寫入", key="upload_force")

    uploaded_files = st.file_uploader(
        "選擇 Excel / CSV（可多選）",
        type=["csv", "xlsx", "xls"],
        accept_multiple_files=True,
        key="upload_files",
    )

    if uploaded_files:
        rows = []
        parsed_items = []

        for f in uploaded_files:
            try:
                if hasattr(f, "seek"):
                    f.seek(0)
                result = parse_holdings_file(f, f.name)
                etf_code = result.inferred_etf or fallback_etf
                date_str = result.inferred_date or fallback_date.strftime("%Y-%m-%d")
                quality = validate_holdings(result.holdings)
                status = "OK"
                if not result.holdings:
                    status = "解析失敗"
                elif not quality["weight_ok"]:
                    status = "權重異常"

                rows.append(
                    {
                        "檔名": f.name,
                        "ETF": etf_code,
                        "交易日": date_str,
                        "成分股": quality["count"],
                        "權重加總%": quality["weight_sum"],
                        "狀態": status,
                        "來源": (
                            "檔名"
                            if (result.inferred_etf and result.inferred_date)
                            else "檔名+預設"
                            if (result.inferred_etf or result.inferred_date)
                            else "預設值"
                        ),
                    }
                )
                parsed_items.append(
                    {
                        "file": f,
                        "etf": etf_code,
                        "date": date_str,
                        "holdings": result.holdings,
                        "quality": quality,
                        "status": status,
                        "result": result,
                    }
                )
            except Exception as e:
                rows.append(
                    {
                        "檔名": f.name,
                        "ETF": "—",
                        "交易日": "—",
                        "成分股": 0,
                        "權重加總%": 0,
                        "狀態": f"錯誤: {e}",
                        "來源": "—",
                    }
                )
                parsed_items.append(None)

        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

        ok_count = sum(1 for r in rows if r["狀態"] == "OK")
        warn_count = sum(1 for r in rows if r["狀態"] == "權重異常")
        fail_count = len(rows) - ok_count - warn_count
        st.write(f"可寫入：{ok_count} · 權重異常：{warn_count} · 失敗：{fail_count}")

        # 單檔時顯示較完整預覽；多檔用 expander
        if len(parsed_items) == 1 and parsed_items[0] and parsed_items[0]["holdings"]:
            item = parsed_items[0]
            result = item["result"]
            if result.sheet_name:
                st.caption(f"分頁：{result.sheet_name} · parser：{result.parser_used}")
            for w in result.warnings:
                st.info(w)
            _render_quality_metrics(item["quality"])
            df_preview = holdings_to_dataframe(item["holdings"])
            st.dataframe(
                df_preview[["股票代號", "股票名稱", "權重(%)", "預覽張數"]].head(15),
                use_container_width=True,
                hide_index=True,
            )
        else:
            with st.expander("逐檔預覽（前 5 檔成分股）"):
                for item in parsed_items:
                    if not item or not item["holdings"]:
                        continue
                    st.markdown(
                        f"**{item['file'].name}** → `{item['etf']}` · `{item['date']}`"
                    )
                    df = holdings_to_dataframe(item["holdings"])
                    st.dataframe(
                        df[["股票代號", "股票名稱", "權重(%)", "預覽張數"]].head(5),
                        use_container_width=True,
                        hide_index=True,
                    )

        savable = [
            item
            for item in parsed_items
            if item
            and item["holdings"]
            and (item["status"] == "OK" or (item["status"] == "權重異常" and allow_force))
        ]

        if st.button(
            f"確認寫入 {len(savable)} 筆",
            type="primary",
            disabled=len(savable) == 0,
            key="upload_save",
        ):
            saved = 0
            with st.spinner("寫入中…"):
                for item in savable:
                    save_to_db(item["date"], item["etf"], parse_to_save_rows(item["holdings"]))
                    saved += 1
            st.success(f"已寫入 {saved} 筆。公開儀表板會立即反映。")
            st.rerun()


with tab_data:
    st.subheader("資料管理")
    st.caption("查看已歸檔的持股日期；若某日上傳錯了，可刪除後重傳。")

    conn = get_connection()
    snapshots = list_snapshots(conn)
    coverage = get_coverage_matrix(conn, SUPPORTED_ETFS, recent_n=15)
    conn.close()

    if snapshots.empty:
        st.info("目前尚無資料。請先到「上傳持股」匯入明細。")
    else:
        total_days = snapshots["date"].nunique()
        total_files = len(snapshots)
        m1, m2, m3 = st.columns(3)
        m1.metric("已存檔組合", total_files)
        m2.metric("涵蓋交易日", total_days)
        m3.metric("最新日期", snapshots["date"].iloc[0])

        if not coverage.empty:
            st.markdown("#### 近日出勤表")
            st.dataframe(coverage, use_container_width=True, hide_index=True)

        st.markdown("#### 已存檔清單")
        show = snapshots.copy()
        show["ETF"] = show["etf_code"].map(
            lambda c: etf_label(c) if c in SUPPORTED_ETFS else c
        )
        show = show.rename(columns={"date": "交易日", "holdings_count": "成分股數"})
        st.dataframe(
            show[["ETF", "交易日", "成分股數"]],
            use_container_width=True,
            hide_index=True,
        )

        st.markdown("#### 刪除錯誤上傳")
        st.caption("只刪除選定的「某一檔 ETF × 某一天」，不影響其他資料。")
        d1, d2 = st.columns(2)
        with d1:
            del_etf = st.selectbox(
                "ETF",
                etf_options,
                key="delete_etf",
            ).split(" ")[0]
        with d2:
            etf_dates = sorted(
                snapshots.loc[snapshots["etf_code"] == del_etf, "date"].tolist(),
                reverse=True,
            )
            if etf_dates:
                del_date = st.selectbox("交易日", etf_dates, key="delete_date")
            else:
                del_date = None
                st.selectbox("交易日", ["（此 ETF 尚無資料）"], disabled=True)

        if st.button(
            "刪除此筆",
            type="secondary",
            disabled=not del_date,
            key="delete_one",
        ):
            delete_snapshot(del_etf, del_date)
            st.success(f"已刪除 `{del_etf}` · `{del_date}`")
            st.rerun()

    with st.expander("進階：清空全部資料（很少用）"):
        st.warning("會刪除所有 ETF、所有日期，無法復原。日常請改用上方「刪除錯誤上傳」。")
        confirm = st.text_input("若確定要清空，請輸入 CLEAR", key="clear_confirm")
        if st.button("清空所有歷史數據", key="clear_btn"):
            if confirm == "CLEAR":
                clear_all_data()
                st.warning("資料庫已清空。")
                st.rerun()
            else:
                st.error("請先輸入 CLEAR 以確認。")
