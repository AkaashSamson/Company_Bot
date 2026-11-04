import os
import sys

# Ensure app is in python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.infrastructure.faq.mongo_faq_store import MongoFAQStore
from app.infrastructure.faq.faq_similarity_cache import FAQSimilarityCache

import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def clear_caches():
    logger.info("Clearing caches...")
    
    # 1. MongoDB FAQ Store
    try:
        faq_store = MongoFAQStore()
        count = faq_store.collection.count_documents({})
        faq_store.collection.delete_many({})
        logger.info(f"Cleared {count} documents from MongoDB FAQ Store.")
    except Exception as e:
        logger.error(f"Failed to clear MongoFAQStore: {e}")

    # 2. Redis FAQ Similarity Cache
    try:
        from app.core.settings import FAQ_SIMILARITY_CACHE_ENABLED
        if FAQ_SIMILARITY_CACHE_ENABLED:
            redis_cache = FAQSimilarityCache()
            keys = redis_cache.redis.keys(f"{redis_cache.key_prefix}*")
            if keys:
                redis_cache.redis.delete(*keys)
                logger.info(f"Cleared {len(keys)} keys from Redis FAQ Similarity Cache.")
            else:
                logger.info("Redis FAQ Similarity Cache is already empty.")
        else:
            logger.info("Redis FAQ Similarity Cache is disabled.")
    except Exception as e:
        logger.error(f"Failed to clear Redis FAQ Similarity Cache: {e}")

    # 3. SQLite Response Cache (if applicable)
    try:
        from app.infrastructure.cache.sqlite_response_cache import SQLiteResponseCache
        sqlite_cache = SQLiteResponseCache()
        sqlite_cache.clear()
        logger.info("Cleared SQLite Response Cache.")
    except ImportError:
        logger.info("SQLiteResponseCache not found, skipping.")
    except Exception as e:
        logger.error(f"Failed to clear SQLite Response Cache: {e}")

if __name__ == "__main__":
    clear_caches()
