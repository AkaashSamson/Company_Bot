from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.routes.auth_routes import router as auth_router
from app.api.routes.chat import router as chat_router
from app.api.routes.documents import router as documents_router


def _seed_default_roles() -> None:
    from app.db.roles_repository import seed_default_roles

    try:
        seed_default_roles()
    except Exception:
        # Startup should not fail if MongoDB is temporarily unreachable;
        # roles are re-seeded on the first authenticated request.
        pass


@asynccontextmanager
async def lifespan(app: FastAPI):
    _seed_default_roles()
    yield


app = FastAPI(title="KnowLayer API", lifespan=lifespan)
app.include_router(chat_router)
app.include_router(documents_router)
app.include_router(auth_router)


@app.get("/health")
async def health():
    from app.db.mongodb import MongoDBClient

    return {
        "status": "ok",
        "mongodb": MongoDBClient.ping(),
    }