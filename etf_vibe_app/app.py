"""公開唯讀儀表板 — 多人遠端查看入口。"""

import streamlit as st

from dashboard import render_dashboard
from db import SUPPORTED_ETFS, get_connection, init_db, using_turso
from ui import inject_styles, render_hero
from views import render_detail_analysis

st.set_page_config(
    page_title="主動式 ETF 盤後追蹤",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="collapsed",
)
inject_styles()
init_db()

# 總覽卡片以 ?etf= / ?chg= 連到單檔分析（須在導覽 widget 建立前處理）
etf_param = st.query_params.get("etf")
chg_param = st.query_params.get("chg")
if etf_param:
    code = etf_param if isinstance(etf_param, str) else str(etf_param)
    if code in SUPPORTED_ETFS:
        st.session_state["view_etf_select"] = f"{code} {SUPPORTED_ETFS[code]}"
        st.session_state["main_nav"] = "單檔分析"
        if chg_param == "add":
            st.session_state["period_chg_filter"] = "加碼"
        elif chg_param == "cut":
            st.session_state["period_chg_filter"] = "減碼"
        else:
            st.session_state["period_chg_filter"] = "全部"
    st.query_params.clear()

render_hero(
    "主動式 ETF 盤後追蹤",
    "公開唯讀儀表板 · 資料由管理員盤後更新",
    kicker="Taiwan Active ETF Desk",
    chips=list(SUPPORTED_ETFS.keys()),
)

with st.sidebar:
    st.markdown("### 關於")
    st.write("追蹤國泰、統一、群益主動 ETF 盤後持股明細。")
    st.caption("資料來源：各投信官網持股明細")
    if using_turso():
        st.markdown("✅ 已連線雲端資料庫")
    else:
        st.markdown("💾 目前使用本機 SQLite")
    st.markdown("---")
    st.caption("上傳與維護請至 Admin（需密碼）")

if "main_nav" not in st.session_state:
    st.session_state.main_nav = "四檔總覽"

nav = st.segmented_control(
    "主畫面",
    options=["四檔總覽", "單檔分析"],
    key="main_nav",
    label_visibility="collapsed",
)

conn = get_connection()
if nav == "單檔分析":
    render_detail_analysis(conn)
else:
    render_dashboard(conn, SUPPORTED_ETFS)
conn.close()
