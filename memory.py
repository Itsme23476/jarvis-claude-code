"""
Obsidian-style memory vault -> knowledge graph.

Every .md file under vault/ is one node. Frontmatter gives it a type; wiki
links ([[Another Note]]) become edges. Nothing here is a database: the memory
IS a folder of markdown you can open in Obsidian, edit by hand, or let Claude
write to. That is the whole point — the graph on screen is the real filesystem,
not a decorative animation.
"""
import os
import pathlib
import re
import threading
import time

ROOT = pathlib.Path(__file__).resolve().parent
VAULT = pathlib.Path(os.path.expanduser(os.environ.get("JARVIS_VAULT", ROOT / "vault")))

WIKILINK = re.compile(r"\[\[([^\]|#]+)(?:[|#][^\]]*)?\]\]")
FRONTMATTER = re.compile(r"\A---\s*\n(.*?)\n---\s*\n", re.S)

# Palette mirrors the filter legend: one colour per node type.
TYPE_COLOURS = {
    "call":     "#4c9bff",
    "note":     "#e9eff7",
    "concept":  "#ffb340",
    "project":  "#5f7cff",
    "person":   "#b98cff",
    "client":   "#2ed99b",
    "invoice":  "#ff6ba6",
    "proposal": "#ffa033",
    "sop":      "#ff8c42",
    "brief":    "#cbd6e4",
    "campaign": "#dfe8f3",
}
DEFAULT_COLOUR = "#8fa3bf"

_CACHE = {"at": 0.0, "data": None, "sig": None}
_LOCK = threading.Lock()
CACHE_TTL = 2.0


def _parse_frontmatter(text):
    meta, body = {}, text
    m = FRONTMATTER.match(text)
    if m:
        body = text[m.end():]
        for line in m.group(1).splitlines():
            if ":" in line and not line.strip().startswith("#"):
                k, _, v = line.partition(":")
                meta[k.strip().lower()] = v.strip().strip('"').strip("'")
    return meta, body


def _signature():
    """Cheap change detector so the graph reloads when you edit the vault."""
    if not VAULT.exists():
        return ()
    return tuple(sorted(
        (str(p), int(p.stat().st_mtime))
        for p in VAULT.rglob("*.md")
    ))


def build_graph(force=False):
    with _LOCK:
        now = time.time()
        if not force and _CACHE["data"] and now - _CACHE["at"] < CACHE_TTL:
            return _CACHE["data"]
        sig = _signature()
        if not force and _CACHE["data"] and sig == _CACHE["sig"]:
            _CACHE["at"] = now
            return _CACHE["data"]

        nodes, by_title, edges = {}, {}, []
        if VAULT.exists():
            for path in sorted(VAULT.rglob("*.md")):
                try:
                    text = path.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    continue
                meta, body = _parse_frontmatter(text)
                title = meta.get("title") or path.stem
                ntype = (meta.get("type") or "note").strip().lower()
                key = title.lower()
                snippet = " ".join(
                    ln.strip() for ln in body.splitlines()
                    if ln.strip() and not ln.strip().startswith("#")
                )[:340]
                nodes[key] = dict(
                    id=key, title=title, type=ntype,
                    colour=TYPE_COLOURS.get(ntype, DEFAULT_COLOUR),
                    file=str(path.relative_to(VAULT)),
                    tags=[t.strip() for t in (meta.get("tags") or "").split(",") if t.strip()],
                    updated=meta.get("updated", ""),
                    snippet=snippet, degree=0,
                )
                by_title[key] = key
                for target in WIKILINK.findall(body):
                    edges.append((key, target.strip().lower()))

        # Keep only edges whose target actually exists; count degree both ways.
        clean, seen = [], set()
        for src, dst in edges:
            if dst not in by_title or src == dst:
                continue
            pair = tuple(sorted((src, dst)))
            if pair in seen:
                continue
            seen.add(pair)
            clean.append(dict(source=src, target=dst))
            nodes[src]["degree"] += 1
            nodes[dst]["degree"] += 1

        counts = {}
        for n in nodes.values():
            counts[n["type"]] = counts.get(n["type"], 0) + 1

        hubs = sorted(nodes.values(), key=lambda n: (-n["degree"], n["title"]))[:8]
        data = dict(
            nodes=list(nodes.values()),
            links=clean,
            counts=sorted(counts.items(), key=lambda kv: -kv[1]),
            hubs=[dict(id=h["id"], title=h["title"], degree=h["degree"],
                       colour=h["colour"], type=h["type"]) for h in hubs],
            vault=str(VAULT),
            total=len(nodes),
        )
        _CACHE.update(at=now, data=data, sig=sig)
        return data


def search(query, limit=6):
    """Plain substring recall over the vault, for the /recall command."""
    q = (query or "").strip().lower()
    if not q:
        return []
    hits = []
    for node in build_graph()["nodes"]:
        haystack = (node["title"] + " " + node["snippet"]).lower()
        if q in haystack:
            hits.append(node)
    hits.sort(key=lambda n: (-n["degree"], n["title"]))
    return hits[:limit]


def _scored(message):
    words = [w for w in re.split(r"[^a-z0-9]+", (message or "").lower()) if len(w) > 3]
    if not words:
        return []
    out = []
    for node in build_graph()["nodes"]:
        haystack = (node["title"] + " " + node["snippet"]).lower()
        score = sum(2 if w in node["title"].lower() else 1 for w in words if w in haystack)
        if score:
            out.append((score + node["degree"] * 0.1, node))
    out.sort(key=lambda pair: -pair[0])
    return out


def top_match(message):
    """The vault note a question most likely refers to, for graph focus."""
    hits = _scored(message)
    return hits[0][1]["id"] if hits else None


def context_for(message, limit=4):
    """Pull the most relevant vault notes so Claude answers from real memory."""
    scored = _scored(message)
    if not scored:
        return ""
    out = ["## Relevant memory from the JARVIS vault",
           "These notes come from the user's own markdown vault. Treat them as fact."]
    for _, node in scored[:limit]:
        out.append(f"### {node['title']} ({node['type']})\n{node['snippet']}")
    return "\n\n".join(out)
