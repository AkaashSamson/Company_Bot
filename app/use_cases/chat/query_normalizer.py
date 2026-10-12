"""
Enhanced Query Normalizer with Advanced NLP Features

Implements comprehensive query normalization for chatbots:
- Case normalization (lowercase)
- Whitespace normalization
- Punctuation & symbol handling
- Spelling correction (pyspellchecker)
- Lemmatization (NLTK WordNetLemmatizer)
- Domain vocabulary mapping (HR-specific)
- Entity preservation (don't alter proper nouns)
- Keyboard layout correction (QWERTY)
- Language detection (optional)
- Modular pipeline design

Based on best practices for chatbot query normalization.
"""

import logging
import math
import re
import unicodedata
from dataclasses import dataclass
from typing import Any, Callable, Iterable, Optional, Sequence, Set

logger = logging.getLogger(__name__)

# Try to import optional NLP libraries
try:
    from spellchecker import SpellChecker
    SPELLCHECK_AVAILABLE = True
except ImportError:
    SPELLCHECK_AVAILABLE = False
    logger.warning("pyspellchecker not available, typo correction limited")

try:
    from nltk.stem import WordNetLemmatizer
    from nltk.corpus import wordnet
    LEMMATIZER_AVAILABLE = True
    # Initialize lemmatizer
    _lemmatizer = WordNetLemmatizer()
except ImportError:
    LEMMATIZER_AVAILABLE = False
    _lemmatizer = None
    logger.warning("NLTK not available, lemmatization disabled")


# ============================================================
# HR Domain Vocabulary - Maps variations to canonical forms
# ============================================================

DOMAIN_VOCABULARY = {
    # Leave-related terms (longer phrases first for proper matching)
    "maternity leave": "maternity leave",
    "paternity leave": "paternity leave",
    "parental leave": "parental leave",
    "bereavement leave": "bereavement leave",
    "annual leave": "annual leave",
    "sick leave": "sick leave",
    "casual leave": "casual leave",
    "unpaid leave": "unpaid leave",
    "paid time off": "paid time off",
    "leave entitlement": "leave entitlement",
    "leave balance": "leave balance",
    "leave accrual": "leave accrual",
    "leave days": "annual leave",
    "vacation days": "annual leave",
    "carry forward": "carry forward",
    "time off": "leave",
    "leaves": "leave",
    "pto": "paid time off",
    "medical leave": "sick leave",
    
    # Compensation terms
    "salary": "salary",
    "pay": "salary",
    "wages": "salary",
    "compensation": "compensation",
    "bonus": "bonus",
    "bonuses": "bonus",
    "performance bonus": "performance bonus",
    "variable pay": "variable pay",
    "benefits": "benefits",
    "perks": "benefits",
    "insurance": "insurance",
    "health insurance": "health insurance",
    "pf": "provident fund",
    "provident fund": "provident fund",
    "gratuity": "gratuity",
    
    # Policy terms
    "policy": "policy",
    "policies": "policy",
    "handbook": "handbook",
    "employee handbook": "handbook",
    "hr policy": "policy",
    "company policy": "policy",
    
    # Work-related terms
    "work from home": "work from home",
    "wfh": "work from home",
    "remote work": "work from home",
    "hybrid": "hybrid work",
    "office": "office",
    "working hours": "working hours",
    "work hours": "working hours",
    "shift": "shift",
    
    # Conduct terms
    "code of conduct": "code of conduct",
    "conduct": "code of conduct",
    "harassment": "harassment",
    "sexual harassment": "sexual harassment",
    "posh": "sexual harassment",
    "grievance": "grievance",
    "disciplinary": "disdisciplinary",
    "misconduct": "misconduct",
    
    # General HR terms
    "employee": "employee",
    "employees": "employee",
    "staff": "employee",
    "hr": "human resources",
    "human resources": "human resources",
    "manager": "manager",
    "supervisor": "manager",
    "appraisal": "performance appraisal",
    "performance review": "performance appraisal",
    "promotion": "promotion",
    "resignation": "resignation",
    "termination": "termination",
    "exit": "resignation",
    
    # Knowledge Assistant & Platform terms
    "knowledge": "knowledge",
    "knowlayer": "knowlayer",
    "know layer": "knowlayer",
    "know ledge": "knowledge",
    "know leedge": "knowledge",
    "knowledge system": "knowledge assistant",
    "knowledge assistant": "knowledge assistant",
}


# ============================================================
# Common Typos in HR Queries
# ============================================================

COMMON_TYPOS = {
    "leave": ["leve", "leaave", "leav", "levae", "myleve", "leavee"],
    "salary": ["slary", "salry", "salery", "selary"],
    "policy": ["polic", "poliocy", "policty", "poilcy", "ploicy", "polciy"],
    "payment": ["pyment", "paymnet", "pymnt", "paymet", "paymnt"],
    "bonus": ["bonas", "bonous", "bonnus"],
    "insurance": ["insuarance", "insurence", "insurans"],
    "harassment": ["harasment", "harassment", "harasment"],
    "benefits": ["benifits", "benefites", "benfits", "benefit"],
    "provident": ["provident", "providnt"],
    "maternity": ["maternity", "materinity"],
    "paternity": ["paternity", "paterinity"],
    "resignation": ["resignaton", "resigantion", "resigntion"],
    "attendance": ["attendace", "attenddance", "atendence"],
    "annual": ["annul", "anual", "annuel"],
    "knowledge": ["knowlege", "knowledg", "knowldge", "knowleedge", "leedge"],
    "knowlayer": ["knowlyer", "knowleyer", "knowler"],
}

# Build reverse lookup for typos (typo -> correct)
TYPO_CORRECTIONS: dict[str, str] = {}
for correct, typos in COMMON_TYPOS.items():
    for typo in typos:
        TYPO_CORRECTIONS[typo] = correct


# ============================================================
# Keyboard Layout Corrections (QWERTY common mistakes)
# ============================================================

QWERTY_MISTAKES = {
    "teh": "the",
    "hte": "the",
    "taht": "that",
    "tje": "the",
    "tje": "the",
    "hw": "how",
    "hwo": "how",
    "wrogn": "wrong",
    "wrok": "work",
    "woek": "work",
    "requst": "request",
    "reques": "request",
}


# ============================================================
# Entities to Preserve (don't alter these)
# ============================================================

# Common HR entities that should not be modified
PRESERVED_ENTITIES: Set[str] = {
    # Company names (example)
    "nexora",
    # Month names
    "january", "february", "march", "april", "may", "june",
    "july", "august", "september", "october", "november", "december",
    # Days
    "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday",
}


@dataclass
class NormalizationResult:
    """Result of query normalization."""
    original_query: str
    normalized_query: str
    cache_key: str
    corrections_made: list[str]
    expansions_applied: list[str]
    was_modified: bool
    detected_language: Optional[str] = None
    entities_preserved: list[str] = None
    
    def __post_init__(self):
        if self.entities_preserved is None:
            self.entities_preserved = []


class QueryNormalizer:
    """
    Enhanced Query Normalizer with comprehensive NLP pipeline.
    
    Pipeline stages (in order):
    1. Text Cleaning (HTML, emojis, control chars)
    2. Unicode Normalization (NFKD, accent removal)
    3. Case Normalization (lowercase)
    4. Whitespace Normalization
    5. Punctuation & Symbol Handling
    6. Keyboard Layout Correction
    7. Spelling Correction
    8. Domain Vocabulary Mapping
    9. Lemmatization
    10. Final Cleanup
    
    Features:
    - Configurable pipeline stages (enable/disable)
    - Entity preservation (don't alter proper nouns)
    - Domain-specific vocabulary mapping
    - Deterministic cache key generation
    - Thread-safe operation
    """
    
    def __init__(
        self,
        enable_text_cleaning: bool = True,
        enable_unicode_normalization: bool = True,
        enable_case_normalization: bool = True,
        enable_whitespace_normalization: bool = True,
        enable_punctuation_handling: bool = True,
        enable_keyboard_correction: bool = True,
        enable_word_boundary: bool = True,
        enable_typo_correction: bool = True,
        enable_spellcheck: bool = True,
        enable_vocabulary_mapping: bool = True,
        enable_lemmatization: bool = True,
        enable_entity_preservation: bool = True,
    ):
        """
        Initialize query normalizer with configurable pipeline.
        
        Args:
            enable_text_cleaning: Remove HTML, emojis, control chars
            enable_unicode_normalization: NFKD normalization, accent removal
            enable_case_normalization: Convert to lowercase
            enable_whitespace_normalization: Fix extra spaces
            enable_punctuation_handling: Remove/standardize punctuation
            enable_keyboard_correction: Fix QWERTY layout mistakes
            enable_word_boundary: Fix conjoined words and camelCase
            enable_typo_correction: Fix common typos via dictionary
            enable_spellcheck: Use pyspellchecker for unknown words
            enable_vocabulary_mapping: Apply domain vocabulary
            enable_lemmatization: Reduce words to base form
            enable_entity_preservation: Don't modify proper nouns
        """
        # Store configuration
        self.config = {
            "text_cleaning": enable_text_cleaning,
            "unicode_normalization": enable_unicode_normalization,
            "case_normalization": enable_case_normalization,
            "whitespace_normalization": enable_whitespace_normalization,
            "punctuation_handling": enable_punctuation_handling,
            "keyboard_correction": enable_keyboard_correction,
            "word_boundary": enable_word_boundary,
            "typo_correction": enable_typo_correction,
            "spellcheck": enable_spellcheck and SPELLCHECK_AVAILABLE,
            "vocabulary_mapping": enable_vocabulary_mapping,
            "lemmatization": enable_lemmatization and LEMMATIZER_AVAILABLE,
            "entity_preservation": enable_entity_preservation,
        }
        
        # Collect distinct domain keywords for fuzzy matching and word boundary fixing
        self._domain_keywords = set()
        for k, v in DOMAIN_VOCABULARY.items():
            for w in k.split() + v.split():
                clean_w = re.sub(r'[^a-z0-9]', '', w.lower())
                if len(clean_w) >= 3:
                    self._domain_keywords.add(clean_w)
        for term in COMMON_TYPOS.keys():
            clean_term = re.sub(r'[^a-z0-9]', '', term.lower())
            if len(clean_term) >= 3:
                self._domain_keywords.add(clean_term)

        # Standard vocabulary words commonly found in HR queries
        self._common_query_words = {
            "available", "balance", "request", "apply", "application", "status",
            "rules", "rule", "days", "day", "hours", "hour", "portal", "process",
            "details", "info", "information", "form", "forms", "date", "dates",
            "list", "types", "type", "guidelines", "guide", "my", "our", "your",
            "can", "how", "what", "when", "who", "where", "why", "get", "take",
            "need", "have", "check", "view", "many", "much", "time", "off", "from",
            "work", "home", "office", "holiday", "holidays", "leave", "leaves",
            "policy", "policies", "salary", "pay", "bonus", "benefits", "insurance"
        }
        self._known_words = self._domain_keywords | self._common_query_words

        # Initialize spellchecker if available
        self._spell = SpellChecker() if SPELLCHECK_AVAILABLE else None
        if self._spell:
            try:
                self._spell.word_frequency.load_words(self._domain_keywords)
            except Exception as e:
                logger.debug("Could not load domain words into spellchecker: %s", e)
        
        # Sort vocabulary by length (longest first) for proper matching
        self._sorted_vocab = sorted(
            DOMAIN_VOCABULARY.items(),
            key=lambda x: len(x[0]),
            reverse=True
        )
        
        logger.info(
            "query_normalizer initialized config=%s",
            {k: v for k, v in self.config.items() if v}
        )

    def add_vocabulary(self, words: Iterable[str]) -> None:
        """Dynamically add new domain words to the vocabulary and spellchecker."""
        new_keywords = set()
        for w in words:
            clean_w = re.sub(r"[^a-z0-9]", "", w.lower().strip())
            if len(clean_w) >= 3 and clean_w.isalpha():
                new_keywords.add(clean_w)
                self._domain_keywords.add(clean_w)
                if clean_w not in DOMAIN_VOCABULARY:
                    DOMAIN_VOCABULARY[clean_w] = clean_w

        if self._spell and new_keywords:
            try:
                self._spell.word_frequency.load_words(new_keywords)
            except Exception as e:
                logger.debug("Could not load words into spellchecker: %s", e)

        # Re-sort vocabulary by length (longest first)
        self._sorted_vocab = sorted(
            DOMAIN_VOCABULARY.items(),
            key=lambda x: len(x[0]),
            reverse=True,
        )

    def register_synonyms(self, synonym_map: dict[str, str]) -> int:
        """Dynamically register synonyms mapping to canonical domain terms."""
        registered_count = 0
        new_keywords = set()
        for syn, canonical in synonym_map.items():
            clean_syn = syn.lower().strip()
            clean_canon = canonical.lower().strip()
            if not clean_syn or not clean_canon or clean_syn == clean_canon:
                continue
            DOMAIN_VOCABULARY[clean_syn] = clean_canon
            for word_part in clean_syn.split():
                if len(word_part) >= 3 and word_part.isalpha():
                    new_keywords.add(word_part)
                    self._domain_keywords.add(word_part)
            registered_count += 1

        if self._spell and new_keywords:
            try:
                self._spell.word_frequency.load_words(new_keywords)
            except Exception as e:
                logger.debug("Could not load words into spellchecker: %s", e)

        # Re-sort vocabulary by length (longest first)
        self._sorted_vocab = sorted(
            DOMAIN_VOCABULARY.items(),
            key=lambda x: len(x[0]),
            reverse=True,
        )
        return registered_count

    def register_synonym_clusters(self, clusters: Iterable[Any]) -> int:
        """Register synonym clusters into domain vocabulary."""
        syn_map = {}
        for c in clusters:
            canon = getattr(c, "canonical", None)
            syns = getattr(c, "synonyms", None)
            if canon and syns:
                for s in syns:
                    syn_map[s] = canon
            elif isinstance(c, dict):
                canon = c.get("canonical")
                syns = c.get("synonyms", [])
                if canon and syns:
                    for s in syns:
                        syn_map[s] = canon
        return self.register_synonyms(syn_map)

    def learn_document(
        self,
        doc_input: Any,
        file_name: Optional[str] = None,
    ) -> list[str]:
        """Extract unique informational words from any document and register them dynamically."""
        from app.use_cases.ingestion.informational_word_extractor import get_unique_informational_words

        unique_words = get_unique_informational_words(doc_input, file_name=file_name)
        self.add_vocabulary(unique_words)
        return unique_words

    def learn_nouns_from_chunks(
        self,
        chunks: Sequence[dict | str] | Iterable[dict | str],
        cluster_synonyms: bool = False,
    ) -> set[str]:
        """
        Dynamically generate unique vocabulary based on the set() of NN (nouns)
        from the chunks retrieved.

        Extracts all noun tokens (NN, NNS, NNP, NNPS), lemmatizes them to canonical
        base forms, and adds the resulting set of unique nouns to the domain vocabulary
        and spellchecker dictionary.

        Args:
            chunks: Retrieved evidence chunks (dicts with 'text' or raw text strings).
            cluster_synonyms: Whether to also compute vector synonym clusters.

        Returns:
            The set of unique canonical noun vocabulary generated from the chunks.
        """
        if not chunks:
            return set()

        from app.use_cases.chat.synonym_clustering import get_synonym_clusterer
        clusterer = get_synonym_clusterer()
        unique_nouns = clusterer.extract_unique_nouns_from_chunks(chunks)

        if unique_nouns:
            self.add_vocabulary(unique_nouns)
            if cluster_synonyms:
                chunk_texts = [c.get("text", "") if isinstance(c, dict) else str(c) for c in chunks]
                chunk_texts = [t for t in chunk_texts if t.strip()]
                if chunk_texts:
                    try:
                        clusterer.cluster_and_register(chunk_texts, normalizer=self)
                    except Exception as exc:
                        logger.debug("Synonym clustering on chunks skipped: %s", exc)
            logger.info(
                "Dynamically generated %d unique noun vocabulary terms from retrieved chunks",
                len(unique_nouns),
            )

        return unique_nouns
    
    def normalize(self, query: str) -> NormalizationResult:
        """
        Normalize a query string through the full pipeline.
        
        Args:
            query: Raw user query
            
        Returns:
            NormalizationResult with normalized query and metadata
        """
        if not query or not query.strip():
            return NormalizationResult(
                original_query=query or "",
                normalized_query="",
                cache_key=self._generate_cache_key(""),
                corrections_made=[],
                expansions_applied=[],
                was_modified=False,
            )
        
        original = query
        corrections_made = []
        expansions_applied = []
        entities_preserved = []
        
        # Stage 1: Text Cleaning
        if self.config["text_cleaning"]:
            query = self._clean_text(query)
        
        # Stage 2: Unicode Normalization
        if self.config["unicode_normalization"]:
            query = self._normalize_unicode(query)
        
        # Stage 3: Case Normalization
        if self.config["case_normalization"]:
            query = query.lower()
        
        # Stage 4: Whitespace Normalization
        if self.config["whitespace_normalization"]:
            query = query.strip()
            query = re.sub(r'\s+', ' ', query)
        
        # Stage 5: Punctuation Handling
        if self.config["punctuation_handling"]:
            query, punct_removed = self._handle_punctuation(query)
            if punct_removed:
                corrections_made.append(f"punctuation_removed: {punct_removed}")
        
        # Stage 5b: Word Boundary Fixing (conjoined words, e.g. "leavesavailable" -> "leaves available")
        if self.config.get("word_boundary", True):
            query, boundary_fixes = self._fix_word_boundaries(query)
            corrections_made.extend(boundary_fixes)
        
        # Stage 6: Keyboard Layout Correction
        if self.config["keyboard_correction"]:
            query, keyboard_fixes = self._fix_keyboard_layout(query)
            corrections_made.extend(keyboard_fixes)
        
        # Stage 7: Spelling/Typo Correction
        if self.config["typo_correction"]:
            query, typo_fixes = self._correct_typos(query)
            corrections_made.extend(typo_fixes)
        
        if self.config["spellcheck"] and self._spell:
            query, spell_fixes = self._spellcheck(query)
            corrections_made.extend(spell_fixes)
        
        # Stage 8: Entity Preservation (identify before vocabulary mapping)
        if self.config["entity_preservation"]:
            preserved_words = self._identify_entities(query)
            entities_preserved.extend(preserved_words)
        
        # Stage 9: Domain Vocabulary Mapping
        if self.config["vocabulary_mapping"]:
            query, vocab_mappings = self._apply_vocabulary(query)
            corrections_made.extend(vocab_mappings)
        
        # Stage 10: Lemmatization
        if self.config["lemmatization"]:
            query, lemma_changes = self._lemmatize(query, entities_preserved)
            corrections_made.extend(lemma_changes)
        
        # Final cleanup
        query = query.strip()
        query = re.sub(r'\s+', ' ', query)
        
        # Generate deterministic cache key
        cache_key = self._generate_cache_key(query)
        
        was_modified = (
            query.lower().strip() != original.lower().strip() or
            len(corrections_made) > 0 or
            len(expansions_applied) > 0
        )
        
        logger.debug(
            "query_normalized original=%r normalized=%r corrections=%s",
            original, query, corrections_made
        )
        
        return NormalizationResult(
            original_query=original,
            normalized_query=query,
            cache_key=cache_key,
            corrections_made=corrections_made,
            expansions_applied=expansions_applied,
            was_modified=was_modified,
            entities_preserved=entities_preserved,
        )
    
    def _clean_text(self, query: str) -> str:
        """Remove HTML, emojis, control characters."""
        # Remove HTML tags
        query = re.sub(r'<[^>]+>', '', query)
        # Remove control characters (except newlines, tabs)
        query = re.sub(r'[\x00-\x08\x0b-\x0c\x0e-\x1f\x7f]', '', query)
        # Remove emoji patterns (simplified)
        emoji_pattern = re.compile(
            "["
            "\U0001F600-\U0001F64F"  # emoticons
            "\U0001F300-\U0001F5FF"  # symbols & pictographs
            "\U0001F680-\U0001F6FF"  # transport & map symbols
            "\U0001F1E0-\U0001F1FF"  # flags
            "]+", 
            flags=re.UNICODE
        )
        query = emoji_pattern.sub('', query)
        return query
    
    def _normalize_unicode(self, query: str) -> str:
        """Unicode normalization (NFKD) and accent removal."""
        # Normalize to NFKD form
        query = unicodedata.normalize('NFKD', query)
        # Remove combining characters (accents)
        query = ''.join(c for c in query if not unicodedata.combining(c))
        return query
    
    def _handle_punctuation(self, query: str) -> tuple[str, str]:
        """Remove or standardize punctuation."""
        # Keep essential punctuation for now (can be configured)
        # Remove leading/trailing punctuation
        query = query.strip('.,!?;:')
        # Remove special characters but keep alphanumerics and spaces
        removed = re.sub(r'[^\w\s]', ' ', query)
        return removed, ""

    def _dp_split_word(self, token: str) -> list[str]:
        """
        Segment a conjoined/compound word into valid constituent words using Dynamic Programming.
        Finds the segmentation that maximizes unigram log-probabilities.
        Examples:
        - "howareyou" -> ["how", "are", "you"]
        - "leavesavailable" -> ["leaves", "available"]
        - "whatisleavepolicy" -> ["what", "is", "leave", "policy"]
        """
        clean_w = token.lower().strip()
        n = len(clean_w)
        if n < 4 or not clean_w.isalpha():
            return [token]

        # Recognized compound single words that must NEVER be split
        do_not_split = {
            "handbook", "provident", "insurance", "harassment", "misconduct",
            "disciplinary", "attendance", "performance", "compensation",
            "bereavement", "maternity", "paternity", "parental", "entitlement",
            "termination", "resignation", "gratuity", "guidelines", "reimbursement",
            "allowance", "probation", "appraisal"
        }
        if clean_w in do_not_split or clean_w in PRESERVED_ENTITIES:
            return [token]

        spell = self._spell
        total_words = (spell.word_frequency.total_words or 1_000_000) if spell else 1_000_000

        def word_log_prob(w: str) -> float:
            if w in self._domain_keywords or w in self._common_query_words:
                return -2.0
            if spell and w in spell:
                freq = spell.word_frequency[w]
                if freq > 0:
                    return math.log(freq / total_words)
            if w in self._known_words:
                return -4.0
            if len(w) == 1:
                return -3.0 if w in ("a", "i") else -18.0
            return -20.0

        def is_valid_word(w: str) -> bool:
            if w in self._known_words or w in self._domain_keywords or w in self._common_query_words:
                return True
            if spell and w in spell:
                return True
            if w in ("a", "i"):
                return True
            return False

        # DP state: best[i] = (max_log_prob, word, prev_index)
        best = [(0.0, "", 0)] + [(-float("inf"), "", 0)] * n
        max_word_len = min(n, 25)

        for i in range(1, n + 1):
            for j in range(max(0, i - max_word_len), i):
                sub = clean_w[j:i]
                if is_valid_word(sub):
                    score = best[j][0] + word_log_prob(sub)
                    if score > best[i][0]:
                        best[i] = (score, sub, j)

        if best[n][0] == -float("inf") or not best[n][1]:
            return [token]

        segments = []
        curr = n
        while curr > 0:
            _, word, prev = best[curr]
            if not word:
                return [token]
            segments.append(word)
            curr = prev

        segments.reverse()

        if len(segments) <= 1:
            return [token]

        # Prevent splitting into single letters
        if any(len(s) == 1 and s not in ("a", "i") for s in segments):
            return [token]

        # Prevent splitting into non-English or invalid two-letter fragments (e.g. "le", "de", "ed")
        valid_two_letter_words = {
            "to", "in", "on", "at", "by", "is", "it", "as", "or", "an",
            "if", "do", "go", "my", "no", "so", "up", "we", "he", "me", "us", "am"
        }
        if any(len(s) == 2 and s not in valid_two_letter_words for s in segments):
            return [token]

        # If the whole token is already a very common English word, don't over-split
        if spell and clean_w in spell and spell.word_frequency[clean_w] > 5000:
            single_prob = math.log(spell.word_frequency[clean_w] / total_words)
            if single_prob > best[n][0] - 2.0:
                return [token]

        return segments

    def _fix_word_boundaries(self, query: str) -> tuple[str, list[str]]:
        """
        Fix word boundary issues such as camelCase, alphanumeric glue, and joined words.
        Uses Dynamic Programming to segment multi-word conjoined tokens.
        Examples:
        - "leavesavailable" -> "leaves available"
        - "howareyou" -> "how are you"
        - "leavepolicy" -> "leave policy"
        - "leavePolicy" -> "leave Policy"
        - "leave2026" -> "leave 2026"
        """
        fixes = []

        # 1. Split CamelCase (e.g. leavePolicy -> leave Policy)
        camel_split = re.sub(r'([a-z])([A-Z])', r'\1 \2', query)
        if camel_split != query:
            fixes.append(f"word_boundary: camelCase split")
            query = camel_split

        # 2. Split letter and digit boundaries (e.g. leave2026 -> leave 2026)
        digit_split = re.sub(r'([a-zA-Z])([0-9])', r'\1 \2', query)
        digit_split = re.sub(r'([0-9])([a-zA-Z])', r'\1 \2', digit_split)
        if digit_split != query:
            fixes.append(f"word_boundary: alphanumeric split")
            query = digit_split

        # 3. Dynamic Programming word segmentation for conjoined words
        words = query.split()
        corrected_words = []

        for word in words:
            clean_w = word.lower().strip()
            if len(clean_w) < 4 or not clean_w.isalpha():
                corrected_words.append(word)
                continue

            segments = self._dp_split_word(clean_w)
            if len(segments) > 1:
                joined_segments = " ".join(segments)
                fixes.append(f"word_boundary: {word} -> {joined_segments}")
                corrected_words.append(joined_segments)
            else:
                corrected_words.append(word)

        return ' '.join(corrected_words), fixes
    
    def _fix_keyboard_layout(self, query: str) -> tuple[str, list[str]]:
        """Fix common QWERTY keyboard layout mistakes."""
        fixes = []
        words = query.split()
        corrected_words = []
        
        for word in words:
            if word in QWERTY_MISTAKES:
                corrected = QWERTY_MISTAKES[word]
                fixes.append(f"keyboard: {word} -> {corrected}")
                corrected_words.append(corrected)
            else:
                corrected_words.append(word)
        
        return ' '.join(corrected_words), fixes
    
    def _correct_typos(self, query: str) -> tuple[str, list[str]]:
        """Correct common typos via dictionary."""
        corrections = []
        words = query.split()
        corrected_words = []
        
        for word in words:
            # Check if word is a known typo
            if word in TYPO_CORRECTIONS:
                corrected = TYPO_CORRECTIONS[word]
                if corrected != word:
                    corrections.append(f"typo: {word} -> {corrected}")
                corrected_words.append(corrected)
            else:
                corrected_words.append(word)
        
        return ' '.join(corrected_words), corrections
    
    @staticmethod
    def _levenshtein_distance(s1: str, s2: str) -> int:
        """Compute Levenshtein edit distance between two strings."""
        if s1 == s2:
            return 0
        if len(s1) < len(s2):
            return QueryNormalizer._levenshtein_distance(s2, s1)
        if len(s2) == 0:
            return len(s1)
        previous_row = list(range(len(s2) + 1))
        for i, c1 in enumerate(s1):
            current_row = [i + 1]
            for j, c2 in enumerate(s2):
                insertions = previous_row[j + 1] + 1
                deletions = current_row[j] + 1
                substitutions = previous_row[j] + (c1 != c2)
                current_row.append(min(insertions, deletions, substitutions))
            previous_row = current_row
        return previous_row[-1]

    def _find_closest_domain_term(self, word: str, max_distance: int = 2) -> Optional[str]:
        """Find the closest domain term within max edit distance for unseen/new words."""
        clean_word = re.sub(r'[^a-z0-9]', '', word.lower())
        if len(clean_word) < 4:
            return None
        threshold = 1 if len(clean_word) <= 4 else max_distance
        best_term = None
        best_dist = threshold + 1
        
        for term in getattr(self, "_domain_keywords", set()):
            if abs(len(term) - len(clean_word)) > threshold:
                continue
            dist = self._levenshtein_distance(clean_word, term)
            if dist <= threshold and dist < best_dist:
                best_dist = dist
                best_term = term
        return best_term

    def _spellcheck(self, query: str) -> tuple[str, list[str]]:
        """Use dynamic domain fuzzy matching and pyspellchecker for unknown words."""
        fixes = []
        words = query.split()
        corrected_words = []
        
        for word in words:
            # Check words already handled by custom corrections
            if word in TYPO_CORRECTIONS or word in QWERTY_MISTAKES:
                corrected_words.append(word)
                continue
            
            # If word is already a valid known English word or domain word, keep it as is
            clean_w = re.sub(r'[^a-z0-9]', '', word.lower())
            if (self._spell and clean_w in self._spell) or clean_w in self._domain_keywords:
                corrected_words.append(word)
                continue
            
            # Word is misspelled/unknown! Check if close to a domain term via Levenshtein edit distance
            closest_domain = self._find_closest_domain_term(word)
            if closest_domain and closest_domain != clean_w:
                fixes.append(f"domain_fuzzy: {word} -> {closest_domain}")
                corrected_words.append(closest_domain)
                continue
            
            # Check if word can be corrected via SpellChecker for general vocabulary
            if self._spell:
                correction = self._spell.correction(word)
                if correction and correction != word and len(correction) > 2:
                    fixes.append(f"spell: {word} -> {correction}")
                    corrected_words.append(correction)
                else:
                    corrected_words.append(word)
            else:
                corrected_words.append(word)
        
        return ' '.join(corrected_words), fixes
    
    def _identify_entities(self, query: str) -> list[str]:
        """Identify entities that should be preserved."""
        words = query.lower().split()
        preserved = []
        
        for word in words:
            if word in PRESERVED_ENTITIES:
                preserved.append(word)
        
        return preserved
    
    def _apply_vocabulary(self, query: str) -> tuple[str, list[str]]:
        """Apply domain vocabulary mapping."""
        mappings = []
        
        # Sort by length descending to match longer phrases first
        for pattern, canonical in self._sorted_vocab:
            # Use word boundary matching
            if re.search(r'\b' + re.escape(pattern) + r'\b', query):
                # Only replace if not already the canonical form
                if pattern.lower() != canonical.lower():
                    query = re.sub(
                        r'\b' + re.escape(pattern) + r'\b',
                        canonical,
                        query,
                        flags=re.IGNORECASE
                    )
                    mappings.append(f"vocab: {pattern} -> {canonical}")
        
        return query, mappings
    
    def _lemmatize(self, query: str, preserved_entities: list[str]) -> tuple[str, list[str]]:
        """Reduce words to their base form using NLTK."""
        if not LEMMATIZER_AVAILABLE or not _lemmatizer:
            return query, []
        
        changes = []
        words = query.split()
        lemmatized_words = []
        
        for word in words:
            # Skip if it's a preserved entity
            if word.lower() in preserved_entities:
                lemmatized_words.append(word)
                continue
            
            # Skip very short words
            if len(word) <= 2:
                lemmatized_words.append(word)
                continue
            
            # Get POS tag (verb by default for -ing forms)
            try:
                # Simple lemmatization - try noun first, then verb
                lemma_noun = _lemmatizer.lemmatize(word, wordnet.NOUN)
                lemma_verb = _lemmatizer.lemmatize(word, wordnet.VERB)
                
                # Use the shorter result (usually more base)
                if len(lemma_verb) < len(word):
                    lemma = lemma_verb
                else:
                    lemma = lemma_noun
                
                if lemma != word:
                    changes.append(f"lemma: {word} -> {lemma}")
                    lemmatized_words.append(lemma)
                else:
                    lemmatized_words.append(word)
            except Exception:
                lemmatized_words.append(word)
        
        return ' '.join(lemmatized_words), changes
    
    def _generate_cache_key(self, normalized_query: str) -> str:
        """
        Generate a deterministic cache key from normalized query.
        
        Uses simple hashing for cache key generation with question prefix canonicalization.
        """
        if not normalized_query:
            return "empty_query"
        
        # Simple hash - just use the normalized query lowercased
        key = normalized_query.lower().strip()
        # Canonicalize leading question prefixes for policy/informational questions
        key = re.sub(r'^(?:what|how)\s+is\s+(?:the\s+)?', 'what_is_the_', key)
        key = re.sub(r'^(?:what|how)\s+are\s+(?:the\s+)?', 'what_are_the_', key)
        key = re.sub(r'^(?:tell\s+me\s+about\s+(?:the\s+)?|explain\s+(?:the\s+)?)', 'what_is_the_', key)
        key = re.sub(r'[^a-z0-9\s_]', '', key)  # Remove special chars
        key = re.sub(r'\s+', '_', key)  # Replace spaces with underscores
        key = re.sub(r'_+', '_', key).strip('_')
        
        return key[:200]  # Limit key length
    
    def is_semantically_equivalent(self, query1: str, query2: str) -> bool:
        """
        Check if two queries are semantically equivalent after normalization.
        
        Args:
            query1: First query
            query2: Second query
            
        Returns:
            True if queries are semantically equivalent
        """
        result1 = self.normalize(query1)
        result2 = self.normalize(query2)
        
        # Check if cache keys match
        if result1.cache_key == result2.cache_key:
            return True
        
        # Check if normalized queries are identical
        if result1.normalized_query == result2.normalized_query:
            return True
        
        # Check if they share significant vocabulary
        terms1 = set(result1.normalized_query.lower().split())
        terms2 = set(result2.normalized_query.lower().split())
        
        if terms1 and terms2:
            overlap = len(terms1 & terms2) / min(len(terms1), len(terms2))
            return overlap >= 0.7  # 70% overlap considered equivalent
        
        return False


# Global singleton instance
_query_normalizer: Optional[QueryNormalizer] = None


def get_query_normalizer() -> QueryNormalizer:
    """Get the global query normalizer instance."""
    global _query_normalizer
    if _query_normalizer is None:
        _query_normalizer = QueryNormalizer()
    return _query_normalizer