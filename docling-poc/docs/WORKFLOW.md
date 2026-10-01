# Workflow Diagram

Two versions of the same diagram:

- **`workflow.png`** — rendered image, open it directly
- **below** — Mermaid source, editable and renders on GitHub / VS Code

Regenerate the PNG after editing the Mermaid:

```
python docs/draw_workflow.py
```

For DOCX page citations, install LibreOffice and run:

```
python -m src.main --citation-pdf
```

This opt-in step writes rendered PDFs under `output/citations/` and emits
`output/citation_chunks.json`. Without this option, DOCX `page_number` remains
`null`; section and element anchors remain available.

---

## Mermaid source

```mermaid
flowchart TD
    IN["<b>INPUT</b> — synthetic documents only<br/>onboarding_guide.docx — headings, list, table, 6 images<br/>policy_text.pdf — 2 pages, born-digital<br/>policy_scanned.pdf — 1 page, no text layer"]

    DOCLING["<b>STAGE 1 · DOCLING</b> — the only parser<br/>Reads DOCX and PDF directly, no DOCX→PDF conversion<br/>Returns headings, paragraphs, lists, tables, images<br/>in reading order, and labels each image"]

    NOTE["⚠ DOCX images arrive UNLABELLED —<br/>Docling's picture classifier only runs in the PDF pipeline"]

    OCR["<b>STAGE 2 · OCR</b> — Docling + EasyOCR<br/>Each image is fed back to Docling as its own document<br/>Docling does not OCR pictures inside a Word file<br/>Character count also feeds the router"]

    ROUTER{"<b>STAGE 4 · ROUTER</b><br/>Which picture needs what?<br/><i>uses Docling's own label</i>"}

    OCR_KEEP["<b>TEXT-HEAVY → OCR</b><br/>Keep the OCR text<br/>Exact words are the best<br/>searchable content"]
    IGNORE["<b>DECORATIVE → IGNORE</b><br/>Logo, icon, divider<br/>No information worth storing"]
    VLM["<b>DIAGRAM / CHART → VLM</b><br/>Only routed images reach the model: 3 of 6<br/>Reads relationships and values OCR cannot"]

    NORM["<b>STAGE 5 · NORMALISE</b><br/>One flat list: heading, paragraph, list, table,<br/>image_ocr, image_description<br/>each with page, section and origin"]

    OUT["<b>STAGE 6 · OUTPUT</b><br/>final_document.json · routing.json<br/>ocr_results.json · vlm_results.json<br/>run_report.json · extracted PNGs"]

    PROV["<b>PROVENANCE</b> on every element<br/><b>docling</b> = text READ from the document<br/><b>docling+easyocr</b> = text READ from inside an image<br/><b>vlm</b> = prose WRITTEN by a model — unverified"]

    IN --> DOCLING
    DOCLING -.-> NOTE
    NOTE --> OCR
    OCR --> ROUTER

    ROUTER -->|table 0.81| OCR_KEEP
    ROUTER -->|screenshot 0.97| OCR_KEEP
    ROUTER -->|logo 0.94| IGNORE
    ROUTER -->|flow_chart 0.99| VLM
    ROUTER -->|flow_chart 1.00| VLM
    ROUTER -->|bar_chart 1.00| VLM

    OCR_KEEP --> NORM
    IGNORE --> NORM
    VLM --> NORM

    NORM --> OUT
    OUT --> PROV

    classDef input fill:#eef2f8,stroke:#788494
    classDef docling fill:#deebfa,stroke:#4a7ab5
    classDef ocr fill:#dff3e4,stroke:#4f9a68
    classDef route fill:#fdf0d6,stroke:#b0821f
    classDef vlm fill:#eee5fa,stroke:#8b62c4
    classDef drop fill:#f0f0f1,stroke:#8a8f96
    classDef norm fill:#dcf0f3,stroke:#4a8fa0
    classDef out fill:#fcf3db,stroke:#b3922f
    classDef note fill:#fdecec,stroke:#b85c5c,stroke-dasharray: 4 3

    class IN input
    class DOCLING docling
    class OCR ocr
    class ROUTER route
    class OCR_KEEP ocr
    class IGNORE drop
    class VLM vlm
    class NORM norm
    class OUT out
    class NOTE note
```

---

## Reading the diagram

**The main spine is top to bottom.** Each stage takes the previous one's
output and adds understanding. Nothing branches except the router.

**The one branch that matters** is the router in the middle. It sends each
image to one of three places based on the label Docling already gave it:

- two images to **OCR** (the text card and the screenshot)
- three images to the **VLM** (architecture diagram, flow diagram, chart)
- one image to **IGNORE** (the logo)

The percentages on those arrows are Docling's own classifier confidence, not
something the POC invented. All six routed correctly.

**The orange dashed note** is a real trap in Docling, not a design choice. Its
picture classifier runs inside the PDF pipeline, but a DOCX is read by a
different backend that never invokes it. Without the explicit classification
pass in `stage1_docling.py`, every DOCX image would reach the router unlabelled
and there would be nothing to route on.

**The provenance panel** at the bottom is what makes the output trustworthy. It
distinguishes text that was *read* from the document (`docling`), text *read*
from inside an image (`docling+easyocr`), and prose a model *wrote* (`vlm`). Only
the third is unverified — and on the last run that is exactly where the
SmolVLM-256M description of the bar chart landed as the single character `63`.
