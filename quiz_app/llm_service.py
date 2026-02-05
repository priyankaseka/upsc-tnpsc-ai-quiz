from groq import Groq
from django.conf import settings
from django.core.cache import cache
import json
import re

client = Groq(api_key=settings.GROQ_API_KEY)

def safe_json_parse(text: str):
    """
    Extract and parse JSON safely from LLM output.
    Handles extra text or malformed responses.
    """
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{[\s\S]*\}", text)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                return None
        return None


def is_upsc_too_factual(question: str) -> bool:
    """
    Reject school-level or direct factual UPSC questions.
    """
    banned_phrases = [
        "is located",
        "is defined as",
        "refers to",
        "means",
        "which country"
    ]
    q = question.lower()
    return any(p in q for p in banned_phrases)


def build_cache_key(exam_type: str, language: str, topic: str) -> str:
    return f"quiz:{exam_type}:{language}:{topic.strip().lower()}"

def generate_upsc_question(exam_type, topic, language="en"):
    """
    Generate ONE MCQ based on UPSC / TNPSC rules.
    Uses Redis cache to avoid repeated LLM calls.
    Returns dict or None.
    """

    exam_type = exam_type.upper()

    # 🔐 UPSC language lock
    if exam_type == "UPSC":
        language = "en"

    cache_key = build_cache_key(exam_type, language, topic)
    cached_data = cache.get(cache_key)

    if cached_data:
        print("✅ Redis HIT → LLM not called")
        return cached_data

    print("❌ Redis MISS → Calling LLM")

    strict_prompt = f"""
You are a senior examiner who sets questions for Indian competitive examinations.

Generate EXACTLY ONE high-quality multiple-choice question
strictly following the rules below.

========================
EXAM TYPE: {exam_type}
TOPIC: {topic}
LANGUAGE: {language}
========================

GLOBAL RULES:
- Output ONLY valid JSON
- No text outside JSON
- Exactly 4 options: A, B, C, D
- Only ONE correct answer
- correct_answer must be A, B, C, or D
- Question must be factually correct and unambiguous

------------------------------------------------
UPSC RULES (APPLY ONLY IF EXAM TYPE = UPSC):

- Language MUST be English
- Difficulty MUST match UPSC Prelims PYQ standard
- Question MUST test conceptual understanding or elimination
- Avoid direct factual or location-based questions
- Avoid “which case introduced…” questions
- Prefer:
  • Statement-based
  • Assertion–Reason
  • Conceptual elimination questions

------------------------------------------------
TNPSC RULES (APPLY ONLY IF EXAM TYPE = TNPSC):

- Language must follow the topic naturally
- Tamil Nadu relevance is mandatory
- Difficulty: TNPSC Group I / II standard
- Prefer chronology and scheme–objective matching

------------------------------------------------
JSON OUTPUT FORMAT:
{{
  "question": "",
  "options": {{
    "A": "",
    "B": "",
    "C": "",
    "D": ""
  }},
  "correct_answer": "",
  "explanation": ""
}}
"""

    fallback_prompt = f"""
Generate ONE conceptual multiple-choice question in English.

RULES:
- No direct factual recall
- No locations
- No definitions
- Use reasoning or elimination
- Output ONLY valid JSON
- Exactly 4 options A, B, C, D

TOPIC:
{topic}

JSON FORMAT:
{{
  "question": "",
  "options": {{
    "A": "",
    "B": "",
    "C": "",
    "D": ""
  }},
  "correct_answer": "",
  "explanation": ""
}}
"""
    max_attempts = 3 if exam_type == "UPSC" else 2

    for attempt in range(max_attempts + 1):
        try:
            prompt = strict_prompt if attempt < max_attempts else fallback_prompt

            response = client.chat.completions.create(
                model="llama-3.1-8b-instant",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.35,
                max_tokens=700
            )

            content = response.choices[0].message.content.strip()
            parsed = safe_json_parse(content)

            if not parsed or not isinstance(parsed, dict):
                continue

            if not {"question", "options", "correct_answer", "explanation"} <= parsed.keys():
                continue

            if not {"A", "B", "C", "D"} <= set(parsed["options"].keys()):
                continue

            if parsed["correct_answer"] not in {"A", "B", "C", "D"}:
                continue

            if exam_type == "UPSC" and is_upsc_too_factual(parsed["question"]):
                continue

            cache.set(cache_key, parsed, timeout=None)  

            return parsed

        except Exception:
            continue

    return None
