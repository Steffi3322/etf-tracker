"""將 DataFrame 匯出為支援繁中的 PDF（含加碼／減碼色標）。"""

from __future__ import annotations

from io import BytesIO
from pathlib import Path

import pandas as pd
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

_FONT_NAME = "NotoSansTC"
_FONT_PATH = Path(__file__).resolve().parent / "fonts" / "NotoSansTC-Regular.ttf"
_font_ready = False

# 台股習慣：紅漲（加碼）、綠跌（減碼）
_ADD_BG = colors.HexColor("#fceceb")
_ADD_FG = colors.HexColor("#b53a3a")
_CUT_BG = colors.HexColor("#e7f5ee")
_CUT_FG = colors.HexColor("#1f6b4f")


def _ensure_font() -> str:
    global _font_ready
    if not _font_ready:
        if not _FONT_PATH.exists():
            raise FileNotFoundError(
                f"找不到繁中字型：{_FONT_PATH}。請確認 fonts/NotoSansTC-Regular.ttf 已一併部署。"
            )
        pdfmetrics.registerFont(TTFont(_FONT_NAME, str(_FONT_PATH)))
        _font_ready = True
    return _FONT_NAME


def _cell_text(value) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    return str(value)


def _fmt_number(value) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    try:
        num = float(str(value).replace(",", ""))
    except (TypeError, ValueError):
        return str(value)
    if abs(num - round(num)) < 1e-9:
        return f"{num:,.0f}"
    return f"{num:,.2f}"


def _to_float(value) -> float | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    try:
        return float(str(value).replace(",", ""))
    except (TypeError, ValueError):
        return None


def _column_widths(headers: list[str], usable: float) -> list[float]:
    """名稱欄加寬，日期／數字欄均分其餘空間。"""
    weights = []
    for h in headers:
        if h in {"#", "index"}:
            weights.append(0.65)
        elif h == "股票代號":
            weights.append(1.15)
        elif h in {"股票名稱", "動向"}:
            weights.append(2.6)
        elif isinstance(h, str) and h.startswith("20") and len(h) >= 10:
            weights.append(1.1)
        else:
            weights.append(1.25)
    total = sum(weights) or 1.0
    return [usable * w / total for w in weights]


def dataframe_to_pdf(
    df: pd.DataFrame,
    *,
    title: str,
    subtitle: str = "",
    landscape_mode: bool = False,
    highlight_time_cols: list[str] | None = None,
) -> bytes:
    """回傳 PDF bytes。

    highlight_time_cols: 日期欄位（由左到右），相對前一日加碼＝紅、減碼＝綠。
    這些欄位可為數值或已千分位字串。
    """
    font = _ensure_font()
    buf = BytesIO()
    pagesize = landscape(A4) if landscape_mode else A4
    doc = SimpleDocTemplate(
        buf,
        pagesize=pagesize,
        leftMargin=8 * mm,
        rightMargin=8 * mm,
        topMargin=10 * mm,
        bottomMargin=10 * mm,
    )

    title_style = ParagraphStyle(
        "pdf_title",
        fontName=font,
        fontSize=13,
        leading=17,
        textColor=colors.HexColor("#243447"),
        spaceAfter=3,
    )
    sub_style = ParagraphStyle(
        "pdf_sub",
        fontName=font,
        fontSize=9,
        leading=12,
        textColor=colors.HexColor("#6b7a88"),
        spaceAfter=4,
    )
    legend_style = ParagraphStyle(
        "pdf_legend",
        fontName=font,
        fontSize=8,
        leading=11,
        textColor=colors.HexColor("#6b7a88"),
        spaceAfter=6,
    )
    name_style = ParagraphStyle(
        "pdf_name",
        fontName=font,
        fontSize=7,
        leading=9,
        alignment=TA_LEFT,
        wordWrap="CJK",
    )

    story: list = [Paragraph(title.replace("\n", "<br/>"), title_style)]
    if subtitle:
        story.append(Paragraph(subtitle.replace("\n", "<br/>"), sub_style))
    if highlight_time_cols and len(highlight_time_cols) >= 2:
        story.append(Paragraph("色標: 紅色=加碼(增加) / 綠色=減碼(減少)", legend_style))
    elif not subtitle:
        story.append(Spacer(1, 3))

    if df is None or df.empty:
        empty_style = ParagraphStyle(
            "pdf_empty", fontName=font, fontSize=10, textColor=colors.grey
        )
        story.append(Paragraph("（無資料）", empty_style))
        doc.build(story)
        return buf.getvalue()

    show = df.copy()
    if list(show.index) != list(range(len(show))):
        show = show.reset_index()
        if "index" in show.columns:
            show = show.rename(columns={"index": "#"})

    time_cols = [c for c in (highlight_time_cols or []) if c in show.columns]
    headers = [str(c) for c in show.columns]
    ncols = len(headers)
    font_size = 8 if ncols <= 8 else (7 if ncols <= 11 else 6.5)

    data: list[list] = [headers]
    numeric_rows: list[dict[str, float | None]] = []

    for _, row in show.iterrows():
        nums = {c: _to_float(row[c]) for c in time_cols}
        numeric_rows.append(nums)
        cells: list = []
        for col in show.columns:
            raw = row[col]
            if col in time_cols:
                cells.append(_fmt_number(raw))
            elif col == "股票名稱":
                safe = (
                    _cell_text(raw)
                    .replace("&", "&amp;")
                    .replace("<", "&lt;")
                    .replace(">", "&gt;")
                )
                cells.append(Paragraph(safe, name_style))
            else:
                cells.append(_cell_text(raw))
        data.append(cells)

    usable = pagesize[0] - 16 * mm
    col_widths = _column_widths(headers, usable)

    table = Table(data, colWidths=col_widths, repeatRows=1)
    style_cmds: list = [
        ("FONTNAME", (0, 0), (-1, -1), font),
        ("FONTSIZE", (0, 0), (-1, -1), font_size),
        ("FONTSIZE", (0, 0), (-1, 0), font_size),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eef2f0")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#243447")),
        ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#d5dbd7")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        (
            "ROWBACKGROUNDS",
            (0, 1),
            (-1, -1),
            [colors.white, colors.HexColor("#fafaf8")],
        ),
        ("TOPPADDING", (0, 0), (-1, -1), 2.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5),
        ("LEFTPADDING", (0, 0), (-1, -1), 2),
        ("RIGHTPADDING", (0, 0), (-1, -1), 2),
    ]

    # 股票名稱靠左
    if "股票名稱" in headers:
        name_i = headers.index("股票名稱")
        style_cmds.append(("ALIGN", (name_i, 1), (name_i, -1), "LEFT"))

    # 相對前一日變動上色
    if len(time_cols) >= 2:
        col_index = {name: i for i, name in enumerate(headers)}
        for r_i, nums in enumerate(numeric_rows, start=1):
            for t_i, col in enumerate(time_cols):
                if t_i == 0:
                    continue
                prev_col = time_cols[t_i - 1]
                cur = nums.get(col)
                prev = nums.get(prev_col)
                if cur is None or prev is None:
                    continue
                c_i = col_index[col]
                if cur > prev:
                    style_cmds.append(("BACKGROUND", (c_i, r_i), (c_i, r_i), _ADD_BG))
                    style_cmds.append(("TEXTCOLOR", (c_i, r_i), (c_i, r_i), _ADD_FG))
                    style_cmds.append(("FONTNAME", (c_i, r_i), (c_i, r_i), font))
                elif cur < prev:
                    style_cmds.append(("BACKGROUND", (c_i, r_i), (c_i, r_i), _CUT_BG))
                    style_cmds.append(("TEXTCOLOR", (c_i, r_i), (c_i, r_i), _CUT_FG))
                    style_cmds.append(("FONTNAME", (c_i, r_i), (c_i, r_i), font))

    table.setStyle(TableStyle(style_cmds))
    story.append(table)
    doc.build(story)
    return buf.getvalue()
