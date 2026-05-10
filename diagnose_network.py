"""
Network Diagnostic Script - Used to troubleshoot phase 2 network error issues
"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), 'dynahmrc'))

import time
import json
from dynahmrc.utils.llm_api import KimiLLMClient, MockLLMClient

def test_api_connection(api_key=None, timeout=60):
    """Test API connection"""
    print("=" * 60)
    print("🔍 Network Diagnostic Tool")
    print("=" * 60)
    
    # 1. Test Mock client
    print("\n[1/4] Testing Mock client...")
    try:
        mock_client = MockLLMClient()
        messages = [{"role": "user", "content": "Hello"}]
        response = mock_client.complete(messages)
        print(f"✅ Mock client normal: {response[:50]}...")
    except Exception as e:
        print(f"❌ Mock client error: {e}")
    
    # 2. Check API Key
    print("\n[2/4] Checking API Key...")
    if not api_key:
        api_key = os.getenv("MOONSHOT_API_KEY")
    
    if not api_key:
        print("❌ API Key not found")
        print("   Please set environment variable MOONSHOT_API_KEY or pass api_key parameter")
        return
    else:
        print(f"✅ API Key set: {api_key[:10]}...")
    
    # 3. Test API connection
    print(f"\n[3/4] Testing Kimi API connection (timeout={timeout}s)...")
    try:
        client = KimiLLMClient(
            api_key=api_key,
            model="kimi-k2.5",
            timeout=timeout
        )
        
        # Send simple test request
        messages = [{"role": "user", "content": "Say hello in one word"}]
        start_time = time.time()
        response = client.complete(messages, max_tokens=10)
        elapsed = time.time() - start_time
        
        print(f"✅ API connection normal")
        print(f"   Response time: {elapsed:.2f}s")
        print(f"   Response content: {response}")
        
    except Exception as e:
        print(f"❌ API connection failed: {e}")
        print(f"   Error type: {type(e).__name__}")
    
    # 4. Test complex task allocation request
    print("\n[4/4] Testing Task Allocation request...")
    try:
        client = KimiLLMClient(
            api_key=api_key,
            model="kimi-k2.5",
            timeout=timeout
        )
        
        # Simulate Task Allocation prompt
        prompt = """You are Alice with capabilities: navigate, open, pick, place, move, communicate, wait.

Task: Pack all red objects into the box.

Teammates:
Bob: I am Bob, a fixed manipulator arm. I can pick and place objects efficiently.

Your goal: Propose YOUR OWN INDEPENDENT task allocation plan for the ENTIRE team and deliver a campaign speech.

Output format:
Thought: [Your independent analysis]

Plan:
Alice: [Your specific task];
Bob: [Their specific task];

Campaign Speech:
Hi team, I'm Alice. [Your campaign]

Begin:"""
        
        messages = [{"role": "user", "content": prompt}]
        start_time = time.time()
        response = client.complete(messages, max_tokens=800, temperature=1.0)
        elapsed = time.time() - start_time
        
        print(f"✅ Task Allocation request successful")
        print(f"   Response time: {elapsed:.2f}s")
        print(f"   Response length: {len(response)} characters")
        print(f"   Response preview:\n{response[:300]}...")
        
    except Exception as e:
        print(f"❌ Task Allocation request failed: {e}")
        print(f"   Error type: {type(e).__name__}")
        print("\n💡 Suggestions:")
        print("   1. Check if network connection is stable")
        print("   2. Increase timeout parameter (e.g., 120s)")
        print("   3. Switch to Mock mode for testing")
        print("   4. Check Kimi API service status")
    
    print("\n" + "=" * 60)
    print("Diagnosis complete")
    print("=" * 60)


def diagnose_streaming():
    """Diagnose streaming response issues"""
    print("\n📡 Streaming Response Diagnosis")
    print("-" * 60)
    
    from flask import Flask
    app = Flask(__name__)
    
    with app.app_context():
        # Test SSE format
        test_data = {"message": "test", "timestamp": time.strftime("%H:%M:%S")}
        event = f"event: test\ndata: {json.dumps(test_data, ensure_ascii=False)}\n\n"
        print(f"✅ SSE format normal")
        print(f"   Example: {repr(event[:100])}")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='Diagnose DynaHMRC network issues')
    parser.add_argument('--api-key', help='Moonshot API Key')
    parser.add_argument('--timeout', type=float, default=60, help='API timeout (seconds)')
    parser.add_argument('--streaming', action='store_true', help='Diagnose streaming response')
    
    args = parser.parse_args()
    
    test_api_connection(args.api_key, args.timeout)
    
    if args.streaming:
        diagnose_streaming()
