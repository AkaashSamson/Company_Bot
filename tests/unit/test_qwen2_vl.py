"""Unit tests for Qwen2-VL visual understanding engine, contract, and integration.

These tests use mocked processors and models so they run in milliseconds
without downloading or executing heavy neural network weights during CI/test runs.
"""

from __future__ import annotations

import json
from io import BytesIO
from unittest.mock import MagicMock, patch

import pytest
from PIL import Image

from app.domain.ports.document_processing import SectionHeading
from app.domain.ports.visual_contract import VisualOutputContract
from app.infrastructure.document.visual_enrichment import PictureFacts, VisualEnricher
from app.infrastructure.document.vlm_engine import OllamaQwen2VLEngine, Qwen2VLEngine
from app.infrastructure.document.vlm_factory import clear_vlm_engine_cache, get_vlm_engine
from app.use_cases.ingestion.document_processing import build_chunk_records_from_processed
from app.domain.ports.document_processing import ProcessedDocument, ProcessedChunk


def _make_test_image_bytes(color: str = "blue", size: tuple[int, int] = (100, 100)) -> bytes:
    img = Image.new("RGB", size, color=color)
    buffer = BytesIO()
    img.save(buffer, format="PNG")
    return buffer.getvalue()


def _dummy_picture(ref: str = "#/pictures/0", label: str = "flow_chart", page: int = 1) -> PictureFacts:
    return PictureFacts(
        ref=ref,
        image_bytes=_make_test_image_bytes(),
        page_number=page,
        section_path=(SectionHeading(level=1, title="Architecture"),),
        classifications=((label, 0.95),),
    )


# =========================================================================
# 1. VisualOutputContract tests
# =========================================================================

def test_visual_output_contract_defaults():
    contract = VisualOutputContract()
    assert contract.visual_type == "other"
    assert contract.summary == ""
    assert contract.entities == []
    assert contract.relationships == []
    assert contract.visible_text == []
    assert contract.uncertain_items == []
    assert contract.source_reference == ""


def test_visual_output_contract_to_search_text():
    contract = VisualOutputContract(
        visual_type="architecture_diagram",
        summary="A microservices ingestion pipeline.",
        entities=["API Gateway", "Docling Parser", "ChromaDB"],
        relationships=["API Gateway -> Docling: raw docs", "Docling -> ChromaDB: indexed chunks"],
        visible_text=["Port 8000", "v1.0"],
        uncertain_items=["unclear cache layer"],
        source_reference="#/pictures/1",
    )
    search_text = contract.to_search_text()
    assert "Visual type: architecture_diagram" in search_text
    assert "Summary: A microservices ingestion pipeline." in search_text
    assert "Components: API Gateway, Docling Parser, ChromaDB" in search_text
    assert "Flows: API Gateway -> Docling: raw docs; Docling -> ChromaDB: indexed chunks" in search_text
    assert "Labels: Port 8000, v1.0" in search_text
    assert "Uncertain: unclear cache layer" in search_text
    # __str__ should match to_search_text
    assert str(contract) == search_text


def test_visual_output_contract_to_metadata():
    contract = VisualOutputContract(
        visual_type="flowchart",
        summary="User authentication flow.",
        entities=["User", "AuthService", "LDAP"],
        relationships=["User -> AuthService: Login"],
        visible_text=["Submit"],
        uncertain_items=[],
        source_reference="#/pictures/2",
    )
    meta = contract.to_metadata()
    assert meta["visual_type"] == "flowchart"
    assert meta["summary"] == "User authentication flow."
    assert meta["entities"] == "User, AuthService, LDAP"
    assert meta["relationships"] == "User -> AuthService: Login"
    assert meta["visible_text"] == "Submit"
    assert meta["uncertain_items"] == ""
    assert meta["source_reference"] == "#/pictures/2"
    assert meta["entity_count"] == 3
    assert meta["relationship_count"] == 1


# =========================================================================
# 2. Qwen2VLEngine Output Parsing & Bounded Recovery tests
# =========================================================================

def test_parse_contract_clean_json():
    raw_json = json.dumps({
        "visual_type": "chart",
        "summary": "Quarterly revenue growth.",
        "entities": ["Q1", "Q2", "Q3", "Q4"],
        "relationships": ["Q1 -> Q2: +15%"],
        "visible_text": ["USD Millions", "Revenue 2026"],
        "uncertain_items": [],
    })
    contract = Qwen2VLEngine._parse_contract(raw_json, picture_ref="#/pictures/chart_1")
    assert contract.visual_type == "chart"
    assert contract.summary == "Quarterly revenue growth."
    assert contract.entities == ["Q1", "Q2", "Q3", "Q4"]
    assert contract.relationships == ["Q1 -> Q2: +15%"]
    assert contract.visible_text == ["USD Millions", "Revenue 2026"]
    assert contract.source_reference == "#/pictures/chart_1"


def test_parse_contract_markdown_fenced_json():
    raw_markdown = (
        "```json\n"
        "{\n"
        '  "visual_type": "architecture_diagram",\n'
        '  "summary": "Kubernetes cluster architecture",\n'
        '  "entities": ["Ingress", "Worker Node"],\n'
        '  "relationships": ["Ingress -> Worker Node"],\n'
        '  "visible_text": ["Kubelet"],\n'
        '  "uncertain_items": []\n'
        "}\n"
        "```"
    )
    contract = Qwen2VLEngine._parse_contract(raw_markdown, picture_ref="#/pictures/k8s")
    assert contract.visual_type == "architecture_diagram"
    assert contract.entities == ["Ingress", "Worker Node"]
    assert contract.source_reference == "#/pictures/k8s"


def test_parse_contract_surrounding_narrative():
    raw = (
        "Here is the detailed visual analysis:\n"
        '{"visual_type": "screenshot", "summary": "Login page with username field", "entities": ["Login Button"], "relationships": [], "visible_text": ["Username", "Password"], "uncertain_items": []}\n'
        "Hope this helps!"
    )
    contract = Qwen2VLEngine._parse_contract(raw, picture_ref="#/pictures/login")
    assert contract.visual_type == "screenshot"
    assert contract.summary == "Login page with username field"
    assert contract.entities == ["Login Button"]


def test_parse_contract_malformed_json_bounded_recovery():
    malformed = "This is not valid JSON at all. It shows a server topology with three nodes."
    contract = Qwen2VLEngine._parse_contract(malformed, picture_ref="#/pictures/corrupt_json")
    assert contract.visual_type == "other"
    assert "This is not valid JSON" in contract.summary
    assert "unstructured_vlm_output" in contract.uncertain_items
    assert contract.source_reference == "#/pictures/corrupt_json"


def test_parse_contract_empty_string():
    contract = Qwen2VLEngine._parse_contract("", picture_ref="#/pictures/empty")
    assert contract.visual_type == "other"
    assert "no description" in contract.summary.lower()


# =========================================================================
# 3. Qwen2VLEngine / OllamaQwen2VLEngine Lifecycle & API tests (Mocked)
# =========================================================================

def test_ollama_qwen2_vl_lazy_client_initialization():
    engine = OllamaQwen2VLEngine(model_name="qwen2-vl:2b", base_url="http://localhost:11434")
    assert engine._client is None
    assert engine.model_id == "qwen2-vl:2b"
    assert engine.base_url == "http://localhost:11434"
    assert engine.device == "ollama"

    client = engine._get_client()
    assert client is not None
    assert engine._client is client
    # Calling again reuses the same client
    assert engine._get_client() is client


@patch("httpx.Client.post")
def test_ollama_qwen2_vl_describe_posts_payload_and_parses_contract(mock_post):
    mock_post.return_value.json.return_value = {
        "message": {
            "content": json.dumps({
                "visual_type": "architecture_diagram",
                "summary": "Ollama VLM architecture",
                "entities": ["FastAPI", "Ollama", "Qwen2-VL"],
                "relationships": ["FastAPI -> Ollama: HTTP", "Ollama -> Qwen2-VL: AVX2"],
                "visible_text": ["Port 11434"],
                "uncertain_items": [],
            })
        },
        "eval_count": 42,
    }
    mock_post.return_value.raise_for_status = lambda: None

    engine = OllamaQwen2VLEngine(model_name="qwen2-vl:2b", base_url="http://localhost:11434")
    image_bytes = _make_test_image_bytes()
    contract = engine.describe(image_bytes, ocr_context="Some OCR text", picture_ref="#/pictures/ollama_1")

    assert mock_post.called
    assert contract.visual_type == "architecture_diagram"
    assert contract.summary == "Ollama VLM architecture"
    assert contract.entities == ["FastAPI", "Ollama", "Qwen2-VL"]
    assert contract.source_reference == "#/pictures/ollama_1"


@patch("httpx.Client.post")
def test_ollama_qwen2_vl_service_error_returns_fallback_contract(mock_post):
    import httpx
    mock_post.side_effect = httpx.ConnectError("Connection refused")

    engine = OllamaQwen2VLEngine(model_name="qwen2-vl:2b")
    image_bytes = _make_test_image_bytes()
    contract = engine.describe(image_bytes, picture_ref="#/pictures/fail_1")

    assert contract.visual_type == "other"
    assert "unavailable" in contract.summary.lower()
    assert "vlm_service_unavailable" in contract.uncertain_items
    assert contract.source_reference == "#/pictures/fail_1"


def test_qwen2_vl_empty_and_corrupt_image_handling():
    engine = Qwen2VLEngine()
    empty_res = engine.describe(b"", picture_ref="#/empty")
    assert "image_empty" in empty_res.uncertain_items

    corrupt_res = engine.describe(b"not an image", picture_ref="#/corrupt")
    assert "image_corrupt_or_unsupported" in corrupt_res.uncertain_items


# =========================================================================
# 4. Factory and Engine Cache tests
# =========================================================================

def test_vlm_factory_singleton_caching():
    clear_vlm_engine_cache()
    engine1 = get_vlm_engine("qwen2-vl:2b")
    engine2 = get_vlm_engine("qwen2-vl:2b")
    assert engine1 is engine2
    assert isinstance(engine1, Qwen2VLEngine)
    clear_vlm_engine_cache()


# =========================================================================
# 5. VisualEnricher Integration with Mocked VLM Engine
# =========================================================================

class MockVLMEngine(Qwen2VLEngine):
    def __init__(self, contract: VisualOutputContract):
        super().__init__()
        self._contract = contract
        self.calls: list[dict] = []

    def describe(self, image_bytes: bytes, ocr_context: str = "", picture_ref: str = "") -> VisualOutputContract:
        self.calls.append({
            "bytes_len": len(image_bytes),
            "ocr_context": ocr_context,
            "picture_ref": picture_ref,
        })
        return self._contract


def test_visual_enricher_uses_vlm_engine_and_emits_structured_chunk():
    contract = VisualOutputContract(
        visual_type="architecture_diagram",
        summary="KnowLayer RAG flow",
        entities=["Parser", "Embedder", "Chroma"],
        relationships=["Parser -> Embedder", "Embedder -> Chroma"],
        visible_text=["RAG v3"],
        source_reference="#/pictures/0",
    )
    mock_engine = MockVLMEngine(contract)
    enricher = VisualEnricher(model_name="Qwen/Qwen2-VL-2B-Instruct", vlm_engine=mock_engine)

    pic = _dummy_picture(ref="#/pictures/0", label="flow_chart")
    with patch.object(enricher, "_pictures", return_value=[pic]), \
         patch.object(enricher, "_classify", return_value=None), \
         patch.object(enricher, "_ocr", return_value="Existing OCR text"):

        chunks = enricher.enrich(document=MagicMock(), facts={}, starting_index=10)

    assert len(chunks) == 2  # 1 OCR chunk + 1 VLM chunk
    ocr_chunk, vlm_chunk = chunks[0], chunks[1]

    # Verify OCR chunk
    assert ocr_chunk.metadata["produced_by"] == "docling+easyocr"
    assert ocr_chunk.text == "Existing OCR text"

    # Verify VLM chunk
    assert vlm_chunk.metadata["produced_by"] == "qwen2-vl"
    assert vlm_chunk.metadata["visual_type"] == "architecture_diagram"
    assert vlm_chunk.metadata["summary"] == "KnowLayer RAG flow"
    assert vlm_chunk.metadata["entities"] == "Parser, Embedder, Chroma"
    assert vlm_chunk.metadata["relationships"] == "Parser -> Embedder; Embedder -> Chroma"
    assert vlm_chunk.metadata["entity_count"] == 3
    assert vlm_chunk.metadata["relationship_count"] == 2
    assert vlm_chunk.metadata["review_required"] is True

    # Verify search text format for embedding
    assert "Visual type: architecture_diagram" in vlm_chunk.text
    assert "Components: Parser, Embedder, Chroma" in vlm_chunk.text

    # Verify OCR context was passed to VLM engine to prevent duplicate text extraction
    assert len(mock_engine.calls) == 1
    assert mock_engine.calls[0]["ocr_context"] == "Existing OCR text"
    assert mock_engine.calls[0]["picture_ref"] == "#/pictures/0"





def test_visual_chunks_pass_through_to_chroma_records():
    """Verify that visual metadata fields pass through build_chunk_records_from_processed without loss."""
    visual_chunk = ProcessedChunk(
        text="Visual type: flowchart\nSummary: Order fulfillment flow.",
        index=0,
        page_number=2,
        section_path=(SectionHeading(level=1, title="Operations"),),
        content_type="text",
        metadata={
            "produced_by": "qwen2-vl",
            "verified": False,
            "review_required": True,
            "picture_ref": "#/pictures/5",
            "routing": "OCR+VLM",
            "docling_class": "flow_chart",
            "visual_type": "flowchart",
            "summary": "Order fulfillment flow.",
            "entities": "Warehouse, Carrier, Customer",
            "relationships": "Warehouse -> Carrier: dispatch",
            "entity_count": 3,
            "relationship_count": 1,
            "model": "Qwen/Qwen2-VL-2B-Instruct",
        },
    )
    doc = ProcessedDocument(
        chunks=(visual_chunk,),
        file_type="pdf",
        page_count=2,
        outline=(SectionHeading(level=1, title="Operations"),),
    )

    records = build_chunk_records_from_processed(
        doc,
        document_id="DOC-999",
        project_id="PROJ-01",
        source="operations_manual.pdf",
    )

    assert len(records) == 1
    record = records[0]
    meta = record["metadata"]
    assert meta["document_id"] == "DOC-999"
    assert meta["project_id"] == "PROJ-01"
    assert meta["produced_by"] == "qwen2-vl"
    assert meta["visual_type"] == "flowchart"
    assert meta["summary"] == "Order fulfillment flow."
    assert meta["entities"] == "Warehouse, Carrier, Customer"
    assert meta["relationships"] == "Warehouse -> Carrier: dispatch"
    assert meta["entity_count"] == 3
    assert meta["picture_ref"] == "#/pictures/5"
    assert meta["routing"] == "OCR+VLM"
    assert meta["docling_class"] == "flow_chart"
    assert meta["model"] == "Qwen/Qwen2-VL-2B-Instruct"


# =========================================================================
# 6. PDF, DOCX, and Markdown format processing with Visual Enrichment
# =========================================================================

def test_docling_processor_with_visual_enrichment_pdf():
    from app.infrastructure.document.docling_processor import DoclingDocumentProcessor
    from tests.unit.test_docling_processor import FakeChunk, FakeConverter, FakeDocument, FakeItem, FakeChunker

    # Document with text item and picture item
    text_item = FakeItem("#/texts/0", "text", "System Overview", page_no=1)
    picture_item = FakeItem("#/pictures/0", "picture", "", page_no=1)
    raw_doc = FakeDocument([(text_item, 1), (picture_item, 1)])

    contract = VisualOutputContract(
        visual_type="architecture_diagram",
        summary="PDF architecture overview",
        entities=["Ingestion", "Chroma"],
        source_reference="#/pictures/0",
    )
    mock_vlm = MockVLMEngine(contract)
    enricher = VisualEnricher(model_name="Qwen/Qwen2-VL-2B-Instruct", vlm_engine=mock_vlm)

    pic = _dummy_picture(ref="#/pictures/0", label="diagram", page=1)
    with patch.object(enricher, "_pictures", return_value=[pic]), \
         patch.object(enricher, "_classify", return_value=None), \
         patch.object(enricher, "_ocr", return_value=""):

        processor = DoclingDocumentProcessor(
            converter=FakeConverter(raw_doc, pages=[1]),
            chunker=FakeChunker([FakeChunk("System Overview", [text_item])]),
            visual_enricher=enricher,
        )
        with patch("app.infrastructure.document.docling_processor.DOCLING_VISUAL_ENRICHMENT_ENABLED", True):
            processed = processor.process(b"%PDF-fake-content", "document.pdf")

    assert len(processed.chunks) == 2  # 1 text chunk + 1 visual chunk
    assert processed.chunks[0].text == "System Overview"
    assert processed.chunks[1].metadata["produced_by"] == "qwen2-vl"
    assert processed.chunks[1].metadata["visual_type"] == "architecture_diagram"
    assert processed.chunks[1].page_number == 1
    assert processed.file_type == "pdf"


def test_docling_processor_with_visual_enrichment_docx():
    from app.infrastructure.document.docling_processor import DoclingDocumentProcessor
    from tests.unit.test_docling_processor import FakeChunk, FakeConverter, FakeDocument, FakeItem, FakeChunker

    heading_item = FakeItem("#/texts/0", "section_header", "Section 1", page_no=None)
    picture_item = FakeItem("#/pictures/1", "picture", "", page_no=None)
    raw_doc = FakeDocument([(heading_item, 1), (picture_item, 1)])

    contract = VisualOutputContract(
        visual_type="chart",
        summary="DOCX sales trend",
        entities=["Q1", "Q2"],
        source_reference="#/pictures/1",
    )
    mock_vlm = MockVLMEngine(contract)
    enricher = VisualEnricher(model_name="Qwen/Qwen2-VL-2B-Instruct", vlm_engine=mock_vlm)

    pic = _dummy_picture(ref="#/pictures/1", label="bar_chart", page=None)
    with patch.object(enricher, "_pictures", return_value=[pic]), \
         patch.object(enricher, "_classify", return_value=None), \
         patch.object(enricher, "_ocr", return_value=""):

        processor = DoclingDocumentProcessor(
            converter=FakeConverter(raw_doc),
            chunker=FakeChunker([FakeChunk("Sales Section", [heading_item])]),
            visual_enricher=enricher,
        )
        with patch("app.infrastructure.document.docling_processor.DOCLING_VISUAL_ENRICHMENT_ENABLED", True), \
             patch("app.infrastructure.document.docling_processor.DOCLING_CITATION_PDF_ENABLED", False):
            processed = processor.process(b"PK-docx-fake-content", "report.docx")

    assert len(processed.chunks) == 2
    assert processed.chunks[1].metadata["visual_type"] == "chart"
    assert processed.chunks[1].metadata["produced_by"] == "qwen2-vl"
    assert processed.file_type == "docx"


def test_docling_processor_with_visual_enrichment_markdown():
    from app.infrastructure.document.docling_processor import DoclingDocumentProcessor
    from tests.unit.test_docling_processor import FakeChunk, FakeConverter, FakeDocument, FakeItem, FakeChunker

    text_item = FakeItem("#/texts/0", "text", "# Markdown title\nParagraph content.", page_no=None)
    raw_doc = FakeDocument([(text_item, 1)])

    enricher = VisualEnricher(model_name="Qwen/Qwen2-VL-2B-Instruct")
    # For a markdown document without pictures, visual enricher returns empty tuple
    with patch.object(enricher, "_pictures", return_value=[]):
        processor = DoclingDocumentProcessor(
            converter=FakeConverter(raw_doc),
            chunker=FakeChunker([FakeChunk("Markdown title\nParagraph content.", [text_item])]),
            visual_enricher=enricher,
        )
        with patch("app.infrastructure.document.docling_processor.DOCLING_VISUAL_ENRICHMENT_ENABLED", True):
            processed = processor.process(b"# Markdown title", "notes.md")

    assert len(processed.chunks) == 1
    assert processed.chunks[0].text == "Markdown title\nParagraph content."
    assert processed.file_type == "md"


def test_selective_routing_decorative_picture_skipped():
    mock_vlm = MockVLMEngine(VisualOutputContract(summary="Should not run"))
    enricher = VisualEnricher(model_name="Qwen/Qwen2-VL-2B-Instruct", vlm_engine=mock_vlm)

    # Decorative picture (logo)
    decorative_pic = _dummy_picture(ref="#/pictures/logo", label="logo")
    with patch.object(enricher, "_pictures", return_value=[decorative_pic]), \
         patch.object(enricher, "_classify", return_value=None), \
         patch("app.infrastructure.document.visual_enrichment.DOCLING_SKIP_DECORATIVE_OCR", True):

        chunks = enricher.enrich(document=MagicMock(), facts={}, starting_index=0)

    # Decorative picture is completely skipped
    assert len(chunks) == 0
    assert len(mock_vlm.calls) == 0

