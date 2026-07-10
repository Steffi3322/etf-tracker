"""公開唯讀儀表板 — 多人遠端查看入口。"""

import streamlit as st

from dashboard import render_dashboard
from db import SUPPORTED_ETFS, get_connection, init_db, using_turso
from views import render_detail_analysis

st.set_page_config(
    page_title="台灣主動式 ETF 盤後追蹤",
    layout="wide",
    initial_sidebar_state="collapsed",
)
init_db()

st.title("台灣主動式 ETF 操盤動向追蹤")
st.caption("公開唯讀儀表板 · 資料由管理員盤後更新")

with st.sidebar:
    st.markdown("### 關於")
    st.write(
        "追蹤四檔主動 ETF 盤後持股異動："
        + "、".join(f"{c} {n}" for c, n in SUPPORTED_ETFS.items())
    )
    st.caption("資料來源：各投信官網持股明細")
    if using_turso():
        st.success("已連線雲端資料庫")
    else:
        st.info("目前使用本機 SQLite")
    st.markdown("---")
    st.caption("上傳與維護請至「Admin」頁（需密碼）")

conn = get_connection()
tab_dashboard, tab_detail = st.tabs(["四檔總覽儀表板", "單檔深度分析"])

with tab_dashboard:
    render_dashboard(conn, SUPPORTED_ETFS)

with tab_detail:
    render_detail_analysis(conn)

conn.close()
