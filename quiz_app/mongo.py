from pymongo import MongoClient

client = MongoClient("mongodb://localhost:27017/")
db = client["upsc_quiz_db"]

quiz_collection = db["quizzes"]

summary_collection = db["quiz_summary"]
