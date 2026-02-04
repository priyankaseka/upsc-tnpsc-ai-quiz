import re

def validate_topic(topic):
    if not topic or len(topic.strip()) < 3:
        return False, "Topic must be at least 3 characters long"

    # Must contain at least one alphabet (Tamil or English)
    if not re.search(r"[A-Za-z\u0B80-\u0BFF]", topic):
        return False, "Topic must contain valid text"

    return True, None


def validate_answer(answer):
    if not answer:
        return False, "Answer is required"

    answer = answer.upper().strip()

    if answer not in {"A", "B", "C", "D"}:
        return False, "Answer must be A, B, C or D"

    return True, None
