"""
Quick diagnostic utility to verify local Ollama + Laya decision model connectivity.

Usage:
    python scripts/test_laya_ollama.py
"""

import sys
import time
from pathlib import Path

# Ensure project root is in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

try:
    from typesafe_sdk import Choice, Noul, Score, TypeSafeClient
    print("[OK] typesafe-sdk is installed.")
except ImportError:
    print("[ERROR] typesafe-sdk is not installed. Run: pip install typesafe-sdk")
    sys.exit(1)

from app.core.settings import TYPESAFE_BASE_URL, TYPESAFE_API_KEY, TYPESAFE_DEFAULT_MODEL
from app.infrastructure.llm.laya_client import LayaClient


def main():
    print("=" * 60)
    print("TypeSafe Laya & Ollama Connectivity Diagnostic")
    print("=" * 60)
    print(f"Base URL : {TYPESAFE_BASE_URL}")
    print(f"API Key  : {TYPESAFE_API_KEY}")
    print(f"Model    : {TYPESAFE_DEFAULT_MODEL}")
    print("-" * 60)

    # 1. Test via direct TypeSafeClient
    print("Testing 1: Direct TypeSafeClient connection to Ollama...")
    questions = {
        "department": Choice(
            instructions="Which department should handle this email?",
            criteria={
                "billing": "Invoices, payments, refunds",
                "technical": "Bugs, outages, integrations",
                "hr": "Leaves, holidays, benefits",
                "other": "Everything else",
            },
        ),
        "is_urgent": Noul(
            instructions="Is this request urgent?",
        ),
    }

    start = time.perf_counter()
    try:
        with TypeSafeClient(
            base_url=TYPESAFE_BASE_URL,
            api_key=TYPESAFE_API_KEY,
            model=TYPESAFE_DEFAULT_MODEL,
            timeout=10.0,
        ) as client:
            res = client.system_one(
                state={"body": "I was double billed for my subscription in March."},
                questions=questions,
            )
            elapsed = (time.perf_counter() - start) * 1000
            print(f"[SUCCESS] Ollama responded in {elapsed:.1f} ms!")
            print(f"  - Department : {res.choices['department'].choice} (confidence: {res.choices['department'].confidence:.2f})")
            print(f"  - Is Urgent  : {res.nouls['is_urgent'].noul:.3f}")
    except Exception as exc:
        print(f"[NOTICE] Direct TypeSafeClient connection failed: {exc}")
        print("  -> If Ollama is not yet installed or running, install it from https://ollama.com/download")
        print("  -> Then run: ollama pull laya")

    print("-" * 60)

    # 2. Test via Company Bot LayaClient Adapter
    print("Testing 2: Company Bot LayaClient adapter (with automatic fallback)...")
    adapter = LayaClient()
    res = adapter.check_input_safety("What is the leave encashment policy?")
    print(f"  - Result: is_safe={res['is_safe']}, threat={res['threat_type']}, provider={res['provider']}")
    if res['provider'] == 'laya':
        print("  [SUCCESS] LayaClient is operating natively with local Ollama!")
    else:
        print(f"  [FALLBACK] LayaClient safely degraded to '{res['provider']}' (zero crashing).")
    print("=" * 60)


if __name__ == "__main__":
    main()
