"""
Dynamic Chunking Strategies Engine for RAG Optimization & Needle Testing
========================================================================
Implements multiple structural, semantic, and windowed chunking algorithms
with soft approximate token budgeting that guarantees complete sentences
are never severed mid-thought.
"""

from dataclasses import dataclass
import re
from typing import Any, Callable, Dict, List, Optional, Tuple


# Word/token heuristic: 1 word ~ 1.33 subword tokens in MiniLM / BPE
def estimate_tokens(text: str) -> int:
    """Fast, robust token estimator (approx 1 word = 1.3 tokens + punctuation)."""
    if not text or not text.strip():
        return 0
    words = text.split()
    return max(1, int(len(words) * 1.3))


def split_into_sentences(text: str) -> List[str]:
    """Split text into sentences cleanly, preserving terminal punctuation and quotes.
    
    Avoids splitting on common abbreviations like e.g., i.e., Dr., vs., etc.
    """
    if not text or not text.strip():
        return []
    
    # Normalize newlines within paragraph
    text = re.sub(r"[ \t]+", " ", text).strip()
    
    # Regex splitting on punctuation followed by space and capital letter or digit
    # Using negative lookbehind for abbreviations
    pattern = r"(?<!\be\.g)(?<!\bi\.e)(?<!\bvs)(?<!\bMr)(?<!\bMs)(?<!\bDr)(?<!\bInc)(?<!\bPvt)(?<!\bLtd)(?<=[.!?])\s+(?=[A-Z0-9\"\'\(\[])"
    raw_sentences = re.split(pattern, text)
    
    sentences = [s.strip() for s in raw_sentences if s.strip()]
    return sentences if sentences else [text]


@dataclass
class ChunkRecord:
    id: str
    text: str
    token_count: int
    char_count: int
    strategy: str
    target_tokens: int
    heading_hierarchy: str
    metadata: Dict[str, Any]
    previous_chunk_id: Optional[str] = None
    next_chunk_id: Optional[str] = None
    sequence_index: int = 0
    bridge_to_next: Optional[Dict[str, Any]] = None
    bridge_from_prev: Optional[Dict[str, Any]] = None
    parent_id: Optional[str] = None
    parent_text: Optional[str] = None

    @property
    def strategy_name(self) -> str:
        return self.strategy



CHUNK_STRATEGIES_META: Dict[str, Dict[str, Any]] = {
    "recursive_sliding_window": {
        "id": "recursive_sliding_window",
        "name": "🔄 Recursive Character & Sentence Sliding Window",
        "short_name": "Recursive Sliding Window",
        "optimal_tokens": 350,
        "recommended_range": "250 – 450 tokens",
        "default_overlap_pct": 15,
        "description": "Splits by paragraph then sentence. Smooth rolling overlap (10-20%) preserves cross-chunk context without severing sentences.",
        "best_for": "General enterprise policies, employee handbooks, and standard narrative documents.",
    },
    "structural_hierarchical": {
        "id": "structural_hierarchical",
        "name": "📑 Structural & Hierarchical Header Chunking",
        "short_name": "Hierarchical Header",
        "optimal_tokens": 450,
        "recommended_range": "350 – 600 tokens",
        "default_overlap_pct": 5,
        "description": "Detects Markdown/Docx headings (# H1 > ## H2). Prepend hierarchical breadcrumbs to preserve section context for every chunk.",
        "best_for": "Deeply structured legal contracts, compliance handbooks, and numbered policy manuals.",
    },
    "semantic_paragraph": {
        "id": "semantic_paragraph",
        "name": "🧠 Semantic Paragraph / Discourse Chunking",
        "short_name": "Semantic Paragraph",
        "optimal_tokens": 300,
        "recommended_range": "200 – 400 tokens",
        "default_overlap_pct": 0,
        "description": "Treats natural discourse paragraphs as atomic units. Never breaks a cohesive thought unless paragraph exceeds 1.5x target budget.",
        "best_for": "Self-contained policy clauses, FAQs, standalone guidelines, and executive summaries.",
    },
    "sentence_window_small_to_big": {
        "id": "sentence_window_small_to_big",
        "name": "🎯 Sentence Window (Small-to-Big) Chunking",
        "short_name": "Sentence Window (Small-to-Big)",
        "optimal_tokens": 150,
        "recommended_range": "100 – 200 tokens (Core) / ~350 tokens (Window)",
        "default_overlap_pct": 20,
        "description": "Generates tight 1-3 sentence core target needles for high-precision vector similarity, enriched with surrounding context window for LLM generation.",
        "best_for": "Precise numeric thresholds, specific definitions, exact dates, and isolated needle facts.",
    },
    "document_section_broad": {
        "id": "document_section_broad",
        "name": "📦 Document Section / Broad Context Chunking",
        "short_name": "Broad Section",
        "optimal_tokens": 650,
        "recommended_range": "500 – 850 tokens",
        "default_overlap_pct": 10,
        "description": "Collects multi-paragraph operational workflows, tables, and conditional exception lists into comprehensive units.",
        "best_for": "Complex multi-step procedures, compensation tables, and multi-clause agreements.",
    },
    "fixed_word_snapped": {
        "id": "fixed_word_snapped",
        "name": "📏 Fixed-Size Word-Snapped Chunking (Baseline)",
        "short_name": "Word-Snapped Fixed",
        "optimal_tokens": 250,
        "recommended_range": "150 – 350 tokens",
        "default_overlap_pct": 10,
        "description": "Standard baseline chunking targeting a fixed token size, with word and punctuation boundary snapping so words are never severed.",
        "best_for": "Uniform indexing workloads, benchmarking baseline comparisons, and token-constrained embeddings.",
    },
    "adaptive_hierarchical_bridge": {
        "id": "adaptive_hierarchical_bridge",
        "name": "🌐 Adaptive Hierarchical Bridge Chunking (AHBC)",
        "short_name": "Adaptive AHBC",
        "optimal_tokens": 200,
        "recommended_range": "150 – 300 tokens (Child) / 500 – 800 tokens (Parent)",
        "default_overlap_pct": 0,
        "description": "Combines Adaptive Structure-Aware routing, Parent-Child hierarchical grounding, and Selective Bridge Graphs with 3-tier dynamic context expansion.",
        "best_for": "Enterprise policies, compliance regulations, multi-clause contracts, and cross-boundary procedural rules.",
    },
}


def _split_markdown_sections(text: str) -> List[Tuple[str, str]]:
    """Parse text into sections separated by Markdown headings, tracking heading hierarchy."""
    lines = text.split("\n")
    sections: List[Tuple[str, str]] = []
    
    current_headers: List[str] = []
    current_body_lines: List[str] = []
    
    heading_re = re.compile(r"^(#{1,6})\s+(.+)$")
    
    for line in lines:
        match = heading_re.match(line.strip())
        if match:
            # Save accumulated section if any body exists
            if current_body_lines:
                hierarchy = " > ".join(current_headers) if current_headers else "General"
                body = "\n".join(current_body_lines).strip()
                if body:
                    sections.append((hierarchy, body))
                current_body_lines = []
            
            level = len(match.group(1))
            title = match.group(2).strip()
            # Update heading stack
            current_headers = current_headers[:level - 1]
            current_headers.append(title)
        else:
            current_body_lines.append(line)
            
    if current_body_lines:
        hierarchy = " > ".join(current_headers) if current_headers else "General"
        body = "\n".join(current_body_lines).strip()
        if body:
            sections.append((hierarchy, body))
            
    if not sections:
        sections = [("General", text)]
        
    return sections


def chunk_recursive_sliding_window(
    text: str,
    target_tokens: int = 350,
    overlap_pct: int = 15,
    doc_prefix: str = "CHUNK",
) -> List[ChunkRecord]:
    """Strategy 1: Recursive Sliding Window with soft sentence boundary snapping.
    
    Accumulates sentences up to approximate target_tokens. Never severs a sentence mid-thought.
    """
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n+", text) if p.strip()]
    if not paragraphs:
        paragraphs = [text.strip()]
        
    chunks: List[ChunkRecord] = []
    current_sentences: List[str] = []
    current_tokens = 0
    
    overlap_budget = max(20, int(target_tokens * (overlap_pct / 100.0)))
    
    for para in paragraphs:
        sentences = split_into_sentences(para)
        for sent in sentences:
            sent_tok = estimate_tokens(sent)
            
            # If adding this sentence keeps us under or reasonably close to target
            if current_tokens + sent_tok <= target_tokens or not current_sentences:
                current_sentences.append(sent)
                current_tokens += sent_tok
            else:
                # Soft boundary check: if current chunk is < 70% of target, absorb the sentence to avoid a tiny stub
                if current_tokens < int(target_tokens * 0.70):
                    current_sentences.append(sent)
                    current_tokens += sent_tok
                
                # Close out current chunk cleanly
                chunk_text = " ".join(current_sentences).strip()
                c_idx = len(chunks) + 1
                chunks.append(
                    ChunkRecord(
                        id=f"{doc_prefix}-{c_idx:03d}",
                        text=chunk_text,
                        token_count=estimate_tokens(chunk_text),
                        char_count=len(chunk_text),
                        strategy="recursive_sliding_window",
                        target_tokens=target_tokens,
                        heading_hierarchy="",
                        metadata={"chunk_index": c_idx, "strategy": "recursive_sliding_window"},
                    )
                )
                
                # Compute overlap sentences for next window
                overlap_sents: List[str] = []
                overlap_accum = 0
                for s in reversed(current_sentences):
                    s_tok = estimate_tokens(s)
                    if overlap_accum + s_tok <= overlap_budget:
                        overlap_sents.insert(0, s)
                        overlap_accum += s_tok
                    else:
                        break
                        
                current_sentences = overlap_sents + [sent]
                current_tokens = sum(estimate_tokens(s) for s in current_sentences)
                
    if current_sentences:
        tail_tokens = sum(estimate_tokens(s) for s in current_sentences)
        # Prevent 250 + 50 micro-fragment by rebalancing across ~150 + 150
        if chunks and tail_tokens < 60:
            prev_chunk = chunks[-1]
            prev_sents = split_into_sentences(prev_chunk.text)
            all_sents = prev_sents + current_sentences
            tot_s = sum(estimate_tokens(s) for s in all_sents)
            if len(all_sents) >= 2 and tot_s <= int(target_tokens * 1.5):
                half_t = tot_s // 2
                best_idx = 1
                best_diff = float("inf")
                acc = 0
                for idx_s in range(len(all_sents) - 1):
                    acc += estimate_tokens(all_sents[idx_s])
                    d = abs(acc - half_t)
                    if d < best_diff and acc <= target_tokens and (tot_s - acc) <= target_tokens:
                        best_diff = d
                        best_idx = idx_s + 1
                p1_s = " ".join(all_sents[:best_idx]).strip()
                p2_s = " ".join(all_sents[best_idx:]).strip()
                if estimate_tokens(p2_s) >= 45:
                    prev_chunk.text = p1_s
                    prev_chunk.token_count = estimate_tokens(p1_s)
                    prev_chunk.char_count = len(p1_s)
                    current_sentences = [p2_s]

        chunk_text = " ".join(current_sentences).strip()
        c_idx = len(chunks) + 1
        chunks.append(
            ChunkRecord(
                id=f"{doc_prefix}-{c_idx:03d}",
                text=chunk_text,
                token_count=estimate_tokens(chunk_text),
                char_count=len(chunk_text),
                strategy="recursive_sliding_window",
                target_tokens=target_tokens,
                heading_hierarchy="",
                metadata={"chunk_index": c_idx, "strategy": "recursive_sliding_window"},
            )
        )
        
    return chunks


def chunk_structural_hierarchical(
    text: str,
    target_tokens: int = 450,
    overlap_pct: int = 5,
    doc_prefix: str = "CHUNK",
) -> List[ChunkRecord]:
    """Strategy 2: Structural & Hierarchical Header Chunking.
    
    Extracts heading hierarchy and prefixes breadcrumbs (`Section > Sub`), grouping paragraphs
    under the same heading up to approximate target_tokens without cutting sentences.
    """
    sections = _split_markdown_sections(text)
    chunks: List[ChunkRecord] = []
    
    for hierarchy, body in sections:
        # Prepend breadcrumb if meaningful
        prefix_tag = f"[{hierarchy}]\n\n" if hierarchy and hierarchy != "General" else ""
        prefix_tokens = estimate_tokens(prefix_tag)
        effective_budget = max(100, target_tokens - prefix_tokens)
        
        # Sub-chunk the body cleanly using sentence sliding window
        sub_chunks = chunk_recursive_sliding_window(
            body,
            target_tokens=effective_budget,
            overlap_pct=overlap_pct,
            doc_prefix=doc_prefix,
        )
        
        for sc in sub_chunks:
            full_text = f"{prefix_tag}{sc.text}".strip()
            c_idx = len(chunks) + 1
            chunks.append(
                ChunkRecord(
                    id=f"{doc_prefix}-{c_idx:03d}",
                    text=full_text,
                    token_count=estimate_tokens(full_text),
                    char_count=len(full_text),
                    strategy="structural_hierarchical",
                    target_tokens=target_tokens,
                    heading_hierarchy=hierarchy,
                    metadata={
                        "chunk_index": c_idx,
                        "strategy": "structural_hierarchical",
                        "hierarchy_path": hierarchy,
                    },
                )
            )
            
    return chunks


def chunk_semantic_paragraph(
    text: str,
    target_tokens: int = 300,
    overlap_pct: int = 0,
    doc_prefix: str = "CHUNK",
) -> List[ChunkRecord]:
    """Strategy 3: Semantic Paragraph / Discourse Chunking.
    
    Treats cohesive paragraphs as atomic units. Groups small paragraphs together,
    and only divides extra-long paragraphs at clean sentence boundaries.
    """
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n+", text) if p.strip()]
    if not paragraphs:
        paragraphs = [text.strip()]
        
    chunks: List[ChunkRecord] = []
    current_paras: List[str] = []
    current_tokens = 0
    
    for para in paragraphs:
        para_tok = estimate_tokens(para)
        
        # If single paragraph is very large (> 1.4x target), split paragraph by sentences
        if para_tok > int(target_tokens * 1.4):
            # Flush existing accumulated paragraphs first
            if current_paras:
                c_text = "\n\n".join(current_paras).strip()
                c_idx = len(chunks) + 1
                chunks.append(
                    ChunkRecord(
                        id=f"{doc_prefix}-{c_idx:03d}",
                        text=c_text,
                        token_count=estimate_tokens(c_text),
                        char_count=len(c_text),
                        strategy="semantic_paragraph",
                        target_tokens=target_tokens,
                        heading_hierarchy="",
                        metadata={"chunk_index": c_idx, "strategy": "semantic_paragraph"},
                    )
                )
                current_paras = []
                current_tokens = 0
                
            # Split the oversized paragraph at sentence boundaries cleanly
            para_chunks = chunk_recursive_sliding_window(
                para,
                target_tokens=target_tokens,
                overlap_pct=overlap_pct,
                doc_prefix=doc_prefix,
            )
            for pc in para_chunks:
                c_idx = len(chunks) + 1
                pc.id = f"{doc_prefix}-{c_idx:03d}"
                pc.strategy = "semantic_paragraph"
                chunks.append(pc)
            continue
            
        # Normal paragraph accumulation
        if current_tokens + para_tok <= target_tokens or not current_paras:
            current_paras.append(para)
            current_tokens += para_tok
        else:
            c_text = "\n\n".join(current_paras).strip()
            c_idx = len(chunks) + 1
            chunks.append(
                ChunkRecord(
                    id=f"{doc_prefix}-{c_idx:03d}",
                    text=c_text,
                    token_count=estimate_tokens(c_text),
                    char_count=len(c_text),
                    strategy="semantic_paragraph",
                    target_tokens=target_tokens,
                    heading_hierarchy="",
                    metadata={"chunk_index": c_idx, "strategy": "semantic_paragraph"},
                )
            )
            current_paras = [para]
            current_tokens = para_tok
            
    if current_paras:
        c_text = "\n\n".join(current_paras).strip()
        c_idx = len(chunks) + 1
        chunks.append(
            ChunkRecord(
                id=f"{doc_prefix}-{c_idx:03d}",
                text=c_text,
                token_count=estimate_tokens(c_text),
                char_count=len(c_text),
                strategy="semantic_paragraph",
                target_tokens=target_tokens,
                heading_hierarchy="",
                metadata={"chunk_index": c_idx, "strategy": "semantic_paragraph"},
            )
        )
        
    return chunks


def chunk_sentence_window_small_to_big(
    text: str,
    target_tokens: int = 150,
    overlap_pct: int = 20,
    doc_prefix: str = "CHUNK",
) -> List[ChunkRecord]:
    """Strategy 4: Sentence Window (Small-to-Big) Chunking.
    
    Generates tight 1-3 sentence core target needles (~100-150 tokens) for high-precision
    embedding similarity, with surrounding sentence context embedded in metadata.
    """
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n+", text) if p.strip()]
    all_sentences: List[str] = []
    for p in paragraphs:
        all_sentences.extend(split_into_sentences(p))
        
    if not all_sentences:
        all_sentences = [text.strip()]
        
    chunks: List[ChunkRecord] = []
    i = 0
    n = len(all_sentences)
    
    while i < n:
        # Core leaf: 1 to 2 sentences up to target_tokens
        core_sents = [all_sentences[i]]
        core_tokens = estimate_tokens(core_sents[0])
        advance = 1
        
        while i + advance < n:
            next_sent = all_sentences[i + advance]
            next_tok = estimate_tokens(next_sent)
            if core_tokens + next_tok <= target_tokens:
                core_sents.append(next_sent)
                core_tokens += next_tok
                advance += 1
            else:
                break
                
        # Expanded window: lookback 1-2 sentences, lookforward 1-2 sentences
        window_start = max(0, i - 1)
        window_end = min(n, i + advance + 1)
        window_text = " ".join(all_sentences[window_start:window_end]).strip()
        core_text = " ".join(core_sents).strip()
        
        # Primary retrieval text has core fact, contextualized with surrounding window
        c_idx = len(chunks) + 1
        chunks.append(
            ChunkRecord(
                id=f"{doc_prefix}-{c_idx:03d}",
                text=core_text,
                token_count=estimate_tokens(core_text),
                char_count=len(core_text),
                strategy="sentence_window_small_to_big",
                target_tokens=target_tokens,
                heading_hierarchy="",
                metadata={
                    "chunk_index": c_idx,
                    "strategy": "sentence_window_small_to_big",
                    "window_context": window_text,
                    "window_token_count": estimate_tokens(window_text),
                },
            )
        )
        
        i += advance
        
    return chunks


def chunk_document_section_broad(
    text: str,
    target_tokens: int = 650,
    overlap_pct: int = 10,
    doc_prefix: str = "CHUNK",
) -> List[ChunkRecord]:
    """Strategy 5: Document Section / Broad Context Chunking.
    
    Aggregates multi-paragraph operational workflows, tables, and conditional lists
    into large, comprehensive thematic units (~650 tokens).
    """
    return chunk_recursive_sliding_window(
        text,
        target_tokens=target_tokens,
        overlap_pct=overlap_pct,
        doc_prefix=doc_prefix,
    )


def chunk_fixed_word_snapped(
    text: str,
    target_tokens: int = 250,
    overlap_pct: int = 10,
    doc_prefix: str = "CHUNK",
) -> List[ChunkRecord]:
    """Strategy 6: Fixed-Size Word-Snapped Chunking (Baseline).
    
    Enforces approximate token count but strictly snaps to word and sentence boundaries
    to prevent severed words.
    """
    return chunk_recursive_sliding_window(
        text,
        target_tokens=target_tokens,
        overlap_pct=overlap_pct,
        doc_prefix=doc_prefix,
    )


def chunk_adaptive_hierarchical_bridge(
    text: str,
    target_tokens: int = 200,
    overlap_pct: int = 0,
    doc_prefix: str = "CHUNK",
) -> List[ChunkRecord]:
    """Strategy 7: Adaptive Hierarchical Bridge Chunking (AHBC).
    
    1. Parses document into parent sections by headings.
    2. Generates tight, searchable child chunks (target ~200 tokens).
    3. Anchors each child chunk with parent_id and parent_text.
    4. Links all chunks sequentially with typed, validated boundary bridges.
    """
    sections = _split_markdown_sections(text)
    chunks: List[ChunkRecord] = []
    
    for s_idx, (hierarchy, section_body) in enumerate(sections, 1):
        parent_id = f"{doc_prefix}-SEC{s_idx:02d}"
        parent_text = f"[{hierarchy}]\n\n{section_body}".strip() if hierarchy else section_body.strip()
        
        paragraphs = [p.strip() for p in re.split(r"\n\s*\n+", section_body) if p.strip()]
        if not paragraphs:
            paragraphs = [section_body.strip()]
            
        current_sentences: List[str] = []
        current_tokens = 0
        
        for para in paragraphs:
            sentences = split_into_sentences(para)
            for sent in sentences:
                sent_tok = estimate_tokens(sent)
                if current_tokens + sent_tok <= target_tokens or not current_sentences:
                    current_sentences.append(sent)
                    current_tokens += sent_tok
                else:
                    if current_tokens < int(target_tokens * 0.70):
                        current_sentences.append(sent)
                        current_tokens += sent_tok
                        
                    child_text = " ".join(current_sentences).strip()
                    c_idx = len(chunks) + 1
                    chunks.append(
                        ChunkRecord(
                            id=f"{doc_prefix}-{c_idx:03d}",
                            text=child_text,
                            token_count=estimate_tokens(child_text),
                            char_count=len(child_text),
                            strategy="adaptive_hierarchical_bridge",
                            target_tokens=target_tokens,
                            heading_hierarchy=hierarchy,
                            parent_id=parent_id,
                            parent_text=parent_text,
                            metadata={
                                "chunk_index": c_idx,
                                "strategy": "adaptive_hierarchical_bridge",
                                "parent_id": parent_id,
                                "parent_tokens": estimate_tokens(parent_text),
                                "heading_hierarchy": hierarchy,
                            },
                        )
                    )
                    current_sentences = [sent]
                    current_tokens = sent_tok
                    
        if current_sentences:
            child_text = " ".join(current_sentences).strip()
            c_idx = len(chunks) + 1
            chunks.append(
                ChunkRecord(
                    id=f"{doc_prefix}-{c_idx:03d}",
                    text=child_text,
                    token_count=estimate_tokens(child_text),
                    char_count=len(child_text),
                    strategy="adaptive_hierarchical_bridge",
                    target_tokens=target_tokens,
                    heading_hierarchy=hierarchy,
                    parent_id=parent_id,
                    parent_text=parent_text,
                    metadata={
                        "chunk_index": c_idx,
                        "strategy": "adaptive_hierarchical_bridge",
                        "parent_id": parent_id,
                        "parent_tokens": estimate_tokens(parent_text),
                        "heading_hierarchy": hierarchy,
                    },
                )
            )
            
    return chunks


STRATEGY_DISPATCH: Dict[str, Callable[..., List[ChunkRecord]]] = {
    "recursive_sliding_window": chunk_recursive_sliding_window,
    "structural_hierarchical": chunk_structural_hierarchical,
    "semantic_paragraph": chunk_semantic_paragraph,
    "sentence_window_small_to_big": chunk_sentence_window_small_to_big,
    "document_section_broad": chunk_document_section_broad,
    "fixed_word_snapped": chunk_fixed_word_snapped,
    "adaptive_hierarchical_bridge": chunk_adaptive_hierarchical_bridge,
}


def apply_chunking_strategy(
    strategy_key: str,
    text: str,
    target_tokens: Optional[int] = None,
    overlap_pct: Optional[int] = None,
    doc_prefix: str = "CHUNK",
    enable_bridge_links: bool = True,
) -> List[ChunkRecord]:
    """Execute the chosen chunking strategy on text with soft approximate token budgeting,
    and link all resulting chunks into a Doubly Linked List with typed boundary bridges.
    """
    from app.infrastructure.document.bridge_linked_chunking import (
        link_chunk_records_into_linked_list,
    )

    meta = CHUNK_STRATEGIES_META.get(strategy_key, CHUNK_STRATEGIES_META["recursive_sliding_window"])
    func = STRATEGY_DISPATCH.get(strategy_key, chunk_recursive_sliding_window)
    
    tokens = target_tokens if target_tokens is not None else meta["optimal_tokens"]
    overlap = overlap_pct if overlap_pct is not None else meta["default_overlap_pct"]
    
    chunks = func(
        text=text,
        target_tokens=tokens,
        overlap_pct=overlap,
        doc_prefix=doc_prefix,
    )
    if enable_bridge_links and chunks:
        chunks = link_chunk_records_into_linked_list(chunks, doc_id=doc_prefix)
    return chunks
