"""
tests/unit/test_chunk_normalizer.py
Tier 1 Core Functional & Pass-by-Pass Tests (TC-F01 through TC-F14).
"""

import pytest
from app.infrastructure.document.chunk_normalizer import (
    ChunkNormalizer,
    NormalizedChunk,
)


@pytest.fixture
def normalizer() -> ChunkNormalizer:
    return ChunkNormalizer(hard_token_ceiling=245, coalesce_max_tokens=220, min_fragment_tokens=55)


def _meta(**kwargs):
    base = {
        "source_filename": "employee_handbook.pdf",
        "document_id": "DOC-001",
        "project_id": "PROJ-HR",
        "page_number": 1,
        "heading_hierarchy": "HR > Benefits",
        "chunk_type": "text",
    }
    base.update(kwargs)
    return base


# TC-F01
def test_pass1_strip_boilerplate_headers(normalizer: ChunkNormalizer):
    chunk = NormalizedChunk(
        chunk_id="c1",
        text="Page 1 of 5\nAll full-time employees receive dental coverage.\nConfidential - Internal Use Only",
        metadata=_meta(),
    )
    res = normalizer._pass1_sanitize_and_heal_boundaries([chunk])
    assert len(res) == 1
    assert "Page 1 of 5" not in res[0].text
    assert "Confidential" not in res[0].text
    assert "dental coverage" in res[0].text


# TC-F02
def test_pass1_orphan_heading_relocation(normalizer: ChunkNormalizer):
    c1 = NormalizedChunk(
        chunk_id="c1",
        text="Annual leave accrues monthly.\n### Bereavement Leave",
        metadata=_meta(),
    )
    c2 = NormalizedChunk(
        chunk_id="c2",
        text="Employees are granted up to 5 paid days for immediate family loss.",
        metadata=_meta(),
    )
    res = normalizer._pass1_sanitize_and_heal_boundaries([c1, c2])
    assert "### Bereavement Leave" not in res[0].text
    assert res[1].text.startswith("### Bereavement Leave")
    assert "Bereavement Leave" in res[1].metadata["heading_hierarchy"]


# TC-F03
def test_pass1_heal_lowercase_mid_sentence(normalizer: ChunkNormalizer):
    c1 = NormalizedChunk(
        chunk_id="c1",
        text="Employees requesting sabbatical leave must submit an application to",
        metadata=_meta(),
    )
    c2 = NormalizedChunk(
        chunk_id="c2",
        text="their department head 60 days in advance. Approval depends on tenure.",
        metadata=_meta(),
    )
    res = normalizer._pass1_sanitize_and_heal_boundaries([c1, c2])
    assert res[0].text.endswith("60 days in advance.")
    assert res[1].text == "Approval depends on tenure."


# TC-F04
def test_pass2_collapse_toc_dot_leaders(normalizer: ChunkNormalizer):
    c1 = NormalizedChunk(chunk_id="c1", text="Benefits ................ 42", metadata=_meta())
    res = normalizer._pass3_strip_repeated_noise_and_punctuation([c1])
    assert res[0].text == "Benefits 42"


# TC-F05
def test_pass2_collapse_repeated_punctuation(normalizer: ChunkNormalizer):
    c1 = NormalizedChunk(chunk_id="c1", text="What is covered???? Everything!!!!", metadata=_meta())
    res = normalizer._pass3_strip_repeated_noise_and_punctuation([c1])
    assert res[0].text == "What is covered? Everything!"


# TC-F06
def test_pass2_preserve_markdown_table_syntax(normalizer: ChunkNormalizer):
    table_md = "| Tier | Days |\n|---|---|\n| L1 | 15 |"
    c1 = NormalizedChunk(chunk_id="c1", text=table_md, metadata=_meta(chunk_type="table"))
    res = normalizer._pass3_strip_repeated_noise_and_punctuation([c1])
    assert "|---|---|" in res[0].text
    assert "| L1 | 15 |" in res[0].text


# TC-F07
def test_pass3_coalesce_forward_low_density(normalizer: ChunkNormalizer):
    stub = NormalizedChunk(chunk_id="c1", text="Eligibility rules follow below:", metadata=_meta())
    nxt = NormalizedChunk(
        chunk_id="c2",
        text="Full-time staff working at least 30 hours per week qualify automatically after 90 days.",
        metadata=_meta(),
    )
    res = normalizer._pass4_standardize_chunk_lengths([stub, nxt])
    assert len(res) == 1
    assert res[0].text.startswith("Eligibility rules follow below:")


# TC-F08
def test_pass3_coalesce_backward_low_density(normalizer: ChunkNormalizer):
    prev = NormalizedChunk(
        chunk_id="c1",
        text=("Standard parental leave provides twelve weeks of paid time off for birth or adoption. " * 2).strip(),
        metadata=_meta(),
    )
    tail_stub = NormalizedChunk(chunk_id="c2", text="Note: Contractors are excluded.", metadata=_meta())
    res = normalizer._pass4_standardize_chunk_lengths([prev, tail_stub])
    assert len(res) == 1
    assert res[0].text.endswith("Note: Contractors are excluded.")


# TC-F09
def test_pass3_orphan_stub_scope_enrichment(normalizer: ChunkNormalizer):
    isolated = NormalizedChunk(chunk_id="c1", text="See HR Portal.", metadata=_meta())
    res = normalizer._pass4_standardize_chunk_lengths([isolated])
    assert len(res) == 1
    assert "[Document Scope:" in res[0].text
    assert res[0].metadata.get("scope_enriched") is True


# TC-F10
def test_pass4_split_oversized_prose_zero_loss(normalizer: ChunkNormalizer):
    sentences = [f"Policy clause number {i} mandates strict compliance with safety rules." for i in range(35)]
    original_text = " ".join(sentences)
    c1 = NormalizedChunk(chunk_id="c1", text=original_text, metadata=_meta())

    res = normalizer._pass2_enforce_token_budget_zero_data_loss([c1])
    assert len(res) >= 2
    assert "<!-- CUTOFF_END -->" in res[0].text
    assert "<!-- CUTOFF_START -->" in res[1].text

    # Verify 0% word loss
    reconstructed = " ".join(
        r.text.replace("<!-- CUTOFF_START -->", "").replace("<!-- CUTOFF_END -->", "").strip()
        for r in res
    )
    for word in original_text.split():
        assert word in reconstructed


# TC-F11
def test_pass4_split_table_clones_headers(normalizer: ChunkNormalizer):
    header = "| Benefit Tier | Annual Cap | Co-Pay Rate | Approval Authority |\n|---|---|---|---|"
    rows = [
        f"| Executive Tier {i} | $15,000 per calendar year | 10% after deductible | VP of Human Resources |"
        for i in range(18)
    ]
    c1 = NormalizedChunk(chunk_id="tbl1", text=header + "\n" + "\n".join(rows), metadata=_meta(chunk_type="table"))
    res = normalizer._pass2_enforce_token_budget_zero_data_loss([c1])
    assert len(res) >= 2
    for sub in res:
        assert "| Benefit Tier | Annual Cap | Co-Pay Rate | Approval Authority |" in sub.text
        assert "|---|---|---|---|" in sub.text


# TC-F12
def test_pass5_canonical_metadata_contract(normalizer: ChunkNormalizer):
    c1 = NormalizedChunk(chunk_id="c1", text="Valid policy text for testing.", metadata={"source_file": "hr.pdf"})
    res = normalizer.normalize_chunks([c1])
    required_keys = {
        "source_filename",
        "document_id",
        "project_id",
        "page_number",
        "hierarchy_path",
        "heading_hierarchy",
        "section_heading",
        "chunk_type",
        "content_hash",
    }
    assert required_keys.issubset(set(res[0].metadata.keys()))


# TC-F13
def test_pass5_sha256_deduplication(normalizer: ChunkNormalizer):
    c1 = NormalizedChunk(chunk_id="c1", text="Duplicate policy statement here.", metadata=_meta())
    c2 = NormalizedChunk(chunk_id="c2", text="Duplicate policy statement here.", metadata=_meta())
    res = normalizer._pass5_inject_context_and_finalize([c1, c2])
    assert len(res) == 1


# TC-F14
def test_stitch_cutoff_chunks_bidirectional(normalizer: ChunkNormalizer):
    sentences = [f"Detailed rule {i} applies to all remote staff members in India." for i in range(30)]
    c1 = NormalizedChunk(chunk_id="c1", text=" ".join(sentences), metadata=_meta())
    parts = normalizer._pass2_enforce_token_budget_zero_data_loss([c1])
    assert len(parts) >= 2

    ab = normalizer.stitch_cutoff_chunks(parts[0], parts[1])
    ba = normalizer.stitch_cutoff_chunks(parts[1], parts[0])
    assert ab.text == ba.text
    assert "CUTOFF" not in ab.text


# Balanced Splitting & Micro-Fragment Prevention Tests (150 + 150 Handling)
def test_pass2_balanced_split_oversized_prose_prevents_micro_fragments(normalizer: ChunkNormalizer):
    """
    Verifies that an oversized ~300 token section splits into balanced ~150 + 150
    chunks instead of greedy 250 + 50, preventing tail micro-fragment creation.
    """
    # 16 sentences of ~18 tokens each => ~290 tokens total (ideal for 150 + 150 split)
    sentences = [
        f"Employee conduct clause {i} requires all personnel to adhere strictly to confidentiality and ethics."
        for i in range(16)
    ]
    original_text = " ".join(sentences)
    total_tokens = normalizer.count_tokens(original_text)
    assert 250 <= total_tokens <= 330

    c1 = NormalizedChunk(chunk_id="c1", text=original_text, metadata=_meta())
    res = normalizer._pass2_enforce_token_budget_zero_data_loss([c1])

    assert len(res) == 2
    tok_0 = normalizer.count_tokens(res[0].text)
    tok_1 = normalizer.count_tokens(res[1].text)

    # Neither chunk should be a micro-fragment (< 55 tokens)
    assert tok_0 >= 55, f"Chunk 0 is a micro-fragment ({tok_0} tokens)"
    assert tok_1 >= 55, f"Chunk 1 is a micro-fragment ({tok_1} tokens)"

    # Both chunks should be balanced within 100-180 tokens (around 150 tokens)
    assert 110 <= tok_0 <= 190, f"Expected chunk 0 to be balanced near 150, got {tok_0}"
    assert 110 <= tok_1 <= 190, f"Expected chunk 1 to be balanced near 150, got {tok_1}"
    assert abs(tok_0 - tok_1) <= 60, f"Expected balanced partition, got diff {abs(tok_0 - tok_1)}"

    # Cutoff tags present for provenance
    assert "<!-- CUTOFF_END -->" in res[0].text
    assert "<!-- CUTOFF_START -->" in res[1].text


def test_pass4_balanced_rebalance_when_prev_full_and_next_different(normalizer: ChunkNormalizer):
    """
    When `curr` is low density (< 55 tokens), `prev` is full (> 200 tokens) in the same
    section, and `nxt` is in a different section:
    Instead of abandoning `curr` as an isolated micro-fragment (250 + 50),
    it rebalances `prev` and `curr` to ~150 + 150.
    """
    # Full prev chunk in section "Benefits" (~210 tokens)
    prev_sents = [
        f"Benefit clause number {i} provides comprehensive healthcare coverage for all dependents."
        for i in range(18)
    ]
    prev_chunk = NormalizedChunk(
        chunk_id="c1",
        text=" ".join(prev_sents),
        metadata=_meta(heading_hierarchy="HR > Benefits"),
    )

    # Low-density tail chunk in section "Benefits" (~35 tokens)
    curr_sents = [
        "Dependent enrollment must be submitted within 30 days of the qualifying life event.",
        "Late submissions require executive approval from HR director.",
    ]
    curr_chunk = NormalizedChunk(
        chunk_id="c2",
        text=" ".join(curr_sents),
        metadata=_meta(heading_hierarchy="HR > Benefits"),
    )

    # Next chunk in a DIFFERENT section ("Compensation")
    nxt_chunk = NormalizedChunk(
        chunk_id="c3",
        text="Base salary reviews occur annually in October for all exempt employees.",
        metadata=_meta(heading_hierarchy="HR > Compensation"),
    )

    prev_tokens_before = normalizer.count_tokens(prev_chunk.text)
    curr_tokens_before = normalizer.count_tokens(curr_chunk.text)
    assert prev_tokens_before >= 200
    assert curr_tokens_before < 55  # initially a micro-fragment!

    res = normalizer._pass4_standardize_chunk_lengths([prev_chunk, curr_chunk, nxt_chunk])

    assert len(res) == 3
    # Check that prev and curr have been rebalanced!
    rebalanced_prev = res[0]
    rebalanced_curr = res[1]
    rebalanced_nxt = res[2]

    tok_prev = normalizer.count_tokens(rebalanced_prev.text)
    tok_curr = normalizer.count_tokens(rebalanced_curr.text)

    # curr is no longer a micro-fragment! Both are balanced (~120-160 tokens)
    assert tok_curr >= 55, f"Expected curr to be lifted above micro-fragment floor, got {tok_curr}"
    assert tok_prev <= 200, f"Expected prev to shed excess load, got {tok_prev}"
    assert 100 <= tok_prev <= 170
    assert 90 <= tok_curr <= 170

    # Section hierarchy is preserved — next section was not contaminated
    assert rebalanced_prev.metadata["heading_hierarchy"] == "HR > Benefits"
    assert rebalanced_curr.metadata["heading_hierarchy"] == "HR > Benefits"
    assert rebalanced_nxt.metadata["heading_hierarchy"] == "HR > Compensation"


def test_pipeline_context_injection_on_balanced_splits(normalizer: ChunkNormalizer):
    """
    Verifies full 5-pass pipeline applies [Policy: ... | Section: ...] context injection
    to both balanced chunks, ensuring neither is a micro-fragment and both are searchable.
    """
    sentences = [
        f"Security protocol rule {i} mandates two-factor authentication on all company-issued laptops."
        for i in range(16)
    ]
    raw_doc = NormalizedChunk(
        chunk_id="sec_doc",
        text=" ".join(sentences),
        metadata=_meta(
            source_filename="it_security_manual.pdf",
            heading_hierarchy="IT > Security > Authentication",
        ),
    )

    normalized = normalizer.normalize_chunks([raw_doc])
    assert len(normalized) == 2

    for c in normalized:
        # Context injection prefix check
        assert c.text.startswith("[Policy: it security manual | Section: IT > Security > Authentication]\n")
        # Token density check
        toks = normalizer.count_tokens(c.text)
        assert 110 <= toks <= 220, f"Chunk token count {toks} outside balanced sweet zone"
        # Zero micro-fragments
        assert toks >= 55
        # Canonical metadata
        assert c.metadata["section_heading"] == "Authentication"
        assert c.metadata["heading_hierarchy"] == "IT > Security > Authentication"


def test_pass4_dynamic_rebalance_more_than_two_parts_when_exceeding_200_tokens(normalizer: ChunkNormalizer):
    """
    Verifies that if after dividing into 2 parts the chunk would still exceed 200 tokens
    (e.g. combined ~450 tokens -> 225 tokens each > 200), it dynamically divides into K >= 3 parts,
    guaranteeing no resulting part exceeds 200 tokens and no micro-fragments are created.
    """
    # 25 sentences in Section "Benefits" (total ~450 tokens)
    sents = [
        f"Employee health benefit item {i} provides full reimbursement for approved outpatient clinical treatments."
        for i in range(25)
    ]
    prev_chunk = NormalizedChunk(
        chunk_id="b_prev",
        text=" ".join(sents[:23]),  # ~410 tokens
        metadata=_meta(heading_hierarchy="HR > Benefits"),
    )
    curr_chunk = NormalizedChunk(
        chunk_id="b_tail",
        text=" ".join(sents[23:]),  # 2 sentences, ~40 tokens (micro-fragment!)
        metadata=_meta(heading_hierarchy="HR > Benefits"),
    )
    nxt_chunk = NormalizedChunk(
        chunk_id="nxt_diff",
        text="Payroll processing cycle occurs bi-weekly on alternate Fridays.",
        metadata=_meta(heading_hierarchy="HR > Payroll"),
    )

    tot_comb = normalizer.count_tokens(f"{prev_chunk.text} {curr_chunk.text}")
    assert tot_comb >= 400
    assert tot_comb // 2 > 200  # dividing into 2 would still exceed 200 tokens!

    res = normalizer._pass4_standardize_chunk_lengths([prev_chunk, curr_chunk, nxt_chunk])

    # Should dynamically produce 3 parts for Benefits + 1 part for Payroll = 4 chunks
    assert len(res) == 4
    benefits_parts = res[:3]
    payroll_part = res[3]

    for idx, p in enumerate(benefits_parts):
        p_toks = normalizer.count_tokens(p.text)
        assert p_toks <= 200, f"Part {idx} exceeds 200 tokens ({p_toks} tokens)"
        assert p_toks >= 55, f"Part {idx} is a micro-fragment ({p_toks} tokens)"
        assert p.metadata["heading_hierarchy"] == "HR > Benefits"
        assert p.metadata.get("rebalanced") is True

    assert payroll_part.metadata["heading_hierarchy"] == "HR > Payroll"


def test_pass2_dynamic_prose_split_exceeding_200_tokens(normalizer: ChunkNormalizer):
    """
    Verifies that in Pass 2, an oversized section of ~460 tokens dynamically divides
    into 3 parts (each <= 200 tokens) rather than 2 parts of 230 tokens (> 200).
    """
    sentences = [
        f"Compliance article {i} outlines data governance standards for financial accounting records."
        for i in range(36)
    ]
    raw_text = " ".join(sentences)
    total_tokens = normalizer.count_tokens(raw_text)
    assert total_tokens >= 400
    assert total_tokens // 2 > 200  # 2 parts would still exceed 200 tokens!

    c = NormalizedChunk(chunk_id="big_c", text=raw_text, metadata=_meta())
    parts = normalizer._pass2_enforce_token_budget_zero_data_loss([c])

    assert len(parts) >= 3
    for p in parts:
        toks = normalizer.count_tokens(p.text)
        assert toks <= 200, f"Expected part <= 200 tokens, got {toks}"
        assert toks >= 55, f"Expected part >= 55 tokens, got {toks}"
