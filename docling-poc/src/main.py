"""Run the whole POC end to end.

    python -m src.main              # generate test data if needed, then run
    python -m src.main --regen      # rebuild the synthetic corpus first
    python -m src.main --vlm gemini # switch the VLM backend
    python -m src.main --quiet      # summary only, no per-element text

Outputs, all under ``output/``:

    docling/<filename>.json     Docling's own structured document, untouched
    pictures/<filename>/         every picture lifted out of the document
    ocr_results.json            what EasyOCR read, per picture
    vlm_results.json            what the VLM wrote, per picture
    routing.json                the decision for every picture and why
    final_document.json         the unified normalised representation
    citation_chunks.json        platform-facing citation chunk contract
    citations/<filename>.pdf    optional rendered citation PDF for DOCX
    run_report.json             timings, counts, errors, environment
"""

from __future__ import annotations

import argparse
import json
import platform
import sys
import time
from pathlib import Path

from . import reporting as rep
from . import testdata
from .citation import build_citation_page_map, citation_chunks
from .config import Settings, load_settings
from .stage1_docling import (
    ParsedDocument,
    PictureClassifier,
    build_converter,
    parse_document,
)
from .stage2_ocr import build_image_converter, run_ocr
from .stage3_vlm import build_vlm, run_vlm
from .stage4_router import Route, decide, report as report_routing
from .stage5_normalize import NormalizedDocument, normalize, report as report_normalized

#: Files the pipeline will attempt to ingest.
DEFAULT_TARGETS = [
    "onboarding_guide.docx",
    "policy_text.pdf",
    "policy_scanned.pdf",
]


def _environment(settings: Settings) -> dict:
    import docling
    import docling_core

    return {
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "docling": getattr(docling, "__version__", "unknown"),
        "docling_core": getattr(docling_core, "__version__", "unknown"),
        "ocr_engine": settings.ocr_engine,
        "ocr_languages": list(settings.ocr_languages),
        "vlm_backend": settings.vlm_backend,
        "vlm_model": settings.local_vlm_model if settings.vlm_backend == "local" else settings.gemini_model,
        "gemini_key_present": bool(settings.gemini_api_key),
    }


def run(settings: Settings, targets: list[str], quiet: bool = False) -> int:
    started = time.perf_counter()
    settings = type(settings)(**{**settings.__dict__, "verbose": not quiet})
    output = settings.output_dir
    output.mkdir(parents=True, exist_ok=True)
    pictures_root = output / "pictures"
    workdir = Path(settings.input_dir).parent / "output" / "_ocr_work"

    rep.rule("DOCLING POC -- document ingestion experiment")
    rep.kv("input dir", settings.input_dir)
    rep.kv("output dir", output)
    for key, value in _environment(settings).items():
        rep.kv(key, value)

    documents = [settings.input_dir / name for name in targets]
    missing = [path.name for path in documents if not path.exists()]
    if missing:
        rep.status("test data", "FAIL", f"missing: {', '.join(missing)} (run with --regen)")
        return 1
    rep.status("test data", "OK", f"{len(documents)} document(s) found")

    # ---- Stage 1 -----------------------------------------------------------
    rep.step("1", "DOCLING -- the only parser")
    converter = build_converter(settings)
    # One classifier for the whole run: it loads the model once and then labels
    # the pictures the pipeline skipped, which is every DOCX picture.
    classifier = PictureClassifier(enabled=settings.enable_picture_classification)
    parsed_documents: list[ParsedDocument] = []
    for path in documents:
        parsed = parse_document(path, converter, settings, classifier)
        parsed_documents.append(parsed)
        if parsed.docling_json is not None:
            target = output / "docling" / f"{path.stem}.json"
            rep.write_json(target, parsed.docling_json)
            rep.kv("saved docling json", target.relative_to(output.parent))

    citation_maps = {}
    if settings.enable_citation_pdf:
        rep.step("1a", "CITATION PDF -- optional rendered page anchors")
        for parsed in parsed_documents:
            if parsed.path.suffix.lower() != ".docx":
                continue
            try:
                citation_maps[parsed.name] = build_citation_page_map(parsed, converter, settings)
                rep.status(
                    "citation pdf",
                    "OK",
                    str(citation_maps[parsed.name].pdf_path.relative_to(output.parent)),
                )
            except Exception as error:  # noqa: BLE001 - citation support must not hide parsed content
                rep.status("citation pdf", "FAIL", f"{type(error).__name__}: {error}")

    # ---- Stages 2 and 4 interleave: OCR doubles as a routing probe --------
    rep.step("2", "OCR -- Docling + EasyOCR on pictures worth OCRing")
    rep.kv("note", "OCR runs first and its character count feeds the router; "
                   "pictures docling already labelled decorative are skipped")
    image_converter = build_image_converter(settings) if settings.enable_ocr else None
    ocr_by_document: dict[str, list] = {}

    for parsed in parsed_documents:
        if image_converter is None:
            rep.status("ocr", "SKIP", "disabled by configuration")
            ocr_by_document[parsed.name] = []
            continue
        if not parsed.pictures:
            rep.status("ocr", "SKIP", f"{parsed.name}: no pictures")
            ocr_by_document[parsed.name] = []
            continue
        results = run_ocr(parsed, image_converter, settings, workdir)
        ocr_by_document[parsed.name] = results
        for result in results:
            if not result.error:
                rep.kv(
                    f"  {Path(result.picture_ref).name}",
                    f"{result.char_count} chars, mean conf "
                    + (
                        f"{result.mean_confidence:.2f}"
                        if result.mean_confidence is not None and result.mean_confidence >= 0
                        else "n/a"
                    ),
                )

    # ---- Stage 4 -----------------------------------------------------------
    rep.step("4", "ROUTING -- what each picture actually needs")
    rep.kv("rule", "TEXT-HEAVY -> OCR | DIAGRAM/CHART -> VLM | TEXT+LAYOUT -> OCR+VLM | DECORATIVE -> IGNORE")
    decisions_by_document: dict[str, list] = {}
    for parsed in parsed_documents:
        ocr_results = ocr_by_document.get(parsed.name, [])
        ocr_lookup = {result.picture_ref: result for result in ocr_results}
        decisions = [
            decide(picture, ocr_lookup.get(picture.ref), settings)
            for picture in parsed.pictures
        ]
        decisions_by_document[parsed.name] = decisions
        if decisions:
            print(f"\n  {rep.bold(parsed.name)}")
            report_routing(decisions, settings)
        else:
            rep.status("routing", "SKIP", f"{parsed.name}: no pictures")

    # ---- Stage 3 -----------------------------------------------------------
    rep.step("3", "VLM -- only for pictures routed to it")
    backend = build_vlm(settings)
    if not settings.enable_vlm:
        rep.status("vlm", "SKIP", "disabled by configuration")
    elif not backend.available:
        rep.status("vlm", "SKIP", backend.unavailable_reason())
    else:
        rep.kv("backend", backend.name)
    vlm_by_document: dict[str, list] = {}
    for parsed in parsed_documents:
        routed = [
            picture
            for picture, decision in zip(parsed.pictures, decisions_by_document.get(parsed.name, []))
            if decision.route.wants_vlm
        ]
        vlm_by_document[parsed.name] = run_vlm(parsed, backend, settings, routed)

    # ---- Stage 5 -----------------------------------------------------------
    rep.step("5", "NORMALISE -- one flat representation of everything found")
    normalized: list[NormalizedDocument] = []
    for parsed in parsed_documents:
        document = normalize(
            parsed,
            ocr_by_document.get(parsed.name, []),
            vlm_by_document.get(parsed.name, []),
            decisions_by_document.get(parsed.name, []),
            settings,
            citation_item_pages=(citation_maps[parsed.name].item_pages if parsed.name in citation_maps else None),
            citation_picture_pages=(citation_maps[parsed.name].picture_pages if parsed.name in citation_maps else None),
        )
        normalized.append(document)
        report_normalized(document, settings)

    # ---- Outputs -----------------------------------------------------------
    rep.step("6", "OUTPUTS")
    written: list[Path] = []

    def dump(name: str, payload) -> None:
        path = rep.write_json(output / name, payload)
        written.append(path)
        rep.status(name, "OK", f"{path.stat().st_size:,} bytes")

    dump("ocr_results.json", {k: [_ocr_dict(r) for r in v] for k, v in ocr_by_document.items()})
    dump("vlm_results.json", {k: [_vlm_dict(r) for r in v] for k, v in vlm_by_document.items()})
    dump("routing.json", {k: [d.as_dict() for d in v] for k, v in decisions_by_document.items()})
    dump("final_document.json", [d.as_dict() for d in normalized])
    dump(
        "citation_chunks.json",
        [
            chunk
            for document in normalized
            for chunk in citation_chunks(document, citation_maps.get(document.source_document))
        ],
    )

    report_payload = _run_report(settings, parsed_documents, normalized, started, missing)
    dump("run_report.json", report_payload)

    _summary(normalized, decisions_by_document, report_payload)
    return 0 if all(p.status != "FAILURE" for p in parsed_documents) else 1


def _ocr_dict(result) -> dict:
    return {
        "source_document": result.source_document,
        "picture_ref": result.picture_ref,
        "page": result.page,
        "section": result.section,
        "engine": result.engine,
        "lines": [{"text": line.text, "confidence": line.confidence} for line in result.lines],
        "text": result.text,
        "character_count": result.char_count,
        "mean_confidence": result.mean_confidence,
        "duration_seconds": round(result.duration_seconds, 2),
        "error": result.error,
    }


def _vlm_dict(result) -> dict:
    return {
        "source_document": result.source_document,
        "picture_ref": result.picture_ref,
        "page": result.page,
        "section": result.section,
        "model": result.model,
        "backend": result.backend,
        "description": result.description,
        "duration_seconds": round(result.duration_seconds, 2),
        "error": result.error,
    }


def _run_report(settings, parsed, normalized, started, missing) -> dict:
    return {
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "total_duration_seconds": round(time.perf_counter() - started, 2),
        "environment": _environment(settings),
        "missing_inputs": missing,
        "documents": [
            {
                "name": p.name,
                "status": p.status,
                "page_count": p.page_count,
                "docling_seconds": round(p.duration_seconds, 2),
                "label_counts": p.label_counts,
                "pictures": len(p.pictures),
                "error": p.error,
            }
            for p in parsed
        ],
        "element_counts": _element_counts(normalized),
        "warnings": [w for document in normalized for w in document.warnings],
    }


def _element_counts(normalized: list[NormalizedDocument]) -> dict:
    counts: dict[str, int] = {}
    for document in normalized:
        for element in document.elements:
            counts[element.content_type] = counts.get(element.content_type, 0) + 1
    return counts


def _summary(normalized, decisions_by_document, report_payload) -> None:
    rep.rule("SUMMARY -- what this run actually produced")
    rows = []
    for document in normalized:
        produced = {}
        for element in document.elements:
            if element.content_type != "image_skipped":
                produced[element.content_type] = produced.get(element.content_type, 0) + 1
        routes = {}
        for decision in decisions_by_document.get(document.source_document, []):
            routes[decision.route.value] = routes.get(decision.route.value, 0) + 1
        rows.append(
            [
                document.source_document,
                str(document.page_count or "-"),
                str(len(document.elements)),
                ", ".join(f"{k}={v}" for k, v in sorted(produced.items())) or "-",
                ", ".join(f"{k}={v}" for k, v in sorted(routes.items())) or "-",
            ]
        )
    rep.table(rows, ["document", "pages", "elements", "by type", "routing"])
    rep.kv("total elements", report_payload["element_counts"])
    rep.kv("total runtime", f"{report_payload['total_duration_seconds']}s")
    warnings = report_payload["warnings"]
    if warnings:
        print()
        for warning in warnings:
            rep.status("warning", "FAIL", warning)
    else:
        print()
        rep.status("no errors or warnings", "OK")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Docling ingestion POC")
    parser.add_argument("--regen", action="store_true", help="rebuild the synthetic test corpus first")
    parser.add_argument("--vlm", choices=["local", "gemini"], help="override the VLM backend")
    parser.add_argument("--quiet", action="store_true", help="summary only")
    parser.add_argument("--no-vlm", action="store_true", help="skip the VLM stage entirely")
    parser.add_argument("--no-ocr", action="store_true", help="skip the OCR stage entirely")
    parser.add_argument(
        "--citation-pdf",
        action="store_true",
        help="render DOCX files to PDF and use rendered pages for citations",
    )
    parser.add_argument("targets", nargs="*", help="file names inside input/")
    args = parser.parse_args(argv)

    settings = load_settings()
    if args.vlm:
        import dataclasses

        settings = dataclasses.replace(settings, vlm_backend=args.vlm)
    if args.no_vlm:
        import dataclasses

        settings = dataclasses.replace(settings, enable_vlm=False)
    if args.no_ocr:
        import dataclasses

        settings = dataclasses.replace(settings, enable_ocr=False)
    if args.citation_pdf:
        import dataclasses

        settings = dataclasses.replace(settings, enable_citation_pdf=True)

    if args.regen:
        rep.rule("GENERATING SYNTHETIC TEST DATA")
        for name, path in testdata.build_all(settings.input_dir).items():
            rep.status(name, "OK", f"{path.stat().st_size:,} bytes")

    started = time.perf_counter()
    return run(settings, args.targets or DEFAULT_TARGETS, quiet=args.quiet)


if __name__ == "__main__":
    raise SystemExit(main())
