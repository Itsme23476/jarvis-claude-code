"""
Claude Code runtime for the JARVIS memory HUD.

The brain is your own `claude` CLI, running headless (`claude -p`) with
`--output-format stream-json`. That means it authenticates the same way your
normal Claude Code sessions do — your subscription, no API key, no per-token
billing — and it keeps the same tools, MCP servers, skills and CLAUDE.md
context that the interactive CLI has.

Never pass --bare: it forces ANTHROPIC_API_KEY auth and would bypass the
subscription this whole dashboard is built around.
"""
import collections
import json
import os
import shlex
import shutil
import subprocess
import threading
import time
import uuid

MODEL = os.environ.get("JARVIS_MODEL", "").strip()
WORKDIR = os.path.expanduser(os.environ.get("JARVIS_WORKDIR", os.getcwd()))
# bypassPermissions by default: a headless `claude -p` can't surface a permission
# prompt, so any gated tool (MCP connectors, web search) would silently fail
# otherwise. This also lets JARVIS take unattended actions (send/delete/shell) —
# see the Security notes in README. Set JARVIS_PERMISSION=acceptEdits to narrow it.
PERMISSION = os.environ.get("JARVIS_PERMISSION", "bypassPermissions").strip()
RUNTIME = os.environ.get("JARVIS_RUNTIME", "auto").strip().lower()   # auto|claude|mock
IDLE_TIMEOUT = int(os.environ.get("JARVIS_TIMEOUT", "180"))
RAW_LOG = os.environ.get("JARVIS_RAW_LOG", "").strip()

# One Claude subprocess at a time: session state is shared, and the browser
# Escape key must be able to kill real backend work, not just the fetch.
EXECUTION_LOCK = threading.RLock()
_ACTIVE_PROC = None
_ACTIVE_LOCK = threading.Lock()

# Hook chatter and internal bookkeeping the HUD should never render.
_NOISE_SUBTYPES = {"hook_started", "hook_response", "post_turn_summary",
                   "compact_boundary", "mcp_status"}


def cancel_active():
    with _ACTIVE_LOCK:
        proc = _ACTIVE_PROC
    if proc is None or proc.poll() is not None:
        return False
    try:
        proc.terminate()
        return True
    except Exception:
        return False


def valid_session(sid):
    """Claude Code session ids are UUIDs."""
    try:
        return bool(sid) and str(uuid.UUID(str(sid))) == str(sid).lower()
    except (ValueError, AttributeError, TypeError):
        return False


def _claude_base():
    configured = os.environ.get("CLAUDE_CMD", "").strip()
    if configured:
        return shlex.split(configured)
    exe = shutil.which("claude")
    if exe:
        return [exe]
    local = os.path.expanduser("~/.local/bin/claude")
    if os.path.exists(local):
        return [local]
    return ["claude"]


def _can_launch():
    try:
        p = subprocess.run(_claude_base() + ["--version"], cwd=WORKDIR, text=True,
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=15)
        return p.returncode == 0, (p.stdout or p.stderr).strip()
    except Exception as e:  # noqa: BLE001
        return False, str(e)


def runtime_kind():
    if RUNTIME in ("mock", "claude"):
        return RUNTIME
    ok, _ = _can_launch()
    return "claude" if ok else "mock"


def version():
    ok, detail = _can_launch()
    return detail if ok else "unavailable"


def build_command(message, session_id=None, system=None):
    cmd = _claude_base() + [
        "-p", message,
        "--output-format", "stream-json",
        "--include-partial-messages",
        "--verbose",
    ]
    if valid_session(session_id):
        cmd += ["--resume", str(session_id)]
    if MODEL:
        cmd += ["--model", MODEL]
    if PERMISSION:
        cmd += ["--permission-mode", PERMISSION]
    if system:
        cmd += ["--append-system-prompt", system]
    return cmd


def _short(value, limit=90):
    """Collapse a tool input dict into one readable line for the action log."""
    if isinstance(value, dict):
        for key in ("command", "query", "prompt", "file_path", "pattern", "path", "url"):
            if key in value and isinstance(value[key], str):
                value = value[key]
                break
        else:
            value = json.dumps(value)
    text = " ".join(str(value).split())
    return text[:limit] + ("…" if len(text) > limit else "")


def run_claude(message, session_id=None, system=None):
    with EXECUTION_LOCK:
        yield from _run_locked(message, session_id, system)


def _run_locked(message, session_id=None, system=None):
    global _ACTIVE_PROC
    started = time.monotonic()
    cmd = build_command(message, session_id, system)

    env = dict(os.environ)
    home = os.path.expanduser("~")
    env["PATH"] = ":".join(dict.fromkeys([
        env.get("PATH", ""), os.path.join(home, ".local", "bin"),
        "/opt/homebrew/bin", "/usr/local/bin",
        os.path.join(home, ".npm-global", "bin"),
        "/usr/bin", "/bin", "/usr/sbin", "/sbin",
    ]))

    try:
        proc = subprocess.Popen(cmd, cwd=WORKDIR, text=True, bufsize=1,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)
        with _ACTIVE_LOCK:
            _ACTIVE_PROC = proc
    except FileNotFoundError:
        raise RuntimeError("claude CLI not found. Install Claude Code or set CLAUDE_CMD.")

    q = collections.deque()
    lock = threading.Lock()
    done = threading.Event()
    errbuf = collections.deque(maxlen=120)
    raw = None
    if RAW_LOG:
        flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        fd = os.open(os.path.expanduser(RAW_LOG), flags, 0o600)
        raw = os.fdopen(fd, "w", encoding="utf-8", errors="replace")

    def pump_out():
        try:
            for ln in proc.stdout:
                if raw:
                    raw.write(ln); raw.flush()
                with lock:
                    q.append(ln)
        finally:
            done.set()

    def pump_err():
        try:
            for ln in proc.stderr:
                errbuf.append(ln.rstrip())
        except Exception:
            pass

    threading.Thread(target=pump_out, daemon=True).start()
    threading.Thread(target=pump_err, daemon=True).start()

    emitted_session = session_id
    last_usage = {}
    streamed_text = False       # partial deltas arrived -> ignore final text blocks
    text_seen = False
    first = True
    last = time.monotonic()

    try:
        while not done.is_set() or q:
            line = None
            with lock:
                if q:
                    line = q.popleft()
            if line is None:
                if proc.poll() is not None and done.is_set():
                    break
                if time.monotonic() - last > IDLE_TIMEOUT:
                    proc.kill()
                    yield dict(t="error", message=(
                        f"Claude went quiet for {IDLE_TIMEOUT}s and was stopped. "
                        + " | ".join(list(errbuf)[-3:]))[:400])
                    return
                time.sleep(0.04)
                continue
            last = time.monotonic()
            line = line.strip()
            if not line or not line.startswith("{"):
                continue
            try:
                ev = json.loads(line)
            except json.JSONDecodeError:
                continue

            kind = ev.get("type")
            sid = ev.get("session_id")
            if valid_session(sid):
                emitted_session = sid

            if kind == "system":
                if ev.get("subtype") == "init":
                    yield dict(t="status", model=ev.get("model") or MODEL or "Claude default",
                               tools=len(ev.get("tools") or []),
                               mcp=[s.get("name") for s in (ev.get("mcp_servers") or [])],
                               permission=ev.get("permissionMode") or PERMISSION,
                               session_id=sid, runtime="claude")
                continue

            if kind == "rate_limit_event":
                info = ev.get("rate_limit_info") or {}
                yield dict(t="ratelimit", status=info.get("status"),
                           window=info.get("rateLimitType"), resets=info.get("resetsAt"))
                continue

            if kind == "stream_event":
                inner = ev.get("event") or {}
                if inner.get("type") == "content_block_delta":
                    delta = inner.get("delta") or {}
                    if delta.get("type") == "text_delta" and delta.get("text"):
                        if first:
                            first = False
                            yield dict(t="latency", ms=int((time.monotonic() - started) * 1000))
                        streamed_text = True
                        text_seen = True
                        yield dict(t="delta", text=delta["text"])
                continue

            if kind == "assistant":
                u = (ev.get("message") or {}).get("usage") or {}
                if u:
                    last_usage = u
                for block in (ev.get("message") or {}).get("content") or []:
                    btype = block.get("type")
                    if btype == "text" and not streamed_text and block.get("text"):
                        if first:
                            first = False
                            yield dict(t="latency", ms=int((time.monotonic() - started) * 1000))
                        text_seen = True
                        yield dict(t="delta", text=block["text"])
                    elif btype == "tool_use":
                        yield dict(t="tool", phase="use", name=block.get("name", "tool"),
                                   input=_short(block.get("input", "")))
                continue

            if kind == "user":
                for block in (ev.get("message") or {}).get("content") or []:
                    if block.get("type") == "tool_result":
                        yield dict(t="tool", phase="result",
                                   ok=not block.get("is_error"),
                                   name=block.get("name", ""))
                continue

            if kind == "result":
                usage = ev.get("usage") or last_usage or {}
                if ev.get("subtype") != "success" and not text_seen:
                    yield dict(t="error", message=str(ev.get("result") or "Claude returned an error")[:400])
                    return
                if not text_seen and ev.get("result"):
                    yield dict(t="delta", text=str(ev["result"]))
                    text_seen = True
                yield dict(t="usage",
                           input_tokens=usage.get("input_tokens", 0),
                           output_tokens=usage.get("output_tokens", 0),
                           total_tokens=(usage.get("input_tokens", 0) + usage.get("output_tokens", 0)))
                yield dict(t="complete", session_id=emitted_session,
                           ms=ev.get("duration_ms") or int((time.monotonic() - started) * 1000))
                return

        rc = proc.wait(timeout=5)
        if rc != 0:
            yield dict(t="error", message=(" | ".join(list(errbuf)[-6:])
                                           or f"claude exited with code {rc}")[:500])
            return
        if not text_seen:
            yield dict(t="delta", text="Claude completed without textual output.")
        yield dict(t="complete", session_id=emitted_session,
                   ms=int((time.monotonic() - started) * 1000))
    finally:
        try:
            if raw:
                raw.close()
        except Exception:
            pass
        if proc.poll() is None:
            proc.terminate()
        with _ACTIVE_LOCK:
            if _ACTIVE_PROC is proc:
                _ACTIVE_PROC = None


def run_mock(message, session_id=None, system=None):
    ok, detail = _can_launch()
    yield dict(t="error", message=("Claude Code is not reachable from this process. "
                                   "Install it, or set CLAUDE_CMD to the executable. "
                                   f"Diagnostic: {detail[:200]}"))


def run(message, session_id=None, system=None):
    if runtime_kind() != "claude":
        yield from run_mock(message, session_id, system)
        return
    try:
        yield from run_claude(message, session_id, system)
    except Exception as e:  # noqa: BLE001
        yield dict(t="error", message=f"could not start Claude core: {e}")
