from groq import Groq
from django.conf import settings
import json

client = Groq(api_key=settings.GROQ_API_KEY)

def generate_upsc_question(exam_type, topic):
    prompt = f"""
Generate ONE HARD-level multiple choice question.

Exam Type: {exam_type}

Rules:
- Difficulty: HARD
- Exactly 4 options (A, B, C, D)
- One correct answer
- Provide brief explanation
- Return ONLY valid JSON

If Exam Type is UPSC:
- National-level questions
- Analytical and constitutional depth
- Suitable for UPSC Prelims

If Exam Type is TNPSC:
- Tamil Nadu specific content
- Tamil Nadu history, polity, geography, schemes
- Suitable for TNPSC Group exams

JSON format:
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

Topic: {topic}
"""

    # ✅ CALL GROQ LLM
    response = client.chat.completions.create(
        model="llama-3.1-8b-instant",
        messages=[
            {"role": "user", "content": prompt}
        ],
        temperature=0.4
    )

    # ✅ PARSE & RETURN JSON
    return json.loads(response.choices[0].message.content)
