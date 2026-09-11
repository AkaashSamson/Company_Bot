#!/usr/bin/env python
"""
Debug script to verify token tracking is working.

Run this to test if tokens are being extracted from OpenRouter API calls.
"""

import json
import logging
from app.infrastructure.llm.openrouter_client import OpenRouterClient
from app.infrastructure.observability.token_tracker import get_token_tracker

# Enable debug logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

print("=" * 60)
print("Token Tracking Debug Test")
print("=" * 60)

# Create a test client
client = OpenRouterClient()

print("\n1. Testing OpenRouter Client token extraction...")
print(f"   API Key configured: {bool(client.api_key)}")
print(f"   Model: {client.model}")

# Simulate an API response with token usage
test_response = {
    "choices": [{"message": {"content": "Test response"}}],
    "usage": {
        "prompt_tokens": 150,
        "completion_tokens": 75,
    }
}

print("\n2. Simulating token extraction from API response...")
print(f"   Test response: {json.dumps(test_response, indent=2)}")

# Test the token extraction
client._track_tokens(test_response)
client._add_tokens_to_langsmith(test_response)

print("\n3. Checking token storage in client...")
last_tokens = client.get_last_tokens()
if last_tokens:
    print(f"   ✅ Tokens stored in client:")
    print(f"      - prompt_tokens: {last_tokens.get('prompt_tokens')}")
    print(f"      - completion_tokens: {last_tokens.get('completion_tokens')}")
    print(f"      - total_tokens: {last_tokens.get('total_tokens')}")
    print(f"      - model: {last_tokens.get('model')}")
else:
    print(f"   ❌ No tokens stored in client")

print("\n4. Checking token tracker...")
tracker = get_token_tracker()
total_stats = tracker.get_total()
print(f"   ✅ Token tracker stats:")
print(f"      - total_tokens: {total_stats.total_tokens}")
print(f"      - total_calls: {total_stats.call_count}")
print(f"      - avg_tokens_per_call: {total_stats.avg_tokens_per_call:.2f}")

recent = tracker.get_recent(limit=1)
if recent:
    print(f"\n5. Recent token record:")
    for usage in recent:
        print(f"   - timestamp: {usage.timestamp}")
        print(f"   - model: {usage.model}")
        print(f"   - prompt_tokens: {usage.prompt_tokens}")
        print(f"   - completion_tokens: {usage.completion_tokens}")
        print(f"   - total_tokens: {usage.total_tokens}")
        print(f"   - session_id: {usage.session_id}")
else:
    print(f"\n5. ❌ No recent token records found")

print("\n" + "=" * 60)
print("Debug test complete!")
print("=" * 60)

# Summary
if last_tokens and recent:
    print("\n✅ Token tracking is working!")
    print("\nYour tokens will appear in:")
    print("  1. FastAPI response in /api/chat endpoint")
    print("  2. Streamlit app sidebar metrics")
    print("  3. LangSmith traces (if enabled)")
else:
    print("\n❌ Token tracking may have issues")
    print("\nTroubleshooting:")
    print("  1. Check OPENROUTER_API_KEY is set")
    print("  2. Verify OpenRouter API responses include 'usage' field")
    print("  3. Check application logs for errors")
