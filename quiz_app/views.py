from rest_framework.views import APIView
from rest_framework.response import Response
from bson import ObjectId
from bson.errors import InvalidId
from django.core.cache import cache

from .mongo import quiz_collection, question_collection
from .llm_service import generate_upsc_question
from .validators import validate_topic, validate_answer


# =======================
# LANGUAGE DETECTION
# =======================
def detect_language_from_text(text: str) -> str:
    """
    Detect Tamil language using Unicode range.
    Returns 'ta' for Tamil, 'en' for English.
    """
    for ch in text:
        if '\u0B80' <= ch <= '\u0BFF':
            return "ta"
    return "en"


def decide_language(exam_type: str, topic: str) -> str:
    """
    Centralized language decision.
    User has NO control over language.
    """
    if exam_type.upper() == "UPSC":
        return "en"
    elif exam_type.upper() == "TNPSC":
        return detect_language_from_text(topic)
    return "en"


# =======================
# START QUIZ
# =======================
class StartQuizAPIView(APIView):
    def post(self, request):
        topic = request.data.get("topic")
        exam_type = request.data.get("exam_type", "UPSC")

        valid, error = validate_topic(topic)
        if not valid:
            return Response({"error": error}, status=400)

        quiz = {
            "exam_type": exam_type.upper(),
            "topic": topic,
            "total_questions": 3,   # change to 25 if needed
            "correct_count": 0
        }

        quiz_id = quiz_collection.insert_one(quiz).inserted_id

        return Response({
            "quiz_id": str(quiz_id),
            "exam_type": exam_type.upper(),
            "message": "Quiz started"
        })


# =======================
# GENERATE ALL QUESTIONS
# =======================
class GenerateAllQuestionsAPIView(APIView):
    def post(self, request):
        quiz_id = request.data.get("quiz_id")

        if not quiz_id:
            return Response({"error": "quiz_id is required"}, status=400)

        try:
            quiz_obj_id = ObjectId(quiz_id)
            quiz = quiz_collection.find_one({"_id": quiz_obj_id})
        except InvalidId:
            return Response({"error": "Invalid quiz_id"}, status=400)

        if not quiz:
            return Response({"error": "Quiz not found"}, status=404)

        exam_type = quiz["exam_type"]
        topic = quiz["topic"]
        total = quiz["total_questions"]

        # 🔐 LANGUAGE LOCK (USER CANNOT CONTROL)
        language = decide_language(exam_type, topic)

        response_questions = []

        for q_no in range(1, total + 1):

            # Check if already generated for this quiz
            existing = question_collection.find_one({
                "quiz_id": quiz_obj_id,
                "question_no": q_no
            })

            if existing:
                response_questions.append({
                    "question_id": str(existing["_id"]),
                    "question_no": q_no,
                    "question": existing["question"],
                    "options": existing["options"]
                })
                continue

            # 🔑 TOPIC-BASED CACHE KEY (REDIS HIT FOR SAME TOPIC)
            safe_topic = topic.strip().lower()
            cache_key = f"topic:{exam_type}:{language}:{safe_topic}:q{q_no}"

            llm_data = cache.get(cache_key)

            if llm_data:
                print(f"✅ REDIS HIT → {cache_key}")
            else:
                print(f"❌ REDIS MISS → {cache_key}")
                llm_data = generate_upsc_question(
                    exam_type=exam_type,
                    topic=topic,
                    language=language
                )

                if not llm_data:
                    return Response(
                        {"error": "Question generation failed. Please retry."},
                        status=500
                    )

                # 🚨 UPSC language safety (English only)
                if exam_type == "UPSC":
                    if detect_language_from_text(llm_data["question"]) != "en":
                        return Response(
                            {"error": "Language violation detected. Retry required."},
                            status=500
                        )

                cache.set(cache_key, llm_data, timeout=3600)

            # Save question for this quiz
            question = {
                "quiz_id": quiz_obj_id,
                "question_no": q_no,
                "question": llm_data["question"],
                "options": llm_data["options"],
                "correct_answer": llm_data["correct_answer"],
                "explanation": llm_data["explanation"],
                "answered": False
            }

            q_id = question_collection.insert_one(question).inserted_id

            response_questions.append({
                "question_id": str(q_id),
                "question_no": q_no,
                "question": question["question"],
                "options": question["options"]
            })

        return Response({"questions": response_questions})


# =======================
# SUBMIT ANSWER
# =======================
class SubmitAnswerAPIView(APIView):
    def post(self, request):
        question_id = request.data.get("question_id")
        user_answer = request.data.get("user_answer")

        valid, error = validate_answer(user_answer)
        if not valid:
            return Response({"error": error}, status=400)

        try:
            question_obj_id = ObjectId(question_id)
            question = question_collection.find_one({"_id": question_obj_id})
        except InvalidId:
            return Response({"error": "Invalid question_id"}, status=400)

        if not question:
            return Response({"error": "Question not found"}, status=404)

        if question["answered"]:
            return Response({
                "message": "Already answered",
                "is_correct": question["is_correct"],
                "correct_answer": question["correct_answer"],
                "explanation": question["explanation"]
            })

        is_correct = user_answer == question["correct_answer"]

        question_collection.update_one(
            {"_id": question_obj_id},
            {"$set": {
                "answered": True,
                "user_answer": user_answer,
                "is_correct": is_correct
            }}
        )

        if is_correct:
            quiz_collection.update_one(
                {"_id": question["quiz_id"]},
                {"$inc": {"correct_count": 1}}
            )

        return Response({
            "is_correct": is_correct,
            "correct_answer": question["correct_answer"],
            "explanation": question["explanation"]
        })


# =======================
# QUIZ SUMMARY
# =======================
class QuizSummaryAPIView(APIView):
    def get(self, request, quiz_id):
        try:
            quiz_obj_id = ObjectId(quiz_id)
            quiz = quiz_collection.find_one({"_id": quiz_obj_id})
        except InvalidId:
            return Response({"error": "Invalid quiz_id"}, status=400)

        if not quiz:
            return Response({"error": "Quiz not found"}, status=404)

        total = quiz["total_questions"]

        answered_count = question_collection.count_documents({
            "quiz_id": quiz_obj_id,
            "answered": True
        })

        if answered_count < total:
            return Response({
                "error": "All questions must be answered before viewing summary",
                "answered": answered_count,
                "total": total
            }, status=400)

        correct = quiz["correct_count"]
        wrong = total - correct
        percentage = round((correct / total) * 100, 2)

        return Response({
            "exam_type": quiz["exam_type"],
            "total_questions": total,
            "correct_questions": correct,
            "wrong_questions": wrong,
            "score": correct,
            "percentage": percentage
        })
