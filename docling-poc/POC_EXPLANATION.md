# Docling Ingestion POC — Plain-Language Explanation

This document explains, without jargon, what the POC does, which tools it uses,
what the alternatives were, why these were chosen, and what is currently
weak about it.

Everything here was measured on this machine. Where something was *not* tested,
it says so.

---

## 1. The problem, in plain words

You have documents — Word files, PDFs. A chatbot can only answer questions about
text it can read. But a Word file is not plain text: it is a zip archive of XML
plus embedded images, and a PDF is a page description that may or may not have a
text layer at all.

A PDF of a printed page that was then scanned has **no text at all**. The words
are just shapes. So before a chatbot can help, something has to read these files
and turn them into text it can search.

That "something" is called a **parser**. The POC tests one specific approach to
this, end to end, and reports honestly on how well it works.

---

## 2. What the pipeline does, step by step

Think of it as six stages. Each one takes the previous one's output and adds a
little more understanding.

### Stage 1 — Docling reads the document

Docling is the reader. It opens the DOCX or PDF and reports what it finds:
headings, paragraphs, bullet points, tables, and images — in reading order.

Docling is smart enough to tell the difference between a *heading* and a
*paragraph*. That matters: a heading tells us what section the following text
belongs to, which lets an answer say "this comes from section 6.2" instead of
just quoting a stray sentence.

Docling also extracts each embedded image as a separate object, so we can look at
it on its own later.

### Stage 2 — OCR reads text out of images

OCR = Optical Character Recognition. It reads words that exist only as pixels.

Here's the important bit: **Docling does not do this automatically for images
that are embedded inside a Word document.** Docling's OCR only kicks in for
whole PDF pages. So if your HR policy Word document contains a screenshot of the
employee record system, Docling will hand you that screenshot as an image and
stop there.

So the POC explicitly takes each image Docling found and feeds it back to
Docling as its own tiny "document", this time with OCR switched on. Same tool,
second pass, different job.

OCR is very good at this. It read the employee record card and the HR portal
screenshot almost perfectly.

### Stage 3 — a small AI model describes images that OCR cannot handle

This is the problem OCR genuinely cannot solve.

Look at the bar chart. OCR will happily read the labels "Q1 Q2 Q3 Q4" and the
numbers "32 45 51 63". But the *content* of that chart — that headcount grew
steadily and is highest in Q4 — is invisible to OCR. The meaning is in the
heights of the bars, not in any words.

The same is true of the architecture diagram. OCR reads "API Gateway" and
"Database", but the actual information is which box connects to which, and in
which direction. That lives in the arrows.

So for those images we call a **VLM** (Vision Language Model) — an AI model that
looks at an image and writes a description.

Critically, **not every image gets sent to the VLM.** That is the whole point of
stage 4.

### Stage 4 — the router decides what each image needs

Three outcomes:

| Image is... | What happens | Why |
|---|---|---|
| Mostly words (text card, screenshot) | OCR only | OCR already reads it exactly. A VLM description would be a lossy summary of something we already have perfectly. |
| A diagram, chart, or flow | VLM | The meaning is in the shapes, not the words. |
| A logo, icon, or decoration | Nothing | It contains no information worth searching. |

The router's input is **Docling's own picture classifier**, not a classifier we
built. Docling already labels each image (it said `bar_chart`, `flow_chart`,
`logo`, `screenshot_from_computer`) with a confidence score. We just group those
labels into three buckets.

On the test corpus all six images routed correctly:

```
table                   0.81  -> OCR
screenshot_from_computer 0.97 -> OCR
flow_chart              0.99  -> VLM
flow_chart              1.00  -> VLM
bar_chart               1.00  -> VLM
logo                    0.94  -> IGNORE
```

### Stage 5 — everything becomes one uniform list

By this point the document exists as three different kinds of text:
words Docling read directly, words OCR read out of an image, and prose a model
wrote about a diagram. They are not comparable as they stand.

Stage 5 flattens them into one list of items, each labelled with what kind of
thing it is (`heading`, `paragraph`, `list`, `table`, `image_ocr`,
`image_description`) and — importantly — **where it came from**.

### Stage 6 — write everything to disk

JSON files plus the raw Docling output plus every extracted image as a PNG, so
you can inspect exactly what was processed.

---

## 3. What each output file is

| File | What it holds |
|---|---|
| `output/docling/<name>.json` | Docling's own structured output, untouched |
| `output/_ocr_work/*.png` | Every extracted image, as the exact bytes that were processed |
| `output/ocr_results.json` | Per image: which engine, each line read, confidence, character count |
| `output/vlm_results.json` | Per image: model name, description, elapsed time |
| `output/routing.json` | Per image: the route, Docling's label and confidence, and a plain-English reason |
| `output/final_document.json` | The unified list of elements |
| `output/run_report.json` | Timings, per-document counts, versions, warnings |

On the last run: 35 elements from the DOCX, 10 from the text PDF, 3 from the
scanned PDF. Totals — 18 headings, 16 paragraphs, 4 list items, 1 table,
6 OCR results, 3 VLM descriptions.

The most important field on every element is `produced_by`:

- `docling` — text that was **read** from the document
- `docling+easyocr` — text **read** from inside an image
- `vlm` — prose that a model **wrote**

A chatbot that quotes text should be able to tell the difference. This lets the
future RAG pipeline know which is which.

---

## 4. Tools used, and why

### Docling — the reader

**What it is:** an open-source document parser. Converts DOCX, PDF, images, HTML
and more into one structured format.

**Why it was chosen:**

- **One tool for everything.** The requirement was a single parser. Docling covers
  both DOCX and PDF natively, so there is no need for a second library and no
  need to convert DOCX to PDF first.
- **It already contains the extra models.** OCR, picture classification, and even
  picture description are all built into the same library, selectable by a flag.
  Most other tools would need separate libraries bolted on.
- **It tells you the structure**, not just the text. Heading levels, tables and
  images are preserved with positions.
- **Active project**, well-documented, already in the main application's
  dependency list.

**Merits:**

- Single dependency for parsing, OCR and image classification
- Preserves document structure and reading order
- Works directly on DOCX and PDF — no conversion needed
- Ships its own picture classifier, which removes the need to build one
- Actively maintained

**Demerits:**

- Heavy. Pulls in PyTorch and several hundred MB of models.
- **Picture classification does not run for DOCX.** This is a real surprise and it
  bit us — see section 7.
- Slow on first run while models download.
- DOCX gets no page numbers, so "page 3" is not available for Word files.

### EasyOCR — the text reader for images

**What it is:** an OCR engine that turns pixel text into real text.

**Why it was chosen:**

- Explicitly requested for this POC.
- Free and open source, runs entirely locally.
- Good accuracy on clean, printed text.
- Reachable through Docling's own OCR registry, so there is no separate code path.

**Merits:**

- Strong on clean printed text — it read the employee card and the portal
  screenshot near-perfectly
- Runs locally, no API cost, no data leaves the machine
- Integrated into Docling, so configuration stays in one place

**Demerits:**

- Slow on CPU. Roughly 10–15 seconds per image.
- **Struggles with small or unusual fonts.** In an early test, text rendered at a
  tiny size was misread badly ("Employee ID" became "Emplovap"). Fine text needs
  to be reasonably large.
- Makes character-level mistakes even on good text. In the scanned PDF it read
  "All travel" as "AIl travel" — a capital I instead of an l. Harmless to a human,
  but it means OCR text should never be treated as an exact quote.
- Needs its models downloaded on first use.

### SmolVLM-256M — the image describer (local)

**What it is:** a very small vision-language model — 256 million parameters —
that runs on the CPU and looks at images.

**Why it was chosen:** it is genuinely lightweight and local, so VLM
experiments cost nothing and send no data anywhere. It is the right tool for
testing whether the *approach* works before committing to a bigger model.

**Merits:**

- Runs on a laptop CPU, no GPU needed
- Free, no API key, no per-call cost
- Nothing leaves the machine — safe for confidential documents

**Demerits — and these are serious:**

- **It failed on the bar chart.** Its description was the single character `63`.
  It read one bar's value and stopped. That is a total failure for that input.
- **It got the architecture diagram wrong.** It described the system as a simple
  chain of boxes, when the real diagram has a branch and a feedback loop.
- Slow: roughly 60 seconds per image.
- Its wording is clumsy and repetitive ("which is connected with... which is
  connected with").

**Honest conclusion:** SmolVLM-256M is adequate for simple flowcharts where the
content is mostly text labels. It is **not** usable for charts or for diagrams
where the relationships are the information. A larger model is needed for those.

### The Gemini backend — implemented but NOT tested

A `GeminiBackend` class was written so a stronger model can be swapped in. It
reads its API key from the `POC_GEMINI_API_KEY` environment variable and refuses
to run without one.

**It has never been executed**, because no API key is configured. Nothing in this
document claims any result from it.

⚠️ **Important warning if you do use it:** Google may use free-tier API content
for product improvement. **Never send real HR or policy documents to it.**

### Pillow — drawing the test images

Used only to *draw* the synthetic test images, never to read a document.

### Other libraries

- `zipfile` and `zipfile`-adjacent raw XML — writing the DOCX by hand
- `requests` — only for the untested Gemini backend
- `torch` / `transformers` — running the local VLM

---

## 5. Alternatives that were considered

### Document parsers

| Tool | Merits | Demerits | Verdict |
|---|---|---|---|
| **Docling** | One library for parsing + OCR + picture classification; structure-aware; DOCX and PDF direct | Heavy; skips picture classification for DOCX | **Chosen** |
| **PDFPlumber** | Excellent PDF tables; simple | PDF only — DOCX would still need another tool, breaking the one-parser rule | Rejected |
| **Marker** | Very high PDF→Markdown quality | Converts *to* Markdown, so structure is flattened into text and lost; no DOCX | Rejected |
| **python-docx** | Small, fast, obvious | DOCX only; reads paragraphs as plain strings with no layout understanding; no OCR | Rejected |
| **Apache Tika** | Extremely broad format support | Java-based; a wrapper service; gives flat text with little structure | Rejected |
| **Unstructured.io** | Good partitioners, many formats | Heavy, commercial cloud dependency for good results | Rejected |

The deciding factor: every alternative requires a *second* tool for the other
file type, or flattens structure that the chatbot needs.

### OCR engines

| Tool | Merits | Demerits | Verdict |
|---|---|---|---|
| **EasyOCR** | Free, local, good on clean text, in Docling's registry | Slow on CPU; weak on small fonts | **Chosen** |
| **RapidOCR** | Already installed; faster than EasyOCR | Less accurate on some scripts | Not chosen, but a reasonable swap |
| **Tesseract** | Mature, fast, widely used | Needs a separate system install; weaker on photos and screenshots | Rejected for this POC |
| **Cloud OCR (Google/Azure)** | Highest accuracy | Costs money, sends data off-machine | Rejected — unacceptable for HR documents |

### Vision models

| Tool | Merits | Demerits | Verdict |
|---|---|---|---|
| **SmolVLM-256M** | Local, free, tiny | Failed on the chart; weak on diagrams | **Chosen for POC** — tests the approach |
| **Gemini 2.5 Flash-Lite** | Much stronger; cheap | Sends data to Google; free tier may train on it | Implemented, untested |
| **LLaVA / Qwen-VL local** | Stronger than SmolVLM, still local | Needs a GPU to be usable | Future option |
| **Docling's built-in picture description** | Already wired in | Fixed to SmolVLM; not swappable | Not used |

---

## 6. Architectural constraints honoured

- Docling is the **only** parser. No PDFPlumber, Marker, python-docx or Tika.
- **No DOCX→PDF conversion** anywhere, including in the test-data generator.
- OCR and VLM are *enrichment* steps on images Docling already located — never
  alternative parsers.
- **No FastAPI, no Streamlit, no ChromaDB, no auth, no database.** The POC
  produces JSON and stops.
- **No import from the `app/` package.** The POC is fully standalone.
- VLM and OCR both talk to **synthetic** documents only.
- No secrets in code. The only credential is an environment variable.

---

## 7. Limitations, ranked by how much they matter

### 1. SmolVLM-256M is not good enough for charts — **blocking for real use**

It described the bar chart as `63`. For a chart, this is worse than useless: it
produces confident, wrong, citable text. If this went into a RAG pipeline, a user
could ask "what was Q3 headcount?" and receive a fabricated answer.

**Fix:** a larger vision model. Until then, treat VLM output as unverified.

### 2. VLM output has no provenance marking and no verification — **blocking**

Nothing currently stops a hallucinated sentence from being stored, embedded,
retrieved and shown to a user as though it came from the document. SmolVLM's
wrong architecture description is exactly the kind of error that gets quoted.

The POC records `produced_by: "vlm"` so the signal *exists*, but nothing acts on
it yet.

**Fix:** keep the provenance flag, and either lower the retrieval weight of
VLM-derived chunks or require human review before citing them.

### 3. OCR runs before routing, so logos waste an OCR call — **performance**

The router needs OCR's character count to make good decisions, but OCR runs on
*every* picture first. The logo was ignored anyway — but it still cost a full OCR
pass.

Here that's 1 wasted pass out of 6. On a real document full of headers,
dividers and icons, the waste would be far worse.

**Fix:** classify first, and only OCR the images that look text-bearing. Cheap
label check before an expensive model.

### 4. Architecture diagrams lose their topology — **accuracy**

OCR reads the box labels. SmolVLM read the labels but flattened the structure
into a single chain, losing the branch and the feedback loop. Relationships are
exactly what a diagram exists to convey.

**Fix:** better model, or explicitly structure the prompt to describe connections
component-by-component.

### 5. DOCX has no page numbers — **minor, and deliberate**

Docling reports no pagination for Word files, so `page` is `null` in the output.
We could estimate a page by counting content, but that would be a **guess**, and
a guess recorded as fact in a document meant to be cited is worse than an honest
`null`. Left as `null` on purpose.

### 6. A screenshot is routed to OCR, losing its layout — **minor**

The router sends text-heavy screenshots to OCR, which is right for the words but
throws away the visual structure — which field sits next to which, which button
is highlighted. For a UI screenshot that structure is often the point.

Noted in the code rather than hidden. A future version could send text-heavy
screenshots to *both* and keep both outputs.

### 7. The table-as-image trap — **minor**

The employee record card was classified `table` at 0.81 confidence. That is
defensible — it *is* a bordered grid of fields. It happened to route to OCR,
which was correct. But a genuine chart misclassified as `table` would be sent to
OCR and lose its values as meaning.

### 8. OCR text is never exact — **minor but easy to forget**

"AIl travel" instead of "All travel". OCR text should never be quoted as a
verbatim quote in a chatbot answer.

### 9. Only three test documents — **scope**

Enough to prove the pipeline works and to expose real weaknesses. Nowhere near
enough to call it accurate across a real corpus. Real evaluation needs a few
dozen real documents with hand-checked answers.

### 10. Everything runs synchronously in one process — **not a POC concern**

No batching, no queue, no caching. Fine for an experiment; would need rethinking
for production.

---

## 8. What the POC actually proved

**Proven by running it:**

- Docling parses DOCX and PDF correctly, preserving headings, lists and tables
- Docling + EasyOCR reads text out of embedded images accurately on clean images
- Docling's picture classifier labels all six test images correctly, with high
  confidence, and those labels route correctly
- The routing idea works — 2 images to OCR, 3 to the VLM, 1 discarded
- All three document types (structured DOCX, born-digital PDF, scanned PDF) reach
  a single unified element list
- Provenance survives all the way through

**Not proven:**

- That Gemini works (never executed — no API key)
- That a *good* VLM is needed, only that a small one is insufficient
- That this is accurate on real documents
- Any throughput or cost figure

**Proven negatively — arguably the most valuable result:**

- SmolVLM-256M fails outright on charts
- SmolVLM-256M misrepresents architecture diagrams
- The pipeline is technically sound but the *VLM quality* is the bottleneck, not
  the architecture

That last point is the real conclusion. The plumbing works. The open question is
which vision model to trust, and that is an accuracy-and-cost decision, not a
design one.
