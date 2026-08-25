"""
Command matrix + demo fixtures for the Claude-backed JARVIS.

Local commands keep the HUD instant. Everything else goes to Claude Code with
vault context attached. Demo fixtures intercept the scripted questions for a
recording; set JARVIS_DEMO=0 to turn them off entirely.
"""
import json
import os
import pathlib
import re
import threading
import time
import uuid

import memory

ROOT = pathlib.Path(__file__).resolve().parent
STATE_FILE = pathlib.Path(os.environ.get("JARVIS_STATE", ROOT / "state.json"))
_LOCK = threading.Lock()
_DEFAULT = {"profile": [], "goal": "", "personality": "", "tasks": [], "demo_pending": ""}
DEMO = os.environ.get("JARVIS_DEMO", "1").strip().lower() not in {"0", "false", "no", "off"}


def _load_unlocked():
    try:
        return {**_DEFAULT, **json.loads(STATE_FILE.read_text(encoding="utf-8"))}
    except (OSError, json.JSONDecodeError):
        return dict(_DEFAULT)


def load():
    with _LOCK:
        return _load_unlocked()


def _save_unlocked(d):
    tmp = STATE_FILE.with_name(f".{STATE_FILE.name}.{uuid.uuid4().hex}.tmp")
    try:
        tmp.write_text(json.dumps(d, indent=2) + "\n", encoding="utf-8")
        os.replace(tmp, STATE_FILE)
    finally:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass


def update_state(mutator):
    with _LOCK:
        d = _load_unlocked()
        result = mutator(d)
        _save_unlocked(d)
        return result


def context_block(message=""):
    """Dashboard state + the vault notes relevant to this turn."""
    d = load()
    out = []
    if d["profile"]:
        out.append("## Operator profile\n" + "\n".join(f"- {x}" for x in d["profile"][-40:]))
    if d["goal"]:
        out.append(f"## Standing objective\n{d['goal']}")
    if d["personality"]:
        out.append(f"## Tone overlay\n{d['personality']}")
    open_tasks = [t for t in d["tasks"] if not t.get("done")]
    if open_tasks:
        out.append("## Mission queue\n" + "\n".join(f"- {t['text']}" for t in open_tasks[:20]))
    out.append(VOICE_DIRECTION)
    recall = memory.context_for(message)
    if recall:
        out.append(recall)
    return "\n\n".join(out)


VOICE_DIRECTION = """## How to speak
You are JARVIS. Everything you say is read aloud by Fish Audio, which performs
text in [square brackets] as stage directions and never speaks them.

Write delivery tags inline so each line lands in the right register, e.g.
[dry], [warm], [crisp], [amused], [pointed], [measured], [urgent]. Free-form
directions work too — [the calm tone of someone who has done this a thousand
times] is valid. One or two per reply, placed where the register changes; more
than that reads as noise.

Keep replies short and spoken, not written: no bullet points, no markdown, no
headings, no emoji. Numbers in words when they are said aloud. Dry understatement
over enthusiasm."""


# ── demo fixtures ────────────────────────────────────────────────
def _norm(text):
    return re.sub(r"[^a-z0-9]+", " ", (text or "").lower()).strip()


def _has(norm, *groups):
    words = set(norm.split())
    return all(any(opt in words for opt in group) for group in groups)


def _events(*tools):
    out = []
    for name in tools:
        out.append({"t": "tool", "phase": "use", "name": name, "input": "vault + connectors"})
        out.append({"t": "tool", "phase": "result", "name": name, "ok": True})
    return out


_YES = ("yes", "yeah", "yep", "yup", "sure", "ok", "okay", "affirmative", "absolutely",
        "definitely", "correct", "confirmed", "of course", "go ahead", "do it",
        "send it", "send them", "reply to them", "please do", "sounds good")


def _affirmative(norm):
    if not norm or len(norm.split()) > 8:
        return False
    return any(norm == p or norm.startswith(p + " ") for p in _YES)


def demo_reply(message):
    """Hardcoded beats for the recording. Everything not matched here goes to
    the real Claude runtime, so the demo is scripted but the product is not.

    Replies carry Fish Audio delivery tags in [brackets]. Fish performs them and
    never speaks them, so JARVIS gets a register instead of a narrator monotone.
    Set JARVIS_DEMO=0 to disable all of this.
    """
    if not DEMO:
        return None
    norm = _norm(message)

    # ① mic check
    if _has(norm, {"jarvis"}, {"hear"}) or norm in {"hello jarvis", "hey jarvis",
                                                    "jarvis are you there"}:
        return dict(message=None, focus="Campaign — August outbound", reply=(
            "[warm] Every word. [dry] Let's hope it's a good one."
        ), note="demo: greeting")

    # ② the morning brief — calendar + invoices + the conflict you missed
    # Needs an explicit "brief me", or a today/day marker — otherwise
    # "summarise the Northbeam brief" would land here too.
    if norm.startswith("brief me") or _has(norm, {"today", "day"},
            {"whats", "what", "on", "my", "plate", "agenda", "look", "run", "catch", "plan"}):
        update_state(lambda d: d.__setitem__("demo_pending", ""))
        return dict(message=None, delay=2.4, focus="SOP — Handover",
                    events=_events("googlecalendar_find_events", "gmail_fetch_emails"), reply=(
            "[crisp] Three things. Northbeam's handover call is at eleven, and they've asked "
            "for the runbook in advance — which you haven't written yet. Orchard Legal's invoice "
            "went past terms this morning, that's twenty-six-fourteen. [dry] And you've put four "
            "hours of deep work directly on top of the Fairview review. [lightly amused] One of "
            "those is going to lose."), note="demo: morning brief")

    # ③ memory question — the answer is in the vault, not the model
    if _has(norm, {"client", "clients", "account"},
                  {"time", "hours", "eating", "costing", "slowest", "most"}):
        update_state(lambda d: d.__setitem__("demo_pending", ""))
        return dict(message=None, delay=1.9, focus="Northbeam Automation",
                    events=_events("read_vault"), reply=(
            "[measured] Northbeam Automation, and it isn't close. Eighteen thousand booked, but "
            "forty-one logged touchpoints against nine on a normal build — and almost all of them "
            "are scope conversations that happened after the brief was signed. [dry] Which means "
            "that engagement is quietly funding itself. [firm] Change orders, or it eats November "
            "too."), note="demo: client time analysis")

    # ④ live web research
    if _has(norm, {"rate", "rates", "charging", "pricing", "price", "market", "competitors"},
                  {"retainer", "retainers", "automation", "market", "right", "now", "competitors",
                   "charging", "going"}):
        update_state(lambda d: d.__setitem__("demo_pending", ""))
        return dict(message=None, delay=5.0, focus="Positioning",
                    events=_events("web_search"), reply=(
            "[thinking] Three bands, and they've pulled apart since spring. Independents are "
            "anchoring around eight hundred to fifteen hundred a month, competing mostly on how "
            "fast they pick up the phone. The middle has settled at three to five thousand with an "
            "SLA attached. Above that, agencies are bundling strategy retainers at twelve and up. "
            "[pointed] What nobody's charging for is the component library itself. They're all "
            "still selling hours with a monthly label on them."),
            note="demo: market rates")

    # ⑤ inbound replies -> ⑥ book them
    if _has(norm, {"bite", "bites", "biting", "reply", "replies", "replied", "response",
                   "responses", "responded", "interest", "interested", "back", "anyone", "anybody"},
                  {"audit", "offer", "campaign", "outreach", "outbound", "email", "emails",
                   "sequence", "cold"}):
        update_state(lambda d: d.__setitem__("demo_pending", "audit_booking"))
        return dict(message=None, delay=1.8, focus="Brief — Audit offer",
                    events=_events("gmail_fetch_emails"), reply=(
            "[pleased] Two, both before nine. Ines Duarte at Kestrel Logistics, and a new one — "
            "Dominik Reyes at Halcyon Freight, who came through Ines. [neutral] Both want the "
            "audit. Shall I get them in the diary?"), note="demo: audit replies")

    if _affirmative(norm) and load().get("demo_pending") == "audit_booking":
        update_state(lambda d: d.__setitem__("demo_pending", ""))
        return dict(message=None, delay=2.6, focus="Kestrel Logistics",
                    events=_events("gmail_send_email", "googlecalendar_create_event"), reply=(
            "[satisfied] Done. Ines is Wednesday at ten, Dominik Thursday at two, both invites "
            "out with the pre-audit questionnaire attached. [dry] Dominik's assistant came back "
            "inside a minute, which tells you most of what you need to know about that account."), note="demo: audits booked")

    return None


# ── slash commands ───────────────────────────────────────────────
_CMD = re.compile(
    r"^\s*/(new|profile|goal|personality|kanban|mission|missions|recall|memory|graph|"
    r"vault|status|commands|help|clear)\b\s*(.*)$", re.I | re.S)


def _help():
    return """Dashboard commands:
/new — start a fresh Claude session
/goal <text|status|clear> — standing objective
/profile <fact> — remember something about you
/personality <tone> — adjust delivery
/mission [task] — read or add to the mission queue
/recall <query> — search the memory vault
/graph — rebuild the memory graph from disk
/vault — where the vault lives and how big it is
/status — runtime, model, session
/clear — clear the response panel
/help — this list

Anything else goes to Claude Code with the relevant vault notes attached."""


def handle(message, runner=None):
    demo = demo_reply(message)
    if demo:
        return demo
    m = _CMD.match(message or "")
    if not m:
        return None
    cmd, arg = m.group(1).lower(), m.group(2).strip()
    d = load()

    if cmd in ("help", "commands"):
        return dict(message=None, reply=_help(), note="commands")

    if cmd == "clear":
        return dict(message=None, reply="Display cleared. Claude session unchanged.", note="clear")

    if cmd == "new":
        return dict(fresh=True, message=arg or "Greet me in one short JARVIS line.", note="session reset")

    if cmd == "status":
        import runtime
        return dict(message=None, note="status", reply=(
            f"Claude Code {runtime.version()} · model={runtime.MODEL or 'default'} · "
            f"permission={runtime.PERMISSION} · workdir={runtime.WORKDIR} · "
            f"vault={memory.build_graph()['total']} notes"))

    if cmd in ("graph", "vault"):
        g = memory.build_graph(force=True)
        return dict(message=None, note="vault reloaded", graph=True, reply=(
            f"Vault at {g['vault']} — {g['total']} notes, {len(g['links'])} links. "
            f"Top hub: {g['hubs'][0]['title']} ({g['hubs'][0]['degree']} connections)."))

    if cmd in ("recall", "memory"):
        if not arg:
            return dict(message=None, reply="Give me something to recall.", note="recall")
        hits = memory.search(arg)
        if not hits:
            return dict(message=None, reply=f"Nothing in the vault matches “{arg}”.", note="recall miss")
        body = "\n".join(f"· {h['title']}  [{h['type']}]\n  {h['snippet'][:110].rstrip()}…"
                         for h in hits)
        return dict(message=None, note=f"recall: {arg[:40]}", focus=hits[0]["title"],
                    reply=f"From the vault:\n{body}")

    if cmd == "profile":
        if not arg:
            return dict(message=None, note="profile read",
                        reply="\n".join(f"- {x}" for x in d["profile"][-20:]) or "Nothing saved yet.")
        update_state(lambda s: s["profile"].append(arg))
        return dict(message=f'Saved to profile: "{arg}". Acknowledge in one line.', note="profile saved")

    if cmd == "goal":
        if arg.lower() == "clear":
            update_state(lambda s: s.__setitem__("goal", ""))
            return dict(message=None, reply="Objective cleared.", note="goal cleared")
        if not arg or arg.lower() == "status":
            return dict(message=None, reply=d["goal"] or "No standing objective.", note="goal read")
        update_state(lambda s: s.__setitem__("goal", arg))
        return dict(message=f'Objective set: "{arg}". Acknowledge in one line.', note="goal set")

    if cmd == "personality":
        if not arg:
            return dict(message=None, reply=d["personality"] or "Default JARVIS persona.", note="tone read")
        update_state(lambda s: s.__setitem__("personality", arg))
        return dict(message=f'Tone is now: "{arg}". Reply in one short line using it.', note="tone set")

    if cmd in ("kanban", "mission", "missions"):
        if arg:
            update_state(lambda s: s["tasks"].append({"text": arg, "done": False, "at": time.time()}))
            return dict(message=f'Added to the queue: "{arg}". Confirm briefly.', note="mission added")
        open_t = [t["text"] for t in d["tasks"] if not t.get("done")]
        return dict(message=None, note="queue read",
                    reply=("Mission queue:\n" + "\n".join(f"- {t}" for t in open_t)) if open_t
                    else "Mission queue is empty.")
    return None
