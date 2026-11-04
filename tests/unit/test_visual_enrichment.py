from app.domain.ports.document_processing import SectionHeading
from app.infrastructure.document.visual_enrichment import PictureFacts, VisualEnricher


def _picture(label: str = "", text: str = "") -> PictureFacts:
    classifications = ((label, 0.9),) if label else ()
    return PictureFacts(
        ref="#/pictures/0",
        image_bytes=b"image",
        page_number=None,
        section_path=(SectionHeading(level=1, title="Policy"),),
        classifications=classifications,
    )


def test_chart_routes_directly_to_vlm():
    assert VisualEnricher._route("bar_chart", "Q1 32 Q2 45") == "VLM"


def test_table_routes_directly_to_vlm():
    assert VisualEnricher._route("table", "Q1 32 Q2 45") == "VLM"


def test_unknown_picture_with_text_routes_to_vlm():
    assert VisualEnricher._route("", "visible text") == "VLM"


def test_unknown_picture_without_text_routes_to_vlm():
    assert VisualEnricher._route("", "") == "VLM"


def test_decorative_picture_is_ignored():
    assert VisualEnricher._route("logo", "brand") == "IGNORE"


def test_visual_chunk_preserves_review_metadata():
    chunk = VisualEnricher._chunk(
        text="A diagram description",
        index=4,
        picture=_picture("flow_chart"),
        route="VLM",
        produced_by="qwen2-vl",
        verified=False,
        review_required=True,
        extra={"model": "test-model"},
    )
    assert chunk.content_type == "text"
    assert chunk.metadata["produced_by"] == "qwen2-vl"
    assert chunk.metadata["verified"] is False
    assert chunk.metadata["review_required"] is True
    assert chunk.metadata["picture_ref"] == "#/pictures/0"


def test_enrich_multiple_candidates_in_deterministic_order(monkeypatch):
    enricher = VisualEnricher()
    # Stub _pictures to return two pictures
    p1 = _picture("flow_chart")
    p2 = PictureFacts(
        ref="#/pictures/1",
        image_bytes=b"image2",
        page_number=2,
        section_path=(SectionHeading(level=1, title="Policy"),),
        classifications=(("bar_chart", 0.9),),
    )
    monkeypatch.setattr(enricher, "_pictures", lambda doc, facts: [p1, p2])
    monkeypatch.setattr(enricher, "_classify", lambda doc, pics: None)
    monkeypatch.setattr(enricher, "_label", lambda pic: "flow_chart" if pic.ref == "#/pictures/0" else "bar_chart")
    monkeypatch.setattr(enricher, "_route", lambda label: "VLM")
    monkeypatch.setattr(enricher, "_describe", lambda bytes_data, picture_ref=None: f"Description for {picture_ref}")

    chunks = enricher.enrich(None, {}, starting_index=0)
    assert len(chunks) == 2
    assert chunks[0].text == "Description for #/pictures/0"
    assert chunks[1].text == "Description for #/pictures/1"
    assert chunks[0].index == 0
    assert chunks[1].index == 1

