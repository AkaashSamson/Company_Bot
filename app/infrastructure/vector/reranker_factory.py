import logging
from app.core import settings
from app.domain.ports.reranker import RerankerPort
from app.infrastructure.vector.bge_reranker import BgeReranker
from app.infrastructure.vector.null_reranker import NullReranker

logger = logging.getLogger(__name__)

def get_reranker() -> RerankerPort:
    """
    Factory function to dynamically instantiate the correct reranker 
    adapter based on the RERANKER_PROVIDER environment variable.
    """
    provider = getattr(settings, "RERANKER_PROVIDER", "bge").strip().lower()

    if provider == "bge":
        logger.info(f"Initializing BgeReranker with model: {settings.RAG_RERANKER_MODEL}")
        return BgeReranker(model_name=settings.RAG_RERANKER_MODEL)
    elif provider in ("none", "null", ""):
        logger.info("Initializing NullReranker (reranking disabled via config).")
        return NullReranker()
    else:
        logger.warning(f"Unknown RERANKER_PROVIDER '{provider}'. Falling back to NullReranker.")
        return NullReranker()
