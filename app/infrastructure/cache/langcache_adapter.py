"""
LangCache Infrastructure Adapter

Implements SemanticCachePort for Redis LangCache Cloud / Enterprise.
Encapsulates all LangCache SDK communication, providing:
- Distributed semantic caching with configurable similarity threshold
- Resilient error handling and network timeout protection
- Negative response filtering to prevent caching unhelpful answers
- Metadata and RBAC attribute serialization
- Vendor-neutral integration adhering to Hexagonal Architecture
"""

import logging
import time
from typing import Any, Dict, List, Mapping, Optional, Sequence

from app.core.cache_quality import is_negative_response
from app.core.settings import (
    LANGCACHE_API_KEY,
    LANGCACHE_CACHE_ID,
    LANGCACHE_SERVER_URL,
    LANGCACHE_SIMILARITY_THRESHOLD,
    LANGCACHE_TIMEOUT_SECONDS,
)
from app.domain.ports.cache import CacheEntryProtocol, SemanticCachePort

logger = logging.getLogger(__name__)

# Try to import official LangCache SDK
try:
    from langcache import LangCache
    LANGCACHE_SDK_AVAILABLE = True
except ImportError:
    LangCache = None  # type: ignore
    LANGCACHE_SDK_AVAILABLE = False
    logger.warning("langcache SDK not installed. LangCacheAdapter will operate in fallback/offline mode.")


class LangCacheAdapter:
    """
    Adapter implementing SemanticCachePort using Redis LangCache.
    """

    def __init__(
        self,
        server_url: Optional[str] = None,
        cache_id: Optional[str] = None,
        api_key: Optional[str] = None,
        similarity_threshold: Optional[float] = None,
        timeout_seconds: Optional[float] = None,
        client: Optional[Any] = None,
    ):
        """
        Initialize LangCache adapter.
        
        Args:
            server_url: Redis LangCache server endpoint URL
            cache_id: Unique cache identifier
            api_key: Authentication API key
            similarity_threshold: Minimum cosine similarity for semantic cache hits (0.0 - 1.0)
            timeout_seconds: Request timeout in seconds
            client: Optional pre-configured LangCache client (useful for testing and dependency injection)
        """
        self.server_url = server_url if server_url is not None else LANGCACHE_SERVER_URL
        self.cache_id = cache_id if cache_id is not None else LANGCACHE_CACHE_ID
        self.api_key = api_key if api_key is not None else LANGCACHE_API_KEY
        self.similarity_threshold = (
            similarity_threshold
            if similarity_threshold is not None
            else LANGCACHE_SIMILARITY_THRESHOLD
        )
        self.timeout_seconds = (
            timeout_seconds
            if timeout_seconds is not None
            else LANGCACHE_TIMEOUT_SECONDS
        )

        self._client = client
        self._is_available = False
        self._supports_attributes = True
        self._stats = {
            "hits": 0,
            "misses": 0,
            "writes": 0,
            "write_failures": 0,
            "errors": 0,
            "negative_responses_skipped": 0,
        }

        # Initialize client if not provided
        if self._client is not None:
            self._is_available = True
            logger.info("langcache_adapter initialized with custom client")
        elif LANGCACHE_SDK_AVAILABLE and self.server_url and self.cache_id and self.api_key:
            try:
                timeout_ms = int(self.timeout_seconds * 1000) if self.timeout_seconds else None
                self._client = LangCache(
                    server_url=self.server_url,
                    cache_id=self.cache_id,
                    api_key=self.api_key,
                    timeout_ms=timeout_ms,
                )
                self._is_available = True
                logger.info(
                    "langcache_adapter connected server=%s cache_id=%s threshold=%.2f",
                    self.server_url, self.cache_id, self.similarity_threshold
                )
            except Exception as e:
                self._is_available = False
                logger.warning("langcache_adapter initialization failed: %s", e)
        else:
            logger.info(
                "langcache_adapter unavailable: sdk_installed=%s server_set=%s cache_id_set=%s api_key_set=%s",
                LANGCACHE_SDK_AVAILABLE, bool(self.server_url), bool(self.cache_id), bool(self.api_key)
            )

    @property
    def is_available(self) -> bool:
        """Return True if LangCache is configured and client initialized."""
        return self._is_available and self._client is not None

    def is_healthy(self) -> bool:
        """Check if LangCache client is initialized and operational."""
        return self.is_available

    def get(
        self,
        cache_key: str,
        original_query: str = "",
        role: Optional[str] = None,
        roles: Optional[Sequence[str]] = None,
        project_ids: Optional[Sequence[str]] = None,
        document_ids: Optional[Sequence[str]] = None,
        is_admin: bool = False,
        **kwargs: Any,
    ) -> Optional[CacheEntryProtocol]:
        """
        Search LangCache for semantically similar prompt.
        """
        if not self.is_available:
            self._stats["misses"] += 1
            return None

        prompt_to_search = (original_query or cache_key or "").strip()
        if not prompt_to_search:
            self._stats["misses"] += 1
            return None

        try:
            # LangCache SDK search call
            search_kwargs: Dict[str, Any] = {
                "prompt": prompt_to_search,
            }
            if self.similarity_threshold is not None:
                search_kwargs["similarity_threshold"] = self.similarity_threshold

            result = self._client.search(**search_kwargs)
            entries = self._extract_search_entries(result)

            if not entries:
                self._stats["misses"] += 1
                logger.debug("langcache_adapter miss prompt='%s'", prompt_to_search[:50])
                return None

            # Get top entry
            top_entry = entries[0]
            top_response = top_entry.get("response", "")
            top_similarity = top_entry.get("similarity", 1.0)
            top_attributes = top_entry.get("attributes", {})
            entry_id = top_entry.get("id", "")

            # RBAC verification against stored attributes
            if not self._check_rbac_attributes(
                top_attributes,
                role=role,
                roles=roles,
                project_ids=project_ids,
                document_ids=document_ids,
                is_admin=is_admin,
            ):
                self._stats["misses"] += 1
                logger.debug("langcache_adapter rbac_denied entry_id=%s", entry_id)
                return None

            # Check if cached response is negative/unhelpful
            if is_negative_response(top_response):
                self._stats["misses"] += 1
                return None

            self._stats["hits"] += 1
            logger.info(
                "langcache_adapter hit sim=%.3f entry_id=%s prompt='%s'",
                top_similarity, entry_id, prompt_to_search[:50]
            )

            # Reconstruct CacheEntryProtocol
            citations = top_attributes.get("citations", [])
            if isinstance(citations, str):
                import json
                try:
                    citations = json.loads(citations)
                except Exception:
                    citations = []

            return CacheEntryProtocol(
                cache_key=cache_key or prompt_to_search,
                original_query=prompt_to_search,
                response=top_response,
                confidence=float(top_similarity),
                source="langcache",
                cache_id=top_attributes.get("cache_id", entry_id),
                assigned_role=top_attributes.get("assigned_role"),
                document_ids=top_attributes.get("document_ids", "").split(",") if top_attributes.get("document_ids") else [],
                project_ids=top_attributes.get("project_ids", "").split(",") if top_attributes.get("project_ids") else [],
                model=top_attributes.get("model", ""),
                citations=citations if isinstance(citations, list) else [],
                metadata=top_attributes,
            )

        except Exception as e:
            self._stats["errors"] += 1
            logger.warning("langcache_adapter search error: %s", e)
            return None

    def put(
        self,
        cache_key: str,
        original_query: str,
        response: str,
        confidence: float = 0.0,
        source: str = "semantic_cache",
        evidence_count: int = 0,
        model: str = "",
        citations: Optional[List[Dict[str, Any]]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        cache_id: str = "",
        assigned_role: Optional[str] = None,
        document_ids: Optional[Sequence[str]] = None,
        project_ids: Optional[Sequence[str]] = None,
        ttl_seconds: Optional[float] = None,
        **kwargs: Any,
    ) -> bool:

    
        """
        Store a prompt-response entry into LangCache with attributes.
        """
        if not self.is_available:
            return False

        prompt_to_store = (original_query or cache_key or "").strip()
        if not prompt_to_store or not response:
            return False

        # Filter out negative responses
        if is_negative_response(response):
            self._stats["negative_responses_skipped"] += 1
            logger.info("langcache_adapter skip negative_response prompt='%s'", prompt_to_store[:50])
            return False

        try:
            # LangCache attributes must be Mapping[str, str]
            attrs: Dict[str, str] = {
                "cache_key": str(cache_key),
                "source": str(source),
            }
            if cache_id:
                attrs["cache_id"] = str(cache_id)
            if assigned_role:
                attrs["assigned_role"] = str(assigned_role)
            if model:
                attrs["model"] = str(model)
            if confidence > 0:
                attrs["confidence"] = str(confidence)
            if document_ids:
                attrs["document_ids"] = ",".join(str(d) for d in document_ids if d)
            if project_ids:
                attrs["project_ids"] = ",".join(str(p) for p in project_ids if p)
            if citations:
                import json
                try:
                    attrs["citations"] = json.dumps(citations[:5])  # Cap stored citations
                except Exception:
                    pass

            ttl_millis = int(ttl_seconds * 1000) if ttl_seconds and ttl_seconds > 0 else None

            set_kwargs: Dict[str, Any] = {
                "prompt": prompt_to_store,
                "response": response,
            }
            if self._supports_attributes and attrs:
                set_kwargs["attributes"] = attrs
            if ttl_millis:
                set_kwargs["ttl_millis"] = ttl_millis

            try:
                res = self._client.set(**set_kwargs)
            except Exception as set_err:
                err_msg = str(set_err)
                if "no attributes are configured" in err_msg or "attributes:" in err_msg:
                    self._supports_attributes = False
                    logger.info("langcache_adapter attributes not configured on cache instance, retrying without attributes")
                    set_kwargs.pop("attributes", None)
                    res = self._client.set(**set_kwargs)
                else:
                    raise set_err

            success = self._verify_set_response(res)

            if success:
                self._stats["writes"] += 1
                logger.debug("langcache_adapter write success prompt='%s'", prompt_to_store[:50])
                return True
            else:
                self._stats["write_failures"] += 1
                logger.warning("langcache_adapter write returned unsuccessful")
                return False

        except Exception as e:
            self._stats["errors"] += 1
            self._stats["write_failures"] += 1
            logger.warning("langcache_adapter set error: %s", e)
            return False

    def delete(self, cache_key: str) -> bool:
        """
        Delete entries associated with cache_key.
        """
        if not self.is_available:
            return False

        try:
            # Attempt deletion by attribute query
            if hasattr(self._client, "delete_query"):
                self._client.delete_query(attributes={"cache_key": str(cache_key)})
                return True
            return False
        except Exception as e:
            logger.debug("langcache_adapter delete error: %s", e)
            return False

    def clear(self) -> None:
        """Flush all cache entries in LangCache."""
        if not self.is_available:
            return

        try:
            if hasattr(self._client, "flush"):
                self._client.flush()
                logger.info("langcache_adapter flushed")
        except Exception as e:
            logger.warning("langcache_adapter clear failed: %s", e)

    def get_stats(self) -> Dict[str, Any]:
        """Return operational statistics."""
        return {
            "is_available": self.is_available,
            "server_url": self.server_url,
            "cache_id": self.cache_id,
            "similarity_threshold": self.similarity_threshold,
            **self._stats,
        }

    @staticmethod
    def _extract_search_entries(result: Any) -> List[Dict[str, Any]]:
        """Normalize search result across various SDK/dict return types."""
        if result is None:
            return []

        entries = []
        data = getattr(result, "data", None)
        if data is None and isinstance(result, dict):
            data = result.get("data", [])

        if isinstance(data, list):
            for item in data:
                if hasattr(item, "response"):
                    entries.append({
                        "id": getattr(item, "id", ""),
                        "response": getattr(item, "response", ""),
                        "similarity": getattr(item, "similarity", 1.0),
                        "attributes": getattr(item, "attributes", {}) or {},
                        "prompt": getattr(item, "prompt", ""),
                    })
                elif isinstance(item, dict):
                    entries.append(item)
        elif hasattr(result, "response"):
            entries.append({
                "id": getattr(result, "id", ""),
                "response": getattr(result, "response", ""),
                "similarity": getattr(result, "similarity", 1.0),
                "attributes": getattr(result, "attributes", {}) or {},
                "prompt": getattr(result, "prompt", ""),
            })

        return entries

    @staticmethod
    def _verify_set_response(res: Any) -> bool:
        """Verify whether set() call was acknowledged."""
        if res is None:
            return False
        if hasattr(res, "entry_id") and res.entry_id:
            return True
        if isinstance(res, dict):
            return bool(res.get("entry_id") or res.get("status") == "success")
        if isinstance(res, bool):
            return res
        return True

    @staticmethod
    def _check_rbac_attributes(
        attributes: Mapping[str, Any],
        role: Optional[str] = None,
        roles: Optional[Sequence[str]] = None,
        project_ids: Optional[Sequence[str]] = None,
        document_ids: Optional[Sequence[str]] = None,
        is_admin: bool = False,
    ) -> bool:
        """Check if cached entry's attributes permit access to the caller."""
        if is_admin:
            return True

        caller_roles = set()
        if role:
            caller_roles.add(str(role).strip().lower())
        if roles:
            for r in roles:
                if r:
                    caller_roles.add(str(r).strip().lower())

        if "admin" in caller_roles:
            return True

        entry_role = attributes.get("assigned_role")
        if entry_role:
            if not caller_roles or entry_role.strip().lower() not in caller_roles:
                return False

        entry_projects_raw = attributes.get("project_ids")
        if entry_projects_raw and project_ids is not None:
            entry_projs = {p.strip().lower() for p in entry_projects_raw.split(",") if p.strip()}
            caller_projs = {p.strip().lower() for p in project_ids if p}
            if not (entry_projs & caller_projs):
                return False

        entry_docs_raw = attributes.get("document_ids")
        if entry_docs_raw and document_ids is not None:
            entry_docs = {d.strip().lower() for d in entry_docs_raw.split(",") if d.strip()}
            caller_docs = {d.strip().lower() for d in document_ids if d}
            for edoc in entry_docs:
                if edoc not in caller_docs:
                    return False

        return True
