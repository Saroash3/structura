"""EXPORT A LESSON AS AN MP4 (local only: headless Chromium + ffmpeg, no external video APIs).

How it works
  1. The lesson the player shows (scenes with their true states, narration, Piper audio, speeds, and the quiz) is stored
     under a job id.
  2. Headless Chromium (Playwright) opens the frontend's /render page for that job at 1280x720. The page is a pure
     function of the video time: it draws exactly what the player draws (the same Stage components and the same frameAt()
     timing), and lists its KEYFRAMES (every moment the picture changes: a new scene, each step, the quiz slide).
     Nothing is captured in real time: for each keyframe the page jumps there, one frame is captured for the still, plus
     ~12 fps only during the short animation that follows (MOTION_WINDOW). Up to 4 pages (WORKERS) capture contiguous
     ranges of keyframes in parallel. A narration that holds a still picture for 8 seconds costs a single frame.
  3. The scene WAVs are joined into one track where every scene lasts exactly duration / speed (time-stretched for a
     revised speed, padded with silence), then silence for the quiz slide.
  4. ffmpeg's concat demuxer holds every captured frame for exactly its duration (to the next capture), and the frames
     are muxed with the track into H.264 + AAC (yuv420p, -preset veryfast), so it plays in any video player. ffprobe
     checks the result: video and audio streams, 1280x720, durations within 0.5 s.
Exports start in the background as soon as a lesson is shown (prefetch), so Download is usually instant; a Download
for the same lesson joins the running job, and every job can be cancelled.
Videos are cached by lesson id + a hash of everything that is drawn or spoken, so a repeat download is instant and a
revised lesson (new narration or speed, so a new hash) is exported again automatically.
"""
from __future__ import annotations

import glob
import hashlib
import json
import logging
import os
import re
import shutil
import subprocess
import tempfile
import threading
import time
import uuid
from pathlib import Path

import tts

log = logging.getLogger("structura.video")
BASE = Path(__file__).parent
CACHE_DIR = BASE / "video_cache"
WIDTH, HEIGHT, FPS = 1280, 720, 25
RENDER_VERSION = "2"  # bump when the render page's look changes, so cached videos are rebuilt
WORKERS = 4  # pages capturing in parallel
MOTION_WINDOW = 0.55  # seconds of animation after each keyframe that are captured frame by frame
MOTION_FPS = 12
QUIZ_SECONDS_PER_QUESTION, QUIZ_MIN_SECONDS = 4.0, 6.0
MAX_DIFF = 0.5  # seconds: video vs audio vs expected duration
LOCAL_ORIGIN = re.compile(r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$")


def allowed_origin(origin: str) -> bool:
    """The local frontend, or a deployed one listed in FRONTEND_ORIGINS (comma-separated, e.g. the Vercel site)."""
    extra = {o.strip().rstrip("/") for o in os.getenv("FRONTEND_ORIGINS", "").split(",") if o.strip()}
    return bool(LOCAL_ORIGIN.match(origin or "")) or (origin or "").rstrip("/") in extra


class ExportError(RuntimeError):
    pass


# ---------------------------------------------------------------- tools
def _find(name: str) -> str | None:
    """ffmpeg / ffprobe: $FFMPEG_DIR, then PATH, then a winget install (a fresh install is not on an old process's PATH)."""
    exe = name + (".exe" if os.name == "nt" else "")
    if os.getenv("FFMPEG_DIR") and (Path(os.environ["FFMPEG_DIR"]) / exe).exists():
        return str(Path(os.environ["FFMPEG_DIR"]) / exe)
    found = shutil.which(name)
    if found:
        return found
    if os.name == "nt" and os.getenv("LOCALAPPDATA"):
        hits = glob.glob(os.path.join(os.environ["LOCALAPPDATA"], "Microsoft", "WinGet", "Packages", "*FFmpeg*", "*", "bin", exe))
        if hits:
            return sorted(hits)[-1]
    return None


INSTALL_HINT = ("ffmpeg is not installed. Install it, then restart the backend: "
                "Windows: winget install Gyan.FFmpeg   macOS: brew install ffmpeg   Linux: sudo apt install ffmpeg")


def check_tools() -> dict:
    """What the export needs, for /health and the startup check."""
    ffmpeg, ffprobe = _find("ffmpeg"), _find("ffprobe")
    try:
        import playwright  # noqa: F401
        pw = True
    except ImportError:
        pw = False
    return {"ffmpeg": bool(ffmpeg), "ffprobe": bool(ffprobe), "playwright": pw}


def _run(args: list[str], timeout: float = 600) -> subprocess.CompletedProcess:
    return subprocess.run(args, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout)


def _ffmpeg() -> str:
    path = _find("ffmpeg")
    if not path:
        raise ExportError(INSTALL_HINT)
    return path


# ---------------------------------------------------------------- the timeline (shared with the render page)
def scene_seconds(scene: dict) -> float:
    """How long a scene is on screen: its audio duration at its own speed (the player plays it at playbackRate = speed)."""
    return float(scene["duration"]) / float(scene.get("speed") or 1.0)


def quiz_seconds(quiz: list[dict] | None) -> float:
    return max(QUIZ_MIN_SECONDS, QUIZ_SECONDS_PER_QUESTION * len(quiz or [])) if quiz else 0.0


def total_seconds(lesson: dict) -> float:
    return round(sum(scene_seconds(s) for s in lesson["scenes"]) + quiz_seconds(lesson.get("quiz")), 3)


def content_hash(lesson: dict) -> str:
    """Everything that is drawn or spoken. A revision changes narration, audio or speed, so it changes the hash."""
    keep = {"topic": lesson.get("topic"), "v": RENDER_VERSION,
            "scenes": [{k: s.get(k) for k in ("narration", "audio_url", "duration", "speed", "ops", "before", "steps", "state",
                                              "analogy", "named", "role")} for s in lesson["scenes"]],
            "quiz": [{k: q.get(k) for k in ("question", "options", "answer_index")} for q in lesson.get("quiz") or []]}
    return hashlib.sha256(json.dumps(keep, sort_keys=True, default=str).encode()).hexdigest()[:16]


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (text or "lesson").lower()).strip("-")[:50] or "lesson"


def cache_path(lesson: dict, lesson_id: str | None) -> Path:
    owner = re.sub(r"[^A-Za-z0-9]", "", lesson_id or "")[:24] or "lesson"
    return CACHE_DIR / f"{owner}-{content_hash(lesson)}.mp4"


def download_name(lesson: dict) -> str:
    return f"structura-{_slug(lesson.get('topic', 'lesson'))}.mp4"


# ---------------------------------------------------------------- audio track
def _wav_for(scene: dict) -> Path:
    m = re.search(r"([0-9a-f]{8,64})\.wav$", scene.get("audio_url") or "")
    if m:
        path = tts.AUDIO_DIR / f"{m.group(1)}.wav"
        if path.exists():
            return path
    return Path(tts.synthesize(_spoken(scene["narration"]))["path"])  # audio cache was cleared: voice it again (same text)


def _spoken(text: str) -> str:
    import lesson as lesson_mod
    return lesson_mod.spoken(text)


def _atempo(speed: float) -> str:
    """atempo accepts 0.5..2 per filter; chain filters for anything outside."""
    parts, s = [], speed
    while s > 2.0:
        parts.append("atempo=2.0000"); s /= 2.0
    while s < 0.5:
        parts.append("atempo=0.5000"); s /= 0.5
    if abs(s - 1.0) > 1e-3:
        parts.append(f"atempo={s:.4f}")
    return ",".join(parts)


def audio_filter(lesson: dict) -> tuple[list[Path], str, float]:
    """(input wavs, filter_complex, total seconds). Each scene is cut or padded to exactly scene_seconds(), so the voice
    starts every scene on the same frame the picture does; the quiz slide is silence."""
    scenes = lesson["scenes"]
    inputs = [_wav_for(s) for s in scenes]
    chains = []
    for i, s in enumerate(scenes):
        d = scene_seconds(s)
        tempo = _atempo(float(s.get("speed") or 1.0))
        chains.append(f"[{i}:a]aresample=22050,aformat=channel_layouts=mono{',' + tempo if tempo else ''},"
                      f"apad=whole_dur={d:.3f},atrim=0:{d:.3f},asetpts=N/SR/TB[a{i}]")
    total = total_seconds(lesson)
    joined = "".join(f"[a{i}]" for i in range(len(scenes)))
    chains.append(f"{joined}concat=n={len(scenes)}:v=0:a=1,apad=whole_dur={total:.3f},atrim=0:{total:.3f}[aout]")
    return inputs, ";".join(chains), total


def build_audio(lesson: dict, out: Path) -> float:
    inputs, graph, total = audio_filter(lesson)
    args = [_ffmpeg(), "-y", "-hide_banner", "-loglevel", "error"]
    for p in inputs:
        args += ["-i", str(p)]
    args += ["-filter_complex", graph, "-map", "[aout]", "-c:a", "pcm_s16le", str(out)]
    r = _run(args)
    if r.returncode or not out.exists():
        raise ExportError("Could not build the voice track: " + r.stderr.strip()[-300:])
    return total


# ---------------------------------------------------------------- recording
class Cancelled(Exception):
    pass


def _chunks(n: int, k: int) -> list[range]:
    """k contiguous, nearly equal ranges of n keyframes."""
    k = max(1, min(k, n))
    size, extra = divmod(n, k)
    out, i = [], 0
    for w in range(k):
        j = i + size + (1 if w < extra else 0)
        out.append(range(i, j))
        i = j
    return out


async def _capture_range(browser, url: str, keys: list[dict], rng: range, total: float, workdir: Path, tag: str,
                         tick, cancelled) -> list[tuple[Path, float]]:
    """One page captures the keyframes in `rng`: a jump to the first (final layout), then each later keyframe animated
    from the previous one, exactly as the player shows it. Returns [(frame, seconds it is shown)]."""
    ctx = await browser.new_context(viewport={"width": WIDTH, "height": HEIGHT}, device_scale_factor=1)
    page = await ctx.new_page()
    try:
        await page.goto(url, wait_until="networkidle", timeout=60_000)
        await page.add_style_tag(content="nextjs-portal, [data-nextjs-toast], [data-next-badge-root] { display: none !important; }")
        await page.wait_for_function("window.__renderReady === true || !!window.__renderError", timeout=60_000)
        err = await page.evaluate("window.__renderError || null")
        if err:
            raise ExportError(f"The render page failed: {err}")
        frames: list[tuple[Path, float]] = []
        n = 0
        for j in rng:
            if cancelled():
                raise Cancelled()
            k = keys[j]
            nxt = keys[j + 1]["at"] if j + 1 < len(keys) else total
            span = max(0.0, nxt - k["at"])
            animate = j != rng.start and k.get("motion", True)
            await page.evaluate("([t, a]) => window.__renderGoto(t, a)", [k["at"], animate])
            t0 = time.monotonic()
            shots: list[tuple[float, bytes]] = []
            window = min(MOTION_WINDOW, span - 0.04) if animate else 0.0
            while True:
                off = time.monotonic() - t0
                shots.append((off, await page.screenshot(type="jpeg", quality=88)))
                if not animate or off >= window:
                    break
                wait = (len(shots) / MOTION_FPS) - (time.monotonic() - t0)
                if wait > 0:
                    await page.wait_for_timeout(wait * 1000)
            if animate and shots[-1][0] < window:  # make sure the settled picture is the one held
                shots.append((window, await page.screenshot(type="jpeg", quality=88)))
            offs = [min(o, span) for o, _ in shots]
            offs[0] = 0.0
            for i, (o, data) in enumerate(shots):
                d = (offs[i + 1] if i + 1 < len(shots) else span) - offs[i]
                if d <= 0.001:
                    continue
                f = workdir / f"{tag}_{n:05d}.jpg"
                f.write_bytes(data)
                frames.append((f, d))
                n += 1
            tick()
        return frames
    finally:
        await ctx.close()


def capture(render_url: str, workdir: Path, progress=lambda f: None, cancelled=lambda: False) -> tuple[list[tuple[Path, float]], float, int]:
    """Capture the lesson as held frames, WORKERS pages in parallel. Returns (frames in order, total seconds, keyframes)."""
    try:
        from playwright.async_api import async_playwright
    except ImportError as e:
        raise ExportError("Playwright is not installed. Run: pip install playwright && playwright install chromium") from e
    import asyncio

    async def run():
        async with async_playwright() as p:
            try:
                browser = await p.chromium.launch(args=["--mute-audio"])
            except Exception as e:  # browser binary missing
                raise ExportError("Chromium for Playwright is missing. Run: playwright install chromium") from e
            try:
                probe = await browser.new_page(viewport={"width": WIDTH, "height": HEIGHT})
                await probe.goto(render_url, wait_until="networkidle", timeout=60_000)
                try:
                    await probe.wait_for_function("window.__renderReady === true || !!window.__renderError", timeout=60_000)
                except Exception as e:
                    raise ExportError("The render page did not load the lesson. Is the frontend running?") from e
                err = await probe.evaluate("window.__renderError || null")
                if err:
                    raise ExportError(f"The render page failed: {err}")
                plan = await probe.evaluate("window.__renderPlan()")
                await probe.close()
                keys, total = plan["keyframes"], float(plan["total"])
                done = [0]

                def tick():
                    done[0] += 1
                    progress(done[0] / max(1, len(keys)))
                parts = await asyncio.gather(*(_capture_range(browser, render_url, keys, r, total, workdir, f"w{w}", tick, cancelled)
                                               for w, r in enumerate(_chunks(len(keys), WORKERS))))
                return [f for part in parts for f in part], total, len(keys)
            finally:
                await browser.close()

    return asyncio.run(run())


def mux_frames(frames: list[tuple[Path, float]], audio: Path, total: float, out: Path) -> None:
    """Hold every frame for its duration (concat demuxer) and mux with the voice track into H.264 + AAC."""
    if not frames:
        raise ExportError("No frames were captured.")
    lst = out.with_suffix(".frames.txt")
    lines = ["ffconcat version 1.0"]
    for f, d in frames:
        lines += [f"file '{f.as_posix()}'", f"duration {d:.4f}"]
    lines.append(f"file '{frames[-1][0].as_posix()}'")  # the concat demuxer needs the last file again
    lst.write_text("\n".join(lines) + "\n", encoding="utf-8")
    tmp = out.with_suffix(".part.mp4")
    args = [_ffmpeg(), "-y", "-hide_banner", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(lst), "-i", str(audio),
            "-vf", f"fps={FPS},scale={WIDTH}:{HEIGHT}:flags=lanczos:in_range=full:out_range=tv,setsar=1,"
                   f"tpad=stop_mode=clone:stop_duration=1,format=yuv420p",
            "-map", "0:v", "-map", "1:a", "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "128k", "-t", f"{total:.3f}", "-movflags", "+faststart", str(tmp)]
    r = _run(args)
    lst.unlink(missing_ok=True)
    if r.returncode or not tmp.exists():
        raise ExportError("ffmpeg could not encode the video: " + r.stderr.strip()[-300:])
    tmp.replace(out)


# ---------------------------------------------------------------- checks
def probe(path: Path) -> dict:
    ffprobe = _find("ffprobe")
    if not ffprobe:
        raise ExportError("ffprobe is missing (it ships with ffmpeg). " + INSTALL_HINT)
    r = _run([ffprobe, "-v", "error", "-show_entries", "format=duration,size,format_name:stream=index,codec_type,codec_name,width,height,"
              "pix_fmt,duration,avg_frame_rate,sample_rate,channels", "-of", "json", str(path)])
    if r.returncode:
        raise ExportError("ffprobe could not read the video: " + r.stderr.strip()[-200:])
    return json.loads(r.stdout)


def check(path: Path, expected: float) -> dict:
    """Video + audio streams, 1280x720 H.264 yuv420p, AAC, and video / audio / expected durations within MAX_DIFF."""
    info = probe(path)
    v = next((s for s in info["streams"] if s["codec_type"] == "video"), None)
    a = next((s for s in info["streams"] if s["codec_type"] == "audio"), None)
    problems = []
    if not v:
        problems.append("no video stream")
    if not a:
        problems.append("no audio stream")
    if v and (int(v["width"]), int(v["height"])) != (WIDTH, HEIGHT):
        problems.append(f"resolution {v['width']}x{v['height']}")
    if v and (v.get("codec_name") != "h264" or v.get("pix_fmt") != "yuv420p"):
        problems.append(f"video codec {v.get('codec_name')}/{v.get('pix_fmt')}")
    dur = float(info["format"]["duration"])
    vd = float(v.get("duration", dur)) if v else 0.0
    ad = float(a.get("duration", dur)) if a else 0.0
    if abs(vd - ad) > MAX_DIFF or abs(dur - expected) > MAX_DIFF:
        problems.append(f"durations video {vd:.2f} s, audio {ad:.2f} s, expected {expected:.2f} s")
    if problems:
        raise ExportError("The exported video failed its checks: " + "; ".join(problems))
    return {"duration": round(dur, 3), "video_duration": round(vd, 3), "audio_duration": round(ad, 3),
            "width": int(v["width"]), "height": int(v["height"]), "size": int(info["format"]["size"]), "ffprobe": info}


class local_api:
    """`with video.local_api() as base:` serves this process's API (and so its export jobs) on a free localhost port, for
    scripts and tests that export without the uvicorn server: the render page fetches the lesson from it."""

    def __enter__(self) -> str:
        import socket

        import uvicorn

        import main
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            port = s.getsockname()[1]
        self.server = uvicorn.Server(uvicorn.Config(main.app, host="127.0.0.1", port=port, log_level="warning"))
        self.thread = threading.Thread(target=self.server.run, daemon=True)
        self.thread.start()
        for _ in range(100):
            if self.server.started:
                break
            time.sleep(0.05)
        return f"http://127.0.0.1:{port}"

    def __exit__(self, *exc) -> None:
        self.server.should_exit = True
        self.thread.join(timeout=5)


def frontend_up(origin: str) -> bool:
    import urllib.request
    try:
        with urllib.request.urlopen(origin.rstrip("/") + "/render?job=ping", timeout=5) as r:
            return r.status == 200
    except Exception:
        return False


# ---------------------------------------------------------------- jobs
_jobs: dict[str, dict] = {}
_jobs_lock = threading.Lock()
_one_at_a_time = threading.Semaphore(1)  # one headless browser + one encoder at a time on a laptop


def _set(job_id: str, **fields) -> None:
    with _jobs_lock:
        _jobs[job_id].update(fields)


def get_job(job_id: str) -> dict | None:
    with _jobs_lock:
        job = _jobs.get(job_id)
        return dict(job) if job else None


def job_lesson(job_id: str) -> dict | None:
    """The lesson the render page draws (only what it needs)."""
    job = get_job(job_id)
    if not job:
        return None
    l = job["lesson"]
    return {"topic": l.get("topic"), "structure": l.get("structure"), "analysis": l.get("analysis"),
            "scenes": l["scenes"], "quiz": l.get("quiz") or [], "quiz_seconds": quiz_seconds(l.get("quiz")),
            "total": total_seconds(l)}


def public(job: dict) -> dict:
    return {k: job.get(k) for k in ("id", "stage", "progress", "message", "cached", "duration", "size", "width", "height", "filename",
                                    "prefetch", "seconds")}


ACTIVE = ("queued", "rendering", "voicing")


def cancel_job(job_id: str) -> dict | None:
    """Stop an export: the worker checks between keyframes. A finished video stays cached."""
    with _jobs_lock:
        job = _jobs.get(job_id)
        if not job:
            return None
        if job["stage"] in ACTIVE:
            job["cancel"] = True
            if job["stage"] == "queued":
                job.update(stage="cancelled", message="Cancelled")
        return dict(job)


def start_export(lesson: dict, origin: str, lesson_id: str | None = None, api_base: str = "http://localhost:8000",
                 prefetch: bool = False) -> dict:
    """Start (or reuse) an export. Returns the public job."""
    if not lesson.get("scenes"):
        raise ExportError("This lesson has no scenes to export.")
    if not allowed_origin(origin):
        raise ExportError("Video export only renders from the local frontend or a site listed in FRONTEND_ORIGINS.")
    out = cache_path(lesson, lesson_id)
    with _jobs_lock:
        running = next((j for j in _jobs.values() if j["path"] == str(out) and j["stage"] in ACTIVE and not j.get("cancel")), None)
        if running:  # the same lesson (often its background prefetch) is already being exported: join it
            if not prefetch:
                running["prefetch"] = False
            return public(running)
        if not prefetch:  # a Download outranks other lessons' background prefetches
            for j in _jobs.values():
                if j.get("prefetch") and j["stage"] in ACTIVE and j["path"] != str(out):
                    j["cancel"] = True
    job_id = uuid.uuid4().hex[:16]
    job = {"id": job_id, "lesson": lesson, "origin": origin.rstrip("/"), "api": api_base.rstrip("/"), "path": str(out),
           "filename": download_name(lesson), "stage": "queued", "progress": 0.0, "message": "Waiting to start", "cached": False,
           "prefetch": prefetch}
    with _jobs_lock:
        _jobs[job_id] = job
    if out.exists():
        try:
            info = check(out, total_seconds(lesson))
            _set(job_id, stage="done", progress=1.0, message="Ready (cached)", cached=True,
                 **{k: info[k] for k in ("duration", "size", "width", "height")})
            return public(get_job(job_id))
        except ExportError:
            out.unlink(missing_ok=True)  # a broken cache file is rebuilt
    threading.Thread(target=_work, args=(job_id,), daemon=True, name=f"export-{job_id}").start()
    return public(get_job(job_id))


def export_now(lesson: dict, origin: str, lesson_id: str | None = None, api_base: str = "http://localhost:8000",
               on_progress=None) -> dict:
    """Synchronous export (used by tests and the eval). Returns the finished job, including the ffprobe check."""
    job = start_export(lesson, origin, lesson_id, api_base)
    while True:
        j = get_job(job["id"])
        if on_progress:
            on_progress(public(j))
        if j["stage"] in ("done", "error", "cancelled"):
            break
        time.sleep(0.25)
    if j["stage"] != "done":
        raise ExportError(j["message"])
    return {**public(j), "path": j["path"], "check": check(Path(j["path"]), total_seconds(lesson))}


def _work(job_id: str) -> None:
    with _one_at_a_time:
        job = get_job(job_id)
        lesson, out = job["lesson"], Path(job["path"])
        cancelled = lambda: bool((get_job(job_id) or {}).get("cancel"))
        t_start = time.monotonic()
        try:
            if cancelled():
                raise Cancelled()
            if not _find("ffmpeg"):
                raise ExportError(INSTALL_HINT)
            CACHE_DIR.mkdir(exist_ok=True)
            with tempfile.TemporaryDirectory(prefix="structura-export-") as tmp:
                work = Path(tmp)
                _set(job_id, stage="rendering", progress=0.0, message="Rendering the animation")
                url = f"{job['origin']}/render?job={job_id}&api={job['api']}"
                frames, total, nkeys = capture(url, work, progress=lambda f: _set(job_id, progress=round(0.8 * f, 3)), cancelled=cancelled)
                _set(job_id, stage="voicing", progress=0.82, message="Adding the voice")
                audio = work / "voice.wav"
                total_audio = build_audio(lesson, audio)
                if abs(total_audio - total) > MAX_DIFF:
                    raise ExportError(f"The picture ({total:.1f} s) and the voice ({total_audio:.1f} s) do not line up.")
                if cancelled():
                    raise Cancelled()
                _set(job_id, progress=0.9, message="Encoding the MP4")
                mux_frames(frames, audio, total_audio, out)
                info = check(out, total_audio)
            secs = round(time.monotonic() - t_start, 1)
            _set(job_id, stage="done", progress=1.0, message="Ready", seconds=secs, **{k: info[k] for k in ("duration", "size", "width", "height")})
            log.info("export %s done in %.1f s: %s (%.1f s video, %d keyframes, %d frames, %d bytes)", job_id, secs, out.name,
                     info["duration"], nkeys, len(frames), info["size"])
        except Cancelled:
            _set(job_id, stage="cancelled", message="Cancelled")
        except ExportError as e:
            log.warning("export %s failed: %s", job_id, e)
            _set(job_id, stage="error", message=str(e))
        except Exception as e:  # never leave a job "rendering" forever
            log.exception("export %s crashed", job_id)
            _set(job_id, stage="error", message=f"The export failed unexpectedly ({type(e).__name__}). Please try again.")
