from fastapi import FastAPI
from app.api.routes.chat import router as chat_router
from app.api.routes.documents import router as documents_router

app = FastAPI(title="KnowLayer API")
app.include_router(chat_router)
app.include_router(documents_router)


@app.get("/health")
async def health():
    return {"status": "ok"}
