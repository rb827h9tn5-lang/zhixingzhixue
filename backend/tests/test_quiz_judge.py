from app.services import quiz_judge


class FakeMimoClient:
    enabled = True

    def __init__(self, **_kwargs):
        pass

    def complete(self, _system, user, **_kwargs):
        if "不会" in user:
            raise RuntimeError("gateway unavailable")
        return '```json\n{"score": 0.5}\n```'


def test_open_answers_are_judged_in_parallel_and_failures_fall_back(monkeypatch):
    monkeypatch.setattr(quiz_judge, "MimoChatClient", FakeMimoClient)
    quiz = {
        "questions": [
            {"id": 1, "type": "fill_blank", "answer": "监督学习"},
            {"id": 2, "type": "short_answer", "answer": "训练集用于拟合参数"},
            {"id": 3, "type": "single_choice", "answer": "A"},
        ]
    }
    scores = quiz_judge.judge_open_answers(
        quiz,
        {"1": "机器学习的一类", "2": "不会", "3": "A"},
        model="mimo-v2.5",
        timeout=2,
    )
    assert scores == {"1": 0.5}

