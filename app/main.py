from contextlib import asynccontextmanager
import logging
from fastapi import FastAPI

from app.api.routes.chat import router as chat_router
from app.infrastructure.logging.conversation_log_cleanup import ConversationLogCleanup

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: execute conversation log retention cleanup
    try:
        cleanup_service = ConversationLogCleanup()
        result = cleanup_service.cleanup_expired_logs()
        logger.info(
            "Startup conversation log cleanup completed: %d deleted, %d preserved, %d failed",
            result.deleted,
            result.preserved,
            result.failed,
        )
    except Exception as exc:
        logger.error("Startup conversation log cleanup failed: %s", exc)

    yield


app = FastAPI(title="KnowLayer API", lifespan=lifespan)
app.include_router(chat_router)


@app.get("/health")
async def health():
    return {"status": "ok"}

