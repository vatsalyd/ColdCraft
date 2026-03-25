"""Test Gemini with new SDK."""
from modules.ai import generate_text, parse_resume_text

print("Test 1: Generate text")
try:
    r = generate_text("Say hello in 5 words", max_tokens=20)
    print(f"  OK: {r}")
except Exception as e:
    print(f"  FAIL: {e}")

print("Test 2: Parse resume")
try:
    r = parse_resume_text("John Doe, Software Engineer. Skills: Python, ML, Flask. Email: john@test.com. GitHub: github.com/johndoe")
    print(f"  OK: name={r.get('name')}, skills={r.get('skills', [])[:3]}")
except Exception as e:
    print(f"  FAIL: {e}")

print("Done!")
