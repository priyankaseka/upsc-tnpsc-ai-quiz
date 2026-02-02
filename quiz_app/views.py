from rest_framework.views import APIView
from rest_framework.response import Response
from bson import ObjectId
from bson.errors import InvalidId

from .mongo import quiz_collection, question_collection
from .llm_service import generate_upsc_question
from .validators import validate_topic, validate_answer


# =======================
# START QUIZ
# =======================
class StartQuizAPIView(APIView):
    def post(self, request):
        topic = request.data.get("topic")
        exam_type = request.data.get("exam_type", "UPSC")  # UPSC / TNPSC

        # Validate topic
        valid, error = validate_topic(topic)
        if not valid:
            return Response({"error": error}, status=400)

        quiz = {
            "exam_type": exam_type,        # ✅ store exam type
            "topic": topic,
            "total_questions": 3,          # ✅ backend fixed
            "current_question": 0,
            "correct_count": 0
        }

        quiz_id = quiz_collection.insert_one(quiz).inserted_id

        return Response({
            "quiz_id": str(quiz_id),
            "exam_type": exam_type,
            "message": "Quiz started"
        })


# =======================
# GENERATE QUESTION
# =======================
class GenerateQuestionAPIView(APIView):
    def post(self, request):
        quiz_id = request.data.get("quiz_id")

        # 1️⃣ quiz_id validation
        if not quiz_id:
            return Response({"error": "quiz_id is required"}, status=400)

        try:
            quiz = quiz_collection.find_one({"_id": ObjectId(quiz_id)})
        except InvalidId:
            return Response({"error": "Invalid quiz_id format"}, status=400)

        if not quiz:
            return Response({"error": "Quiz not found"}, status=404)

        # 2️⃣ Calculate next question number
        q_no = quiz.get("current_question", 0) + 1

        # 3️⃣ HARD STOP after total questions
        if q_no > quiz["total_questions"]:
            return Response({"message": "Quiz completed"})

        # 4️⃣ Check if question already exists (prevents duplicates)
        existing_question = question_collection.find_one({
            "quiz_id": quiz_id,
            "question_no": q_no
        })

        if existing_question:
            return Response({
                "question_id": str(existing_question["_id"]),
                "question_no": existing_question["question_no"],
                "question": existing_question["question"],
                "options": existing_question["options"]
            })

        # 5️⃣ Generate new question using LLM
        llm_data = generate_upsc_question(
            quiz.get("exam_type", "UPSC"),
            quiz["topic"]
        )

        question = {
            "quiz_id": quiz_id,
            "question_no": q_no,
            "question": llm_data["question"],
            "options": llm_data["options"],
            "correct_answer": llm_data["correct_answer"],
            "explanation": llm_data["explanation"],
            "answered": False
        }

        q_id = question_collection.insert_one(question).inserted_id

        return Response({
            "question_id": str(q_id),
            "question_no": q_no,
            "question": question["question"],
            "options": question["options"]
        })


# =======================
# SUBMIT ANSWER
# =======================
class SubmitAnswerAPIView(APIView):
    def post(self, request):
        question_id = request.data.get("question_id")
        user_answer = request.data.get("user_answer")

        # Validate answer
        valid, error = validate_answer(user_answer)
        if not valid:
            return Response({"error": error}, status=400)

        if not question_id:
            return Response({"error": "question_id is required"}, status=400)

        try:
            question = question_collection.find_one({"_id": ObjectId(question_id)})
        except InvalidId:
            return Response({"error": "Invalid question_id format"}, status=400)

        if not question:
            return Response({"error": "Question not found"}, status=404)

        # Already answered
        if question["answered"]:
            return Response({
                "message": "Already answered",
                "user_answer": question.get("user_answer"),
                "correct_answer": question["correct_answer"],
                "is_correct": question.get("is_correct"),
                "explanation": question["explanation"]
            })

        is_correct = user_answer == question["correct_answer"]

        # Update question
        question_collection.update_one(
            {"_id": ObjectId(question_id)},
            {"$set": {
                "user_answer": user_answer,
                "is_correct": is_correct,
                "answered": True
            }}
        )

        # Update quiz stats
        quiz_collection.update_one(
            {"_id": ObjectId(question["quiz_id"])},
            {"$inc": {
                "current_question": 1,
                "correct_count": 1 if is_correct else 0
            }}
        )

        return Response({
            "is_correct": is_correct,
            "correct_answer": question["correct_answer"],
            "explanation": question["explanation"]
        })


# =======================
# FINAL SUMMARY
# =======================
class QuizSummaryAPIView(APIView):
    def get(self, request, quiz_id):

        try:
            quiz = quiz_collection.find_one({"_id": ObjectId(quiz_id)})
        except InvalidId:
            return Response({"error": "Invalid quiz_id format"}, status=400)

        if not quiz:
            return Response({"error": "Quiz not found"}, status=404)

        total = quiz["total_questions"]
        correct = quiz["correct_count"]
        wrong = total - correct
        percentage = round((correct / total) * 100, 2)

        return Response({
            "exam_type": quiz.get("exam_type", "UPSC"),
            "total_questions": total,
            "correct_questions": correct,
            "wrong_questions": wrong,
            "score": correct,
            "percentage": percentage
        })
