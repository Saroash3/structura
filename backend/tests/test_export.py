"""VIDEO EXPORT: a real MP4 (H.264 + AAC, 1280x720) built locally from the lesson the player shows.

Unit tests need nothing. The ffmpeg tests need ffmpeg + ffprobe. The end-to-end test also needs Playwright's Chromium and
the frontend running (STRUCTURA_FRONTEND, default http://localhost:3001); it is skipped, never failed, when they are missing.
"""
import os
import subprocess
import time
import wave
from pathlib import Path

import pytest

import video

HAS_FFMPEG = bool(video._find("ffmpeg") and video._find("ffprobe"))
FRONTEND = os.getenv("STRUCTURA_FRONTEND", "http://localhost:3001")
needs_ffmpeg = pytest.mark.skipif(not HAS_FFMPEG, reason="ffmpeg/ffprobe not installed")


def _scene(i, duration, speed=1.0, narration=None, audio=None):
    return {"id": i, "narration": narration or f"Scene {i}.", "duration": duration, "speed": speed, "ops": [],
            "audio_url": audio or f"/audio/{'%024x' % i}.wav", "state": {"kind": "queue", "items": []}}


def test_the_timeline_follows_scene_durations_and_speeds():
    lesson = {"topic": "t", "scenes": [_scene(1, 10), _scene(2, 6, speed=0.75), _scene(3, 4, speed=2.0)], "quiz": [{}, {}, {}]}
    assert video.scene_seconds(lesson["scenes"][1]) == pytest.approx(8.0)  # slowed down: on screen longer
    assert video.quiz_seconds(lesson["quiz"]) == 12.0 and video.quiz_seconds([]) == 0.0 and video.quiz_seconds([{}]) == 6.0
    assert video.total_seconds(lesson) == pytest.approx(10 + 8 + 2 + 12)


def test_a_revision_changes_the_cache_key_and_the_lesson_id_names_the_file():
    a = {"topic": "q", "scenes": [_scene(1, 5), _scene(2, 5)], "quiz": []}
    b = {**a, "scenes": [a["scenes"][0], {**a["scenes"][1], "narration": "Simpler words."}]}
    c = {**a, "scenes": [a["scenes"][0], {**a["scenes"][1], "speed": 0.75}]}
    assert len({video.content_hash(x) for x in (a, b, c)}) == 3
    assert video.content_hash(a) == video.content_hash({**a})
    assert video.cache_path(a, "abc123").name.startswith("abc123-")
    assert video.download_name(a) == "structura-q.mp4"


def test_atempo_handles_any_speed():
    assert video._atempo(1.0) == ""
    assert video._atempo(0.75) == "atempo=0.7500"
    assert video._atempo(4.0) == "atempo=2.0000,atempo=2.0000"


def test_only_the_local_frontend_can_be_rendered():
    with pytest.raises(video.ExportError):
        video.start_export({"scenes": [_scene(1, 5)]}, "http://example.com")
    with pytest.raises(video.ExportError):
        video.start_export({"scenes": []}, "http://localhost:3001")


# ---------------------------------------------------------------- ffmpeg
def _tone(path: Path, seconds: float, rate: int = 22050) -> None:
    import math
    import struct
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(rate)
        w.writeframes(b"".join(struct.pack("<h", int(8000 * math.sin(2 * math.pi * 440 * n / rate))) for n in range(int(seconds * rate))))


@needs_ffmpeg
def test_the_voice_track_gives_every_scene_exactly_its_time(tmp_path, monkeypatch):
    monkeypatch.setattr(video.tts, "AUDIO_DIR", tmp_path)
    for i, d in ((1, 3.0), (2, 2.0)):
        _tone(tmp_path / f"{'%024x' % i}.wav", d)
    lesson = {"topic": "t", "scenes": [_scene(1, 3.0), _scene(2, 2.0, speed=0.5)], "quiz": [{}]}
    out = tmp_path / "voice.wav"
    total = video.build_audio(lesson, out)
    assert total == pytest.approx(3.0 + 4.0 + 6.0)
    with wave.open(str(out)) as w:
        assert w.getnframes() / w.getframerate() == pytest.approx(total, abs=0.05)


@needs_ffmpeg
def test_held_frames_make_a_video_of_exactly_the_lesson_length(tmp_path, monkeypatch):
    """Keyframe capture: a few frames, each held for its duration (concat demuxer), muxed with the voice track."""
    ff = video._ffmpeg()
    frames = []
    for i, (color, d) in enumerate((("0x0D0D0D", 10.0), ("0x1E1E1E", 0.08), ("0x404040", 20.92))):
        f = tmp_path / f"f{i}.jpg"
        subprocess.run([ff, "-v", "error", "-y", "-f", "lavfi", "-i", f"color={color}:s=1280x720", "-frames:v", "1", str(f)], check=True)
        frames.append((f, d))
    monkeypatch.setattr(video.tts, "AUDIO_DIR", tmp_path)
    _tone(tmp_path / f"{'%024x' % 1}.wav", 31.0)
    lesson = {"topic": "t", "scenes": [_scene(1, 31.0)], "quiz": []}
    audio = tmp_path / "voice.wav"
    total = video.build_audio(lesson, audio)
    out = tmp_path / "out.mp4"
    video.mux_frames(frames, audio, total, out)
    info = video.check(out, total)
    assert (info["width"], info["height"]) == (1280, 720) and info["duration"] >= 30
    assert abs(info["video_duration"] - info["audio_duration"]) <= 0.5


def test_keyframes_are_split_into_contiguous_worker_ranges():
    parts = video._chunks(10, 4)
    assert [list(r) for r in parts] == [[0, 1, 2], [3, 4, 5], [6, 7], [8, 9]]
    assert video._chunks(2, 4) == [range(0, 1), range(1, 2)]


# ---------------------------------------------------------------- end to end (real render page, real Piper voice)
def _small_lesson(monkeypatch) -> dict:
    import lesson as lesson_mod
    import quiz
    monkeypatch.setattr(quiz.llm, "generate_json", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("offline")))
    plan = {"topic": "how does a queue work", "structure": "queue", "scenes": [
        {"id": 1, "ops": [], "narration": "A queue is like a line of people: newcomers join at the back and the front person leaves first."},
        {"id": 2, "ops": [{"op": "enqueue", "args": [5]}], "narration": "We enqueue 5. The front is 5 and the size is 1."},
        {"id": 3, "ops": [{"op": "enqueue", "args": [6]}], "narration": "We enqueue 6. The front is 5 and the back is 6."},
        {"id": 4, "ops": [{"op": "dequeue", "args": []}], "narration": "We dequeue 5. The front is 6 and the size is 1."},
        {"id": 5, "ops": [], "narration": "That is a queue: items leave in the same order they arrive, from the front to the back of the line."},
    ]}
    r = lesson_mod.build_from_plan(plan)
    r["quiz"] = quiz.make_quiz_from_plan(r["plan"], seed="export-test", level="beginner")
    return r


@pytest.mark.skipif(not HAS_FFMPEG, reason="ffmpeg/ffprobe not installed")
def test_export_a_small_lesson_end_to_end(monkeypatch):
    pytest.importorskip("playwright")
    if not video.frontend_up(FRONTEND):
        pytest.skip(f"frontend not running at {FRONTEND}")
    r = _small_lesson(monkeypatch)
    assert r["total_duration"] >= 30
    with video.local_api() as api:
        t0 = time.monotonic()
        job = video.export_now(r, FRONTEND, None, api)
        took = time.monotonic() - t0
    path = Path(job["path"])
    assert path.suffix == ".mp4" and path.stat().st_size > 50_000
    info = job["check"]
    kinds = {s["codec_type"]: s for s in info["ffprobe"]["streams"]}
    assert kinds["video"]["codec_name"] == "h264" and kinds["audio"]["codec_name"] == "aac"
    assert (info["width"], info["height"]) == (1280, 720)
    assert info["duration"] >= 30 and info["duration"] == pytest.approx(video.total_seconds(r), abs=0.5)
    assert abs(info["video_duration"] - info["audio_duration"]) <= 0.5
    assert took < 0.6 * info["duration"], f"export took {took:.1f} s for a {info['duration']:.1f} s video"  # no real-time capture
    with video.local_api() as api:  # the same lesson again: served from the cache, instantly
        again = video.export_now(r, FRONTEND, None, api)
    assert again["cached"] and again["path"] == job["path"]
