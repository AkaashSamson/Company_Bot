import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.routes.chat import router as chat_router
from app.api.routes.documents import router as documents_router
from app.api.routes.organization import router as organization_router
from app.api.routes.authentication import router as authentication_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("knowlayer")


@asynccontextmanager
async def lifespan(app: FastAPI):
    from app.infrastructure.persistence.factory import get_session_factory, initialize_persistence

    initialize_persistence(get_session_factory)
    logger.info("application finished startup initialization")
    yield


app = FastAPI(title="KnowLayer API", lifespan=lifespan)
app.include_router(chat_router)
app.include_router(organization_router)
app.include_router(documents_router)
app.include_router(authentication_router)


@app.get("/health")
async def health():
    return {"status": "ok"}