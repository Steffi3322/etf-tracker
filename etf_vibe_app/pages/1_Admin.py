"""管理後台 — 單檔 / 批次上傳與資料庫維護（需密碼）。"""

from __future__ import annotations

import datetime

import pandas as pd
import streamlit as st

from auth import require_admin
from db import SUPPORTED_ETFS, clear_all_data, init_db, save_to_db, using_turso
from parser import (
    default_trade_date,
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
st.caption("單檔或批次上傳投信持股明細 · 檔名可自動推斷 ETF 與交易日")

if using_turso():
    st.success("已連線雲端資料庫（Turso）")
else:
    st.info("目前寫入本機 SQLite。部署多人查看前請設定 Turso secrets。")

etf_codes = list(SUPPORTED_ETFS.keys())
etf_options = [etf_label(c) for c in etf_codes]

tab_single, tab_batch, tab_maintain = st.tabs(
    ["單檔上傳", "批次上傳", "資料庫維護"]
)


def _render_quality_metrics(quality: dict):
    m1, m2, m3 = st.columns(3)
    m1.metric("成分股數", quality["count"])
    m2.metric("權重加總 (%)", f"{quality['weight_sum']:.2f}")
    m3.metric("權重檢查", "通過" if quality["weight_ok"] else "異常")
    for w in quality["warnings"]:
        st.warning(w)


with tab_single:
    st.subheader("單檔上傳")
    selected_upload_etf_str = st.selectbox("ETF（可被檔名覆寫）", etf_options, key="single_etf")
    default_etf = selected_upload_etf_str.split(" ")[0]

    uploaded_file = st.file_uploader(
        "上傳官方 Excel / CSV",
        type=["csv", "xlsx", "xls"],
        key="single_uploader",
    )

    if uploaded_file is not None:
        try:
            result = parse_holdings_file(uploaded_file, uploaded_file.name, etf_code=None)
            etf_code = result.inferred_etf or default_etf
            trade_dt = default_trade_date(result.inferred_date)

            c1, c2 = st.columns(2)
            with c1:
                etf_idx = etf_codes.index(etf_code) if etf_code in etf_codes else 0
                chosen_etf = st.selectbox(
                    "確認 ETF",
                    etf_options,
                    index=etf_idx,
                    key="single_etf_confirm",
                ).split(" ")[0]
            with c2:
                chosen_date = st.date_input("確認交易日", trade_dt, key="single_date")
                date_str = chosen_date.strftime("%Y-%m-%d")

            if result.sheet_name:
                st.caption(f"分頁：{result.sheet_name} · parser：{result.parser_used}")
            for w in result.warnings:
                st.info(w)
            if result.inferred_date or result.inferred_etf:
                st.success(
                    f"檔名推斷 → ETF `{result.inferred_etf or '—'}` · "
                    f"日期 `{result.inferred_date or '—'}`"
                )

            if not result.holdings:
                st.error("無法從檔案中提取出台股成分股。請確認檔案格式。")
            else:
                quality = validate_holdings(result.holdings)
                df_preview = holdings_to_dataframe(result.holdings)
                _render_quality_metrics(quality)
                st.dataframe(
                    df_preview[["股票代號", "股票名稱", "權重(%)", "預覽張數"]].head(10),
                    use_container_width=True,
                    hide_index=True,
                )

                force = False
                if not quality["weight_ok"]:
                    force = st.checkbox("權重異常仍強制寫入", key="single_force")

                if st.button(
                    "確認寫入資料庫",
                    disabled=not (quality["weight_ok"] or force),
                    type="primary",
                    key="single_save",
                ):
                    save_to_db(date_str, chosen_etf, parse_to_save_rows(result.holdings))
                    st.success(
                        f"已歸檔 `{chosen_etf}` · `{date_str}` · {quality['count']} 檔"
                    )
                    st.rerun()
        except Exception as e:
            st.error(f"解析失敗：{e}")


with tab_batch:
    st.subheader("批次上傳")
    st.caption(
        "一次拖入多個檔案。建議檔名含代號與日期，例如 "
        "`00400A_20260709.xlsx` 或 `國泰動能_2026-07-09.xlsx`。"
    )

    fallback_etf = st.selectbox(
        "檔名無法辨識時的預設 ETF",
        etf_options,
        key="batch_fallback_etf",
    ).split(" ")[0]
    fallback_date = st.date_input(
        "檔名無法辨識時的預設交易日",
        datetime.date.today(),
        key="batch_fallback_date",
    )
    allow_force_all = st.checkbox("允許權重異常的檔案一併寫入", key="batch_force")

    batch_files = st.file_uploader(
        "選擇多個 Excel / CSV",
        type=["csv", "xlsx", "xls"],
        accept_multiple_files=True,
        key="batch_uploader",
    )

    if batch_files:
        rows = []
        parsed_items = []

        for f in batch_files:
            try:
                # Streamlit UploadedFile 可重複讀；保險起見 seek(0)
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
                        "parser": result.parser_used,
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
                        "parser": "—",
                    }
                )
                parsed_items.append(None)

        summary = pd.DataFrame(rows)
        st.dataframe(summary, use_container_width=True, hide_index=True)

        ok_count = sum(1 for r in rows if r["狀態"] == "OK")
        warn_count = sum(1 for r in rows if r["狀態"] == "權重異常")
        fail_count = len(rows) - ok_count - warn_count
        st.write(f"可寫入：{ok_count} · 權重異常：{warn_count} · 失敗：{fail_count}")

        with st.expander("逐檔預覽（前 5 檔成分股）"):
            for item in parsed_items:
                if not item or not item["holdings"]:
                    continue
                st.markdown(f"**{item['file'].name}** → `{item['etf']}` · `{item['date']}`")
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
            and (item["status"] == "OK" or (item["status"] == "權重異常" and allow_force_all))
        ]

        if st.button(
            f"批次寫入 {len(savable)} 筆",
            type="primary",
            disabled=len(savable) == 0,
            key="batch_save",
        ):
            saved = 0
            with st.spinner("批次寫入中…"):
                for item in savable:
                    save_to_db(item["date"], item["etf"], parse_to_save_rows(item["holdings"]))
                    saved += 1
            st.success(f"已寫入 {saved} 筆。")
            st.rerun()


with tab_maintain:
    st.subheader("資料庫維護")
    st.caption("危險操作：清空後無法復原。")
    confirm = st.text_input("若要清空全部資料，請輸入 CLEAR", key="clear_confirm")
    if st.button("清空所有歷史數據", type="secondary", key="clear_btn"):
        if confirm == "CLEAR":
            clear_all_data()
            st.warning("資料庫已清空。")
            st.rerun()
        else:
            st.error("請先在上方輸入 CLEAR 以確認。")
