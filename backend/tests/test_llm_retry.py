"""Model fallback and retry logic in llm.py, with a fake LLM client (no network, no real sleeping)."""
import json

import pytest
from fastapi.testclient import TestClient
from google.genai import errors

import llm


def server_503():
    return errors.ServerError(503, {"error": {"code": 503, "message": "The model is overloaded.", "status": "UNAVAILABLE"}})


def client_error(code, message, details=None):
    body = {"error": {"code": code, "message": message, "status": "X"}}
    if details:
        body["error"]["details"] = details
    return errors.ClientError(code, body)


class FakeClient:
    """Plays a script of outcomes, one per call: an Exception to raise, or a dict to return as JSON."""

    def __init__(self, script=None, per_model=None):
        self.script = list(script or [])
        self.per_model = per_model or {}
        self.calls: list[str] = []

    def __call__(self, model, prompt):
        self.calls.append(model)
        outcome = self.per_model[model].pop(0) if model in self.per_model else self.script.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return json.dumps(outcome)


@pytest.fixture
def env(monkeypatch, tmp_path):
    sleeps: list[float] = []
    monkeypatch.setattr(llm, "MODELS", ["model-a", "model-b"])
    monkeypatch.setattr(llm, "MODEL", "model-a")
    monkeypatch.setattr(llm, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(llm, "_sleep", sleeps.append)

    def use(fake):
        monkeypatch.setattr(llm, "_call_model", fake)
        return fake

    return use, sleeps


def test_503_twice_then_success_falls_back_to_another_model(env):
    use, sleeps = env
    fake = use(FakeClient(script=[server_503(), server_503(), {"ok": True}]))
    assert llm.generate_json("p1") == {"ok": True}
    assert fake.calls == ["model-a", "model-b", "model-a"]  # tried the second model after the first failed
    assert len(sleeps) == 1 and 1.0 <= sleeps[0] <= 1.5  # one backoff after a full pass over the list


def test_second_model_answers_when_first_is_overloaded(env):
    use, sleeps = env
    fake = use(FakeClient(per_model={"model-a": [server_503()], "model-b": [{"ok": "b"}]}))
    assert llm.generate_json("p2") == {"ok": "b"}
    assert fake.calls == ["model-a", "model-b"] and sleeps == []  # no waiting needed


def test_always_503_ends_in_ai_busy_after_the_limit(env):
    use, sleeps = env
    fake = use(FakeClient(script=[server_503() for _ in range(50)]))
    with pytest.raises(llm.LLMError) as exc:
        llm.generate_json("p3")
    assert exc.value.code == "ai_busy" and "busy" in str(exc.value)
    assert len(fake.calls) == llm.MAX_ROUNDS * 2  # every model, every pass, then stop
    assert len(sleeps) == llm.MAX_ROUNDS - 1
    assert all(b >= a for a, b in zip(sleeps, sleeps[1:])) and sleeps[-1] >= 8  # 1, 2, 4, 8 (+ jitter)
    assert all(s <= llm.MAX_WAIT_S for s in sleeps)


def test_401_fails_immediately_without_retries(env):
    use, sleeps = env
    fake = use(FakeClient(script=[client_error(401, "API key not valid")]))
    with pytest.raises(llm.LLMError) as exc:
        llm.generate_json("p4")
    assert exc.value.code == "invalid_key"
    assert fake.calls == ["model-a"] and sleeps == []
    assert "API key" in str(exc.value) and "AIza" not in str(exc.value)


def test_400_bad_request_is_not_retried(env):
    use, sleeps = env
    fake = use(FakeClient(script=[client_error(400, "Invalid argument")]))
    with pytest.raises(llm.LLMError) as exc:
        llm.generate_json("p5")
    assert exc.value.code == "bad_request" and fake.calls == ["model-a"] and sleeps == []


def test_429_retry_after_is_respected_and_capped(env):
    use, sleeps = env
    retry = [{"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": "7s"}]
    use(FakeClient(script=[client_error(429, "Quota", retry), client_error(429, "Quota", retry), {"ok": 1}]))
    assert llm.generate_json("p6") == {"ok": 1}
    assert sleeps == [7.0]  # the server's hint beats the 1s backoff
    huge = [{"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": "900s"}]
    sleeps.clear()
    use(FakeClient(script=[client_error(429, "Quota", huge), client_error(429, "Quota", huge), {"ok": 2}]))
    assert llm.generate_json("p7") == {"ok": 2} and sleeps == [llm.MAX_WAIT_S]


def test_persistent_429_is_quota_exceeded(env):
    use, _ = env
    use(FakeClient(script=[client_error(429, "Quota exceeded") for _ in range(50)]))
    with pytest.raises(llm.LLMError) as exc:
        llm.generate_json("p8")
    assert exc.value.code == "quota_exceeded"


def test_timeouts_and_network_errors_fall_back(env):
    use, _ = env
    fake = use(FakeClient(script=[TimeoutError("read timed out"), ConnectionError("reset"), {"ok": 3}]))
    assert llm.generate_json("p9") == {"ok": 3} and len(fake.calls) == 3


def test_missing_model_is_skipped(env):
    use, sleeps = env
    fake = use(FakeClient(per_model={"model-a": [client_error(404, "not found")], "model-b": [{"ok": 4}]}))
    assert llm.generate_json("p10") == {"ok": 4} and fake.calls == ["model-a", "model-b"] and sleeps == []


def test_cached_prompt_never_calls_the_api(env):
    use, _ = env
    fake = use(FakeClient(script=[{"ok": 5}]))
    assert llm.generate_json("same prompt") == {"ok": 5}
    assert llm.generate_json("same prompt") == {"ok": 5}
    assert fake.calls == ["model-a"]


def test_models_env_parsing():
    assert llm.models_from_env({"GEMINI_MODELS": " m1, m2 ,,m3 ", "GEMINI_MODEL": "x"}) == ["m1", "m2", "m3"]
    assert llm.models_from_env({"GEMINI_MODEL": "solo"}) == ["solo"]  # single-model setting still works
    assert llm.models_from_env({}) == [llm.DEFAULT_MODEL]


@pytest.mark.parametrize("code,status", [("ai_busy", 503), ("quota_exceeded", 429), ("invalid_key", 502)])
def test_api_returns_clear_json_errors(monkeypatch, code, status):
    import lesson
    import main

    def boom(*_a, **_k):
        raise llm.LLMError(llm.MESSAGES[code], code)

    monkeypatch.setattr(lesson, "build_lesson", boom)
    r = TestClient(main.app, raise_server_exceptions=False).post("/lesson", json={"topic": "how does a queue work"})
    assert r.status_code == status
    assert r.json() == {"error": code, "message": llm.MESSAGES[code]}


def test_unexpected_errors_never_leak_a_stack_trace(monkeypatch):
    import lesson
    import main

    monkeypatch.setattr(lesson, "build_lesson", lambda *_a, **_k: 1 / 0)
    r = TestClient(main.app, raise_server_exceptions=False).post("/lesson", json={"topic": "how does a queue work"})
    assert r.status_code == 500 and r.json()["error"] == "server_error" and "Traceback" not in r.text
