import asyncio
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.routes.chat import router as chat_router, init_orchestrator
from app.api.routes.tokens import router as tokens_router
from app.api.routes.documents import router as documents_router
from app.api.routes.explorer import router as explorer_router
from app.api.routes.organization import router as organization_router
from app.api.routes.authentication import router as authentication_router
from app.api.routes.roles import router as roles_router
from app.api.routes.channels import router as channels_router

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
    from app.infrastructure.persistence.factory import get_session_factory, initialize_persistence, create_unit_of_work
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

    # Recover any zombie documents stuck in "processing" state prior to restart
    try:
        with create_unit_of_work() as uow:
            recovered_count = 0
            for doc in uow.documents.list():
                if getattr(doc, "status", None) == "processing":
                    doc.status = "failed"
                    reason = "Server restarted during ingestion"
                    doc.description = f"{doc.description} [{reason}]" if doc.description else reason
                    uow.documents.save(doc)
                    recovered_count += 1
            if recovered_count > 0:
                uow.commit()
                logger.info("Recovered %d zombie processing documents to failed state.", recovered_count)
    except Exception as exc:
        logger.warning("Zombie document recovery skipped or failed: %s", exc)

    is_testing = bool(os.getenv("PYTEST_CURRENT_TEST"))
    if not is_testing:
        logger.info("Lifespan: warming up orchestrator in background thread…")
        await asyncio.to_thread(init_orchestrator)
        try:
            from app.infrastructure.channels.registry import register_channel_adapter
            from app.infrastructure.channels.teams.adapter import TeamsChannelAdapter
            skip_auth = os.getenv("TEAMS_SKIP_AUTH", "true").lower() == "true"
            security_token = os.getenv("TEAMS_SECURITY_TOKEN")
            register_channel_adapter(TeamsChannelAdapter(security_token=security_token, skip_auth=skip_auth))
            logger.info("Lifespan: Teams channel adapter registered (skip_auth=%s).", skip_auth)
        except Exception as exc:
            logger.warning("Failed to register Teams channel adapter: %s", exc)
        logger.info("Lifespan: startup complete.")

    cleanup_task = None
    if not is_testing:
        cleanup_task = asyncio.create_task(periodic_log_cleanup_task())
    
    yield
    logger.info("Lifespan: shutdown.")
    if cleanup_task is not None:
        cleanup_task.cancel()
        try:
            await cleanup_task
        except asyncio.CancelledError:
            pass

    try:
        from app.infrastructure.observability.manager import get_observability_manager
        get_observability_manager().flush()
    except Exception as exc:
        logger.debug("Observability flush on shutdown error: %s", exc)


app = FastAPI(title="KnowLayer API", lifespan=lifespan)
app.include_router(chat_router)
app.include_router(tokens_router)
app.include_router(organization_router)
app.include_router(explorer_router)
app.include_router(documents_router)
app.include_router(authentication_router)
app.include_router(roles_router)
app.include_router(channels_router)


@app.get("/health")
async def health():
    return {"status": "ok"}
