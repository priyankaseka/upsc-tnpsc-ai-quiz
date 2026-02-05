import re

EN_VOWELS = set("aeiou")
TA_VOWELS = set("அஆஇஈஉஊஎஏஐஒஓஔ")


def is_meaningful_word(word: str) -> bool:
    word = word.strip().lower()

    if re.fullmatch(r"[a-z]+", word):
        return len(word) >= 4 and any(ch in EN_VOWELS for ch in word)

    if re.search(r"[\u0B80-\u0BFF]", word):
        return len(word) >= 4 and any(ch in TA_VOWELS for ch in word)

    return False


def validate_topic(topic):
    if not topic:
        return False, "Topic is required"

    topic = topic.strip()

    words = re.findall(r"[A-Za-z\u0B80-\u0BFF]+", topic)

    meaningful_words = [w for w in words if is_meaningful_word(w)]

    if len(meaningful_words) >= 2:
        return True, None

    for w in meaningful_words:
        if len(w) >= 6:
            return True, None

    return False, "Topic is not a valid exam subject"


def validate_answer(answer):
    if not answer:
        return False, "Answer is required"

    answer = answer.upper().strip()
    if answer not in {"A", "B", "C", "D"}:
        return False, "Answer must be A, B, C or D"

    return True, None
