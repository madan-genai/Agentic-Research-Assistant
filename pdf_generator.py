import io
import logging
import re

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import HRFlowable, Paragraph, SimpleDocTemplate, Spacer

logger = logging.getLogger(__name__)


# ── Custom paragraph styles ───────────────────────────────────────────────────
# reportlab comes with default styles (Title, Heading2, Normal, etc.) via
# getSampleStyleSheet(). We extend these with our own custom styles.

def _build_styles() -> dict:
    """
    Build and return a dict of paragraph styles for the report PDF.
    We extend the default stylesheet with custom colors and sizes.
    """
    base = getSampleStyleSheet()

    styles = {
        # Big title at the top (the research topic)
        "title": ParagraphStyle(
            name="ReportTitle",
            parent=base["Title"],
            fontSize=22,
            textColor=colors.HexColor("#1a1a2e"),   # dark navy
            spaceAfter=12,
        ),

        # ## Section headings
        "h2": ParagraphStyle(
            name="ReportH2",
            parent=base["Heading2"],
            fontSize=14,
            textColor=colors.HexColor("#16213e"),   # slightly lighter navy
            spaceBefore=16,
            spaceAfter=6,
            borderPadding=(0, 0, 4, 0),
        ),

        # ### Sub-headings
        "h3": ParagraphStyle(
            name="ReportH3",
            parent=base["Heading3"],
            fontSize=12,
            textColor=colors.HexColor("#0f3460"),   # medium blue
            spaceBefore=10,
            spaceAfter=4,
        ),

        # Regular body text
        "body": ParagraphStyle(
            name="ReportBody",
            parent=base["Normal"],
            fontSize=10,
            leading=16,          # line height (points) — 16pt feels comfortable to read
            textColor=colors.HexColor("#2d2d2d"),
            spaceAfter=8,
        ),

        # Bullet list items (indented)
        "bullet": ParagraphStyle(
            name="ReportBullet",
            parent=base["Normal"],
            fontSize=10,
            leading=15,
            leftIndent=20,       # indent from left margin
            bulletIndent=10,
            textColor=colors.HexColor("#2d2d2d"),
            spaceAfter=4,
        ),

        # Source URLs at the bottom (smaller, blue for links)
        "source_title": ParagraphStyle(
            name="SourceTitle",
            parent=base["Normal"],
            fontSize=10,
            textColor=colors.HexColor("#1a1a2e"),
            spaceBefore=4,
            spaceAfter=2,
        ),
        "source_url": ParagraphStyle(
            name="SourceURL",
            parent=base["Normal"],
            fontSize=9,
            textColor=colors.HexColor("#0066cc"),   # blue, like a link
            spaceAfter=8,
        ),

        # Small label for the sources section heading
        "sources_heading": ParagraphStyle(
            name="SourcesHeading",
            parent=base["Heading2"],
            fontSize=14,
            textColor=colors.HexColor("#16213e"),
            spaceBefore=20,
            spaceAfter=8,
        ),
    }

    return styles

def _convert_inline(text: str) -> str:
    """
    Convert inline markdown to reportlab's HTML-like markup.

    reportlab Paragraph supports a small subset of HTML:
      <b>...</b>  → bold
      <i>...</i>  → italic

    We convert:
      **word**  →  <b>word</b>
      *word*    →  <i>word</i>

    We also escape the `&` character which is special in HTML/XML.
    """
    # Escape & first (must be done before adding any < > tags)
    text = text.replace("&", "&amp;")

    # **bold** → <b>bold</b>
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)

    # *italic* → <i>italic</i>  (must come AFTER bold replacement)
    text = re.sub(r"\*(.+?)\*", r"<i>\1</i>", text)

    return text


# ── Main function ─────────────────────────────────────────────────────────────

def generate_pdf(topic: str, report_md: str, sources: list) -> bytes:
    """
    Convert a markdown research report to a PDF file.

    Args:
        topic      — The research topic (used in page footer)
        report_md  — The full report in markdown format
        sources    — List of source dicts: [{title, url, content_preview}, ...]

    Returns:
        Raw PDF bytes. The caller sends these directly in an HTTP response:
          Response(content=pdf_bytes, media_type="application/pdf")

    Example:
        pdf_bytes = generate_pdf("AI in Healthcare", "# AI in Healthcare\\n...", [...])
        # pdf_bytes is ready to stream to the browser
    """
    # ── Set up the in-memory buffer ───────────────────────────────────────────
    # BytesIO acts exactly like a file, but lives in memory (no disk writes).
    buffer = io.BytesIO()

    # SimpleDocTemplate wires together: the buffer, page size, and margins.
    # A4 = 210mm × 297mm (standard international paper size).
    # Margins are in "points" — we use cm (1 cm ≈ 28 points) for readability.
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=2.5 * cm,
        leftMargin=2.5 * cm,
        topMargin=2.5 * cm,
        bottomMargin=2.5 * cm,
        title=topic,          # Sets the PDF document metadata title
        author="Agentic Researcher — Lecture 19",
    )

    styles = _build_styles()

    # "story" is reportlab's term for the ordered list of content blocks.
    # doc.build(story) renders them top-to-bottom, paginating automatically.
    story = []

    # ── Parse the markdown report line by line ────────────────────────────────
    # We strip out the Sources section from the body because we render
    # sources separately at the bottom using the structured sources list.
    lines = report_md.split("\n")

    # Find where the sources section starts (if LLM included one)
    sources_start_idx = len(lines)
    for i, line in enumerate(lines):
        if line.strip().lower() in ("## sources", "## references", "## 📚 sources"):
            sources_start_idx = i
            break

    # Only process lines before the sources section
    for line in lines[:sources_start_idx]:

        # ── H1 heading ────────────────────────────────────────────────────────
        if line.startswith("# "):
            # Remove the "# " prefix and convert inline markdown
            text = _convert_inline(line[2:].strip())
            story.append(Paragraph(text, styles["title"]))
            # Add a decorative horizontal rule below the title
            story.append(HRFlowable(width="100%", thickness=2, color=colors.HexColor("#1a1a2e")))
            story.append(Spacer(1, 8))

        # ── H2 heading ────────────────────────────────────────────────────────
        elif line.startswith("## "):
            text = _convert_inline(line[3:].strip())
            story.append(Paragraph(text, styles["h2"]))

        # ── H3 heading ────────────────────────────────────────────────────────
        elif line.startswith("### "):
            text = _convert_inline(line[4:].strip())
            story.append(Paragraph(text, styles["h3"]))

        # ── Bullet point ──────────────────────────────────────────────────────
        elif line.startswith("- "):
            text = _convert_inline(line[2:].strip())
            # The bullet character "•" is set via the bulletText argument
            story.append(Paragraph(f"• {text}", styles["bullet"]))

        # ── Numbered list item ────────────────────────────────────────────────
        elif re.match(r"^\d+\.\s", line):
            text = _convert_inline(re.sub(r"^\d+\.\s+", "", line).strip())
            story.append(Paragraph(f"• {text}", styles["bullet"]))

        # ── Empty line → vertical spacer ──────────────────────────────────────
        elif line.strip() == "":
            # Spacer(width, height) — width is ignored for block layouts
            story.append(Spacer(1, 6))

        # ── Normal paragraph ──────────────────────────────────────────────────
        else:
            text = _convert_inline(line.strip())
            if text:  # Skip lines that are empty after stripping
                story.append(Paragraph(text, styles["body"]))

    # ── Sources section ───────────────────────────────────────────────────────
    if sources:
        story.append(Spacer(1, 12))
        story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#cccccc")))
        story.append(Paragraph("Sources", styles["sources_heading"]))

        for i, source in enumerate(sources, start=1):
            title = source.get("title", f"Source {i}")
            url = source.get("url", "")

            # Number + title
            story.append(Paragraph(f"{i}. {_convert_inline(title)}", styles["source_title"]))

            # URL (always plain text — no clickable links in basic reportlab)
            if url:
                story.append(Paragraph(url, styles["source_url"]))

    # ── Build the PDF ─────────────────────────────────────────────────────────
    # doc.build() iterates through the story, places each flowable on the page,
    # and writes the binary PDF data into our BytesIO buffer.
    try:
        doc.build(story)
    except Exception as e:
        logger.error(f"PDF generation failed: {e}", exc_info=True)
        raise

    # Return the raw bytes from the buffer.
    # getvalue() reads everything that was written to the buffer.
    return buffer.getvalue()
