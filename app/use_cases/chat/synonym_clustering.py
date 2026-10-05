"""
Synonym Clustering and Lexical Grounding Module (Task AB-3.3)

Extracts and filters noun-type words (NN, NNS, NNP, NNPS) from documents and queries
using Part-of-Speech (POS) tagging and lemmatization, clusters them based on
embedding vector cosine similarity, and integrates the resulting synonym clusters
into QueryNormalizer's domain vocabulary for enhanced lexical grounding.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Optional, Set, Sequence

import numpy as np

logger = logging.getLogger(__name__)

# ── Optional NLTK Imports & Fallbacks ──────────────────────────────────────────
try:
    import nltk
    from nltk import pos_tag, word_tokenize
    from nltk.stem import WordNetLemmatizer
    from nltk.corpus import wordnet

    # Ensure required NLTK resources are available without throwing uncaught exceptions
    for res, name in [
        ("tokenizers/punkt", "punkt"),
        ("tokenizers/punkt_tab", "punkt_tab"),
        ("taggers/averaged_perceptron_tagger", "averaged_perceptron_tagger"),
        ("taggers/averaged_perceptron_tagger_eng", "averaged_perceptron_tagger_eng"),
        ("corpora/wordnet", "wordnet"),
        ("corpora/omw-1.4", "omw-1.4"),
    ]:
        try:
            nltk.data.find(res)
        except (LookupError, AttributeError):
            try:
                nltk.download(name, quiet=True)
            except Exception:
                pass

    _lemmatizer = WordNetLemmatizer()
    NLTK_AVAILABLE = True
except Exception as e:  # pragma: no cover
    logger.warning("NLTK not fully available, falling back to heuristic NLP: %s", e)
    NLTK_AVAILABLE = False
    _lemmatizer = None

# Allowed POS tags for noun filtering (as specified in Task AB-3.3)
NOUN_POS_TAGS = {"NN", "NNS", "NNP", "NNPS"}

# Common English stop words to exclude from noun clustering
STOP_WORDS: Set[str] = {
    "a", "an", "the", "and", "or", "but", "if", "because", "as", "what",
    "which", "this", "that", "these", "those", "then", "just", "so", "than",
    "such", "both", "through", "about", "for", "is", "of", "while", "during",
    "to", "from", "in", "out", "on", "off", "again", "further", "then", "once",
    "here", "there", "when", "where", "why", "how", "all", "any", "both",
    "each", "few", "more", "most", "other", "some", "such", "no", "nor",
    "not", "only", "own", "same", "so", "than", "too", "very", "s", "t",
    "can", "will", "don", "should", "now", "i", "me", "my", "we", "our",
    "you", "your", "he", "him", "his", "she", "her", "it", "its", "they",
    "them", "their", "who", "whom", "whose", "be", "been", "being", "have",
    "has", "had", "do", "does", "did", "would", "could", "shall",
}

# Heuristic noun suffixes for fallback POS filtering
_NOUN_SUFFIXES = (
    "tion", "sion", "ment", "ness", "ity", "ance", "ence", "ship",
    "hood", "ism", "ist", "er", "or", "age", "cy", "ure", "dom", "ee"
)


# ── Data Classes ──────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class NounToken:
    """Represents a tagged and lemmatized noun token."""
    raw_token: str
    lemma: str
    pos_tag: str
    is_proper: bool = False

    def __str__(self) -> str:
        return f"{self.raw_token}/{self.pos_tag} -> {self.lemma}"


@dataclass
class SynonymCluster:
    """A cluster of semantically equivalent nouns centered around a canonical term."""
    canonical: str
    synonyms: list[str] = field(default_factory=list)
    members: list[str] = field(default_factory=list)
    similarity_scores: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "canonical": self.canonical,
            "synonyms": self.synonyms,
            "members": self.members,
            "similarity_scores": self.similarity_scores,
        }


@dataclass
class ClusteringResult:
    """Outcome of noun extraction, vector clustering, and synonym map generation."""
    clusters: list[SynonymCluster]
    synonym_map: dict[str, str]
    canonical_nouns: list[str]
    extracted_tokens: list[NounToken]

    @property
    def total_synonyms(self) -> int:
        return len(self.synonym_map)

    @property
    def total_clusters(self) -> int:
        return len(self.clusters)


# ── Main Service Class ────────────────────────────────────────────────────────

class SynonymClusterer:
    """
    Service for extracting noun terms from queries/documents, reducing them to
    canonical lemmas, clustering them via embedding vector cosine similarity,
    and registering synonym maps into QueryNormalizer.
    """

    def __init__(
        self,
        embedding_model: Any = None,
        similarity_threshold: float = 0.65,
        min_word_length: int = 3,
        stop_words: Optional[Set[str]] = None,
    ) -> None:
        """
        Initialize the clusterer.

        Args:
            embedding_model: Optional SentenceTransformer instance or custom encoder.
                             If None, lazily loaded from EMBEDDING_MODEL setting.
            similarity_threshold: Cosine similarity cutoff (default: 0.65) for grouping.
            min_word_length: Minimum character length for valid noun tokens.
            stop_words: Set of words to exclude from noun extraction.
        """
        self._embedding_model = embedding_model
        self.similarity_threshold = float(similarity_threshold)
        self.min_word_length = int(min_word_length)
        self.stop_words = set(stop_words) if stop_words is not None else STOP_WORDS

    def _get_embedding_model(self) -> Any:
        """Lazily load SentenceTransformer embedding model."""
        if self._embedding_model is None:
            try:
                from sentence_transformers import SentenceTransformer
                from app.core.settings import EMBEDDING_MODEL
                self._embedding_model = SentenceTransformer(EMBEDDING_MODEL)
            except Exception as e:
                logger.warning("Could not initialize SentenceTransformer (%s). Mock encoder will be used: %s", type(e), e)
                self._embedding_model = None
        return self._embedding_model

    # ── 1. POS Tagging & Noun Filtering ───────────────────────────────────────

    def _tokenize(self, text: str) -> list[str]:
        """Tokenize text into alphanumeric words."""
        if NLTK_AVAILABLE:
            try:
                return word_tokenize(text)
            except Exception:
                pass
        return re.findall(r"\b[A-Za-z0-9_-]+\b", text)

    def _heuristic_pos_tag(self, tokens: list[str]) -> list[tuple[str, str]]:
        """Fallback heuristic POS tagger when NLTK is unavailable."""
        tagged = []
        for tok in tokens:
            lower = tok.lower()
            if lower in self.stop_words or not tok.isalnum():
                tagged.append((tok, "OTHER"))
            elif tok[0].isupper() and len(tok) > 1:
                tagged.append((tok, "NNP"))
            elif lower.endswith(_NOUN_SUFFIXES) or lower.endswith("s"):
                tagged.append((tok, "NNS" if lower.endswith("s") else "NN"))
            else:
                tagged.append((tok, "NN"))
        return tagged

    def extract_noun_tokens(self, text: str) -> list[NounToken]:
        """
        Extract and filter all noun-type words (NN, NNS, NNP, NNPS) from text.

        Args:
            text: Query or document content.

        Returns:
            List of NounToken objects with raw token, canonical lemma, and POS tag.
        """
        if not text or not text.strip():
            return []

        tokens = self._tokenize(text)
        if not tokens:
            return []

        # Part-of-speech tagging
        tagged_tokens: list[tuple[str, str]] = []
        if NLTK_AVAILABLE:
            try:
                tagged_tokens = pos_tag(tokens)
            except Exception as e:
                logger.debug("NLTK pos_tag failed, using heuristic: %s", e)
                tagged_tokens = self._heuristic_pos_tag(tokens)
        else:
            tagged_tokens = self._heuristic_pos_tag(tokens)

        noun_tokens: list[NounToken] = []
        for raw_tok, tag in tagged_tokens:
            if tag in NOUN_POS_TAGS:
                clean_tok = raw_tok.strip()
                lower_tok = clean_tok.lower()

                # Filter out pure numbers, short tokens, and stop words
                if (
                    len(clean_tok) < self.min_word_length
                    or lower_tok in self.stop_words
                    or not re.search(r"[a-zA-Z]", clean_tok)
                ):
                    continue

                lemma = self.lemmatize_noun(lower_tok)
                is_proper = tag in {"NNP", "NNPS"}

                noun_tokens.append(
                    NounToken(
                        raw_token=clean_tok,
                        lemma=lemma,
                        pos_tag=tag,
                        is_proper=is_proper,
                    )
                )

        return noun_tokens

    # ── 2. Lemmatization ──────────────────────────────────────────────────────

    def lemmatize_noun(self, word: str) -> str:
        """
        Reduce an individual noun token to its canonical lemma base form.

        Args:
            word: The noun string to lemmatize.

        Returns:
            Canonical base lemma in lowercase.
        """
        clean = word.lower().strip()
        if not clean:
            return ""

        # Domain-specific noun lemma overrides (e.g. HR "leaves" -> "leave", not botanical "leaf")
        DOMAIN_LEMMA_OVERRIDES = {
            "leaves": "leave",
            "timeoffs": "timeoff",
            "ptos": "pto",
            "wfh": "work from home",
        }
        if clean in DOMAIN_LEMMA_OVERRIDES:
            return DOMAIN_LEMMA_OVERRIDES[clean]

        if NLTK_AVAILABLE and _lemmatizer is not None:
            try:
                lemma = _lemmatizer.lemmatize(clean, pos="n")
                if lemma:
                    return lemma
            except Exception:
                pass

        # Rule-based fallback lemmatization for English plurals
        if clean.endswith("ies") and len(clean) > 4:
            return clean[:-3] + "y"  # policies -> policy
        elif clean.endswith("es") and len(clean) > 3:
            for stem_ending in ("s", "sh", "ch", "x", "z"):
                if clean[:-2].endswith(stem_ending):
                    return clean[:-2]  # bonuses -> bonus
            return clean[:-1]  # rules -> rule (via es)
        elif clean.endswith("s") and not clean.endswith("ss") and len(clean) > 3:
            return clean[:-1]  # leaves -> leave, days -> day

        return clean

    def extract_canonical_nouns(self, text_or_texts: str | Sequence[str]) -> list[str]:
        """
        Extract deduplicated canonical noun lemmas from one or more texts.

        Args:
            text_or_texts: A single text string or a collection of text documents/queries.

        Returns:
            Sorted list of unique canonical noun lemmas.
        """
        if isinstance(text_or_texts, str):
            texts = [text_or_texts]
        else:
            texts = list(text_or_texts)

        unique_lemmas: Set[str] = set()
        for doc in texts:
            tokens = self.extract_noun_tokens(doc)
            for tok in tokens:
                if len(tok.lemma) >= self.min_word_length and tok.lemma.isalpha():
                    unique_lemmas.add(tok.lemma)

        return sorted(unique_lemmas)

    # ── 3. Vector Embedding & Cosine Similarity Clustering ─────────────────────

    def encode_words(self, words: Sequence[str]) -> np.ndarray:
        """
        Compute embedding vectors for a list of words.

        Args:
            words: Sequence of canonical lemmas.

        Returns:
            2D numpy array of shape (len(words), embedding_dim).
        """
        if not words:
            return np.empty((0, 384), dtype=np.float32)

        model = self._get_embedding_model()
        if model is not None and hasattr(model, "encode"):
            try:
                embeddings = model.encode(list(words), show_progress_bar=False)
                return np.asarray(embeddings, dtype=np.float32)
            except Exception as e:
                logger.warning("Embedding model encode failed: %s", e)

        # Fallback pseudo-embeddings (character n-gram bag of features)
        dim = 128
        matrix = np.zeros((len(words), dim), dtype=np.float32)
        for i, w in enumerate(words):
            for j, ch in enumerate(w):
                idx = (ord(ch) * 31 + j * 17) % dim
                matrix[i, idx] += 1.0
        return matrix

    def compute_cosine_similarity(self, matrix: np.ndarray) -> np.ndarray:
        """
        Compute pairwise cosine similarity matrix with L2 normalization.

        Args:
            matrix: 2D array of embeddings (N x D).

        Returns:
            Symmetric cosine similarity matrix (N x N) bounded in [-1.0, 1.0].
        """
        if matrix.shape[0] == 0:
            return np.empty((0, 0), dtype=np.float32)

        norms = np.linalg.norm(matrix, axis=1, keepdims=True)
        norms = np.where(norms == 0, 1e-9, norms)
        normalized = matrix / norms
        sim_matrix = np.dot(normalized, normalized.T)
        return np.clip(sim_matrix, -1.0, 1.0)

    def cluster_nouns(
        self,
        nouns: Sequence[str],
        threshold: Optional[float] = None,
    ) -> list[SynonymCluster]:
        """
        Group canonical nouns into synonym clusters based on cosine similarity.

        Args:
            nouns: Sequence of canonical noun lemmas to cluster.
            threshold: Optional cosine similarity cutoff. Defaults to self.similarity_threshold.

        Returns:
            List of SynonymCluster objects with canonical representatives and synonyms.
        """
        unique_nouns = [w.lower().strip() for w in dict.fromkeys(nouns) if w.strip()]
        if not unique_nouns:
            return []

        if len(unique_nouns) == 1:
            w = unique_nouns[0]
            return [SynonymCluster(canonical=w, synonyms=[], members=[w], similarity_scores={w: 1.0})]

        cutoff = float(threshold if threshold is not None else self.similarity_threshold)
        embeddings = self.encode_words(unique_nouns)
        sim_matrix = self.compute_cosine_similarity(embeddings)

        n = len(unique_nouns)
        # Graph connected components: an edge exists if sim_matrix[i, j] >= cutoff
        visited = [False] * n
        clusters: list[SynonymCluster] = []

        for i in range(n):
            if visited[i]:
                continue

            # BFS/DFS to collect all connected words in this cluster
            component_indices: list[int] = []
            queue = [i]
            visited[i] = True

            while queue:
                curr = queue.pop(0)
                component_indices.append(curr)
                for neighbor in range(n):
                    if not visited[neighbor] and sim_matrix[curr, neighbor] >= cutoff:
                        visited[neighbor] = True
                        queue.append(neighbor)

            members = [unique_nouns[idx] for idx in component_indices]

            # Choose the canonical representative:
            # The member with the highest average similarity to all other members in the cluster,
            # using shortest length and alphabetical order as tie-breakers.
            if len(members) == 1:
                canonical = members[0]
                synonyms = []
                scores = {canonical: 1.0}
            else:
                best_member = members[0]
                best_score = -1.0

                for idx in component_indices:
                    avg_sim = float(np.mean([sim_matrix[idx, other] for other in component_indices]))
                    cand = unique_nouns[idx]
                    # Score combines centrality with preference for concise canonical words
                    composite_score = avg_sim - (len(cand) * 0.001)
                    if composite_score > best_score:
                        best_score = composite_score
                        best_member = cand

                canonical = best_member
                synonyms = [m for m in members if m != canonical]

                canonical_idx = unique_nouns.index(canonical)
                scores = {
                    unique_nouns[idx]: float(sim_matrix[canonical_idx, idx])
                    for idx in component_indices
                }

            clusters.append(
                SynonymCluster(
                    canonical=canonical,
                    synonyms=sorted(synonyms),
                    members=sorted(members),
                    similarity_scores=scores,
                )
            )

        return clusters

    # ── 4. Synonym Mapping & QueryNormalizer Integration ──────────────────────

    def build_synonym_map(self, clusters: Sequence[SynonymCluster]) -> dict[str, str]:
        """
        Convert clusters into a flat synonym-to-canonical dictionary.

        Args:
            clusters: Sequence of SynonymCluster objects.

        Returns:
            Dictionary mapping {synonym: canonical_lemma}.
        """
        synonym_map: dict[str, str] = {}
        for cluster in clusters:
            for syn in cluster.synonyms:
                if syn != cluster.canonical:
                    synonym_map[syn] = cluster.canonical
        return synonym_map

    def integrate_with_query_normalizer(
        self,
        synonym_map: dict[str, str],
        normalizer: Optional[Any] = None,
    ) -> int:
        """
        Register synonym mappings into QueryNormalizer's domain vocabulary.

        Args:
            synonym_map: Mapping of {synonym: canonical}.
            normalizer: QueryNormalizer instance. If None, uses global singleton.

        Returns:
            Number of registered synonym pairs.
        """
        if not synonym_map:
            return 0

        if normalizer is None:
            from app.use_cases.chat.query_normalizer import get_query_normalizer
            normalizer = get_query_normalizer()

        if hasattr(normalizer, "register_synonyms"):
            return normalizer.register_synonyms(synonym_map)

        # Fallback direct registration if register_synonyms not present
        from app.use_cases.chat.query_normalizer import DOMAIN_VOCABULARY
        count = 0
        for syn, canon in synonym_map.items():
            DOMAIN_VOCABULARY[syn] = canon
            count += 1

        if hasattr(normalizer, "_sorted_vocab"):
            normalizer._sorted_vocab = sorted(
                DOMAIN_VOCABULARY.items(),
                key=lambda x: len(x[0]),
                reverse=True,
            )
        return count

    def cluster_and_register(
        self,
        texts: str | Sequence[str],
        normalizer: Optional[Any] = None,
        threshold: Optional[float] = None,
    ) -> ClusteringResult:
        """
        End-to-end pipeline: extracts nouns from input texts, reduces them to lemmas,
        clusters by embedding similarity, and registers synonym pairs into QueryNormalizer.

        Args:
            texts: Query, list of queries, or document strings to learn from.
            normalizer: QueryNormalizer instance to update (defaults to global singleton).
            threshold: Cosine similarity cutoff.

        Returns:
            ClusteringResult containing clusters, synonym map, and extracted nouns.
        """
        if isinstance(texts, str):
            text_list = [texts]
        else:
            text_list = list(texts)

        all_tokens: list[NounToken] = []
        for t in text_list:
            all_tokens.extend(self.extract_noun_tokens(t))

        canonical_nouns = sorted(list({tok.lemma for tok in all_tokens if tok.lemma}))
        clusters = self.cluster_nouns(canonical_nouns, threshold=threshold)
        synonym_map = self.build_synonym_map(clusters)

        if synonym_map:
            self.integrate_with_query_normalizer(synonym_map, normalizer=normalizer)
            logger.info(
                "Registered %d vector synonym clusters (%d synonyms mapped) into QueryNormalizer",
                len([c for c in clusters if c.synonyms]),
                len(synonym_map),
            )

        return ClusteringResult(
            clusters=clusters,
            synonym_map=synonym_map,
            canonical_nouns=canonical_nouns,
            extracted_tokens=all_tokens,
        )


# ── Global Singleton Access ───────────────────────────────────────────────────

_global_synonym_clusterer: Optional[SynonymClusterer] = None


def get_synonym_clusterer(
    embedding_model: Any = None,
    similarity_threshold: float = 0.65,
) -> SynonymClusterer:
    """Return the global SynonymClusterer singleton instance."""
    global _global_synonym_clusterer
    if _global_synonym_clusterer is None:
        _global_synonym_clusterer = SynonymClusterer(
            embedding_model=embedding_model,
            similarity_threshold=similarity_threshold,
        )
    return _global_synonym_clusterer
