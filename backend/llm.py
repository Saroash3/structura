"""The ONLY place that talks to an LLM. Swap providers by editing `_call_model` and `classify`.

Reliability:
- Models are tried in order from GEMINI_MODELS (comma-separated), or GEMINI_MODEL if that is unset.
- Transient failures (503 overloaded, 5xx, 429 rate limit, timeouts, network errors) move on to the next
  model. After a full pass over the list we back off (about 1s, 2s, 4s, 8s plus jitter, or the server's
  retry-after hint, capped) and go through the list again, up to MAX_ROUNDS passes.
- Permanent failures (400 bad request, 401/403 invalid key) fail immediately without retrying.
- Every call has a timeout, so one hung request never freezes the app.
- A semaphore caps concurrent Gemini calls; within a lesson, calls are already strictly sequential.
- Responses are cached on disk by prompt hash (unchanged), so a cached prompt never calls the API.
The API key is never logged or included in error messages.
"""
from __future__ import annotations

import contextlib
import contextvars
import hashlib
import json
import logging
import os
import random
import re
import threading
import time
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

CACHE_DIR = Path(__file__).parent / "cache" / "llm"
DEFAULT_MODEL = "gemini-3.5-flash-lite"


def models_from_env(env=os.environ) -> list[str]:
    """GEMINI_MODELS (comma-separated, in order of preference), else GEMINI_MODEL, else the default."""
    listed = [m.strip() for m in env.get("GEMINI_MODELS", "").split(",") if m.strip()]
    return listed or [env.get("GEMINI_MODEL", "").strip() or DEFAULT_MODEL]


MODELS: list[str] = models_from_env()
MODEL = MODELS[0]  # primary model; also part of the cache key, exactly as before

MAX_ROUNDS = 5  # full passes over the model list
TIMEOUT_S = 45  # per call
BACKOFF_BASE_S = 1.0  # 1, 2, 4, 8 ... between passes
MAX_WAIT_S = 30.0  # cap for backoff and for a server's retry-after hint

log = logging.getLogger("uvicorn.error")  # shows up in the uvicorn console
_sleep = time.sleep  # replaced in tests
_client = None
_slots = threading.BoundedSemaphore(2)  # at most 2 Gemini calls in flight across the whole server


class LLMError(RuntimeError):
    """User-safe error. `code` is one of: ai_busy, quota_exceeded, invalid_key, bad_request,
    model_unavailable, bad_plan, llm_error. Messages never contain the API key."""

    def __init__(self, message: str, code: str = "llm_error"):
        super().__init__(message)
        self.code = code


MESSAGES = {
    "ai_busy": "The AI is busy, please try again in a moment.",
    "quota_exceeded": "The free AI quota is used up for now. Please try again in a few minutes.",
    "invalid_key": "The AI service rejected the API key. Check GEMINI_API_KEY in backend/.env.",
    "bad_request": "The AI could not process this request.",
    "model_unavailable": "None of the configured Gemini models are available. Check GEMINI_MODELS in backend/.env.",
}


def _get_client():
    global _client
    if _client is None:
        key = os.getenv("GEMINI_API_KEY")
        if not key:
            raise LLMError("GEMINI_API_KEY is not set. Add it to backend/.env.", "invalid_key")
        from google import genai
        from google.genai import types

        _client = genai.Client(api_key=key, http_options=types.HttpOptions(timeout=TIMEOUT_S * 1000))
    return _client


_temperature: contextvars.ContextVar[float] = contextvars.ContextVar("temperature", default=0.4)


@contextlib.contextmanager
def temperature(value: float):
    """`with llm.temperature(0): llm.generate_json(...)`: e.g. the answer judge runs at temperature 0."""
    token = _temperature.set(value)
    try:
        yield
    finally:
        _temperature.reset(token)


def _call_model(model: str, prompt: str) -> str:
    """One raw request to one model. Returns the response text."""
    from google.genai import types

    config = types.GenerateContentConfig(response_mime_type="application/json", temperature=_temperature.get())
    resp = _get_client().models.generate_content(model=model, contents=prompt, config=config)
    return resp.text


# ---------------------------------------------------------------- error classification
RETRY_DELAY_RE = re.compile(r"retry[_ ]?delay['\"]?\s*[:=]\s*['\"]?(\d+(?:\.\d+)?)s", re.I)
RETRY_IN_RE = re.compile(r"retry in (\d+(?:\.\d+)?)\s*s", re.I)


def _retry_after(exc: Exception) -> float | None:
    """Seconds the server asked us to wait (Retry-After header or Gemini's RetryInfo), if any."""
    resp = getattr(exc, "response", None)
    headers = getattr(resp, "headers", None)
    if headers is not None:
        try:
            value = headers.get("retry-after")
            if value:
                return float(value)
        except (TypeError, ValueError):
            pass
    text = str(getattr(exc, "details", "")) + " " + str(exc)
    m = RETRY_DELAY_RE.search(text) or RETRY_IN_RE.search(text)
    return float(m.group(1)) if m else None


def classify(exc: Exception) -> tuple[str, float | None]:
    """-> (kind, retry_after). kind: transient | rate_limited | invalid_key | bad_request | model_missing | bad_json."""
    if isinstance(exc, json.JSONDecodeError):
        return "bad_json", None
    code = getattr(exc, "code", None)
    if isinstance(code, int):
        text = str(exc)
        if code in (401, 403) or (code == 400 and re.search(r"api[ _]?key", text, re.I)):
            return "invalid_key", None
        if code == 429:
            return "rate_limited", _retry_after(exc)
        if code == 404:
            return "model_missing", None
        if code in (408, 500, 502, 503, 504):
            return "transient", _retry_after(exc)
        if 400 <= code < 500:
            return "bad_request", None
        return "transient", None
    name = type(exc).__name__.lower()
    if isinstance(exc, (TimeoutError, ConnectionError, OSError)) or "timeout" in name or "connect" in name or "network" in name or "transport" in name:
        return "transient", None
    return "transient", None  # unknown failures are treated as transient, but still bounded by MAX_ROUNDS


# ---------------------------------------------------------------- the call
def _cache_file(full_prompt: str) -> Path:
    t = _temperature.get()  # the default temperature keeps the old cache keys
    key = hashlib.sha256((f"{MODEL}\n{full_prompt}" + (f"\nT={t}" if t != 0.4 else "")).encode()).hexdigest()
    return CACHE_DIR / f"{key}.json"


def generate_json(prompt: str, schema: dict | None = None) -> dict:
    """Send a prompt, get parsed JSON back, with model fallback and bounded retries."""
    full_prompt = prompt
    if schema:
        full_prompt += "\n\nRespond with JSON only, matching this JSON schema:\n" + json.dumps(schema)

    cache_file = _cache_file(full_prompt)
    if cache_file.exists():
        return json.loads(cache_file.read_text(encoding="utf-8"))

    data = _generate_with_fallback(full_prompt)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_file.write_text(json.dumps(data), encoding="utf-8")
    return data


def _generate_with_fallback(full_prompt: str) -> dict:
    models = list(MODELS)
    missing: set[str] = set()
    attempts = 0
    last_kind = "transient"
    for round_no in range(MAX_ROUNDS):
        hint: float | None = None
        for model in models:
            if model in missing:
                continue
            attempts += 1
            try:
                with _slots:
                    text = _call_model(model, full_prompt)
                data = json.loads(text)
                log.info("LLM: %s answered after %d attempt(s)", model, attempts)
                return data
            except LLMError:
                raise
            except Exception as exc:  # classified below; nothing that could contain the key is logged
                kind, retry_after = classify(exc)
                code = getattr(exc, "code", type(exc).__name__)
                log.warning("LLM: %s failed (%s, %s), attempt %d", model, kind, code, attempts)
                if kind == "invalid_key":
                    raise LLMError(MESSAGES["invalid_key"], "invalid_key") from None
                if kind == "bad_request":
                    raise LLMError(MESSAGES["bad_request"], "bad_request") from None
                if kind == "model_missing":
                    missing.add(model)
                    continue
                last_kind = kind
                if retry_after:
                    hint = max(hint or 0.0, retry_after)
        if len(missing) == len(models):
            raise LLMError(MESSAGES["model_unavailable"], "model_unavailable")
        if round_no < MAX_ROUNDS - 1:
            backoff = BACKOFF_BASE_S * (2**round_no) + random.uniform(0, 0.5 * BACKOFF_BASE_S * (2**round_no))
            wait = min(max(backoff, hint or 0.0), MAX_WAIT_S)
            log.info("LLM: all models busy, waiting %.1fs before pass %d of %d", wait, round_no + 2, MAX_ROUNDS)
            _sleep(wait)
    if last_kind == "rate_limited":
        raise LLMError(MESSAGES["quota_exceeded"], "quota_exceeded")
    raise LLMError(MESSAGES["ai_busy"], "ai_busy")
