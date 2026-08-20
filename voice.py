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
import pathlib
import shutil
import subprocess
import tempfile
import urllib.error
import urllib.request

TTS_URL = os.environ.get("FISH_AUDIO_TTS_URL", "https://api.fish.audio/v1/tts")
ASR_URL = os.environ.get("FISH_AUDIO_ASR_URL", "https://api.fish.audio/v1/asr")
MODEL = os.environ.get("FISH_AUDIO_MODEL", "s2.1-pro-free")
VOICE_ID = os.environ.get("FISH_AUDIO_VOICE_ID", "").strip()

# ── local speech-to-text ────────────────────────────────────────
# Listening is the one thing Fish Audio charges for, and the browser's own
# recogniser needs Google's service — which Brave ships without, so it fails
# with a bare "network". whisper.cpp sidesteps both: offline, free, ~1s for a
# short clip, and it works in any browser.
WHISPER_BIN = os.environ.get("WHISPER_BIN", "").strip() or shutil.which("whisper-cli") \
    or shutil.which("whisper-cpp") or ""
FFMPEG = os.environ.get("FFMPEG_BIN", "").strip() or shutil.which("ffmpeg") or ""


def _whisper_model():
    explicit = os.environ.get("WHISPER_MODEL", "").strip()
    if explicit and os.path.exists(os.path.expanduser(explicit)):
        return os.path.expanduser(explicit)
    for guess in ("~/.clawbot/models/ggml-base.bin",
                  "~/.cache/whisper/ggml-base.bin",
                  "/opt/homebrew/share/whisper-cpp/ggml-base.bin"):
        path = os.path.expanduser(guess)
        if os.path.exists(path):
            return path
    return ""


def whisper_ready():
    return bool(WHISPER_BIN and FFMPEG and _whisper_model())


def stt_kind():
    """Which listener is actually usable right now."""
    if os.environ.get("JARVIS_STT", "auto").strip().lower() == "fish":
        return "fish" if available() else "browser"
    if whisper_ready():
        return "whisper"
    return "fish" if available() else "browser"


def describe_stt():
    kind = stt_kind()
    if kind == "whisper":
        return f"whisper.cpp local ({pathlib.Path(_whisper_model()).name})"
    if kind == "fish":
        return f"Fish Audio ASR ({MODEL})"
    return "browser speech recognition"


def transcribe_local(audio, mime="audio/webm"):
    """Browser clip -> 16 kHz mono wav -> whisper.cpp -> text. Never leaves the machine."""
    model = _whisper_model()
    if not (WHISPER_BIN and FFMPEG and model):
        raise RuntimeError("whisper.cpp not available")
    ext = {"audio/webm": ".webm", "audio/ogg": ".ogg", "audio/mp4": ".mp4",
           "audio/mpeg": ".mp3", "audio/wav": ".wav"}.get(mime.split(";")[0], ".webm")
    with tempfile.TemporaryDirectory() as tmp:
        raw = os.path.join(tmp, "turn" + ext)
        wav = os.path.join(tmp, "turn.wav")
        with open(raw, "wb") as fh:
            fh.write(audio)
        conv = subprocess.run([FFMPEG, "-y", "-loglevel", "error", "-i", raw,
                               "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le", wav],
                              capture_output=True, text=True, timeout=60)
        if conv.returncode != 0 or not os.path.exists(wav):
            raise RuntimeError(f"audio convert failed: {(conv.stderr or '')[:160]}")
        out = subprocess.run([WHISPER_BIN, "-m", model, "-f", wav, "-nt", "-np",
                              "-t", "4", "-l", os.environ.get("WHISPER_LANG", "auto")],
                             capture_output=True, text=True, timeout=180)
        if out.returncode != 0:
            raise RuntimeError(f"whisper failed: {(out.stderr or '')[-160:]}")
        text = " ".join(out.stdout.split()).strip()
        if text.startswith("[") and "]" in text:      # drop any [BLANK_AUDIO] marker
            text = text.split("]", 1)[1].strip()
        return text


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
    """Speech to text. Prefers local whisper.cpp, falls back to Fish Audio ASR."""
    if not audio:
        raise ValueError("empty audio")
    if stt_kind() == "whisper":
        return transcribe_local(audio, mime)
    if not available():
        raise RuntimeError("no local whisper and no FISH_AUDIO_API_KEY")

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
