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

render_hero(
    "主動式 ETF 盤後追蹤",
    "公開唯讀儀表板，掌握四檔主動 ETF 持股異動、跨檔加碼與權重結構。",
    kicker="Taiwan Active ETF Desk",
    chips=[f"{c} {n}" for c, n in SUPPORTED_ETFS.items()],
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

conn = get_connection()
tab_dashboard, tab_detail = st.tabs(["四檔總覽", "單檔分析"])

with tab_dashboard:
    render_dashboard(conn, SUPPORTED_ETFS)

with tab_detail:
    render_detail_analysis(conn)

conn.close()
