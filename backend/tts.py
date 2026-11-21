"""Local text-to-speech with Piper. Audio is cached on disk by a hash of the text."""
from __future__ import annotations

import hashlib
import threading
import wave
from pathlib import Path

BASE = Path(__file__).parent
VOICE = BASE / "voices" / "en_US-lessac-medium.onnx"
AUDIO_DIR = BASE / "audio_cache"

_voice = None
_lock = threading.Lock()  # Piper/onnx session is not guaranteed thread-safe


class TTSError(RuntimeError):
    pass


def _get_voice():
    global _voice
    if _voice is None:
        if not VOICE.exists():
            raise TTSError("Piper voice not found. Run setup.sh to download en_US-lessac-medium.")
        from piper import PiperVoice

        _voice = PiperVoice.load(str(VOICE))
    return _voice


def text_hash(text: str) -> str:
    return hashlib.sha256(f"{VOICE.name}\n{text}".encode()).hexdigest()[:24]


def wav_duration(path: Path) -> float:
    with wave.open(str(path)) as w:
        return round(w.getnframes() / w.getframerate(), 3)


def synthesize(text: str) -> dict:
    """Return {"id", "path", "duration"} for the spoken text, generating it only once."""
    h = text_hash(text)
    path = AUDIO_DIR / f"{h}.wav"
    if not path.exists():
        AUDIO_DIR.mkdir(exist_ok=True)
        tmp = path.with_suffix(".tmp")
        with _lock:
            voice = _get_voice()
            with wave.open(str(tmp), "wb") as w:
                voice.synthesize_wav(text, w)
        tmp.replace(path)
    return {"id": h, "path": path, "duration": wav_duration(path)}
