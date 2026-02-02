from pymongo import MongoClient

client = MongoClient("mongodb://localhost:27017/")
db = client["upsc_quiz_db"]

quiz_collection = db["quiz_sessions"]
question_collection = db["quiz_questions"]
