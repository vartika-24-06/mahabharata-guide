"""
One-off manual test: classify a few real eval-set questions using your
own OpenAI key (reuses OPENAI_API_KEY from your .env - no new key
needed). Safe to delete after checking the results.

Run with: python test_classifier_live.py
"""
import os
from pathlib import Path

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent / ".env")

import classifier

# (question, expected label from docs/qna-eval-set)
questions = [
    ("Did Bhishma get married?", "factual"),
    ("Why should Arjuna have fought the war?", "philosophical"),
    ("Is fate stronger than effort in the epic?", "philosophical (Settle)"),
    ("Was the Mahabharata war necessary?", "ambiguous"),
    ("What does Vidura say about greed?", "philosophical"),
    ("Was Karna wrong to stay loyal to Duryodhana?", "ambiguous"),
]

for q, expected in questions:
    result = classifier.classify_question("openai", os.environ["OPENAI_API_KEY"], q)
    print(f"{result['label']:15} (conf {result['confidence']:.2f})  expected: {expected:25}  {q}")
