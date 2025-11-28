#!/usr/bin/env python3
import requests
import os
import sys
import json
from datetime import datetime

# Endpoint to test
ENDPOINT_URL = os.environ.get("ENDPOINT_URL", "http://localhost:5000/quiz")
ROOT_URL = ENDPOINT_URL.rsplit('/', 1)[0] + '/'

# Your student credentials
EMAIL = os.environ.get("STUDENT_EMAIL")
SECRET = os.environ.get("STUDENT_SECRET")

def test_health(base_url):
    """Check if the service is running"""
    try:
        r = requests.get(base_url, timeout=5)
        assert r.status_code == 200
        print("✅ Health check passed")
        return True
    except Exception as e:
        print(f"❌ Health check failed: {e}")
        return False

def test_invalid_json(url):
    """Send invalid JSON and expect a 400 response"""
    try:
        r = requests.post(url, data="not json", headers={"Content-Type":"application/json"}, timeout=5)
        assert r.status_code == 400
        print("✅ Invalid JSON test passed")
        return True
    except Exception as e:
        print(f"❌ Invalid JSON test failed: {e}")
        return False

def test_invalid_secret(url):
    """Send wrong secret and expect 401"""
    try:
        r = requests.post(
            url,
            json={"email": EMAIL, "secret": "wrong_secret", "url": "https://example.com"},
            timeout=5
        )
        assert r.status_code == 401
        print("✅ Invalid secret test passed")
        return True
    except Exception as e:
        print(f"❌ Invalid secret test failed: {e}")
        return False

def test_demo_quiz(url):
    """Send a real demo quiz URL and check response"""
    try:
        print("⏳ Testing demo quiz (may take 30-60s)...")
        r = requests.post(
            url,
            json={
                "email": EMAIL,
                "secret": SECRET,
                "url": "https://tds-llm-analysis.s-anand.net/demo"
            },
            timeout=180
        )

        assert r.status_code == 200
        print("✅ Demo quiz test passed")
        print(json.dumps(r.json(), indent=2))
        return True
    except Exception as e:
        print(f"❌ Demo quiz failed: {e}")
        return False

def run_tests():
    """Run all tests"""
    print(f"Testing endpoint: {ENDPOINT_URL} at {datetime.now()}")
    results = [
        test_health(ROOT_URL),
        test_invalid_json(ENDPOINT_URL),
        test_invalid_secret(ENDPOINT_URL),
        test_demo_quiz(ENDPOINT_URL)
    ]
    print(f"\n✅ Passed {sum(results)}/{len(results)} tests")
    return 0 if all(results) else 1

if __name__ == "__main__":
    if not EMAIL or not SECRET:
        print("❌ Set STUDENT_EMAIL and STUDENT_SECRET")
        sys.exit(1)
    sys.exit(run_tests())
