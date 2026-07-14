"""Shared visual system for Streamlit pages."""

from __future__ import annotations

import streamlit as st

# Ink + jade: market desk feel, not purple / cream defaults
COLORS = {
    "ink": "#0f2744",
    "ink_soft": "#243b55",
    "jade": "#1f7a5c",
    "jade_deep": "#155a44",
    "mint": "#e8f3ee",
    "sand": "#f4f1ea",
    "paper": "#f7f6f2",
    "line": "#d7ddd8",
    "buy": "#1f7a5c",
    "sell": "#c45c26",
    "muted": "#5c6b7a",
    "danger": "#b42318",
}


def inject_styles() -> None:
    if st.session_state.get("_vibe_styles_injected"):
        return
    st.session_state["_vibe_styles_injected"] = True

    st.markdown(
        f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,560;9..144,700&family=Noto+Sans+TC:wght@400;500;600;700&display=swap');

html, body, [class*="css"] {{
  font-family: "Noto Sans TC", "PingFang TC", "Helvetica Neue", sans-serif;
}}

.stApp {{
  background:
    radial-gradient(1200px 500px at 8% -10%, rgba(31, 122, 92, 0.14), transparent 55%),
    radial-gradient(900px 420px at 92% 0%, rgba(15, 39, 68, 0.10), transparent 50%),
    linear-gradient(180deg, {COLORS["paper"]} 0%, #eef2ef 100%);
  color: {COLORS["ink"]};
}}

[data-testid="stHeader"] {{
  background: rgba(247, 246, 242, 0.72);
  backdrop-filter: blur(10px);
}}

[data-testid="stSidebar"] {{
  background: linear-gradient(180deg, #102a45 0%, #183552 100%);
}}
[data-testid="stSidebar"] * {{
  color: #eef3f7 !important;
}}
[data-testid="stSidebar"] .stCaption, [data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p {{
  color: #c5d0da !important;
}}

.block-container {{
  padding-top: 1.4rem;
  padding-bottom: 3rem;
  max-width: 1180px;
}}

h1, h2, h3, .vibe-brand {{
  font-family: "Fraunces", "Noto Serif TC", Georgia, serif !important;
  letter-spacing: 0.01em;
  color: {COLORS["ink"]} !important;
}}

[data-testid="stMetric"] {{
  background: rgba(255,255,255,0.72);
  border: 1px solid {COLORS["line"]};
  border-radius: 14px;
  padding: 0.75rem 0.9rem;
}}
[data-testid="stMetricValue"] {{
  font-family: "Fraunces", Georgia, serif;
  color: {COLORS["ink"]};
}}
[data-testid="stMetricLabel"] {{
  color: {COLORS["muted"]};
}}

div[data-testid="stTabs"] button[data-baseweb="tab"] {{
  font-weight: 600;
  color: {COLORS["muted"]};
}}
div[data-testid="stTabs"] button[aria-selected="true"] {{
  color: {COLORS["jade_deep"]} !important;
}}

.stButton > button[kind="primary"], .stButton > button[data-testid="baseButton-primary"] {{
  background: linear-gradient(135deg, {COLORS["jade"]} 0%, {COLORS["jade_deep"]} 100%);
  border: none;
  color: white;
  font-weight: 600;
  border-radius: 12px;
  box-shadow: 0 8px 20px rgba(31, 122, 92, 0.22);
}}
.stButton > button[kind="secondary"] {{
  border-radius: 12px;
  border: 1px solid {COLORS["line"]};
}}

[data-testid="stFileUploader"] {{
  background: rgba(255,255,255,0.7);
  border: 1px dashed {COLORS["jade"]};
  border-radius: 16px;
  padding: 0.6rem 0.8rem;
}}

.vibe-hero {{
  position: relative;
  overflow: hidden;
  border-radius: 22px;
  padding: 1.55rem 1.7rem 1.4rem;
  margin-bottom: 1.1rem;
  background:
    linear-gradient(135deg, rgba(15,39,68,0.96) 0%, rgba(24,58,84,0.94) 48%, rgba(31,122,92,0.88) 100%);
  color: #f5f8fa;
  box-shadow: 0 18px 40px rgba(15, 39, 68, 0.18);
}}
.vibe-hero::after {{
  content: "";
  position: absolute;
  inset: auto -20% -55% 40%;
  height: 180px;
  background: radial-gradient(circle, rgba(255,255,255,0.16), transparent 65%);
  pointer-events: none;
}}
.vibe-kicker {{
  font-family: "Noto Sans TC", sans-serif;
  font-size: 0.78rem;
  font-weight: 600;
  letter-spacing: 0.14em;
  text-transform: uppercase;
  color: rgba(232, 243, 238, 0.82);
  margin-bottom: 0.45rem;
}}
.vibe-brand {{
  font-size: clamp(1.7rem, 2.4vw, 2.35rem);
  line-height: 1.15;
  margin: 0 0 0.45rem 0;
  color: #fff !important;
}}
.vibe-sub {{
  margin: 0;
  max-width: 42rem;
  color: rgba(235, 242, 246, 0.88);
  font-size: 0.98rem;
  line-height: 1.55;
}}
.vibe-chips {{
  display: flex;
  flex-wrap: wrap;
  gap: 0.45rem;
  margin-top: 1rem;
}}
.vibe-chip {{
  display: inline-flex;
  align-items: center;
  padding: 0.28rem 0.65rem;
  border-radius: 999px;
  background: rgba(255,255,255,0.12);
  border: 1px solid rgba(255,255,255,0.18);
  color: #f3f7f5;
  font-size: 0.8rem;
  font-weight: 500;
}}

.vibe-section {{
  margin: 1.35rem 0 0.65rem;
}}
.vibe-section h3 {{
  margin: 0;
  font-size: 1.28rem;
}}
.vibe-section p {{
  margin: 0.25rem 0 0;
  color: {COLORS["muted"]};
  font-size: 0.92rem;
}}

.vibe-card {{
  background: rgba(255,255,255,0.82);
  border: 1px solid {COLORS["line"]};
  border-radius: 16px;
  padding: 0.95rem 1rem 0.85rem;
  height: 100%;
  box-shadow: 0 10px 24px rgba(15, 39, 68, 0.05);
}}
.vibe-card-code {{
  font-family: "Fraunces", Georgia, serif;
  font-size: 1.15rem;
  font-weight: 700;
  color: {COLORS["ink"]};
  margin: 0;
}}
.vibe-card-name {{
  color: {COLORS["muted"]};
  font-size: 0.82rem;
  margin: 0.15rem 0 0.7rem;
}}
.vibe-card-date {{
  font-size: 0.78rem;
  color: {COLORS["muted"]};
  margin-bottom: 0.15rem;
}}
.vibe-card-stat {{
  font-family: "Fraunces", Georgia, serif;
  font-size: 1.55rem;
  font-weight: 700;
  color: {COLORS["ink"]};
  line-height: 1.1;
}}
.vibe-card-stat span {{
  font-size: 0.85rem;
  font-weight: 500;
  color: {COLORS["muted"]};
  margin-left: 0.25rem;
}}
.vibe-pill-row {{
  display: flex;
  gap: 0.4rem;
  margin-top: 0.7rem;
  flex-wrap: wrap;
}}
.vibe-pill {{
  font-size: 0.75rem;
  font-weight: 600;
  padding: 0.22rem 0.55rem;
  border-radius: 999px;
}}
.vibe-pill-buy {{
  background: {COLORS["mint"]};
  color: {COLORS["jade_deep"]};
}}
.vibe-pill-sell {{
  background: #f8ebe3;
  color: {COLORS["sell"]};
}}
.vibe-pill-muted {{
  background: #eef1f4;
  color: {COLORS["muted"]};
}}
.vibe-card-note {{
  margin-top: 0.65rem;
  font-size: 0.78rem;
  color: {COLORS["ink_soft"]};
  line-height: 1.4;
}}
.vibe-empty {{
  color: {COLORS["danger"]};
  font-weight: 600;
  font-size: 0.9rem;
}}

.vibe-name-grid {{
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 0.65rem;
  margin: 0.4rem 0 0.8rem;
}}
@media (max-width: 900px) {{
  .vibe-name-grid {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
}}
.vibe-name-card {{
  background: rgba(255,255,255,0.85);
  border: 1px solid {COLORS["line"]};
  border-radius: 14px;
  padding: 0.75rem 0.8rem;
}}
.vibe-name-card code {{
  font-size: 0.95rem;
  font-weight: 700;
  color: {COLORS["jade_deep"]};
  background: {COLORS["mint"]};
  padding: 0.15rem 0.4rem;
  border-radius: 6px;
}}
.vibe-name-card small {{
  display: block;
  margin-top: 0.35rem;
  color: {COLORS["muted"]};
}}
</style>
        """,
        unsafe_allow_html=True,
    )


def render_hero(
    brand: str,
    subtitle: str,
    *,
    kicker: str = "Active ETF Desk",
    chips: list[str] | None = None,
) -> None:
    chip_html = ""
    if chips:
        chip_html = (
            '<div class="vibe-chips">'
            + "".join(f'<span class="vibe-chip">{c}</span>' for c in chips)
            + "</div>"
        )
    st.markdown(
        f"""
<div class="vibe-hero">
  <div class="vibe-kicker">{kicker}</div>
  <h1 class="vibe-brand">{brand}</h1>
  <p class="vibe-sub">{subtitle}</p>
  {chip_html}
</div>
        """,
        unsafe_allow_html=True,
    )


def render_section(title: str, caption: str = "") -> None:
    cap = f"<p>{caption}</p>" if caption else ""
    st.markdown(
        f'<div class="vibe-section"><h3>{title}</h3>{cap}</div>',
        unsafe_allow_html=True,
    )


def render_etf_status_card(
    code: str,
    name: str,
    *,
    latest_date: str | None = None,
    change_count: int | None = None,
    add_count: int | None = None,
    reduce_count: int | None = None,
    top_buy: str | None = None,
    top_sell: str | None = None,
    holding_count: int | None = None,
    empty: bool = False,
) -> None:
    if empty:
        body = '<div class="vibe-empty">尚無資料</div>'
    elif change_count is None:
        body = (
            f'<div class="vibe-card-date">{latest_date}</div>'
            f'<div class="vibe-card-stat">{holding_count or 0}<span>檔持股</span></div>'
            f'<div class="vibe-pill-row"><span class="vibe-pill vibe-pill-muted">僅單日資料</span></div>'
        )
    else:
        notes = []
        if top_buy:
            notes.append(f"最大加碼 {top_buy}")
        if top_sell:
            notes.append(f"最大減碼 {top_sell}")
        note_html = (
            f'<div class="vibe-card-note">{" · ".join(notes)}</div>' if notes else ""
        )
        body = (
            f'<div class="vibe-card-date">最新 {latest_date}</div>'
            f'<div class="vibe-card-stat">{change_count}<span>檔異動</span></div>'
            f'<div class="vibe-pill-row">'
            f'<span class="vibe-pill vibe-pill-buy">加碼 {add_count}</span>'
            f'<span class="vibe-pill vibe-pill-sell">減碼 {reduce_count}</span>'
            f"</div>{note_html}"
        )

    st.markdown(
        f"""
<div class="vibe-card">
  <p class="vibe-card-code">{code}</p>
  <p class="vibe-card-name">{name}</p>
  {body}
</div>
        """,
        unsafe_allow_html=True,
    )


def render_filename_cards(items: list[tuple[str, str]]) -> None:
    """items: (stem, caption)"""
    cards = "".join(
        f'<div class="vibe-name-card"><code>{stem}</code><small>{caption}</small></div>'
        for stem, caption in items
    )
    st.markdown(f'<div class="vibe-name-grid">{cards}</div>', unsafe_allow_html=True)


def plotly_layout(**extra):
    base = dict(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(255,255,255,0.55)",
        font=dict(family="Noto Sans TC, sans-serif", color=COLORS["ink"]),
        margin=dict(l=16, r=16, t=48, b=16),
        title=dict(font=dict(family="Fraunces, Georgia, serif", size=16)),
    )
    base.update(extra)
    return base
