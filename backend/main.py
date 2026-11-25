"""Structura API. Run: uvicorn main:app --reload"""
from __future__ import annotations

import os
import re
from contextlib import asynccontextmanager
from typing import Literal

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field, ValidationError

import answer
import lesson
import planner
import revision
import tts
import video
from llm import MODEL, MODELS, LLMError, log
from structures import OpError

@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Startup check: say clearly what video export needs if something is missing."""
    tools = video.check_tools()
    if not tools["ffmpeg"] or not tools["ffprobe"]:
        log.warning("Video export unavailable. %s", video.INSTALL_HINT)
    if not tools["playwright"]:
        log.warning("Video export unavailable: Playwright is missing. Run: pip install playwright && playwright install chromium")
    yield


app = FastAPI(title="Structura", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"http://(localhost|127\.0\.0\.1)(:\d+)?",  # any local dev port
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Audio-Duration"],
)


class LessonRequest(BaseModel):
    topic: str = Field(min_length=2, max_length=200)
    level: Literal["beginner", "intermediate"] = "beginner"


class ReviseRequest(BaseModel):
    plan: dict
    scene_id: int | None = None
    instruction: str = Field(min_length=2, max_length=300)
    scenes: list[dict] | None = None  # the scenes the viewer has now: every scene but the revised one comes back unchanged


class ExportRequest(BaseModel):
    lesson: dict  # the lesson exactly as the player shows it (scenes with states and audio, plus the quiz)
    origin: str = Field(min_length=8, max_length=100)  # the frontend that serves /render (must be localhost)
    lesson_id: str | None = Field(default=None, max_length=64)
    prefetch: bool = False  # started in the background right after a lesson is shown (a Download outranks it)
    api_base: str | None = Field(default=None, max_length=200)  # how the /render page reaches this API (e.g. the site's proxy)


class TTSRequest(BaseModel):
    text: str = Field(min_length=1, max_length=2000)


class ApiError(Exception):
    """Becomes {"error": code, "message": message} with the given HTTP status."""

    def __init__(self, status: int, code: str, message: str):
        self.status, self.code, self.message = status, code, message


# HTTP status per LLM error code
LLM_STATUS = {"ai_busy": 503, "quota_exceeded": 429, "invalid_key": 502, "model_unavailable": 502, "bad_request": 502, "bad_plan": 502}


def _errors(fn):
    """Turns every known failure into a clear JSON error. No stack traces reach the client."""
    try:
        return fn()
    except LLMError as e:
        raise ApiError(LLM_STATUS.get(e.code, 502), e.code, str(e))
    except tts.TTSError as e:
        raise ApiError(500, "tts_error", str(e))
    except answer.NotAnswered as e:  # honest notice: the lesson could not be made to answer the question
        raise ApiError(422, "not_answered", str(e))
    except answer.NeedsClarification as e:  # too vague: the UI asks this one short question instead of building a lesson
        raise ApiError(422, "clarify", str(e))
    except planner.UnsupportedTopic as e:
        raise ApiError(422, "unsupported_topic", str(e))
    except (OpError, revision.RevisionError) as e:
        raise ApiError(422, "invalid_request", str(e))
    except ValidationError:
        raise ApiError(422, "invalid_request", "That lesson plan is not valid.")
    except video.ExportError as e:
        raise ApiError(500, "export_failed", str(e))


@app.exception_handler(ApiError)
async def api_error(_request: Request, exc: ApiError):
    return JSONResponse({"error": exc.code, "message": exc.message}, status_code=exc.status)


@app.exception_handler(RequestValidationError)
async def bad_input(_request: Request, exc: RequestValidationError):
    return JSONResponse({"error": "invalid_request", "message": "Please check your input and try again."}, status_code=422)


@app.exception_handler(Exception)
async def unexpected(_request: Request, exc: Exception):
    log.exception("Unhandled error: %s", type(exc).__name__)  # full trace stays in the server log
    return JSONResponse({"error": "server_error", "message": "Something went wrong on the server. Please try again."}, status_code=500)


@app.get("/health")
def health():
    return {"ok": True, "model": MODEL, "models": MODELS, "key_configured": bool(os.getenv("GEMINI_API_KEY")),
            "voice_installed": tts.VOICE.exists(), "video_export": video.check_tools()}


@app.post("/export")
def export(req: ExportRequest, request: Request):
    """Start exporting the lesson as an MP4 (or reuse the cached file). Poll GET /export/{id} for progress."""
    api_base = req.api_base if req.api_base and re.match(r"^https?://", req.api_base) else str(request.base_url).rstrip("/")
    return _errors(lambda: video.start_export(req.lesson, req.origin, req.lesson_id, api_base, prefetch=req.prefetch))


@app.post("/export/{job_id}/cancel")
def export_cancel(job_id: str):
    job = video.cancel_job(job_id)
    if not job:
        raise ApiError(404, "not_found", "That export was not found.")
    return video.public(job)


@app.get("/export/{job_id}")
def export_status(job_id: str):
    job = video.get_job(job_id)
    if not job:
        raise ApiError(404, "not_found", "That export was not found. Start it again.")
    return video.public(job)


@app.get("/export/{job_id}/lesson")
def export_lesson(job_id: str):
    """What the /render page draws."""
    data = video.job_lesson(job_id)
    if not data:
        raise ApiError(404, "not_found", "That export was not found.")
    return data


@app.get("/export/{job_id}/video")
def export_video(job_id: str):
    job = video.get_job(job_id)
    if not job or job["stage"] != "done":
        raise ApiError(404, "not_found", "The video is not ready yet.")
    return FileResponse(job["path"], media_type="video/mp4", filename=job["filename"])


@app.post("/lesson")
def create_lesson(req: LessonRequest):
    return _errors(lambda: lesson.build_lesson(req.topic, req.level))


@app.post("/revise")
def revise(req: ReviseRequest):
    return _errors(lambda: revision.revise(req.plan, req.scene_id, req.instruction, req.scenes))


@app.post("/tts")
def speak(req: TTSRequest):
    audio = _errors(lambda: tts.synthesize(req.text))
    return FileResponse(audio["path"], media_type="audio/wav",
                        headers={"X-Audio-Duration": str(audio["duration"]), "X-Audio-Url": f"/audio/{audio['id']}.wav"})


@app.get("/audio/{name}")
def audio_file(name: str):
    path = tts.AUDIO_DIR / name
    if not name.endswith(".wav") or "/" in name or "\\" in name or ".." in name or not path.exists():
        raise HTTPException(404, "audio not found")
    return FileResponse(path, media_type="audio/wav")
