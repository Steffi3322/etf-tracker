"""將 DataFrame 匯出為支援繁中的 PDF。"""

from __future__ import annotations

from io import BytesIO

import pandas as pd
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

# Adobe 內建繁中明體（無需另附 TTF；reportlab CID）
_FONT = "MSung-Light"
_font_ready = False


def _ensure_font() -> None:
    global _font_ready
    if _font_ready:
        return
    pdfmetrics.registerFont(UnicodeCIDFont(_FONT))
    _font_ready = True


def dataframe_to_pdf(
    df: pd.DataFrame,
    *,
    title: str,
    subtitle: str = "",
    landscape_mode: bool = False,
) -> bytes:
    """回傳 PDF bytes；欄位多時建議 landscape_mode=True。"""
    _ensure_font()
    buf = BytesIO()
    pagesize = landscape(A4) if landscape_mode else A4
    doc = SimpleDocTemplate(
        buf,
        pagesize=pagesize,
        leftMargin=10 * mm,
        rightMargin=10 * mm,
        topMargin=12 * mm,
        bottomMargin=12 * mm,
    )

    title_style = ParagraphStyle(
        "pdf_title",
        fontName=_FONT,
        fontSize=13,
        leading=18,
        textColor=colors.HexColor("#243447"),
        spaceAfter=4,
    )
    sub_style = ParagraphStyle(
        "pdf_sub",
        fontName=_FONT,
        fontSize=9,
        leading=12,
        textColor=colors.HexColor("#6b7a88"),
        spaceAfter=8,
    )

    story: list = [Paragraph(title.replace("\n", "<br/>"), title_style)]
    if subtitle:
        story.append(Paragraph(subtitle.replace("\n", "<br/>"), sub_style))
    else:
        story.append(Spacer(1, 4))

    if df is None or df.empty:
        empty_style = ParagraphStyle(
            "pdf_empty", fontName=_FONT, fontSize=10, textColor=colors.grey
        )
        story.append(Paragraph("（無資料）", empty_style))
        doc.build(story)
        return buf.getvalue()

    show = df.copy()
    # 索引若不是 0..n-1，一併匯出（例如列號 1..n）
    if list(show.index) != list(range(len(show))):
        show = show.reset_index()
        if "index" in show.columns:
            show = show.rename(columns={"index": "#"})

    headers = [str(c) for c in show.columns]
    data = [headers]
    for row in show.itertuples(index=False):
        data.append(["" if v is None or (isinstance(v, float) and pd.isna(v)) else str(v) for v in row])

    ncols = len(headers)
    usable = pagesize[0] - 20 * mm
    font_size = 8 if ncols <= 8 else (7 if ncols <= 11 else 6)
    col_widths = [usable / ncols] * ncols

    table = Table(data, colWidths=col_widths, repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (-1, -1), _FONT),
                ("FONTSIZE", (0, 0), (-1, -1), font_size),
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eef2f0")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#243447")),
                ("FONTSIZE", (0, 0), (-1, 0), font_size),
                ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#d5dbd7")),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                (
                    "ROWBACKGROUNDS",
                    (0, 1),
                    (-1, -1),
                    [colors.white, colors.HexColor("#fafaf8")],
                ),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ("LEFTPADDING", (0, 0), (-1, -1), 2),
                ("RIGHTPADDING", (0, 0), (-1, -1), 2),
            ]
        )
    )
    story.append(table)
    doc.build(story)
    return buf.getvalue()
