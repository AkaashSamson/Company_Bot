"""
Unit Tests for Synonym Clustering & Lexical Grounding (Task AB-3.3)

Validates:
- POS noun extraction (NN, NNS, NNP, NNPS)
- Lemmatization to canonical noun base forms
- Vector embedding cosine similarity clustering
- Integration with QueryNormalizer domain vocabulary
"""

import pytest
import numpy as np
from unittest.mock import MagicMock

from app.use_cases.chat.synonym_clustering import (
    SynonymClusterer,
    SynonymCluster,
    NounToken,
    ClusteringResult,
    get_synonym_clusterer,
)
from app.use_cases.chat.query_normalizer import QueryNormalizer


class MockEncoder:
    """Mock embedding model that returns controlled vector representations."""

    def __init__(self, vector_map: dict[str, list[float]], default_dim: int = 4):
        self.vector_map = {k.lower(): np.array(v, dtype=np.float32) for k, v in vector_map.items()}
        self.default_dim = default_dim

    def encode(self, words: list[str], show_progress_bar: bool = False) -> np.ndarray:
        vectors = []
        for w in words:
            lower = w.lower()
            if lower in self.vector_map:
                vectors.append(self.vector_map[lower])
            else:
                # Random deterministic vector
                np.random.seed(abs(hash(lower)) % (2**32))
                vec = np.random.randn(self.default_dim).astype(np.float32)
                vectors.append(vec / np.linalg.norm(vec))
        return np.array(vectors)


class TestPOSNounExtraction:
    """Test Part-of-Speech noun filtering and lemmatization."""

    @pytest.fixture
    def clusterer(self):
        return SynonymClusterer()

    def test_extract_noun_tokens_basic(self, clusterer):
        text = "Employees must submit their leave applications to the department manager."
        tokens = clusterer.extract_noun_tokens(text)

        # Expected noun words: employees, leave, applications, department, manager
        lemmas = [tok.lemma for tok in tokens]
        assert "employee" in lemmas
        assert "application" in lemmas
        assert "leave" in lemmas or "department" in lemmas

        # Ensure verbs/prepositions/pronouns are NOT included
        assert "must" not in lemmas
        assert "submit" not in lemmas
        assert "their" not in lemmas
        assert "to" not in lemmas

    def test_pos_tags_are_strictly_nouns(self, clusterer):
        text = "The doctor prescribes modern medicines for acute sickness."
        tokens = clusterer.extract_noun_tokens(text)

        for tok in tokens:
            assert tok.pos_tag in {"NN", "NNS", "NNP", "NNPS"}

    def test_lemmatize_plural_nouns(self, clusterer):
        test_cases = [
            ("policies", "policy"),
            ("leaves", "leave"),
            ("allowances", "allowance"),
            ("bonuses", "bonus"),
            ("days", "day"),
            ("salaries", "salary"),
        ]
        for plural, expected_lemma in test_cases:
            lemma = clusterer.lemmatize_noun(plural)
            assert lemma == expected_lemma, f"Failed for {plural}: got {lemma}"

    def test_extract_canonical_nouns_deduplication(self, clusterer):
        docs = [
            "What are the leave policies for full-time employees?",
            "How does an employee request annual leave or sick leaves?",
        ]
        canonical = clusterer.extract_canonical_nouns(docs)

        # Verify deduplicated and canonical
        assert isinstance(canonical, list)
        assert len(canonical) == len(set(canonical))
        assert "employee" in canonical
        assert "leave" in canonical
        assert "policy" in canonical

    def test_empty_and_noise_text(self, clusterer):
        assert clusterer.extract_noun_tokens("") == []
        assert clusterer.extract_noun_tokens("   123  !@#  ") == []
        assert clusterer.extract_canonical_nouns([]) == []


class TestVectorSynonymClustering:
    """Test cosine similarity grouping and cluster generation."""

    def test_cluster_nouns_with_mock_embeddings(self):
        # salary and wages are very close ([1, 0, 0]), vacation and holiday are close ([0, 1, 0])
        vector_map = {
            "salary": [1.0, 0.0, 0.0, 0.0],
            "wages": [0.98, 0.05, 0.0, 0.0],
            "vacation": [0.0, 1.0, 0.0, 0.0],
            "holiday": [0.0, 0.95, 0.05, 0.0],
            "computer": [0.0, 0.0, 1.0, 0.0],
        }
        mock_encoder = MockEncoder(vector_map, default_dim=4)
        clusterer = SynonymClusterer(embedding_model=mock_encoder, similarity_threshold=0.80)

        nouns = ["salary", "wages", "vacation", "holiday", "computer"]
        clusters = clusterer.cluster_nouns(nouns)

        assert len(clusters) == 3

        # Check multi-member clusters
        multi_clusters = [c for c in clusters if len(c.members) > 1]
        assert len(multi_clusters) == 2

        cluster_members = [set(c.members) for c in multi_clusters]
        assert {"salary", "wages"} in cluster_members
        assert {"vacation", "holiday"} in cluster_members

        # Check synonym map
        synonym_map = clusterer.build_synonym_map(clusters)
        assert len(synonym_map) == 2
        assert "wages" in synonym_map or "salary" in synonym_map
        assert "holiday" in synonym_map or "vacation" in synonym_map

    def test_single_noun_clustering(self):
        clusterer = SynonymClusterer()
        clusters = clusterer.cluster_nouns(["policy"])
        assert len(clusters) == 1
        assert clusters[0].canonical == "policy"
        assert clusters[0].synonyms == []

    def test_cosine_similarity_bounds(self):
        clusterer = SynonymClusterer()
        mat = np.array([[1.0, 2.0], [-1.0, -2.0], [0.0, 1.0]])
        sim = clusterer.compute_cosine_similarity(mat)
        assert sim.shape == (3, 3)
        assert np.isclose(sim[0, 0], 1.0)
        assert np.isclose(sim[0, 1], -1.0)


class TestQueryNormalizerIntegration:
    """Test full integration between SynonymClusterer and QueryNormalizer."""

    def test_cluster_and_register_into_normalizer(self):
        normalizer = QueryNormalizer(
            enable_vocabulary_mapping=True,
            enable_typo_correction=False,
            enable_lemmatization=False,
        )

        # Vector map with stipend mapped to allowance
        vector_map = {
            "allowance": [1.0, 0.0],
            "stipend": [0.99, 0.05],
        }
        mock_encoder = MockEncoder(vector_map, default_dim=2)
        clusterer = SynonymClusterer(embedding_model=mock_encoder, similarity_threshold=0.85)

        texts = ["What is the monthly stipend and travel allowance?"]
        result = clusterer.cluster_and_register(texts, normalizer=normalizer, threshold=0.85)

        assert isinstance(result, ClusteringResult)
        assert "stipend" in result.synonym_map or "allowance" in result.synonym_map

        # Verify QueryNormalizer now normalizes the synonym!
        norm_result = normalizer.normalize("How to claim my stipend?")
        assert "allowance" in norm_result.normalized_query or "stipend" in norm_result.normalized_query
        assert norm_result.was_modified is True

    def test_register_synonyms_direct_method(self):
        normalizer = QueryNormalizer(enable_vocabulary_mapping=True)
        count = normalizer.register_synonyms({"remuneration": "salary", "timeoff": "leave"})
        assert count == 2

        norm = normalizer.normalize("check my remuneration and timeoff")
        assert "salary" in norm.normalized_query
        assert "leave" in norm.normalized_query

    def test_singleton_retrieval(self):
        c1 = get_synonym_clusterer()
        c2 = get_synonym_clusterer()
        assert c1 is c2
