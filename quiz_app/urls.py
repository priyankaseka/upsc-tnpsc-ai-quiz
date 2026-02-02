from django.urls import path
from .views import *

urlpatterns = [
    path("start-quiz/", StartQuizAPIView.as_view()),
    path("generate-question/", GenerateQuestionAPIView.as_view()),
    path("submit-answer/", SubmitAnswerAPIView.as_view()),
    path("quiz-summary/<str:quiz_id>/", QuizSummaryAPIView.as_view()),
]
