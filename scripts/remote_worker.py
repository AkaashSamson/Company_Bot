# scripts/remote_worker.py
import re
import subprocess
import threading
import uvicorn
from fastapi import FastAPI, UploadFile, File, HTTPException
import torch

# IMPORT DIRECTLY FROM YOUR LOCAL REPO!
from app.infrastructure.document.docling_processor import DoclingDocumentProcessor

app = FastAPI(title="KnowLayer Native GPU Worker")

# Uses the exact same local converter, tokenizer, and HybridChunker!
processor = DoclingDocumentProcessor()

@app.get("/health")
def health():
    return {
        "status": "ready",
        "cuda": torch.cuda.is_available(),
        "device": torch.cuda.get_device_name(0) if torch.cuda.is_available() else "cpu"
    }

@app.post("/process-document")
async def process_document(file: UploadFile = File(...)):
    try:
        content = await file.read()
        # Executes the repo's native processing logic on Kaggle's GPU
        processed = processor.process(content, file.filename)
        return {
            "chunks": [
                {
                    "text": c.text,
                    "index": c.index,
                    "page_number": c.page_number,
                    "section_path": [{"level": h.level, "title": h.title} for h in c.section_path],
                    "content_type": c.content_type,
                    "metadata": dict(c.metadata),
                }
                for c in processed.chunks
            ],
            "outline": [{"level": h.level, "title": h.title} for h in processed.outline],
            "page_count": processed.page_count,
            "file_type": processed.file_type,
            "metadata": dict(processed.metadata),
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

if __name__ == "__main__":
    # Start Cloudflare Tunnel
    tunnel = subprocess.Popen(
        ["cloudflared", "tunnel", "--url", "http://localhost:8000"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )

    def print_tunnel_url():
        for line in tunnel.stderr:
            match = re.search(r"https://[a-zA-Z0-9-]+\.trycloudflare\.com", line)
            if match:
                url = match.group(0)
                print("\n" + "=" * 65, flush=True)
                print(f"  YOUR KAGGLE INGESTION URL:\n  {url}", flush=True)
                print("=" * 65 + "\n", flush=True)
                break

    threading.Thread(target=print_tunnel_url, daemon=True).start()
    uvicorn.run(app, host="0.0.0.0", port=8000)
