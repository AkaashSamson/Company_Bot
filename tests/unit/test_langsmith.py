#!/usr/bin/env python
"""
Test script to verify LangSmith integration is working.

This will help you debug if tokens are appearing in LangSmith.
"""

import os
import logging
from app.core.settings import LANGCHAIN_TRACING_V2, LANGCHAIN_API_KEY, LANGCHAIN_PROJECT

# Setup logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

print("=" * 70)
print("LangSmith Integration Test")
print("=" * 70)

# Check 1: Environment configuration
print("\n1. Checking LangSmith Configuration:")
print(f"   LANGCHAIN_TRACING_V2: {LANGCHAIN_TRACING_V2}")
print(f"   LANGCHAIN_API_KEY: {'***' + LANGCHAIN_API_KEY[-10:] if LANGCHAIN_API_KEY else 'NOT SET'}")
print(f"   LANGCHAIN_PROJECT: {LANGCHAIN_PROJECT}")

if not LANGCHAIN_TRACING_V2:
    print("\n   ❌ ERROR: LANGCHAIN_TRACING_V2 is not enabled!")
    print("   Add to .env: LANGCHAIN_TRACING_V2=true")
    
if not LANGCHAIN_API_KEY:
    print("\n   ❌ ERROR: LANGCHAIN_API_KEY is not set!")
    print("   Add to .env: LANGCHAIN_API_KEY=ls_...")

# Check 2: LangSmith library
print("\n2. Checking if langsmith is installed:")
try:
    import langsmith
    print(f"   ✅ langsmith version: {langsmith.__version__}")
except ImportError:
    print("   ❌ langsmith not installed")
    print("   Install with: pip install langsmith")

# Check 3: Test creating a run
print("\n3. Testing LangSmith trace:")
try:
    from langsmith import Client, traceable
    
    if LANGCHAIN_TRACING_V2 and LANGCHAIN_API_KEY:
        client = Client()
        
        # Create a test run
        test_run = client.create_run(
            name="test_trace",
            run_type="chain",
            project_name=LANGCHAIN_PROJECT,
            inputs={"test": "input"},
        )
        
        print(f"   ✅ Created test run: {test_run.id}")
        
        # Update run with outputs (including tokens)
        client.update_run(
            test_run.id,
            outputs={
                "test_output": "success",
                "prompt_tokens": 100,
                "completion_tokens": 50,
                "total_tokens": 150,
            }
        )
        
        print(f"   ✅ Updated run with token data")
        print(f"\n   Visit: https://api.smith.langchain.com/")
        print(f"   Project: {LANGCHAIN_PROJECT}")
        print(f"   Look for run: {test_run.id}")
        
    else:
        print("   ⚠️  LangSmith not fully configured - skipping test")
        
except Exception as e:
    print(f"   ❌ Error: {e}")
    import traceback
    traceback.print_exc()

# Check 4: Test decorator
print("\n4. Testing @traceable decorator:")
try:
    from langsmith import traceable
    
    @traceable(name="test_function", run_type="llm")
    def test_llm_call():
        return {
            "answer": "Test answer",
            "prompt_tokens": 342,
            "completion_tokens": 156,
            "total_tokens": 498,
        }
    
    print("   ✅ Decorator syntax is correct")
    print("   (Would create trace when called with LANGCHAIN_TRACING_V2=true)")
    
except Exception as e:
    print(f"   ❌ Error: {e}")

print("\n" + "=" * 70)
print("Test Complete")
print("=" * 70)

# Summary
print("\nNext Steps:")
print("1. Make sure LANGCHAIN_TRACING_V2=true in .env")
print("2. Make sure LANGCHAIN_API_KEY is set in .env")
print("3. Run the app: python -m uvicorn app.main:app --host 127.0.0.1 --port 8000")
print("4. Ask a question in Streamlit or via API")
print("5. Check https://api.smith.langchain.com for traces")
print("6. Expand 'LLMGenerate' trace to see token metadata")
