from contextlib import asynccontextmanager

from fastapi import FastAPI
from app.api.routes.chat import router as chat_router
from app.infrastructure.channels.teams.app import initialize_teams


@asynccontextmanager
async def lifespan(application: FastAPI):
    await initialize_teams(application)
    yield

app = FastAPI(title="KnowLayer API", lifespan=lifespan)
app.include_router(chat_router)


@app.get("/health")
async def health():
    return {"status": "ok"}
