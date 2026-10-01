"""Generate synthetic, non-confidential test documents for the POC.

Nothing here is confidential and nothing here is scraped from the real
Company_Bot corpus. Every byte is generated locally so the experiment is
reproducible and safe to send to a hosted VLM.

Only two libraries are used:

* Pillow  -- to *draw* the images. Pillow never parses a document in this POC.
* zipfile -- to write the DOCX container, which is just a ZIP of XML parts.

There is deliberately no python-docx here. Writing the OOXML by hand keeps the
POC honest about the "Docling is the only parser" rule: not even the test-data
generator leans on a second document library.
"""

from __future__ import annotations

import zipfile
from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

# --------------------------------------------------------------------------
# Fonts
# --------------------------------------------------------------------------

_FONT_DIR = Path("C:/Windows/Fonts")
_FONT_CANDIDATES = {
    "regular": ["arial.ttf", "calibri.ttf", "segoeui.ttf", "tahoma.ttf"],
    "bold": ["arialbd.ttf", "calibrib.ttf", "segoeuib.ttf", "tahomabd.ttf"],
    "mono": ["consola.ttf", "cour.ttf", "lucon.ttf"],
}


def _resolve_font(kind: str) -> Path:
    for name in _FONT_CANDIDATES[kind]:
        candidate = _FONT_DIR / name
        if candidate.exists():
            return candidate
    raise FileNotFoundError(f"No usable {kind!r} TrueType font found in {_FONT_DIR}")


_FONT_FILES = {kind: _resolve_font(kind) for kind in _FONT_CANDIDATES}


def font(kind: str, size: int) -> ImageFont.FreeTypeFont:
    """Load a TrueType font. Real fonts matter: OCR accuracy collapses on the
    ~11px bitmap font that PIL falls back to when no font file is given."""
    return ImageFont.truetype(str(_FONT_FILES[kind]), size)


# --------------------------------------------------------------------------
# Drawing helpers
# --------------------------------------------------------------------------

INK = (17, 17, 17)
MUTED = (90, 90, 90)
ACCENT = (26, 86, 150)
LIGHT = (238, 242, 247)
BORDER = (120, 130, 145)


def _arrow(draw: ImageDraw.ImageDraw, start, end, colour=ACCENT, width=5, head=16):
    """A line plus a filled triangular head, so arrows survive both OCR and a
    VLM looking at the rendered image."""
    x0, y0 = start
    x1, y1 = end
    draw.line([(x0, y0), (x1, y1)], fill=colour, width=width)
    dx, dy = x1 - x0, y1 - y0
    length = max((dx * dx + dy * dy) ** 0.5, 1e-6)
    ux, uy = dx / length, dy / length
    px, py = -uy, ux
    base = (x1 - ux * head, y1 - uy * head)
    draw.polygon(
        [
            (x1, y1),
            (base[0] + px * head * 0.55, base[1] + py * head * 0.55),
            (base[0] - px * head * 0.55, base[1] - py * head * 0.55),
        ],
        fill=colour,
    )


def _box(draw: ImageDraw.ImageDraw, rect, title, subtitle="", fill=LIGHT, outline=ACCENT):
    draw.rounded_rectangle(rect, radius=12, fill=fill, outline=outline, width=4)
    cx = (rect[0] + rect[2]) / 2
    title_font = font("bold", 30)
    if subtitle:
        draw.text((cx, rect[1] + 26), title, font=title_font, fill=INK, anchor="ma")
        draw.text((cx, rect[1] + 68), subtitle, font=font("regular", 20), fill=MUTED, anchor="ma")
    else:
        draw.text((cx, (rect[1] + rect[3]) / 2), title, font=title_font, fill=INK, anchor="mm")


# --------------------------------------------------------------------------
# The eight test images
# --------------------------------------------------------------------------


def make_text_card() -> Image.Image:
    """Category 3 -- an image whose only content is plain text.

    Expected route: OCR.
    """
    img = Image.new("RGB", (900, 340), "white")
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, 899, 339], outline=BORDER, width=3)
    d.rectangle([0, 0, 899, 70], fill=LIGHT)
    d.text((450, 35), "EMPLOYEE RECORD", font=font("bold", 34), fill=ACCENT, anchor="mm")
    rows = [
        "Employee ID: EMP001",
        "Department: Engineering",
        "Manager: Priya Raman",
        "Joining Date: 14 April 2026",
    ]
    for index, row in enumerate(rows):
        y = 120 + index * 52
        d.text((50, y), row, font=font("regular", 32), fill=INK)
    return img


def make_screenshot() -> Image.Image:
    """Category 4 -- a UI screenshot. Text-heavy *and* visually meaningful."""
    img = Image.new("RGB", (900, 560), "white")
    d = ImageDraw.Draw(img)
    # window chrome
    d.rectangle([0, 0, 899, 54], fill=(60, 66, 78))
    for index, colour in enumerate([(237, 106, 94), (245, 191, 79), (98, 197, 84)]):
        d.ellipse([22 + index * 30, 18, 40 + index * 30, 36], fill=colour)
    d.text((140, 27), "hr-portal / onboarding / new-hire", font=font("regular", 22), fill="white", anchor="lm")
    # sidebar
    d.rectangle([0, 54, 210, 559], fill=(246, 247, 249))
    for index, item in enumerate(["Dashboard", "Employees", "Onboarding", "Payroll", "Reports"]):
        y = 92 + index * 52
        if item == "Onboarding":
            d.rectangle([10, y - 18, 200, y + 24], fill=(222, 234, 248))
        d.text((32, y), item, font=font("regular", 24), fill=INK, anchor="lm")
    # form
    d.text((250, 100), "New Hire Onboarding", font=font("bold", 30), fill=INK)
    fields = [
        ("Employee ID", "EMP001"),
        ("Full Name", "Ananya Sharma"),
        ("Department", "Engineering"),
        ("Approving Manager", "Priya Raman"),
    ]
    for index, (label, value) in enumerate(fields):
        y = 160 + index * 74
        d.text((250, y), label, font=font("regular", 22), fill=MUTED)
        d.rectangle([250, y + 26, 840, y + 62], outline=BORDER, width=2)
        d.text((264, y + 44), value, font=font("regular", 24), fill=INK, anchor="lm")
    d.rounded_rectangle([690, 470, 840, 520], radius=8, fill=ACCENT)
    d.text((765, 495), "Submit", font=font("bold", 24), fill="white", anchor="mm")
    return img


def make_architecture_diagram() -> Image.Image:
    """Category 5 -- architecture diagram. Relationships live in the arrows, so
    OCR alone loses the meaning. Expected route: VLM."""
    img = Image.new("RGB", (1180, 520), "white")
    d = ImageDraw.Draw(img)
    d.text((40, 34), "Onboarding Platform Architecture", font=font("bold", 34), fill=INK)
    _box(d, (40, 130, 250, 250), "Employee", "browser")
    _box(d, (330, 130, 560, 250), "API Gateway", "auth + routing")
    _box(d, (640, 90, 900, 210), "Onboarding Service", "workflow engine")
    _box(d, (640, 300, 900, 420), "Payroll Service", "salary records")
    _box(d, (980, 195, 1140, 315), "Database", "PostgreSQL")
    _arrow(d, (250, 190), (330, 190))
    _arrow(d, (560, 175), (640, 160))
    _arrow(d, (900, 160), (980, 240))
    _arrow(d, (770, 300), (770, 210))
    d.text((935, 190), "reads / writes", font=font("regular", 20), fill=MUTED, anchor="lm")
    d.text((580, 250), "creates payroll record after approval", font=font("regular", 20), fill=MUTED, anchor="lm")
    return img


def make_flow_diagram() -> Image.Image:
    """Category 6 -- process flow. Expected route: VLM."""
    img = Image.new("RGB", (1000, 720), "white")
    d = ImageDraw.Draw(img)
    d.text((40, 34), "Leave Request Approval Flow", font=font("bold", 34), fill=INK)
    steps = [
        "1. Employee submits request",
        "2. Manager reviews",
        "3. HR policy validation",
        "4. HR approves",
        "5. Payroll updates balance",
    ]
    top = 100
    for index, step in enumerate(steps):
        rect = (180, top + index * 118, 820, top + index * 118 + 74)
        fill = LIGHT if index % 2 == 0 else (226, 238, 250)
        _box(d, rect, step, fill=fill)
        if index < len(steps) - 1:
            cx = (rect[0] + rect[2]) / 2
            _arrow(d, (cx, rect[3]), (cx, rect[3] + 44))
    d.text((840, 240), "rejected ->\nback to step 2", font=font("regular", 22), fill=MUTED)
    d.line([(820, 268), (860, 268), (860, 500), (820, 500)], fill=(170, 60, 60), width=4)
    d.polygon([(820, 500), (812, 486), (828, 486)], fill=(170, 60, 60))
    return img


def make_chart() -> Image.Image:
    """Category 7 -- chart. The bar heights carry meaning a VLM can summarise.
    Expected route: VLM."""
    img = Image.new("RGB", (1000, 620), "white")
    d = ImageDraw.Draw(img)
    d.text((500, 46), "Engineering Headcount by Quarter", font=font("bold", 34), fill=INK, anchor="mm")
    left, base, top = 120, 520, 110
    d.line([(left, base), (940, base)], fill=INK, width=3)
    d.line([(left, base), (left, top)], fill=INK, width=3)
    for value in (0, 20, 40, 60):
        y = base - value * 6
        d.line([(left - 10, y), (left, y)], fill=INK, width=3)
        d.text((left - 22, y), str(value), font=font("regular", 22), fill=MUTED, anchor="rm")
    data = [("Q1", 32), ("Q2", 45), ("Q3", 51), ("Q4", 63)]
    bar_w, gap = 130, 60
    x = left + 70
    for label, value in data:
        y = base - value * 6
        d.rectangle([x, y, x + bar_w, base], fill=ACCENT, outline=(20, 60, 105))
        d.text((x + bar_w / 2, y - 16), str(value), font=font("bold", 26), fill=INK, anchor="ms")
        d.text((x + bar_w / 2, base + 26), label, font=font("regular", 26), fill=INK, anchor="ma")
        x += bar_w + gap
    d.text((60, (top + base) / 2), "Headcount", font=font("regular", 24), fill=MUTED, anchor="mm")
    return img


def make_logo() -> Image.Image:
    """Category 8 -- decorative brand mark with no retrievable information.
    Expected route: IGNORE."""
    img = Image.new("RGB", (420, 150), "white")
    d = ImageDraw.Draw(img)
    d.ellipse([24, 30, 114, 120], fill=ACCENT)
    d.polygon([(69, 45), (92, 108), (46, 108)], fill="white")
    d.text((132, 58), "NEXORA", font=font("bold", 40), fill=ACCENT, anchor="lm")
    d.text((134, 96), "TECHNOLOGIES", font=font("regular", 18), fill=MUTED, anchor="lm")
    return img


IMAGE_BUILDERS = {
    "img_text_card.png": make_text_card,
    "img_screenshot.png": make_screenshot,
    "img_architecture.png": make_architecture_diagram,
    "img_flowchart.png": make_flow_diagram,
    "img_chart.png": make_chart,
    "img_logo.png": make_logo,
}


def write_images(directory: Path) -> dict[str, Path]:
    directory.mkdir(parents=True, exist_ok=True)
    written: dict[str, Path] = {}
    for name, builder in IMAGE_BUILDERS.items():
        path = directory / name
        builder().save(path, "PNG")
        written[name] = path
    return written


# --------------------------------------------------------------------------
# Minimal DOCX writer (OOXML by hand -- no python-docx)
# --------------------------------------------------------------------------

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
WP_NS = "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing"
A_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"
PIC_NS = "http://schemas.openxmlformats.org/drawingml/2006/picture"

EMU_PER_PX = 9525  # 914400 EMU per inch / 96 px per inch


def _esc(text: str) -> str:
    return (
        text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")
    )


@dataclass
class Block:
    """One paragraph-level thing in the document body."""

    kind: str  # heading | paragraph | list | table | image
    text: str = ""
    level: int = 1
    image: bytes | None = None
    image_name: str = ""
    image_px: tuple[int, int] = (0, 0)
    rows: list[list[str]] = field(default_factory=list)
    numbered: bool = False


def _run(text: str) -> str:
    return f'<w:r><w:t xml:space="preserve">{_esc(text)}</w:t></w:r>'


def _block_xml(block: Block, rel_ids: dict[str, str], doc_pr_id: list[int]) -> str:
    if block.kind == "heading":
        return (
            f'<w:p><w:pPr><w:pStyle w:val="Heading{block.level}"/></w:pPr>'
            f"{_run(block.text)}</w:p>"
        )
    if block.kind == "paragraph":
        return f"<w:p>{_run(block.text)}</w:p>"
    if block.kind == "list":
        num_id = 2 if block.numbered else 1
        return (
            f'<w:p><w:pPr><w:pStyle w:val="ListParagraph"/>'
            f'<w:numPr><w:ilvl w:val="0"/><w:numId w:val="{num_id}"/></w:numPr>'
            f"</w:pPr>{_run(block.text)}</w:p>"
        )
    if block.kind == "table":
        grid = "".join('<w:gridCol w:w="2400"/>' for _ in block.rows[0])
        rows_xml = []
        for row_index, row in enumerate(block.rows):
            cells = []
            for cell in row:
                shading = '<w:shd w:val="clear" w:fill="E8EEF6"/>' if row_index == 0 else ""
                cells.append(
                    "<w:tc><w:tcPr><w:tcW w:w=\"2400\" w:type=\"dxa\"/>"
                    f"{shading}</w:tcPr>"
                    f'<w:p><w:pPr><w:spacing w:before="40" w:after="40"/></w:pPr>'
                    f"{_run(cell)}</w:p></w:tc>"
                )
            header_mark = '<w:trPr><w:tblHeader/></w:trPr>' if row_index == 0 else ""
            rows_xml.append(f"<w:tr>{header_mark}{''.join(cells)}</w:tr>")
        return (
            "<w:tbl><w:tblPr><w:tblStyle w:val=\"TableGrid\"/>"
            '<w:tblW w:w="0" w:type="auto"/>'
            '<w:tblBorders>'
            '<w:top w:val="single" w:sz="4" w:color="9AA6B4"/>'
            '<w:left w:val="single" w:sz="4" w:color="9AA6B4"/>'
            '<w:bottom w:val="single" w:sz="4" w:color="9AA6B4"/>'
            '<w:right w:val="single" w:sz="4" w:color="9AA6B4"/>'
            '<w:insideH w:val="single" w:sz="4" w:color="9AA6B4"/>'
            '<w:insideV w:val="single" w:sz="4" w:color="9AA6B4"/>'
            "</w:tblBorders></w:tblPr>"
            f"<w:tblGrid>{grid}</w:tblGrid>{''.join(rows_xml)}</w:tbl>"
            "<w:p/>"
        )
    if block.kind == "image":
        rel_id = rel_ids[block.image_name]
        doc_pr_id[0] += 1
        cx = block.image_px[0] * EMU_PER_PX
        cy = block.image_px[1] * EMU_PER_PX
        return (
            "<w:p><w:pPr><w:jc w:val=\"left\"/></w:pPr><w:r><w:drawing>"
            f'<wp:inline distT="0" distB="0" distL="0" distR="0">'
            f'<wp:extent cx="{cx}" cy="{cy}"/>'
            f'<wp:effectExtent l="0" t="0" r="0" b="0"/>'
            f'<wp:docPr id="{doc_pr_id[0]}" name="{_esc(block.image_name)}"/>'
            "<a:graphic>"
            '<a:graphicData uri="http://schemas.openxmlformats.org/drawingml/2006/picture">'
            f'<pic:pic xmlns:pic="{PIC_NS}">'
            f'<pic:nvPicPr><pic:cNvPr id="{doc_pr_id[0]}" name="{_esc(block.image_name)}"/>'
            "<pic:cNvPicPr/></pic:nvPicPr>"
            f'<pic:blipFill><a:blip r:embed="{rel_id}"/>'
            "<a:stretch><a:fillRect/></a:stretch></pic:blipFill>"
            f'<pic:spPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="{cx}" cy="{cy}"/></a:xfrm>'
            '<a:prstGeom prst="rect"><a:avLst/></a:prstGeom></pic:spPr>'
            "</pic:pic></a:graphicData></a:graphic></wp:inline>"
            "</w:drawing></w:r></w:p>"
        )
    raise ValueError(f"unknown block kind {block.kind!r}")


_CONTENT_TYPES = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Default Extension="png" ContentType="image/png"/>
<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
<Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>
<Override PartName="/word/numbering.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.numbering+xml"/>
</Types>"""

_ROOT_RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>"""


def _styles_xml() -> str:
    parts = [
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
        f'<w:styles xmlns:w="{W_NS}">',
        "<w:docDefaults><w:rPrDefault><w:rPr>"
        '<w:rFonts w:ascii="Calibri" w:hAnsi="Calibri"/><w:sz w:val="22"/>'
        "</w:rPr></w:rPrDefault></w:docDefaults>",
    ]
    for level, size in ((1, 36), (2, 30), (3, 26)):
        parts.append(
            f'<w:style w:type="paragraph" w:styleId="Heading{level}">'
            f'<w:name w:val="heading {level}"/><w:basedOn w:val="Normal"/>'
            '<w:qFormat/>'
            f'<w:pPr><w:outlineLvl w:val="{level - 1}"/><w:spacing w:before="240" w:after="120"/>'
            "<w:keepNext/></w:pPr>"
            f'<w:rPr><w:b/><w:sz w:val="{size}"/><w:color w:val="1A5696"/></w:rPr>'
            "</w:style>"
        )
    parts.append(
        '<w:style w:type="paragraph" w:styleId="ListParagraph">'
        '<w:name w:val="List Paragraph"/><w:basedOn w:val="Normal"/><w:qFormat/>'
        '<w:pPr><w:ind w:left="720"/><w:contextualSpacing/></w:pPr></w:style>'
    )
    parts.append(
        '<w:style w:type="table" w:styleId="TableGrid"><w:name w:val="Table Grid"/>'
        '<w:tblPr><w:tblBorders>'
        '<w:top w:val="single" w:sz="4" w:color="9AA6B4"/>'
        '<w:left w:val="single" w:sz="4" w:color="9AA6B4"/>'
        '<w:bottom w:val="single" w:sz="4" w:color="9AA6B4"/>'
        '<w:right w:val="single" w:sz="4" w:color="9AA6B4"/>'
        '<w:insideH w:val="single" w:sz="4" w:color="9AA6B4"/>'
        '<w:insideV w:val="single" w:sz="4" w:color="9AA6B4"/>'
        "</w:tblBorders></w:tblPr></w:style>"
    )
    parts.append("</w:styles>")
    return "".join(parts)


def _numbering_xml() -> str:
    def abstract(aid: str, fmt: str, text: str) -> str:
        return (
            f'<w:abstractNum w:abstractNumId="{aid}">'
            f'<w:multiLevelType w:val="singleLevel"/>'
            f'<w:lvl w:ilvl="0"><w:start w:val="1"/><w:numFmt w:val="{fmt}"/>'
            f'<w:lvlText w:val="{text}"/><w:lvlJc w:val="left"/>'
            '<w:pPr><w:ind w:left="720" w:hanging="360"/></w:pPr></w:lvl></w:abstractNum>'
        )

    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<w:numbering xmlns:w="{W_NS}">'
        + abstract("0", "bullet", "")
        + abstract("1", "decimal", "%1.")
        + '<w:num w:numId="1"><w:abstractNumId w:val="0"/></w:num>'
        '<w:num w:numId="2"><w:abstractNumId w:val="1"/></w:num>'
        "</w:numbering>"
    )


def write_docx(path: Path, blocks: list[Block]) -> Path:
    """Serialise ``blocks`` into a real .docx package."""
    images: dict[str, tuple[bytes, tuple[int, int]]] = {}
    for block in blocks:
        if block.kind == "image":
            from io import BytesIO

            with Image.open(BytesIO(block.image)) as handle:
                size = handle.size
            images[block.image_name] = (block.image, size)

    rel_ids = {name: f"rId{10 + index}" for index, name in enumerate(images)}
    doc_pr_id = [0]
    body = "".join(_block_xml(block, rel_ids, doc_pr_id) for block in blocks)

    document_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<w:document xmlns:w="{W_NS}" xmlns:r="{R_NS}" xmlns:wp="{WP_NS}" xmlns:a="{A_NS}">'
        f"<w:body>{body}"
        '<w:sectPr><w:pgSz w:w="11906" w:h="16838"/>'
        '<w:pgMar w:top="1134" w:right="1134" w:bottom="1134" w:left="1134"/></w:sectPr>'
        "</w:body></w:document>"
    )

    rel_parts = [
        f'<Relationship Id="rId1" Type="{R_NS}/styles" Target="styles.xml"/>',
        f'<Relationship Id="rId2" Type="{R_NS}/numbering" Target="numbering.xml"/>',
    ]
    for name, rel_id in rel_ids.items():
        rel_parts.append(f'<Relationship Id="{rel_id}" Type="{R_NS}/image" Target="media/{name}"/>')
    document_rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        + "".join(rel_parts)
        + "</Relationships>"
    )

    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", _CONTENT_TYPES)
        archive.writestr("_rels/.rels", _ROOT_RELS)
        archive.writestr("word/document.xml", document_xml)
        archive.writestr("word/_rels/document.xml.rels", document_rels)
        archive.writestr("word/styles.xml", _styles_xml())
        archive.writestr("word/numbering.xml", _numbering_xml())
        for name, (data, _) in images.items():
            archive.writestr(f"word/media/{name}", data)
    return path


# --------------------------------------------------------------------------
# PDFs
# --------------------------------------------------------------------------


def _pdf_escape(text: str) -> str:
    return text.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")


def write_text_pdf(path: Path, pages: list[list[tuple[str, int, int]]]) -> Path:
    """Write a small text-based PDF from (text, size, x) tuples per page.

    Hand-rolled because a PDF is a plain text container; this keeps the POC
    free of any report-writing dependency. Exercises Docling's *native* text
    path, as opposed to the scanned path below.
    """
    objects: list[bytes] = []

    def add(body: bytes) -> int:
        objects.append(body)
        return len(objects)

    # Resource names /F1 and /F2 map to these two font objects, in that order.
    f_regular, f_bold = 1, 2
    add(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>")
    add(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>")
    # Object numbering is fixed: 2 fonts, then a (content, page) pair per page,
    # then the /Pages node, then the catalog.
    pages_obj_number = 2 + 2 * len(pages) + 1

    page_numbers: list[int] = []
    for lines in pages:
        parts = []
        y = 780
        for text, size, x in lines:
            font_ref = f_bold if size >= 15 else f_regular
            parts.append(
                b"BT /F%d %d Tf %d %d Td (%s) Tj ET"
                % (font_ref, size, x, y, _pdf_escape(text).encode("cp1252", "replace"))
            )
            y -= size + 10
        content = b"\n".join(parts)
        content_number = add(b"<< /Length %d >>\nstream\n" % len(content) + content + b"\nendstream")
        page_numbers.append(
            add(
                b"<< /Type /Page /Parent %d 0 R /MediaBox [0 0 595 842] "
                b"/Resources << /Font << /F%d 0 R /F%d 0 R >> >> /Contents %d 0 R >>"
                % (pages_obj_number, f_regular, f_bold, content_number)
            )
        )

    kids = b" ".join(b"%d 0 R" % number for number in page_numbers)
    pages_obj = add(
        b"<< /Type /Pages /Kids [%s] /Count %d >>" % (kids, len(page_numbers))
    )
    assert pages_obj == pages_obj_number, (pages_obj, pages_obj_number)
    catalog = add(b"<< /Type /Catalog /Pages %d 0 R >>" % pages_obj)

    out = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for index, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % index + body + b"\nendobj\n"
    xref_at = len(out)
    out += b"xref\n0 %d\n" % (len(objects) + 1)
    out += b"0000000000 65535 f \n"
    for offset in offsets[1:]:
        out += b"%010d 00000 n \n" % offset
    out += b"trailer\n<< /Size %d /Root %d 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (
        len(objects) + 1,
        catalog,
        xref_at,
    )
    path.write_bytes(bytes(out))
    return path


def write_scanned_pdf(path: Path, pages: list[Image.Image]) -> Path:
    """Rasterise pages into an image-only PDF.

    This is the case where Docling must fall back to page-level OCR, so it is
    the direct counterpart to the text PDF.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    converted = [page.convert("RGB") for page in pages]
    converted[0].save(path, "PDF", save_all=True, append_images=converted[1:], resolution=150)
    return path


# --------------------------------------------------------------------------
# The document set
# --------------------------------------------------------------------------

DOCUMENT_SECTIONS = [
    ("Employee Onboarding Guide", "H1", None),
    ("1. Overview", "H2", None),
    ("1.1 Purpose", "H3", None),
    ("2. Onboarding Steps", "H2", None),
    ("3. Access Matrix by Department", "H2", None),
    ("4. Employee Record Card", "H2", "img_text_card.png"),
    ("5. HR Portal Screenshot", "H2", "img_screenshot.png"),
    ("6. Platform Architecture", "H2", "img_architecture.png"),
    ("7. Leave Approval Flow", "H2", "img_flowchart.png"),
    ("8. Headcount by Quarter", "H2", "img_chart.png"),
    ("9. Company Identity", "H2", "img_logo.png"),
]

ACCESS_TABLE = [
    ["Department", "Portal Role", "Approver", "Payroll Access"],
    ["Engineering", "Employee", "Engineering Manager", "Read Only"],
    ["Engineering", "Manager", "VP Engineering", "Read Only"],
    ["Finance", "Employee", "Finance Director", "Read Write"],
    ["Human Resources", "HR Admin", "HR Director", "Read Write"],
]

ONBOARDING_STEPS = [
    "HR creates the employee account in the HR portal.",
    "The manager assigns the employee to a delivery project.",
    "IT issues the laptop and provisions repository access.",
    "Payroll adds the employee to the monthly salary cycle.",
]

OVERVIEW_PARAGRAPHS = [
    "This guide describes how a new employee is onboarded, which systems they "
    "are granted access to, and who approves each step. It is synthetic test "
    "content generated for a document-ingestion experiment.",
    "Every role named in this document is fictional. No real employee, client, "
    "or system from any production environment is referenced.",
]


def build_all(input_dir: Path) -> dict[str, Path]:
    """Create every test artefact and return the paths that were written."""
    input_dir.mkdir(parents=True, exist_ok=True)
    images = write_images(input_dir / "images")

    blocks: list[Block] = []
    for title, level_tag, image_name in DOCUMENT_SECTIONS:
        level = int(level_tag[1:])
        if title == "Employee Onboarding Guide":
            blocks.append(Block("heading", title, level=1))
        elif title == "1. Overview":
            blocks.append(Block("heading", title, level=2))
            for paragraph in OVERVIEW_PARAGRAPHS:
                blocks.append(Block("paragraph", paragraph))
        elif title == "1.1 Purpose":
            blocks.append(Block("heading", title, level=3))
            blocks.append(
                Block(
                    "paragraph",
                    "The purpose of this section is to state that onboarding is "
                    "completed within five working days of the joining date, and "
                    "that the approving manager is recorded in the access matrix.",
                )
            )
        elif title == "2. Onboarding Steps":
            blocks.append(Block("heading", title, level=2))
            for step in ONBOARDING_STEPS:
                blocks.append(Block("list", step, numbered=True))
        elif title == "3. Access Matrix by Department":
            blocks.append(Block("heading", title, level=2))
            blocks.append(
                Block(
                    "paragraph",
                    "The table below records the portal role, the approver and the "
                    "payroll access level granted to each department.",
                )
            )
            blocks.append(Block("table", rows=ACCESS_TABLE))
        else:
            blocks.append(Block("heading", title, level=2))
            blocks.append(
                Block(
                    "paragraph",
                    f"The figure below shows {title.lower().rstrip('0123456789. ')} "
                    "as it appears in the source document.",
                )
            )
            blocks.append(
                Block(
                    "image",
                    image=images[image_name].read_bytes(),
                    image_name=image_name,
                )
            )

    written: dict[str, Path] = dict(images)
    written["onboarding_guide.docx"] = write_docx(input_dir / "onboarding_guide.docx", blocks)

    written["policy_text.pdf"] = write_text_pdf(
        input_dir / "policy_text.pdf",
        [
            [
                ("Annual Leave Policy", 20, 60),
                ("1. Entitlement", 16, 60),
                (
                    "Every full-time employee accrues 18 days of annual leave per "
                    "calendar year, accrued monthly at 1.5 days.",
                    11,
                    60,
                ),
                ("Carry over is limited to a maximum of 5 unused days.", 11, 60),
                ("2. Approval", 16, 60),
                (
                    "Leave requests must be approved by the reporting manager "
                    "before the requested start date.",
                    11,
                    60,
                ),
                ("Requests of more than 10 consecutive days also need HR approval.", 11, 60),
            ],
            [
                ("3. Payroll and Record Keeping", 16, 60),
                (
                    "The payroll service updates the leave balance after the "
                    "HR approval step completes.",
                    11,
                    60,
                ),
                (
                    "A leave ledger entry is created for every approved request, "
                    "referencing the employee ID and the approver.",
                    11,
                    60,
                ),
                ("4. Unpaid Leave", 16, 60),
                (
                    "Leave taken beyond the accrued balance is recorded as unpaid "
                    "leave and requires written director approval.",
                    11,
                    60,
                ),
            ],
        ],
    )

    scanned = Image.new("RGB", (1240, 1754), "white")
    d = ImageDraw.Draw(scanned)
    d.text((120, 140), "Scanned Travel Policy", font=font("bold", 52), fill=INK)
    d.text((120, 250), "Section 1 - Booking", font=font("bold", 36), fill=INK)
    for index, line in enumerate(
        [
            "All travel must be booked through the internal portal.",
            "Flights are booked in economy for journeys under 6 hours.",
            "Hotel spend is capped at 450 USD per night.",
        ]
    ):
        d.text((120, 320 + index * 56), line, font=font("regular", 32), fill=INK)
    written["policy_scanned.pdf"] = write_scanned_pdf(
        input_dir / "policy_scanned.pdf", [scanned]
    )
    return written


if __name__ == "__main__":
    import sys

    target = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("input")
    for name, path in build_all(target).items():
        print(f"{name:26s} {path.stat().st_size:>9,d} bytes  {path}")
