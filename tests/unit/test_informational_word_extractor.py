"""Unit tests for InformationalWordExtractor and dynamic document vocabulary extraction."""

import io
from pathlib import Path

import pytest

from app.use_cases.chat.query_normalizer import QueryNormalizer
from app.use_cases.ingestion.informational_word_extractor import (
    InformationalWordExtractor,
    InformationalWordReport,
    extract_informational_words,
    get_unique_informational_words,
)


class TestPOSFiltration:
    """Validate that non-informational parts of speech are removed."""

    def setup_method(self):
        self.extractor = InformationalWordExtractor(include_verbs=True, min_word_length=3)

    def test_articles_removed(self):
        text = "The employee submitted a request for an allowance."
        words = self.extractor.extract(text).unique_words
        assert "the" not in words
        assert "a" not in words
        assert "an" not in words
        assert "employee" in words
        assert "allowance" in words

    def test_pronouns_removed(self):
        text = "She told him that they will assist us with our department goals, and he can manage it himself."
        report = self.extractor.extract(text)
        words = report.unique_words

        pronouns_to_check = ["she", "him", "they", "us", "our", "he", "it", "himself"]
        for p in pronouns_to_check:
            assert p not in words, f"Pronoun '{p}' was not filtered!"

        # Informational words should remain
        assert "department" in words
        assert "goals" in words

    def test_adjectives_removed(self):
        text = "The annual policy gives eligible employees new benefits and large allowances."
        report = self.extractor.extract(text)
        words = report.unique_words

        adjectives_to_check = ["annual", "eligible", "new", "large"]
        for adj in adjectives_to_check:
            assert adj not in words, f"Adjective '{adj}' was not filtered!"

        # Core nouns/verbs should remain
        assert "policy" in words
        assert "employees" in words
        assert "benefits" in words
        assert "allowances" in words

    def test_prepositions_and_conjunctions_removed(self):
        text = "Employees in the office or at home can apply for leave because health matters."
        words = self.extractor.extract(text).unique_words

        for prep_conj in ["in", "or", "at", "for", "because"]:
            assert prep_conj not in words

        assert "office" in words
        assert "home" in words
        assert "leave" in words

    def test_auxiliaries_and_modals_removed(self):
        text = "The manager has approved what could be done and is expecting results."
        words = self.extractor.extract(text).unique_words

        for aux in ["has", "could", "be", "done", "and", "is"]:
            assert aux not in words

        assert "manager" in words
        assert "results" in words

    def test_adverbs_and_negations_removed(self):
        text = "Employees should not ever access confidential data very quickly."
        words = self.extractor.extract(text).unique_words

        for adv in ["not", "ever", "very", "quickly"]:
            assert adv not in words


class TestInformationalRetention:
    """Validate that substantive nouns and action verbs are correctly retained."""

    def test_informational_nouns_retained(self):
        text = "Reimbursement for travel, maternity leave, and employee insurance policies."
        report = extract_informational_words(text)
        words = report.unique_words

        expected_nouns = ["reimbursement", "travel", "maternity", "leave", "employee", "insurance", "policies"]
        for expected in expected_nouns:
            assert expected in words, f"Expected informational noun '{expected}' was missing!"

    def test_action_verbs_included_by_default(self):
        text = "The supervisor will investigate allegations, sanction violators, and approve claims."
        extractor = InformationalWordExtractor(include_verbs=True)
        report = extractor.extract(text)
        words = report.unique_words

        assert "investigate" in words
        assert "allegations" in words
        assert "violators" in words
        assert "claims" in words

    def test_verbs_excluded_when_disabled(self):
        text = "The supervisor will investigate allegations and approve claims."
        extractor = InformationalWordExtractor(include_verbs=False)
        report = extractor.extract(text)
        words = report.unique_words

        # With verbs excluded, only nouns should remain
        assert "supervisor" in words
        assert "allegations" in words
        assert "claims" in words
        assert "investigate" not in words
        assert "approve" not in words
        assert report.filtered_categories.get("verb_excluded", 0) > 0


class TestDynamicDocumentAcceptance:
    """Validate that any document type (path, raw text, bytes, CSV, JSON) is accepted."""

    def test_accept_raw_string(self):
        text = "Nexora Technologies provides annual leave and bereavement benefits."
        words = get_unique_informational_words(text)
        assert isinstance(words, list)
        assert "technologies" in words
        assert "leave" in words
        assert "benefits" in words

    def test_accept_path_object_and_docx(self):
        path = Path("input/HR_Policy_Manual.docx")
        if path.exists():
            report = extract_informational_words(path)
            assert isinstance(report, InformationalWordReport)
            assert report.unique_word_count > 100
            assert "company" in report.unique_words
            assert "policy" in report.unique_words
            assert "leave" in report.unique_words
            assert "the" not in report.unique_words
            assert "annual" not in report.unique_words

    def test_accept_posh_docx(self):
        path = Path("input/POSH_Policy.docx")
        if path.exists():
            report = extract_informational_words(str(path))
            assert "complaint" in report.unique_words
            assert "committee" in report.unique_words
            assert "harassment" in report.unique_words
            assert "posh" in report.unique_words
            assert "she" not in report.unique_words
            assert "her" not in report.unique_words

    def test_accept_bytes_with_filename(self):
        csv_content = b"department,role,policy\nEngineering,Architect,Security\nOperations,Manager,Discipline"
        report = extract_informational_words(csv_content, file_name="data.csv")
        assert "engineering" in report.unique_words
        assert "architect" in report.unique_words
        assert "security" in report.unique_words
        assert "operations" in report.unique_words

    def test_accept_json_content(self):
        json_bytes = b'{"policy": "Attendance", "section": "Probation Guidelines", "rules": ["Punctuality", "Notice"]}'
        report = extract_informational_words(json_bytes, file_name="policy.json")
        assert "attendance" in report.unique_words
        assert "probation" in report.unique_words
        assert "guidelines" in report.unique_words
        assert "punctuality" in report.unique_words

    def test_empty_input(self):
        report = extract_informational_words("")
        assert report.unique_words == []
        assert report.total_document_words == 0
        assert report.unique_word_count == 0


class TestDynamicSpellcheckerLearning:
    """Validate that extracted document words expand the spellchecker's vocabulary."""

    def test_query_normalizer_learns_document(self):
        normalizer = QueryNormalizer()
        sample_doc = "The quantumcryptography module ensures hyperencryption standards across the cluster."

        # Extract & learn words
        learned = normalizer.learn_document(sample_doc)
        assert "quantumcryptography" in learned
        assert "hyperencryption" in learned
        assert "standards" in learned

        # Verify dynamic vocabulary registration
        assert "quantumcryptography" in normalizer._domain_keywords
        assert "hyperencryption" in normalizer._domain_keywords

        # Test normalization on query containing newly learned word
        res = normalizer.normalize("Tell me about hyperencryption")
        assert "hyperencryption" in res.normalized_query
