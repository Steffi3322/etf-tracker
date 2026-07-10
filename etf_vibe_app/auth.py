"""簡易密碼驗證（Streamlit secrets / 環境變數）。"""

from __future__ import annotations

import hmac
import os


def _expected_password() -> str | None:
    try:
        import streamlit as st

        if hasattr(st, "secrets") and "ADMIN_PASSWORD" in st.secrets:
            return str(st.secrets["ADMIN_PASSWORD"])
    except Exception:
        pass
    return os.environ.get("ADMIN_PASSWORD")


def require_admin() -> bool:
    """
    在 sidebar 顯示登入表單。通過回傳 True。
    若未設定 ADMIN_PASSWORD，本機開發模式允許進入並顯示警告。
    """
    import streamlit as st

    expected = _expected_password()

    if "admin_authenticated" not in st.session_state:
        st.session_state.admin_authenticated = False

    if st.session_state.admin_authenticated:
        with st.sidebar:
            if st.button("登出管理"):
                st.session_state.admin_authenticated = False
                st.rerun()
        return True

    st.title("🔐 管理後台")
    if not expected:
        st.warning(
            "尚未設定 `ADMIN_PASSWORD`（secrets 或環境變數）。"
            "本機開發模式已開放寫入權限；部署前請務必設定密碼。"
        )
        if st.button("以開發模式進入"):
            st.session_state.admin_authenticated = True
            st.rerun()
        return False

    st.caption("僅管理員可上傳持股明細或維護資料庫。")
    password = st.text_input("管理密碼", type="password")
    if st.button("登入"):
        if hmac.compare_digest(password, expected):
            st.session_state.admin_authenticated = True
            st.rerun()
        st.error("密碼錯誤")
    return False
