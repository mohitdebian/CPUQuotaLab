#!/usr/bin/env python3
"""Build the editable Markdown paper source into a two-column PDF."""

from __future__ import annotations

from html import escape
from pathlib import Path
import re

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import BaseDocTemplate, Frame, FrameBreak, Image, PageBreak, PageTemplate, Paragraph, Spacer


ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "CPUQuotaLab_Preliminary_Paper.md"
OUTPUT = ROOT / "CPUQuotaLab_Preliminary_Paper.pdf"


def clean(text: str) -> str:
    text = text.replace("**", "").replace("`", "")
    return escape(text)


def header_footer(canvas, doc) -> None:
    canvas.saveState()
    canvas.setStrokeColor(colors.HexColor("#A0A0A0")); canvas.setLineWidth(0.4)
    canvas.line(0.62 * inch, 0.48 * inch, 7.88 * inch, 0.48 * inch)
    canvas.setFont("Helvetica", 7.5); canvas.setFillColor(colors.HexColor("#555555"))
    canvas.drawString(0.62 * inch, 0.30 * inch, "CPUQuotaLab - preliminary independent research")
    canvas.drawRightString(7.88 * inch, 0.30 * inch, str(doc.page))
    canvas.restoreState()


def parse_source(styles: dict[str, ParagraphStyle]) -> list:
    lines = SOURCE.read_text().splitlines()
    title = lines[0][2:]
    author = next(line.split(":", 1)[1].strip() for line in lines if line.startswith("Author:"))
    status = next(line.split(":", 1)[1].strip() for line in lines if line.startswith("Status:"))
    abstract_start = lines.index("## Abstract") + 1
    abstract_parts = []
    index = abstract_start
    while index < len(lines) and not lines[index].startswith("## "):
        if lines[index].strip(): abstract_parts.append(lines[index].strip())
        index += 1
    story = [Paragraph(clean(title), styles["title"]), Paragraph(clean(author), styles["author"]),
             Paragraph(clean(status), styles["status"]), Spacer(1, 5),
             Paragraph("Abstract", styles["abstract_head"]), Paragraph(clean(" ".join(abstract_parts)), styles["abstract"]), FrameBreak()]
    paragraph: list[str] = []
    current_style = "body"

    def flush() -> None:
        if paragraph:
            story.append(Paragraph(clean(" ".join(paragraph)), styles[current_style])); paragraph.clear()

    for line in lines[index:]:
        stripped = line.strip()
        if not stripped:
            flush(); continue
        if stripped.startswith("## "):
            flush()
            heading = stripped[3:]
            story.append(Paragraph(clean(heading), styles["h2"]))
            current_style = "reference" if heading == "References" else "body"
            continue
        if stripped.startswith("### "):
            flush(); story.append(Paragraph(clean(stripped[4:]), styles["h3"])); continue
        if stripped == "[PAGEBREAK]":
            flush(); story.append(PageBreak()); continue
        match = re.fullmatch(r"\[FIGURE:(.+?)\|(.+)\]", stripped)
        if match:
            flush(); path, caption = match.groups(); image = Image(str(ROOT / path))
            max_width, max_height = 3.38 * inch, 2.35 * inch
            scale = min(max_width / image.imageWidth, max_height / image.imageHeight)
            image.drawWidth = image.imageWidth * scale; image.drawHeight = image.imageHeight * scale
            story.extend([Spacer(1, 3), image, Paragraph(clean(caption), styles["caption"]), Spacer(1, 3)]); continue
        paragraph.append(stripped)
    flush()
    return story


def main() -> int:
    page_width, page_height = letter
    margin, gap, footer = 0.58 * inch, 0.22 * inch, 0.56 * inch
    column_width = (page_width - 2 * margin - gap) / 2
    styles_raw = getSampleStyleSheet()
    styles = {
        "title": ParagraphStyle("Title", parent=styles_raw["Title"], fontName="Helvetica-Bold", fontSize=16, leading=18, alignment=TA_CENTER, spaceAfter=5),
        "author": ParagraphStyle("Author", parent=styles_raw["Normal"], fontName="Helvetica-Bold", fontSize=10, leading=12, alignment=TA_CENTER),
        "status": ParagraphStyle("Status", parent=styles_raw["Normal"], fontName="Times-Italic", textColor=colors.HexColor("#555555"), fontSize=8, leading=10, alignment=TA_CENTER),
        "abstract_head": ParagraphStyle("AbstractHead", parent=styles_raw["Heading2"], fontName="Helvetica-Bold", fontSize=9, leading=10, alignment=TA_CENTER, spaceAfter=2),
        "abstract": ParagraphStyle("Abstract", parent=styles_raw["Normal"], fontName="Helvetica", fontSize=8.7, leading=10.4, alignment=TA_JUSTIFY),
        "h2": ParagraphStyle("H2", parent=styles_raw["Heading2"], fontName="Helvetica-Bold", fontSize=9.9, leading=11.4, spaceBefore=5.5, spaceAfter=2.5, keepWithNext=True),
        "h3": ParagraphStyle("H3", parent=styles_raw["Heading3"], fontName="Helvetica-Bold", fontSize=9.2, leading=10.7, spaceBefore=4.5, spaceAfter=2, keepWithNext=True),
        "body": ParagraphStyle("Body", parent=styles_raw["BodyText"], fontName="Times-Roman", fontSize=9.2, leading=11.0, alignment=TA_JUSTIFY, spaceAfter=3.5),
        "reference": ParagraphStyle("Reference", parent=styles_raw["BodyText"], fontName="Times-Roman", fontSize=7.8, leading=9.0, alignment=TA_LEFT, spaceAfter=2.5),
        "caption": ParagraphStyle("Caption", parent=styles_raw["Normal"], fontName="Times-Italic", fontSize=7.8, leading=9.0, alignment=TA_JUSTIFY),
    }
    title_height = 2.05 * inch
    title_frame = Frame(margin, page_height - margin - title_height, page_width - 2 * margin, title_height, leftPadding=3, rightPadding=3, topPadding=3, bottomPadding=3, id="title")
    body_height_first = page_height - margin - footer - title_height
    first_left = Frame(margin, footer, column_width, body_height_first, leftPadding=2, rightPadding=2, topPadding=3, bottomPadding=2, id="first-left")
    first_right = Frame(margin + column_width + gap, footer, column_width, body_height_first, leftPadding=2, rightPadding=2, topPadding=3, bottomPadding=2, id="first-right")
    full_height = page_height - margin - footer
    left = Frame(margin, footer, column_width, full_height, leftPadding=2, rightPadding=2, topPadding=3, bottomPadding=2, id="left")
    right = Frame(margin + column_width + gap, footer, column_width, full_height, leftPadding=2, rightPadding=2, topPadding=3, bottomPadding=2, id="right")
    doc = BaseDocTemplate(str(OUTPUT), pagesize=letter, leftMargin=margin, rightMargin=margin, topMargin=margin, bottomMargin=footer,
                          title="Beyond Core Counts", author="Mohit Singh", subject="CPUQuotaLab preliminary research")
    doc.addPageTemplates([PageTemplate(id="First", frames=[title_frame, first_left, first_right], onPage=header_footer, autoNextPageTemplate="Later"),
                          PageTemplate(id="Later", frames=[left, right], onPage=header_footer)])
    doc.build(parse_source(styles))
    print(OUTPUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
