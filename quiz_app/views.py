from rest_framework.views import APIView
from rest_framework.response import Response
from bson import ObjectId
from bson.errors import InvalidId

from .mongo import quiz_collection, summary_collection
from .llm_service import generate_upsc_question
from .validators import validate_topic, validate_answer


# =======================
# LANGUAGE DETECTION
# =======================
def detect_language_from_text(text: str) -> str:
    for ch in text:
        if '\u0B80' <= ch <= '\u0BFF':
            return "ta"
    return "en"


def decide_language(exam_type: str, topic: str) -> str:
    if exam_type.upper() == "UPSC":
        return "en"
    if exam_type.upper() == "TNPSC":
        return detect_language_from_text(topic)
    return "en"


# =======================
# START QUIZ
# =======================
class StartQuizAPIView(APIView):
    def post(self, request):
        topic = request.data.get("topic")
        exam_type = request.data.get("exam_type", "UPSC").upper()

        valid, error = validate_topic(topic)
        if not valid:
            return Response({"error": error}, status=400)

        quiz = {
            # if authentication exists, you can add:
            # "user_id": request.user.id,
            "topic": topic,
            "exam_type": exam_type,
            "questions": [],
            "total_questions": 3
        }

        quiz_id = quiz_collection.insert_one(quiz).inserted_id

        return Response({
            "quiz_id": str(quiz_id),
            "exam_type": exam_type,
            "message": "Quiz started"
        })


# =======================
# GENERATE QUESTIONS
# =======================
class GenerateAllQuestionsAPIView(APIView):
    def post(self, request):
        quiz_id = request.data.get("quiz_id")

        if not quiz_id:
            return Response({"error": "quiz_id is required"}, status=400)

        try:
            quiz_obj_id = ObjectId(quiz_id)
        except InvalidId:
            return Response({"error": "Invalid quiz_id"}, status=400)

        quiz = quiz_collection.find_one({"_id": quiz_obj_id})
        if not quiz:
            return Response({"error": "Quiz not found"}, status=404)

        # Prevent re-generation
        if quiz.get("questions"):
            return Response({
                "questions": [
                    {
                        "question_id": q["question_id"],
                        "question_no": q["question_no"],
                        "question": q["question"],
                        "options": q["options"]
                    }
                    for q in quiz["questions"]
                ]
            })

        exam_type = quiz["exam_type"]
        topic = quiz["topic"]
        language = decide_language(exam_type, topic)

        questions = []

        for q_no in range(1, quiz["total_questions"] + 1):
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

            questions.append({
                "question_id": str(ObjectId()),
                "question_no": q_no,
                "question": llm_data["question"],
                "options": llm_data["options"],
                "correct_answer": llm_data["correct_answer"],
                "explanation": llm_data["explanation"],
                "answered": False
            })

        quiz_collection.update_one(
            {"_id": quiz_obj_id},
            {"$set": {"questions": questions}}
        )

        return Response({
            "questions": [
                {
                    "question_id": q["question_id"],
                    "question_no": q["question_no"],
                    "question": q["question"],
                    "options": q["options"]
                }
                for q in questions
            ]
        })


# =======================
# SUBMIT ANSWER
# =======================
class SubmitAnswerAPIView(APIView):
    def post(self, request):
        quiz_id = request.data.get("quiz_id")
        question_id = request.data.get("question_id")
        user_answer = request.data.get("user_answer")

        if not quiz_id or not question_id:
            return Response(
                {"error": "quiz_id and question_id are required"},
                status=400
            )

        valid, error = validate_answer(user_answer)
        if not valid:
            return Response({"error": error}, status=400)

        user_answer = user_answer.upper().strip()
        question_id = question_id.strip()

        try:
            quiz_obj_id = ObjectId(quiz_id)
        except InvalidId:
            return Response({"error": "Invalid quiz_id"}, status=400)

        quiz = quiz_collection.find_one({"_id": quiz_obj_id})
        if not quiz:
            return Response({"error": "Quiz not found"}, status=404)

        if not quiz.get("questions"):
            return Response(
                {"error": "Questions not generated yet"},
                status=400
            )

        question = next(
            (q for q in quiz["questions"] if q["question_id"] == question_id),
            None
        )

        if not question:
            return Response({"error": "Question not found"}, status=404)

        if question.get("answered"):
            return Response({
                "message": "Already answered",
                "is_correct": question["is_correct"],
                "correct_answer": question["correct_answer"],
                "explanation": question["explanation"]
            })

        is_correct = user_answer == question["correct_answer"]

        quiz_collection.update_one(
            {"_id": quiz_obj_id, "questions.question_id": question_id},
            {"$set": {
                "questions.$.answered": True,
                "questions.$.user_answer": user_answer,
                "questions.$.is_correct": is_correct
            }}
        )

        return Response({
            "is_correct": is_correct,
            "correct_answer": question["correct_answer"],
            "explanation": question["explanation"]
        })


# =======================
# QUIZ SUMMARY (STORED IN DB)
# =======================
class QuizSummaryAPIView(APIView):
    def get(self, request, quiz_id):
        try:
            quiz_obj_id = ObjectId(quiz_id)
        except InvalidId:
            return Response({"error": "Invalid quiz_id"}, status=400)

        quiz = quiz_collection.find_one({"_id": quiz_obj_id})
        if not quiz:
            return Response({"error": "Quiz not found"}, status=404)

        total = quiz["total_questions"]
        answered = [q for q in quiz["questions"] if q.get("answered")]
        correct = sum(1 for q in answered if q.get("is_correct"))

        if len(answered) < total:
            return Response({
                "error": "All questions must be answered",
                "answered": len(answered),
                "total": total
            }, status=400)

        percentage = round((correct / total) * 100, 2)

        # ✅ STORE SUMMARY FOR ADMIN
        summary_collection.update_one(
            {"quiz_id": quiz_obj_id},
            {"$set": {
                "quiz_id": quiz_obj_id,
                # "user_id": quiz.get("user_id"),  # enable if auth added
                "exam_type": quiz["exam_type"],
                "total_questions": total,
                "correct_questions": correct,
                "wrong_questions": total - correct,
                "percentage": percentage
            }},
            upsert=True
        )

        return Response({
            "exam_type": quiz["exam_type"],
            "total_questions": total,
            "correct_questions": correct,
            "wrong_questions": total - correct,
            "percentage": percentage
        })
