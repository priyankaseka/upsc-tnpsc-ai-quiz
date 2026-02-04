from groq import Groq
from django.conf import settings
import json
import re

# =======================
# GROQ CLIENT
# =======================
client = Groq(api_key=settings.GROQ_API_KEY)


# =======================
# SAFE JSON PARSER
# =======================
def safe_json_parse(text: str):
    """
    Safely extract and parse JSON from LLM output.
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
        "is known as",
        "which country",
        "which of the following is",
        "refers to",
        "is defined as"
    ]
    q = question.lower()
    return any(p in q for p in banned_phrases)

def generate_upsc_question(exam_type, topic, language="en"):
    """
    Generate ONE MCQ based on UPSC / TNPSC rules.
    Returns dict or None.
    """

    exam_type = exam_type.upper()

    # 🔐 UPSC language lock
    if exam_type == "UPSC":
        language = "en"


    prompt = f"""
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
- Do NOT add any text outside JSON
- Exactly 4 options: A, B, C, D
- Only ONE correct answer
- correct_answer must be A, B, C, or D
- Question must be factually correct and unambiguous

------------------------------------------------
UPSC RULES (APPLY ONLY IF EXAM TYPE = UPSC):

- Language MUST be English
- Difficulty MUST match UPSC Prelims PYQ standard
- Question MUST test conceptual understanding or elimination
- Do NOT ask direct factual or location-based questions
- Do NOT ask “which case introduced…” questions
- Avoid list-based and memory-based questions
- Prefer:
  • Statement-based questions
  • Assertion–Reason questions
  • Conceptual elimination questions

------------------------------------------------
TNPSC RULES (APPLY ONLY IF EXAM TYPE = TNPSC):

- Language must follow the topic naturally
  (Tamil topic → Tamil, English topic → English)
- Tamil Nadu relevance is mandatory
- Difficulty: TNPSC Group I / II standard
- Prefer:
  • Chronology
  • Scheme–objective matching
  • Tamil Nadu administration, polity, history, geography

------------------------------------------------
JSON OUTPUT FORMAT (STRICT):
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

IMPORTANT:
- Explanation must clearly justify why the correct option is correct
- Do NOT mention the exam name in the question
"""

    # =======================
    # RETRY LOGIC
    # =======================
    max_attempts = 4 if exam_type == "UPSC" else 2

    for _ in range(max_attempts):
        try:
            response = client.chat.completions.create(
                model="llama-3.1-8b-instant",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.35,
                max_tokens=700
            )

            content = response.choices[0].message.content.strip()
            parsed = safe_json_parse(content)

            # -----------------------
            # BASIC VALIDATION
            # -----------------------
            if not parsed or not isinstance(parsed, dict):
                continue

            if "question" not in parsed or "options" not in parsed:
                continue

            # TNPSC-TOLERANT OPTION CHECK
            if not set(parsed["options"].keys()).issuperset({"A", "B", "C", "D"}):
                continue

            if parsed.get("correct_answer") not in {"A", "B", "C", "D"}:
                continue

            if "explanation" not in parsed:
                continue

            # UPSC QUALITY FILTER (ONLY FOR UPSC)
            if exam_type == "UPSC":
                if is_upsc_too_factual(parsed["question"]):
                    continue

            return parsed

        except Exception:
            continue

    # All attempts failed
    return None
