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
    parse_standard_filename,
    parse_to_save_rows,
    suggested_filename_stem,
    validate_holdings,
)
from ui import inject_styles, render_hero, render_section

st.set_page_config(page_title="ETF 追蹤 · 管理後台", layout="wide", page_icon="🗂️")
inject_styles()
init_db()

if not require_admin():
    st.stop()


@st.dialog("寫入完成")
def _dialog_save_done(payload: dict):
    st.success(payload.get("title", "寫入完成"))
    detail = payload.get("detail")
    if detail:
        st.write(detail)
    rows = payload.get("rows") or []
    if rows:
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    st.caption("公開儀表板已可查看最新資料。")
    if st.button("知道了", type="primary", key="flash_save_ok"):
        st.session_state.pop("admin_flash", None)
        st.rerun()


@st.dialog("操作完成")
def _dialog_action_done(payload: dict):
    level = payload.get("level", "success")
    msg = payload.get("title", "完成")
    if level == "warning":
        st.warning(msg)
    else:
        st.success(msg)
    if payload.get("detail"):
        st.write(payload["detail"])
    if st.button("知道了", type="primary", key="flash_action_ok"):
        st.session_state.pop("admin_flash", None)
        st.rerun()


def _set_flash(payload: dict):
    st.session_state["admin_flash"] = payload


def _show_flash_if_any():
    flash = st.session_state.get("admin_flash")
    if not flash:
        return
    kind = flash.get("kind")
    if kind == "save":
        st.toast(flash.get("title", "寫入完成"), icon="✅")
        _dialog_save_done(flash)
    elif kind in ("delete", "clear"):
        st.toast(flash.get("title", "操作完成"), icon="✅")
        _dialog_action_done(flash)


db_chip = "雲端資料庫已連線" if using_turso() else "本機 SQLite"
render_hero(
    "管理後台",
    "盤後上傳持股明細；統一檔名即可自動歸檔到正確 ETF 與交易日。",
    kicker="Admin Desk",
    chips=[db_chip, "批量上傳", "資料管理"],
)

_show_flash_if_any()

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
    render_section("上傳持股", "一次拖入單檔或多檔，依檔名自動歸檔。")

    naming_date = st.date_input(
        "建議檔名用的交易日",
        datetime.date.today(),
        key="naming_date",
    )
    render_section(
        "統一檔名",
        "格式 ETF代號_YYYYMMDD（不含副檔名）。點右上角圖示即可複製。",
    )
    name_cols = st.columns(4)
    for col, code in zip(name_cols, etf_codes):
        with col:
            st.code(suggested_filename_stem(code, naming_date), language=None)
            st.caption(SUPPORTED_ETFS[code])
    st.caption("流程：官網下載 → 只改檔名 → 一次拖入 → 確認寫入。")

    with st.expander("檔名無法辨識時的預設值（少用）"):
        c1, c2 = st.columns(2)
        with c1:
            fallback_etf = st.selectbox(
                "預設 ETF",
                etf_options,
                key="upload_fallback_etf",
            ).split(" ")[0]
        with c2:
            fallback_date = st.date_input(
                "預設交易日",
                naming_date,
                key="upload_fallback_date",
            )
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
                std_etf, std_date = parse_standard_filename(f.name)
                etf_code = result.inferred_etf or fallback_etf
                date_str = result.inferred_date or fallback_date.strftime("%Y-%m-%d")
                quality = validate_holdings(result.holdings)
                status = "OK"
                if not result.holdings:
                    status = "解析失敗"
                elif not quality["weight_ok"]:
                    status = "權重異常"

                if std_etf and std_date:
                    source = "統一檔名"
                elif result.inferred_etf and result.inferred_date:
                    source = "檔名推斷"
                elif result.inferred_etf or result.inferred_date:
                    source = "檔名+預設"
                else:
                    source = "預設值"

                rows.append(
                    {
                        "檔名": f.name,
                        "ETF": etf_code,
                        "交易日": date_str,
                        "成分股": quality["count"],
                        "權重加總%": quality["weight_sum"],
                        "狀態": status,
                        "歸檔依據": source,
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
                        "歸檔依據": "—",
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
            saved_rows = []
            with st.spinner("寫入中…"):
                for item in savable:
                    save_to_db(item["date"], item["etf"], parse_to_save_rows(item["holdings"]))
                    saved_rows.append(
                        {
                            "ETF": item["etf"],
                            "交易日": item["date"],
                            "成分股": item["quality"]["count"],
                            "檔名": item["file"].name,
                        }
                    )
            _set_flash(
                {
                    "kind": "save",
                    "title": f"已成功寫入 {len(saved_rows)} 筆",
                    "detail": "下列資料已存入資料庫，儀表板可立即查看。",
                    "rows": saved_rows,
                }
            )
            st.balloons()
            st.rerun()


with tab_data:
    render_section("資料管理", "查看已歸檔日期；錯傳可刪除單日後重傳。")

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
            _set_flash(
                {
                    "kind": "delete",
                    "level": "success",
                    "title": f"已刪除 {del_etf} · {del_date}",
                    "detail": "可回到「上傳持股」重新上傳正確檔案。",
                }
            )
            st.rerun()

    with st.expander("進階：清空全部資料（很少用）"):
        st.warning("會刪除所有 ETF、所有日期，無法復原。日常請改用上方「刪除錯誤上傳」。")
        confirm = st.text_input("若確定要清空，請輸入 CLEAR", key="clear_confirm")
        if st.button("清空所有歷史數據", key="clear_btn"):
            if confirm == "CLEAR":
                clear_all_data()
                _set_flash(
                    {
                        "kind": "clear",
                        "level": "warning",
                        "title": "資料庫已清空",
                        "detail": "所有歷史持股資料都已刪除。",
                    }
                )
                st.rerun()
            else:
                st.error("請先輸入 CLEAR 以確認。")
