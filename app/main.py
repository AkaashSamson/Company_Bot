import logging

from fastapi import FastAPI
from app.api.routes.chat import router as chat_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)

app = FastAPI(title="KnowLayer API")
app.include_router(chat_router)


@app.get("/health")
async def health():
    return {"status": "ok"}
