"""Render the POC workflow as a diagram.

    python docs/draw_workflow.py

Writes docs/workflow.png. Uses Pillow for drawing only -- nothing here reads a
document, and nothing here is part of the ingestion pipeline.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

FONTS = Path("C:/Windows/Fonts")
REG = FONTS / "arial.ttf"
BOLD = FONTS / "arialbd.ttf"

INK = (26, 30, 38)
MUTED = (100, 110, 125)
LINE = (90, 100, 115)

C_INPUT = (238, 242, 248)
C_DOCLING = (222, 235, 250)
C_OCR = (223, 243, 228)
C_ROUTE = (253, 240, 214)
C_VLM = (238, 229, 250)
C_DROP = (240, 240, 241)
C_NORM = (220, 240, 243)
C_OUT = (252, 243, 219)
C_NOTE = (255, 255, 255)

W, H = 1560, 1648


def f(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(BOLD if bold else REG), size)


def wrap(draw, text, font, max_width):
    words, lines, current = text.split(), [], ""
    for word in words:
        trial = f"{current} {word}".strip()
        if draw.textlength(trial, font=font) <= max_width:
            current = trial
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def box(d, x, y, w, h, fill, title, lines, badge=None, edge=(120, 132, 148)):
    d.rounded_rectangle([x, y, x + w, y + h], radius=14, fill=fill, outline=edge, width=3)
    if badge:
        d.ellipse([x + 16, y + 16, x + 62, y + 62], fill=edge)
        tw = d.textlength(badge, font=f(22, True))
        d.text((x + 39 - tw / 2, y + 39), badge, font=f(22, True), fill="white", anchor="mm")
    d.text((x + w / 2, y + 36), title, font=f(25, True), fill=INK, anchor="mm")
    y_cursor = y + 68
    for line in lines:
        for wrapped in wrap(d, line, f(19), w - 44):
            d.text((x + w / 2, y_cursor), wrapped, font=f(19), fill=MUTED, anchor="ma")
            y_cursor += 24
        y_cursor += 4


def poly_arrow(d, points, colour=LINE, width=4, head=15):
    d.line(points, fill=colour, width=width, joint="curve")
    (x1, y1), (x2, y2) = points[-2], points[-1]
    dx, dy = x2 - x1, y2 - y1
    length = max((dx * dx + dy * dy) ** 0.5, 1e-6)
    ux, uy = dx / length, dy / length
    px, py = -uy, ux
    base = (x2 - ux * head, y2 - uy * head)
    d.polygon(
        [
            (x2, y2),
            (base[0] + px * head * 0.55, base[1] + py * head * 0.55),
            (base[0] - px * head * 0.55, base[1] - py * head * 0.55),
        ],
        fill=colour,
    )


def build() -> Image.Image:
    img = Image.new("RGB", (W, H), "white")
    d = ImageDraw.Draw(img)

    d.text((W / 2, 52), "Docling Ingestion POC", font=f(42, True), fill=INK, anchor="mm")
    d.text(
        (W / 2, 96),
        "One parser (Docling), enriched by OCR and a VLM, then flattened into one searchable list",
        font=f(20),
        fill=MUTED,
        anchor="mm",
    )
    d.line([(120, 126), (W - 120, 126)], fill=(200, 208, 218), width=2)

    cx = 700
    bw = 660

    box(
        d, cx - bw / 2, 150, bw, 118, C_INPUT,
        "INPUT  --  synthetic documents only",
        [
            "onboarding_guide.docx   headings, list, table, 6 embedded images",
            "policy_text.pdf         2 pages, born-digital text",
            "policy_scanned.pdf      1 page, no text layer at all",
        ],
        badge="1",
    )
    poly_arrow(d, [(cx, 268), (cx, 308)])

    box(
        d, cx - bw / 2, 308, bw, 148, C_DOCLING,
        "STAGE 1  --  DOCLING  (the only parser)",
        [
            "Reads DOCX and PDF directly. No DOCX-to-PDF conversion.",
            "Returns headings, paragraphs, lists, tables and images in reading order.",
            "Also labels each image: bar_chart, flow_chart, logo, screenshot ...",
        ],
        badge="2",
    )
    poly_arrow(d, [(cx, 456), (cx, 496)])
    d.text(
        (cx + 16, 476), "DOCX pictures arrive UNLABELLED -- the PDF pipeline skips classification for Word",
        font=f(17), fill=(176, 96, 20), anchor="lm",
    )

    box(
        d, cx - bw / 2, 496, bw, 148, C_OCR,
        "STAGE 2  --  OCR  (Docling + EasyOCR)",
        [
            "Each embedded image is fed back to Docling as its own document, OCR on.",
            "Needed because Docling does not OCR pictures inside a Word document.",
            "Its character count is also a signal the router uses on the next stage.",
        ],
        badge="3",
    )
    poly_arrow(d, [(cx, 644), (cx, 672)])

    # Router decision
    dy, dh, dw = 760, 100, 330
    d.polygon(
        [
            (cx, dy - dh), (cx + dw, dy), (cx, dy + dh), (cx - dw, dy),
        ],
        fill=C_ROUTE, outline=LINE,
    )
    d.polygon(
        [
            (cx, dy - dh), (cx + dw, dy), (cx, dy + dh), (cx - dw, dy),
        ],
        outline=LINE,
    )
    d.text((cx, dy - 26), "STAGE 4  --  ROUTER", font=f(25, True), fill=INK, anchor="mm")
    for i, line in enumerate(["Which picture actually", "needs what?"]):
        d.text((cx, dy + 10 + i * 26), line, font=f(19), fill=MUTED, anchor="mm")
    d.text(
        (cx, dy + 78), "uses Docling's own label",
        font=f(17), fill=MUTED, anchor="mm",
    )

    poly_arrow(d, [(cx, dy + dh), (cx, 880)])
    d.line([(cx - 330, dy), (235, 880)], fill=LINE, width=4)
    d.line([(cx + 330, dy), (1220, 880)], fill=LINE, width=4)

    oy, oh = 880, 132
    box(
        d, 30, oy, 410, oh, C_OCR,
        "TEXT-HEAVY  ->  OCR",
        ["Keep the OCR text.", "Exact words are the best", "searchable content."],
    )
    box(
        d, 470, oy, 460, oh, C_DROP,
        "DECORATIVE  ->  IGNORE",
        ["Logo, icon, divider.", "No information worth", "storing or searching."],
    )
    box(
        d, 960, oy, 520, oh, C_VLM,
        "DIAGRAM / CHART  ->  VLM",
        ["Only routed images reach the model: 3 of 6.", "Reads relationships and values", "that OCR cannot express."],
    )

    bus = oy + oh + 46
    for x in (235, 700, 1220):
        d.line([(x, oy + oh), (x, bus)], fill=LINE, width=4)
    d.line([(235, bus), (1220, bus)], fill=LINE, width=4)
    poly_arrow(d, [(700, bus), (700, bus + 46)])

    ny = bus + 46
    box(
        d, cx - bw / 2, ny, bw, 132, C_NORM,
        "STAGE 5  --  NORMALISE",
        [
            "One flat list of elements: heading, paragraph, list, table,",
            "image_ocr, image_description -- each with page, section and origin.",
        ],
        badge="4",
    )
    poly_arrow(d, [(cx, ny + 132), (cx, ny + 168)])

    oy2 = ny + 168
    box(
        d, cx - bw / 2, oy2, bw, 118, C_OUT,
        "STAGE 6  --  OUTPUT",
        [
            "final_document.json  (unified list)   routing.json  (decisions + reasons)",
            "ocr_results.json  vlm_results.json   run_report.json   extracted PNGs",
        ],
        badge="5",
    )
    poly_arrow(d, [(cx, oy2 + 118), (cx, oy2 + 152)])

    py = oy2 + 152
    d.rounded_rectangle([210, py, W - 210, py + 176], radius=14, fill=C_NOTE, outline=(170, 180, 195), width=3)
    d.text((W / 2, py + 32), "PROVENANCE  --  carried on every single element", font=f(23, True), fill=INK, anchor="mm")
    rows = [
        ("docling", "text READ from the document", C_DOCLING),
        ("docling+easyocr", "text READ from inside an image", C_OCR),
        ("vlm", "prose WRITTEN by a model -- unverified, must not be quoted as fact", C_VLM),
    ]
    ry = py + 66
    for label, meaning, colour in rows:
        d.rounded_rectangle([258, ry, 470, ry + 26], radius=6, fill=colour, outline=(160, 170, 185))
        d.text((364, ry + 13), label, font=f(18, True), fill=INK, anchor="mm")
        d.text((492, ry + 13), meaning, font=f(18), fill=MUTED, anchor="lm")
        ry += 34

    return img


if __name__ == "__main__":
    target = Path(__file__).resolve().parent / "workflow.png"
    build().save(target)
    print(f"wrote {target}  ({target.stat().st_size:,} bytes)")
