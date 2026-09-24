"""
check_gemini.py — standalone diagnostic. Run this directly to see the
REAL error Gemini is returning, instead of the friendly message the app
shows. Doesn't touch any of your other files.

Run with:
    python check_gemini.py
"""

import os
from dotenv import load_dotenv

load_dotenv()

api_key = os.getenv("GEMINI_API_KEY")
print("Key loaded from .env:", (api_key[:8] + "...") if api_key else "MISSING")

from google import genai

client = genai.Client(api_key=api_key)

try:
    response = client.models.generate_content(
        model="gemini-3.6-flash",
        contents="Say hello in one short sentence.",
    )
    print("SUCCESS:", response.text)
except Exception as e:
    print("FULL ERROR TYPE:", type(e))
    print("FULL ERROR MESSAGE:")
    print(str(e))