from fastapi import FastAPI
from app.api.routes.chat import router as chat_router

app = FastAPI(title="KnowLayer API")
app.include_router(chat_router)


@app.get("/health")
async def health():
    return {"status": "ok"}
