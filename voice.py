"""
Voice for JARVIS.

Step 1 of the build ships deliberately mute: the browser's own speechSynthesis
voice. That is the robotic default the Fish Audio segment replaces.

Step 2 drops a FISH_AUDIO_API_KEY into .env and this module starts serving real
audio from /api/speak instead. The key stays server-side — the browser only ever
receives mp3 bytes, so nothing leaks into devtools or a screen recording.

Contract verified against the live API: TTS is POST /v1/tts with the model in a
header and reference_id choosing the voice; ASR is POST /v1/asr with a multipart
field named `audio`. See .agents/skills/fish-audio-api for the full spec.
"""
import json
import os
import urllib.error
import urllib.request

TTS_URL = os.environ.get("FISH_AUDIO_TTS_URL", "https://api.fish.audio/v1/tts")
ASR_URL = os.environ.get("FISH_AUDIO_ASR_URL", "https://api.fish.audio/v1/asr")
MODEL = os.environ.get("FISH_AUDIO_MODEL", "s2.1-pro-free")
VOICE_ID = os.environ.get("FISH_AUDIO_VOICE_ID", "").strip()


def available():
    return bool(os.environ.get("FISH_AUDIO_API_KEY"))


def describe():
    if not available():
        return "browser speechSynthesis (add FISH_AUDIO_API_KEY for real voice)"
    return f"Fish Audio · {MODEL}" + (f" · {VOICE_ID[:8]}…" if VOICE_ID else " · default voice")


def speak(text):
    """Returns mp3 bytes, or raises. The caller decides what to do on failure."""
    if not available():
        raise RuntimeError("no FISH_AUDIO_API_KEY — browser voice is handling this")
    text = (text or "").strip()
    if not text:
        raise ValueError("empty text")

    payload = {"text": text[:2500], "format": "mp3", "latency": "normal"}
    if VOICE_ID:
        payload["reference_id"] = VOICE_ID

    req = urllib.request.Request(
        TTS_URL, data=json.dumps(payload).encode(), method="POST",
        headers={
            "content-type": "application/json",
            "authorization": f"Bearer {os.environ['FISH_AUDIO_API_KEY']}",
            "model": MODEL,
        })
    try:
        with urllib.request.urlopen(req, timeout=45) as r:
            return r.read()
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"Fish Audio TTS HTTP {e.code}: {e.read(400).decode('utf-8','replace')}") from e


def transcribe(audio, mime="audio/webm"):
    """Speech to text. Falls back to the browser when no key is present."""
    if not available():
        raise RuntimeError("no FISH_AUDIO_API_KEY — browser speech recognition is handling this")
    if not audio:
        raise ValueError("empty audio")

    boundary = "----jarvis" + os.urandom(8).hex()
    b = boundary.encode()
    ext = {"audio/webm": "webm", "audio/ogg": "ogg", "audio/mp4": "mp4",
           "audio/mpeg": "mp3", "audio/wav": "wav"}.get(mime.split(";")[0], "webm")
    body = b"".join([
        b"--", b, b"\r\n",
        f'Content-Disposition: form-data; name="audio"; filename="turn.{ext}"\r\n'.encode(),
        f"Content-Type: {mime}\r\n\r\n".encode(), audio, b"\r\n",
        b"--", b, b"--\r\n",
    ])
    req = urllib.request.Request(
        ASR_URL, data=body, method="POST",
        headers={"content-type": f"multipart/form-data; boundary={boundary}",
                 "authorization": f"Bearer {os.environ['FISH_AUDIO_API_KEY']}"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return (json.loads(r.read()).get("text") or "").strip()
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"Fish Audio ASR HTTP {e.code}: {e.read(400).decode('utf-8','replace')}") from e
