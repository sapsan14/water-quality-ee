from __future__ import annotations

from html import escape
from pathlib import Path

from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, Preformatted, SimpleDocTemplate, Spacer


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "docs" / "report.md"
TARGET = ROOT / "docs" / "report.pdf"

FONT_PATH = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")
FONT_NAME = "DejaVuSans"


def register_font() -> None:
    pdfmetrics.registerFont(TTFont(FONT_NAME, str(FONT_PATH)))


def make_styles():
    styles = getSampleStyleSheet()
    base = ParagraphStyle(
        "Base",
        parent=styles["BodyText"],
        fontName=FONT_NAME,
        fontSize=10.5,
        leading=14,
        alignment=TA_LEFT,
        spaceAfter=4,
    )
    return {
        "body": base,
        "title": ParagraphStyle(
            "TitleRu",
            parent=base,
            fontSize=18,
            leading=22,
            spaceAfter=12,
        ),
        "h1": ParagraphStyle(
            "H1Ru",
            parent=base,
            fontSize=15,
            leading=18,
            spaceBefore=8,
            spaceAfter=6,
        ),
        "h2": ParagraphStyle(
            "H2Ru",
            parent=base,
            fontSize=12.5,
            leading=16,
            spaceBefore=6,
            spaceAfter=4,
        ),
        "bullet": ParagraphStyle(
            "BulletRu",
            parent=base,
            leftIndent=14,
            firstLineIndent=0,
        ),
        "table": ParagraphStyle(
            "TableRu",
            parent=base,
            fontSize=9,
            leading=11,
            leftIndent=6,
        ),
    }


def flush_paragraph(buffer: list[str], story: list, style: ParagraphStyle) -> None:
    if not buffer:
        return
    text = " ".join(part.strip() for part in buffer if part.strip())
    if text:
        story.append(Paragraph(escape(text), style))
    buffer.clear()


def flush_table(buffer: list[str], story: list, style: ParagraphStyle) -> None:
    if not buffer:
        return
    table_text = "\n".join(buffer)
    story.append(Preformatted(table_text, style))
    story.append(Spacer(1, 4))
    buffer.clear()


def render_markdown(md_text: str) -> list:
    styles = make_styles()
    story = []
    paragraph_buffer: list[str] = []
    table_buffer: list[str] = []

    for raw_line in md_text.splitlines():
        line = raw_line.rstrip()

        if line.startswith("|"):
            flush_paragraph(paragraph_buffer, story, styles["body"])
            table_buffer.append(line)
            continue

        flush_table(table_buffer, story, styles["table"])

        if not line.strip():
            flush_paragraph(paragraph_buffer, story, styles["body"])
            story.append(Spacer(1, 4))
            continue

        if line.startswith("# "):
            flush_paragraph(paragraph_buffer, story, styles["body"])
            story.append(Paragraph(escape(line[2:].strip()), styles["title"]))
            continue

        if line.startswith("## "):
            flush_paragraph(paragraph_buffer, story, styles["body"])
            story.append(Paragraph(escape(line[3:].strip()), styles["h1"]))
            continue

        if line.startswith("### "):
            flush_paragraph(paragraph_buffer, story, styles["body"])
            story.append(Paragraph(escape(line[4:].strip()), styles["h2"]))
            continue

        if line.startswith("- "):
            flush_paragraph(paragraph_buffer, story, styles["body"])
            story.append(Paragraph(escape(line[2:].strip()), styles["bullet"], bulletText="•"))
            continue

        paragraph_buffer.append(line)

    flush_table(table_buffer, story, styles["table"])
    flush_paragraph(paragraph_buffer, story, styles["body"])
    return story


def main() -> None:
    register_font()
    doc = SimpleDocTemplate(
        str(TARGET),
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=16 * mm,
        bottomMargin=16 * mm,
        title="Water Quality EE Report",
        author="Anton Sokolov",
    )
    story = render_markdown(SOURCE.read_text(encoding="utf-8"))
    doc.build(story)
    print(f"Built {TARGET}")


if __name__ == "__main__":
    main()
