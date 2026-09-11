import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.routes.chat import router as chat_router, init_orchestrator
from app.api.routes.tokens import router as tokens_router

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Warm up all heavy components before the server starts accepting requests."""
    logger.info("Lifespan: warming up orchestrator…")
    init_orchestrator()
    logger.info("Lifespan: warm-up complete.")
    yield
    logger.info("Lifespan: shutdown.")


app = FastAPI(title="KnowLayer API", lifespan=lifespan)
app.include_router(chat_router)
app.include_router(tokens_router)


@app.get("/health")
async def health():
    return {"status": "ok"}
