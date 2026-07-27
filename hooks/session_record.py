#!/usr/bin/env python3
"""
rulecheck session hook — the accruing record.

A one-shot `rulecheck` run can only see the transcripts still sitting on disk.
Those age out, get cleaned up, or grow too large to scan. So a single run can
tell you "this rule has never fired" but never "this rule stopped firing five
weeks ago" — and the second statement is the useful one.

This hook fixes that. At the end of every session it appends ONE compact line
to ~/.tare/history.jsonl recording which rules the session engaged. The
record then survives the transcripts it was derived from.

Local only. It writes one file on this machine and sends nothing anywhere.

It must never interfere with the session: every failure path exits 0 silently.
A measurement tool that can break your editor is not worth having.
"""
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

HISTORY = Path.home() / ".tare" / "history.jsonl"
MAX_TRANSCRIPT_BYTES = 60_000_000


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0

    cwd = payload.get("cwd") or os.getcwd()
    transcript = payload.get("transcript_path")
    session_id = (payload.get("session_id") or "")[:8]
    if not transcript:
        return 0

    # Import the checker that ships beside this hook, so the parsing rules and
    # the report can never drift apart.
    plugin_root = Path(__file__).resolve().parent.parent
    sys.path.insert(0, str(plugin_root))
    try:
        import rulecheck as rc
    except Exception:
        return 0

    repo = Path(cwd)
    try:
        rules = rc.parse_rules(repo)
    except Exception:
        return 0
    if not rules:
        return 0  # no rule file here; nothing to record

    tpath = Path(transcript)
    try:
        if not tpath.is_file() or tpath.stat().st_size > MAX_TRANSCRIPT_BYTES:
            return 0
    except OSError:
        return 0

    text, calls = _evidence(tpath, rc)
    if not calls:
        return 0  # a session with no tool calls is not evidence of anything

    fired = []
    checkable = 0
    for r in rules:
        if not r["literals"]:
            continue
        checkable += 1
        if any(lit in text for lit in r["literals"]):
            fired.append(r["key"])

    row = {
        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "session": session_id,
        "repo": str(repo),
        "rules": len(rules),
        "checkable": checkable,
        "tool_calls": calls,
        "fired": sorted(fired),
    }

    try:
        HISTORY.parent.mkdir(parents=True, exist_ok=True)
        with HISTORY.open("a") as fh:
            fh.write(json.dumps(row) + "\n")
    except OSError:
        return 0
    return 0


def _evidence(tpath: Path, rc) -> tuple[str, int]:
    """Flatten this one transcript's tool inputs into searchable text."""
    blob, n = [], 0
    try:
        with tpath.open(errors="replace") as fh:
            for line in fh:
                if '"tool_use"' not in line:
                    continue
                try:
                    d = json.loads(line)
                except Exception:
                    continue
                if d.get("type") != "assistant":
                    continue
                content = (d.get("message") or {}).get("content")
                if not isinstance(content, list):
                    continue
                for b in content:
                    if isinstance(b, dict) and b.get("type") == "tool_use":
                        n += 1
                        blob.extend(rc._tool_evidence(b.get("input")))
    except OSError:
        return "", 0
    return "\n".join(blob).lower(), n


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        sys.exit(0)
