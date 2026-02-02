def validate_topic(topic):
    if not topic or len(topic.strip()) < 3:
        return False, "Topic must be at least 3 characters"
    return True, None


def validate_answer(answer):
    if answer not in ["A", "B", "C", "D"]:
        return False, "Answer must be A, B, C or D"
    return True, None
