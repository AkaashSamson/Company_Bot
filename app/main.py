import logging
import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.routes.chat import router as chat_router, init_orchestrator
from app.api.routes.tokens import router as tokens_router
from app.api.routes.documents import router as documents_router
from app.api.routes.explorer import router as explorer_router
from app.api.routes.organization import router as organization_router
from app.api.routes.authentication import router as authentication_router
from app.api.routes.roles import router as roles_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("knowlayer")


from app.core.settings import LOG_CLEANUP_INTERVAL_SECONDS

async def periodic_log_cleanup_task(interval_seconds: int = LOG_CLEANUP_INTERVAL_SECONDS):
    from app.infrastructure.logging.conversation_log_cleanup import ConversationLogCleanup
    cleanup_service = ConversationLogCleanup()
    while True:
        try:
            await asyncio.sleep(interval_seconds)
            result = await asyncio.to_thread(cleanup_service.cleanup_expired_logs)
            logger.info(
                "Periodic conversation log cleanup completed: %d deleted, %d preserved, %d failed",
                result.deleted,
                result.preserved,
                result.failed,
            )
        except asyncio.CancelledError:
            logger.info("Periodic conversation log cleanup task cancelled.")
            break
        except Exception as exc:
            logger.error("Periodic conversation log cleanup failed: %s", exc)


@asynccontextmanager
async def lifespan(app: FastAPI):
    from app.infrastructure.persistence.factory import get_session_factory, initialize_persistence
    from app.infrastructure.logging.conversation_log_cleanup import ConversationLogCleanup

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

    initialize_persistence(get_session_factory)
    logger.info("Lifespan: warming up orchestrator…")
    init_orchestrator()
    logger.info("Lifespan: startup complete.")
    
    cleanup_task = asyncio.create_task(periodic_log_cleanup_task())
    
    yield
    logger.info("Lifespan: shutdown.")
    cleanup_task.cancel()
    try:
        await cleanup_task
    except asyncio.CancelledError:
        pass


app = FastAPI(title="KnowLayer API", lifespan=lifespan)
app.include_router(chat_router)
app.include_router(tokens_router)
app.include_router(organization_router)
app.include_router(explorer_router)
app.include_router(documents_router)
app.include_router(authentication_router)
app.include_router(roles_router)


@app.get("/health")
async def health():
    return {"status": "ok"}