"""Informational Word Extractor.

Extracts unique informational words from any document (Word .docx, text, markdown,
raw text strings, or bytes) while filtering out grammatical/function parts of speech:
- Articles (a, an, the)
- Pronouns (personal, possessive, demonstrative, indefinite, relative, reflexive)
- Adjectives (descriptive, comparative, superlative)
- Prepositions & Conjunctions
- Determiners, Quantifiers, and Auxiliaries/Modals

Retains core informational words:
- Informational Nouns (singular, plural, proper nouns, domain concepts)
- Informational Action Verbs (lexical verbs, excluding auxiliary forms)
"""

from __future__ import annotations

import csv
import io
import json
import logging
import re
from dataclasses import dataclass, field
from io import BytesIO
from pathlib import Path
from typing import Any, Iterable, List, Optional, Set, Union

from docx import Document

logger = logging.getLogger(__name__)

# Try to initialize NLTK components gracefully with fallbacks
_NLTK_AVAILABLE = False
try:
    import nltk
    from nltk import pos_tag, sent_tokenize, word_tokenize

    # Ensure required tokenizers and taggers are accessible
    try:
        nltk.data.find("taggers/averaged_perceptron_tagger_eng")
    except LookupError:
        nltk.download("averaged_perceptron_tagger_eng", quiet=True)

    try:
        nltk.data.find("tokenizers/punkt_tab")
    except LookupError:
        nltk.download("punkt_tab", quiet=True)

    try:
        nltk.data.find("tokenizers/punkt")
    except LookupError:
        nltk.download("punkt", quiet=True)

    _NLTK_AVAILABLE = True
except Exception as exc:  # pragma: no cover
    logger.warning("NLTK not fully initialized (%s). Using built-in POS classifier fallback.", exc)
    _NLTK_AVAILABLE = False


# ==============================================================================
# Comprehensive Grammatical Stopword / POS Dictionaries for Robust Filtering
# ==============================================================================

ARTICLES: Set[str] = {
    "a",
    "an",
    "the",
}

PRONOUNS: Set[str] = {
    # Personal pronouns (subject & object)
    "i",
    "me",
    "you",
    "he",
    "him",
    "she",
    "her",
    "it",
    "we",
    "us",
    "they",
    "them",
    # Possessive pronouns & determiners
    "my",
    "mine",
    "your",
    "yours",
    "his",
    "hers",
    "its",
    "our",
    "ours",
    "their",
    "theirs",
    # Reflexive pronouns
    "myself",
    "yourself",
    "himself",
    "herself",
    "itself",
    "ourselves",
    "yourselves",
    "themselves",
    # Demonstrative pronouns
    "this",
    "that",
    "these",
    "those",
    # Relative & Interrogative pronouns
    "who",
    "whom",
    "whose",
    "which",
    "what",
    "whatever",
    "whoever",
    "whomever",
    "whichever",
    # Indefinite pronouns
    "all",
    "another",
    "any",
    "anybody",
    "anyone",
    "anything",
    "both",
    "each",
    "either",
    "everybody",
    "everyone",
    "everything",
    "few",
    "many",
    "neither",
    "nobody",
    "none",
    "no one",
    "nothing",
    "one",
    "other",
    "others",
    "several",
    "some",
    "somebody",
    "someone",
    "something",
    "such",
}

PREPOSITIONS_AND_CONJUNCTIONS: Set[str] = {
    # Prepositions
    "about",
    "above",
    "across",
    "after",
    "against",
    "along",
    "amid",
    "among",
    "around",
    "at",
    "before",
    "behind",
    "below",
    "beneath",
    "beside",
    "between",
    "beyond",
    "by",
    "concerning",
    "despite",
    "down",
    "during",
    "except",
    "for",
    "from",
    "in",
    "inside",
    "into",
    "like",
    "near",
    "of",
    "off",
    "on",
    "onto",
    "out",
    "outside",
    "over",
    "past",
    "per",
    "regarding",
    "round",
    "since",
    "through",
    "throughout",
    "till",
    "to",
    "toward",
    "towards",
    "under",
    "underneath",
    "unlike",
    "until",
    "unto",
    "up",
    "upon",
    "versus",
    "via",
    "with",
    "within",
    "without",
    # Coordinating conjunctions
    "and",
    "but",
    "or",
    "nor",
    "so",
    "yet",
    # Subordinating conjunctions
    "although",
    "because",
    "if",
    "since",
    "unless",
    "while",
    "whereas",
    "whether",
    "though",
    "even",
    "once",
    "whenever",
    "wherever",
}

AUXILIARY_AND_MODAL_VERBS: Set[str] = {
    "am",
    "is",
    "are",
    "was",
    "were",
    "be",
    "been",
    "being",
    "have",
    "has",
    "had",
    "having",
    "do",
    "does",
    "did",
    "done",
    "doing",
    "can",
    "could",
    "will",
    "would",
    "shall",
    "should",
    "may",
    "might",
    "must",
    "ought",
    "dare",
    "need",
    "used",
}

COMMON_ADJECTIVES_FALLBACK: Set[str] = {
    "annual",
    "applicable",
    "general",
    "good",
    "bad",
    "better",
    "best",
    "new",
    "old",
    "great",
    "high",
    "low",
    "small",
    "large",
    "big",
    "major",
    "minor",
    "eligible",
    "full",
    "total",
    "various",
    "different",
    "same",
    "specific",
    "certain",
    "important",
    "necessary",
    "official",
    "prior",
    "maximum",
    "minimum",
    "daily",
    "weekly",
    "monthly",
    "yearly",
    "standard",
    "regular",
    "current",
    "future",
    "past",
    "active",
    "valid",
    "direct",
    "indirect",
    "internal",
    "external",
    "confidential",
    "formal",
    "informal",
    "disciplinary",
    "statutory",
}

NON_INFORMATIONAL_ADVERBS: Set[str] = {
    "not",
    "n't",
    "no",
    "nor",
    "as",
    "so",
    "very",
    "quite",
    "too",
    "also",
    "just",
    "only",
    "here",
    "there",
    "now",
    "then",
    "always",
    "never",
    "ever",
    "already",
    "soon",
    "almost",
    "nearly",
    "well",
    "thus",
    "hence",
    "therefore",
    "however",
    "indeed",
    "perhaps",
    "maybe",
    "where",
    "when",
    "why",
    "how",
}


@dataclass
class InformationalWordReport:
    """Detailed summary of unique informational words extracted from a document."""

    unique_words: List[str]
    total_document_words: int
    total_informational_words: int
    word_frequencies: dict[str, int] = field(default_factory=dict)
    word_pos_tags: dict[str, List[str]] = field(default_factory=dict)
    filtered_categories: dict[str, int] = field(default_factory=dict)

    @property
    def unique_word_count(self) -> int:
        return len(self.unique_words)

    def top_words(self, n: int = 20) -> List[tuple[str, int]]:
        """Return the top N most frequent informational words."""
        sorted_items = sorted(self.word_frequencies.items(), key=lambda x: (-x[1], x[0]))
        return sorted_items[:n]


class InformationalWordExtractor:
    """Dynamic extractor that accepts any document, strips grammatical parts of speech

    (articles, adjectives, pronouns, prepositions, auxiliaries), and returns
    unique informational words.
    """

    def __init__(
        self,
        include_verbs: bool = True,
        min_word_length: int = 3,
        custom_stopwords: Optional[Iterable[str]] = None,
    ) -> None:
        self.include_verbs = include_verbs
        self.min_word_length = min_word_length
        self.custom_stopwords = set(w.lower() for w in (custom_stopwords or []))

    # --------------------------------------------------------------------------
    # Document Input Ingestion
    # --------------------------------------------------------------------------

    def load_text(
        self,
        doc_input: Union[str, Path, bytes, dict, list],
        file_name: Optional[str] = None,
    ) -> str:
        """Dynamically load and extract plain text from any document input."""
        if isinstance(doc_input, bytes):
            return self._extract_from_bytes(doc_input, file_name or "document.txt")

        if isinstance(doc_input, Path):
            return self._extract_from_file_path(doc_input)

        if isinstance(doc_input, str):
            # Check if doc_input is an existing file path on the filesystem
            candidate_path = Path(doc_input)
            if candidate_path.is_file():
                return self._extract_from_file_path(candidate_path)
            # Otherwise, treat the string as raw document text content
            return doc_input

        if isinstance(doc_input, dict):
            # Extract common document content keys
            for key in ("text", "content", "body", "data", "document"):
                if key in doc_input and isinstance(doc_input[key], str):
                    return doc_input[key]
            return json.dumps(doc_input, ensure_ascii=False)

        if isinstance(doc_input, (list, tuple)):
            return "\n\n".join(str(item) for item in doc_input)

        return str(doc_input)

    def _extract_from_file_path(self, path: Path) -> str:
        if not path.exists():
            raise FileNotFoundError(f"Document file not found: {path}")
        return self._extract_from_bytes(path.read_bytes(), path.name)

    def _extract_from_bytes(self, content: bytes, file_name: str) -> str:
        suffix = Path(file_name).suffix.lower()

        # 1. Word Document (.docx)
        if suffix == ".docx":
            doc = Document(BytesIO(content))
            parts: List[str] = []
            # Extract paragraphs
            for p in doc.paragraphs:
                text = p.text.strip()
                if text:
                    parts.append(text)
            # Extract table cells
            for table in doc.tables:
                for row in table.rows:
                    row_text = " | ".join(cell.text.strip() for cell in row.cells if cell.text.strip())
                    if row_text:
                        parts.append(row_text)
            return "\n\n".join(parts)

        # 2. Text / Markdown / RST / Code
        if suffix in {".txt", ".md", ".rst", ".log", ".py", ".yaml", ".yml", ".ini"}:
            return content.decode("utf-8", errors="ignore")

        # 3. CSV / TSV
        if suffix in {".csv", ".tsv"}:
            decoded = content.decode("utf-8", errors="ignore")
            delimiter = "\t" if suffix == ".tsv" else ","
            reader = csv.reader(io.StringIO(decoded), delimiter=delimiter)
            rows = [" ".join(col.strip() for col in row if col.strip()) for row in reader]
            return "\n".join(rows)

        # 4. JSON
        if suffix == ".json":
            try:
                data = json.loads(content.decode("utf-8", errors="ignore"))
                return self.load_text(data)
            except Exception:
                return content.decode("utf-8", errors="ignore")

        # 5. Fallback: try decoding as UTF-8
        try:
            return content.decode("utf-8", errors="ignore")
        except Exception:
            raise ValueError(f"Unsupported document type: {suffix}")

    # --------------------------------------------------------------------------
    # POS Tagging & Word Classification
    # --------------------------------------------------------------------------

    def _is_article(self, word: str, tag: str) -> bool:
        if word in ARTICLES:
            return True
        return tag == "DT" and word in ARTICLES

    def _is_pronoun(self, word: str, tag: str) -> bool:
        if word in PRONOUNS:
            return True
        # Penn Treebank pronoun tags: PRP, PRP$, WP, WP$
        if tag in {"PRP", "PRP$", "WP", "WP$"}:
            return True
        return False

    def _is_adjective(self, word: str, tag: str) -> bool:
        # Penn Treebank adjective tags: JJ, JJR, JJS
        if tag in {"JJ", "JJR", "JJS"}:
            return True
        if word in COMMON_ADJECTIVES_FALLBACK:
            return True
        return False

    def _is_preposition_or_conjunction(self, word: str, tag: str) -> bool:
        if word in PREPOSITIONS_AND_CONJUNCTIONS:
            return True
        # IN: preposition/subordinating conjunction, CC: coordinating conjunction, TO: to
        if tag in {"IN", "CC", "TO"}:
            return True
        return False

    def _is_auxiliary_or_modal(self, word: str, tag: str) -> bool:
        if word in AUXILIARY_AND_MODAL_VERBS:
            return True
        # MD: modal auxiliary
        if tag == "MD":
            return True
        return False

    def _is_other_functional_word(self, word: str, tag: str) -> bool:
        if word in NON_INFORMATIONAL_ADVERBS:
            return True
        if word in self.custom_stopwords:
            return True
        # DT (determiners like 'this', 'that', 'all', 'any'), PDT, WDT
        # RP (particles like 'up', 'off'), UH (interjections), EX (existential there)
        if tag in {"DT", "PDT", "WDT", "RP", "UH", "EX"}:
            return True
        return False

    def is_informational(self, word: str, tag: str) -> tuple[bool, str]:
        """Determine if a word is informational or if it should be removed.

        Returns (is_informational, category_name).
        """
        w = word.lower()

        # Length check
        if len(w) < self.min_word_length:
            return False, "short_or_symbol"

        # Check if non-alphanumeric or purely numeric
        if not re.search(r"[a-zA-Z]", w) or w.isnumeric():
            return False, "number_or_symbol"

        # 1. Articles (a, an, the)
        if self._is_article(w, tag):
            return False, "article"

        # 2. Pronouns (he, she, it, they, us, our, someone, etc.)
        if self._is_pronoun(w, tag):
            return False, "pronoun"

        # 3. Adjectives (annual, good, new, applicable, etc.)
        if self._is_adjective(w, tag):
            return False, "adjective"

        # 4. Prepositions & Conjunctions (in, on, at, with, and, or, but)
        if self._is_preposition_or_conjunction(w, tag):
            return False, "preposition_conjunction"

        # 5. Auxiliaries & Modals (is, was, were, been, have, can, will, should)
        if self._is_auxiliary_or_modal(w, tag):
            return False, "auxiliary_modal"

        # 6. Adverbs (not, very, quite, also, only, etc.) & Wh-words
        if tag.startswith("RB") or w in NON_INFORMATIONAL_ADVERBS:
            return False, "adverb"

        if tag in {"WRB", "WDT", "WP", "WP$"}:
            return False, "wh_word"

        # 7. Other functional tokens (determiners, particles)
        if self._is_other_functional_word(w, tag):
            return False, "other_functional"

        # 8. Check if word is an Informational Noun
        # Penn Treebank noun tags: NN (singular), NNS (plural), NNP (proper singular), NNPS (proper plural)
        if tag.startswith("NN"):
            return True, "noun"

        # 9. Check if word is an Informational Verb (action verbs)
        # Penn Treebank verb tags: VB, VBD, VBG, VBN, VBP, VBZ
        if tag.startswith("VB"):
            if self.include_verbs:
                return True, "verb"
            return False, "verb_excluded"

        # Fallback for words not tagged as functional stop words
        # If NLTK tagged as unknown/foreign or if running in fallback mode,
        # retain if it looks like a substantive noun or domain token
        if re.match(r"^[a-z][a-z0-9\-]*[a-z0-9]$", w):
            return True, "substantive_word"

        return False, "other_excluded"

    # --------------------------------------------------------------------------
    # Extraction Pipeline
    # --------------------------------------------------------------------------

    def extract(
        self,
        doc_input: Union[str, Path, bytes, dict, list],
        file_name: Optional[str] = None,
    ) -> InformationalWordReport:
        """Extract unique informational words and comprehensive metrics from any document."""
        text = self.load_text(doc_input, file_name=file_name)
        if not text.strip():
            return InformationalWordReport(
                unique_words=[],
                total_document_words=0,
                total_informational_words=0,
                word_frequencies={},
                word_pos_tags={},
                filtered_categories={},
            )

        # Sentence-level tokenization & POS tagging
        tagged_tokens: List[tuple[str, str]] = []

        if _NLTK_AVAILABLE:
            try:
                sentences = sent_tokenize(text)
                for sentence in sentences:
                    words = word_tokenize(sentence)
                    tagged_tokens.extend(pos_tag(words))
            except Exception as exc:  # pragma: no cover
                logger.warning("NLTK sentence tagging failed (%s), using regex tokenization", exc)
                raw_words = re.findall(r"\b[A-Za-z0-9\-_]+\b", text)
                tagged_tokens = [(w, "NN") for w in raw_words]
        else:
            raw_words = re.findall(r"\b[A-Za-z0-9\-_]+\b", text)
            tagged_tokens = [(w, "NN") for w in raw_words]

        total_document_words = len(tagged_tokens)
        informational_words: List[str] = []
        word_frequencies: dict[str, int] = {}
        word_pos_tags: dict[str, List[str]] = {}
        filtered_categories: dict[str, int] = {
            "article": 0,
            "pronoun": 0,
            "adjective": 0,
            "preposition_conjunction": 0,
            "auxiliary_modal": 0,
            "adverb": 0,
            "wh_word": 0,
            "other_functional": 0,
            "short_or_symbol": 0,
            "number_or_symbol": 0,
            "verb_excluded": 0,
            "other_excluded": 0,
        }

        for raw_word, tag in tagged_tokens:
            # Clean word: strip hyphens/apostrophes/symbols at edges
            clean_word = re.sub(r"^[^a-zA-Z0-9]+|[^a-zA-Z0-9]+$", "", raw_word).lower()
            if not clean_word:
                continue

            keep, category = self.is_informational(clean_word, tag)
            if keep:
                informational_words.append(clean_word)
                word_frequencies[clean_word] = word_frequencies.get(clean_word, 0) + 1

                if clean_word not in word_pos_tags:
                    word_pos_tags[clean_word] = []
                if tag not in word_pos_tags[clean_word]:
                    word_pos_tags[clean_word].append(tag)
            else:
                if category in filtered_categories:
                    filtered_categories[category] += 1
                else:
                    filtered_categories[category] = 1

        unique_words = sorted(set(informational_words))

        return InformationalWordReport(
            unique_words=unique_words,
            total_document_words=total_document_words,
            total_informational_words=len(informational_words),
            word_frequencies=word_frequencies,
            word_pos_tags=word_pos_tags,
            filtered_categories=filtered_categories,
        )


# ==============================================================================
# Public Helper Functions
# ==============================================================================


def get_unique_informational_words(
    doc_input: Union[str, Path, bytes, dict, list],
    include_verbs: bool = True,
    min_word_length: int = 3,
    file_name: Optional[str] = None,
) -> List[str]:
    """Top-level convenience function to get an alphabetically sorted list of

    unique informational words from any document.
    """
    extractor = InformationalWordExtractor(
        include_verbs=include_verbs,
        min_word_length=min_word_length,
    )
    report = extractor.extract(doc_input, file_name=file_name)
    return report.unique_words


def extract_informational_words(
    doc_input: Union[str, Path, bytes, dict, list],
    include_verbs: bool = True,
    min_word_length: int = 3,
    file_name: Optional[str] = None,
) -> InformationalWordReport:
    """Return full report with unique words, frequencies, and filtration stats."""
    extractor = InformationalWordExtractor(
        include_verbs=include_verbs,
        min_word_length=min_word_length,
    )
    return extractor.extract(doc_input, file_name=file_name)


if __name__ == "__main__":  # pragma: no cover
    import sys

    doc_path = sys.argv[1] if len(sys.argv) > 1 else "input/HR_Policy_Manual.docx"
    print(f"\n--- Extracting Unique Informational Words from: {doc_path} ---")

    report = extract_informational_words(doc_path)
    print(f"Total Document Words: {report.total_document_words}")
    print(f"Total Informational Words: {report.total_informational_words}")
    print(f"Unique Informational Words Count: {report.unique_word_count}\n")

    print("Filtered Grammatical Categories:")
    for cat, count in sorted(report.filtered_categories.items()):
        print(f"  - {cat}: {count}")

    print("\nTop 25 Most Frequent Informational Words:")
    for word, freq in report.top_words(25):
        tags = ",".join(report.word_pos_tags.get(word, []))
        print(f"  {word:<22} ({freq}x, POS: {tags})")

    print(f"\nFirst 50 Unique Words (Alphabetical):")
    print(", ".join(report.unique_words[:50]))
