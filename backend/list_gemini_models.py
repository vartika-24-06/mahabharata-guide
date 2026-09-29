"""
One-off helper: lists every Gemini model your API key can access, and
which ones support embedContent. Run this once to find out the right
model name for push_to_supabase.py - safe to delete afterward.
"""
import os
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent / ".env")
except ImportError:
    pass

import google.generativeai as genai

genai.configure(api_key=os.environ["GEMINI_API_KEY"])

print("Models available to your key that support embedContent:\n")
for m in genai.list_models():
    if "embedContent" in m.supported_generation_methods:
        print(f"  {m.name}")

print("\nAll models available to your key (for reference):\n")
for m in genai.list_models():
    print(f"  {m.name}  -> {m.supported_generation_methods}")
