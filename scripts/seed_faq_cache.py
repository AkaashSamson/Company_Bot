"""
FAQ Cache Seeder — Company Bot
Pre-populates response_cache.json with deterministic answers for all
standard HR FAQ questions. Run this once; the cache then serves instant
results without hitting the LLM.

Usage:
    python scripts/seed_faq_cache.py
"""
import sys
import json
import time
import math
import urllib.request
import urllib.error
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.stdout.reconfigure(encoding="utf-8")

# ── Load embedder to compute vectors (same model as the app) ────────────────
from sentence_transformers import SentenceTransformer
from app.core.settings import EMBEDDING_MODEL, RESPONSE_CACHE_FILE, LLM_CACHE_SIMILARITY_THRESHOLD

API_URL   = "http://127.0.0.1:8000/api/chat"
CACHE_PATH = Path(RESPONSE_CACHE_FILE)

STANDARD_FAQS = [
    # Leave
    "How many annual leave days do employees receive per year?",
    "What is the sick leave entitlement?",
    "Can I carry forward unused annual leave?",
    "What happens to unused casual leave at year end?",
    "Do I need manager approval before taking leave?",
    "What is the maternity leave policy?",
    "Is there paternity leave available?",
    "What is bereavement leave?",
    # Payroll
    "What are the payment policies available?",
    "When is salary paid each month?",
    "What is the difference between gross and net salary?",
    "What happens if there is an overpayment of salary?",
    "How do I report a payroll error or incorrect payment?",
    "What deductions are applied to my salary?",
    # Benefits
    "What employee benefits does the company offer?",
    "Is health insurance provided to employees?",
    "What is the provident fund contribution policy?",
    "Are there any performance bonuses?",
    "Can I get reimbursed for a professional certification?",
    # Code of Conduct
    "What is the company code of conduct?",
    "How do I report a code of conduct violation?",
    "What are the consequences of misconduct?",
    "What behaviour is expected in the workplace?",
    # Remote Work
    "What is the remote work policy?",
    "Can I work from another city or country?",
    "What expenses are reimbursed for remote workers?",
    # Performance
    "How does the performance review process work?",
    "What is a performance improvement plan (PIP)?",
    "How are performance ratings determined?",
    # Grievance / Harassment
    "How do I report workplace harassment?",
    "What is the anti-harassment policy?",
    # Employment
    "What is the notice period for resignation?",
    "What are my responsibilities during the notice period?",
]

def cosine_similarity(a, b):
    dot = sum(x * y for x, y in zip(a, b))
    na  = math.sqrt(sum(x * x for x in a))
    nb  = math.sqrt(sum(x * x for x in b))
    return dot / (na * nb) if na and nb else 0.0

def load_cache():
    if CACHE_PATH.exists():
        data = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
        return data.get("entries", []) if isinstance(data, dict) else []
    return []

def save_cache(entries):
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    CACHE_PATH.write_text(
        json.dumps({"entries": entries}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

def is_cached(question, entries, model, threshold=LLM_CACHE_SIMILARITY_THRESHOLD):
    vec = model.encode(question, convert_to_numpy=True).tolist()
    for e in entries:
        score = cosine_similarity(vec, e.get("vector", []))
        if score >= threshold:
            return True, vec
    return False, vec

def call_api(question):
    payload = json.dumps({
        "question": question,
        "session_id": "faq-seeder",
        "conversation_history": []
    }).encode("utf-8")
    req = urllib.request.Request(
        API_URL,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    resp = urllib.request.urlopen(req, timeout=60)
    return json.loads(resp.read().decode("utf-8"))

# ── Main ────────────────────────────────────────────────────────────────────
print("=" * 65)
print("  FAQ CACHE SEEDER")
print(f"  Model : {EMBEDDING_MODEL}")
print(f"  Cache : {CACHE_PATH}")
print(f"  FAQs  : {len(STANDARD_FAQS)}")
print("=" * 65)

print("\nLoading embedding model...")
model = SentenceTransformer(EMBEDDING_MODEL)

entries = load_cache()
print(f"Existing cache entries: {len(entries)}\n")

seeded = 0
skipped = 0
errors  = 0

for i, question in enumerate(STANDARD_FAQS, 1):
    already_cached, vec = is_cached(question, entries, model)
    if already_cached:
        print(f"[{i:02d}] ⏭  SKIP (cached)  {question[:70]}")
        skipped += 1
        continue

    try:
        print(f"[{i:02d}] 🔄  Seeding...    {question[:70]}")
        result = call_api(question)
        answer = result.get("answer", "")
        cit_count = len(result.get("citations", []))

        # Store in cache with the pre-computed vector
        entry = {
            "input":  question,
            "vector": vec,
            "output": json.dumps(result, sort_keys=True, ensure_ascii=False),
        }
        # Remove any existing near-duplicate entry
        entries = [e for e in entries if e.get("input") != question]
        entries.append(entry)
        save_cache(entries)

        seeded += 1
        print(f"       ✅ Stored  citations={cit_count}  answer={answer[:90]!r}")
        time.sleep(0.4)  # be polite to the API

    except urllib.error.URLError as e:
        errors += 1
        print(f"       ❌ ERROR: {e}")
    except Exception as e:
        errors += 1
        print(f"       ❌ ERROR: {e}")

print("\n" + "=" * 65)
print(f"  DONE: {seeded} seeded  |  {skipped} skipped  |  {errors} errors")
print(f"  Total cache entries: {len(entries)}")
print("=" * 65)
