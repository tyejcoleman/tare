#!/usr/bin/env python3
"""
harness — how much of your agent setup is dead weight?

Every MCP server you connect, every subagent you define, every skill you add
loads into context. None of it ever gets removed. Harnesses accumulate debt the
same way codebases do, except nobody has ever measured it.

This reads the Claude Code session transcripts already on your disk and compares
what you have CONFIGURED against what you have actually INVOKED.

Unlike prose rules, this is exact. A tool call is a recorded fact, not an
inference — so every number here is auditable and nothing is guessed.

Usage:
    python3 harness.py            # audit this machine
    python3 harness.py --json
    python3 harness.py --days 30  # only count activity in the last N days

Reads only. Never writes, never sends anything anywhere, never edits your config.
"""
from __future__ import annotations
import json, re, sys, time, argparse
from collections import defaultdict
from pathlib import Path

VERSION = "0.1.0"

HOME = Path.home()
PROJECTS = HOME / ".claude" / "projects"
CONFIG = HOME / ".claude.json"
AGENTS_DIR = HOME / ".claude" / "agents"
SKILLS_DIR = HOME / ".claude" / "skills"
MAX_FILE = 80_000_000

# Matched against the raw bytes of a transcript. Regex over bytes is ~20x faster
# than parsing every line as JSON, and these keys only appear inside tool_use
# blocks, so there is nothing to disambiguate.
# Whitespace-tolerant on purpose. A transcript serialized with standard JSON
# spacing would otherwise match nothing, and a silent zero here would tell
# someone to delete a server they use every day.
RE_MCP = re.compile(rb'"name"\s*:\s*"mcp__([a-zA-Z0-9_-]+)__([a-zA-Z0-9_]+)"')
# Any mention, not just a call. Tool listings appear verbatim in transcripts, so
# the set of names ever seen is a floor on how many tools a server exposes —
# i.e. how much of your context it occupies whether you use it or not.
RE_MCP_ANY = re.compile(rb'mcp__([a-zA-Z0-9_-]+)__([a-zA-Z0-9_]+)')
RE_AGENT = re.compile(rb'"subagent_type"\s*:\s*"([a-zA-Z0-9:_-]+)"')
RE_SKILL = re.compile(rb'"skill"\s*:\s*"([a-zA-Z0-9:._-]+)"')


# ----------------------------------------------------------------- what exists

def configured_mcp() -> dict[str, str]:
    """server -> where it is configured."""
    out: dict[str, str] = {}
    try:
        d = json.loads(CONFIG.read_text(errors="replace"))
    except Exception:
        return out
    for name in (d.get("mcpServers") or {}):
        out[name] = "global"
    for path, cfg in (d.get("projects") or {}).items():
        for name in (cfg.get("mcpServers") or {}):
            out.setdefault(name, f"project: {Path(path).name}")
    return out


def configured_agents() -> dict[str, str]:
    out = {}
    if AGENTS_DIR.is_dir():
        for f in AGENTS_DIR.glob("*.md"):
            out[f.stem] = "user"
    return out


def configured_skills() -> dict[str, str]:
    out = {}
    if SKILLS_DIR.is_dir():
        for f in SKILLS_DIR.glob("*/SKILL.md"):
            out[f.parent.name] = "user"
    return out


# --------------------------------------------------------------- what was used

def scan(days: int | None) -> dict:
    """Walk every transcript once, tallying invocations by kind."""
    cutoff = time.time() - days * 86400 if days else None
    mcp_calls: dict[str, int] = defaultdict(int)
    mcp_tools: dict[str, set] = defaultdict(set)
    # Which projects each server was actually used in. A server configured
    # globally but only ever called in one project is not dead — it is
    # misplaced, and every other project is paying for it.
    mcp_projects: dict[str, set] = defaultdict(set)
    mcp_exposed: dict[str, set] = defaultdict(set)
    agents: dict[str, int] = defaultdict(int)
    skills: dict[str, int] = defaultdict(int)
    last: dict[str, float] = {}
    files = sessions = 0

    if not PROJECTS.is_dir():
        return {"error": f"no transcripts at {PROJECTS}"}

    for f in PROJECTS.rglob("*.jsonl"):
        try:
            st = f.stat()
            if st.st_size > MAX_FILE:
                continue
            if cutoff and st.st_mtime < cutoff:
                continue
            data = f.read_bytes()
        except OSError:
            continue
        files += 1
        touched = False

        for srv, tool in RE_MCP_ANY.findall(data):
            mcp_exposed[srv.decode()].add(tool.decode())
        for srv, tool in RE_MCP.findall(data):
            s = srv.decode()
            mcp_calls[s] += 1
            mcp_tools[s].add(tool.decode())
            mcp_projects[s].add(f.parent.name)
            _bump(last, "mcp:" + s, st.st_mtime)
            touched = True
        for a in RE_AGENT.findall(data):
            n = a.decode()
            agents[n] += 1
            _bump(last, "agent:" + n, st.st_mtime)
            touched = True
        for s in RE_SKILL.findall(data):
            n = s.decode()
            skills[n] += 1
            _bump(last, "skill:" + n, st.st_mtime)
            touched = True
        if touched:
            sessions += 1

    return {
        "mcp_calls": dict(mcp_calls),
        "mcp_tools": {k: sorted(v) for k, v in mcp_tools.items()},
        "mcp_projects": {k: sorted(v) for k, v in mcp_projects.items()},
        "mcp_exposed": {k: len(v) for k, v in mcp_exposed.items()},
        "agents": dict(agents),
        "skills": dict(skills),
        "last": last,
        "files": files,
        "sessions": sessions,
    }


def _bump(d: dict, k: str, v: float) -> None:
    if k not in d or v > d[k]:
        d[k] = v


# ----------------------------------------------------------------- assessment

def assess(scanned: dict) -> dict:
    now = time.time()
    groups = []

    def build(title, unit, configured, counts, prefix, note):
        rows = []
        for name, where in sorted(configured.items()):
            n = counts.get(name, 0)
            ts = scanned["last"].get(f"{prefix}:{name}")
            projs = scanned["mcp_projects"].get(name, []) if prefix == "mcp" else []
            rows.append({
                "name": name,
                "where": where,
                "calls": n,
                "days": int((now - ts) // 86400) if ts else None,
                "tools_used": len(scanned["mcp_tools"].get(name, [])) if prefix == "mcp" else None,
                "tools_exposed": scanned["mcp_exposed"].get(name) if prefix == "mcp" else None,
                "projects": projs,
                # Configured for everything, used in one place.
                # Configured for everything, used in one place — but "used only
                # from the home directory" is not a project, so it doesn't count.
                "misplaced": bool(where == "global" and n > 0 and len(projs) == 1
                                  and projs[0].strip("-") != _HOME_SLUG.strip("-")),
            })
        rows.sort(key=lambda r: (r["calls"], -(r["days"] or 9999)))
        return {"title": title, "unit": unit, "rows": rows, "note": note}

    groups.append(build(
        "MCP servers", "server", configured_mcp(), scanned["mcp_calls"], "mcp",
        "Every connected server loads its tool definitions into context on every session."))
    groups.append(build(
        "Subagents", "agent", configured_agents(), scanned["agents"], "agent",
        "Defined in ~/.claude/agents. Each one's description is offered to the model."))
    groups.append(build(
        "Skills", "skill", configured_skills(), scanned["skills"], "skill",
        "Defined in ~/.claude/skills. Each one's description is offered to the model."))
    return {"groups": groups}


# --------------------------------------------------------------------- output

BOLD, DIM, RST = "\033[1m", "\033[2m", "\033[0m"
GRN, YEL, RED, CYA = "\033[32m", "\033[33m", "\033[31m", "\033[36m"

COLD_DAYS = 21          # not touched in three weeks
def color(s, c, on): return f"{c}{s}{RST}" if on else s

_HOME_SLUG = re.sub(r"[^A-Za-z0-9]+", "-", str(HOME))


def _pretty(slug: str) -> str:
    """Transcript dirs are slugified absolute paths; drop the home prefix so the
    recommendation is readable. The slug is lossy, so we never try to rebuild
    the real path from it."""
    if slug.startswith(_HOME_SLUG):
        slug = slug[len(_HOME_SLUG):]
    return slug.strip("-") or "(home)"


def report(scanned, a, days, tty=True):
    print()
    print(color(f"harness {VERSION}", BOLD, tty),
          color(f"· {scanned['files']} transcripts", DIM, tty),
          color(f"· last {days} days" if days else "· all time", DIM, tty))
    print(color("─" * 68, DIM, tty))

    dead_total = cold_total = live_total = 0

    for g in a["groups"]:
        rows = g["rows"]
        if not rows:
            continue
        dead = [r for r in rows if r["calls"] == 0]
        cold = [r for r in rows if r["calls"] > 0 and (r["days"] or 0) >= COLD_DAYS]
        dead_total += len(dead); cold_total += len(cold)
        live_total += len(rows) - len(dead) - len(cold)

        print()
        print(f"  {color(g['title'].upper(), BOLD, tty)}  "
              f"{color(f'{len(rows)} configured', DIM, tty)}")
        print(color("  " + "─" * 66, DIM, tty))
        for r in rows:
            if r["calls"] == 0:
                # In a windowed run "never" would be a lie — we only looked at
                # part of the record.
                label = f"unused in {days}d" if days else "NEVER USED"
                dot, tag = color("●", RED, tty), color(label, RED, tty)
            elif (r["days"] or 0) >= COLD_DAYS:
                dot, tag = color("●", YEL, tty), color(f"{r['days']}d cold", YEL, tty)
            else:
                dot, tag = color("●", GRN, tty), color(f"{r['days']}d ago", DIM, tty)
            extra = ""
            if r.get("tools_exposed"):
                extra = color(f"  {r['tools_used']}/{r['tools_exposed']} tools used",
                              DIM, tty)
            print(f"  {dot} {r['name']:<20} {r['calls']:>6} calls   {tag}{extra}")
            if r.get("misplaced"):
                print(color(f"       ↳ global, but only ever used in "
                            f"{_pretty(r['projects'][0])} — scope it there", CYA, tty))
        if g["note"]:
            print(color(f"     {g['note']}", DIM, tty))

    print()
    print(color("  " + "─" * 66, DIM, tty))
    dead_label = f"unused {days}d" if days else "never used"
    print(f"  {color('●', RED, tty)} {color(str(dead_total).rjust(3), BOLD, tty)}  {dead_label:<14} "
          f"{color('loaded every session, never once invoked' if not days
                    else f'loaded every session, not invoked in {days} days', DIM, tty)}")
    print(f"  {color('●', YEL, tty)} {color(str(cold_total).rjust(3), BOLD, tty)}  cold           "
          f"{color(f'not touched in {COLD_DAYS}+ days', DIM, tty)}")
    print(f"  {color('●', GRN, tty)} {color(str(live_total).rjust(3), BOLD, tty)}  live           "
          f"{color('earning their place', DIM, tty)}")
    print()

    if dead_total or cold_total:
        print(color(f"  {dead_total + cold_total} pieces of your harness are costing you context "
                    f"on every session", BOLD, tty))
        print(color("  and giving nothing back. Nothing here is edited for you — "
                    "that is your call.", DIM, tty))
        print()
        print(color("  Counted from recorded invocations only. A skill loaded some other "
                    "way,", DIM, tty))
        print(color("  or used before it was added to your config, will not appear here.",
                    DIM, tty))
        print(color("  'n/m tools used' counts tool names seen in your transcripts — a "
                    "floor on", DIM, tty))
        print(color("  what each server exposes, not a reading of its live schema.",
                    DIM, tty))
    else:
        print(color("  Every configured piece of your harness has been used recently.",
                    BOLD, tty))
    print()


def main():
    ap = argparse.ArgumentParser(description="How much of your agent harness is dead weight?")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--days", type=int, help="only count activity in the last N days")
    ap.add_argument("--version", action="version", version=f"harness {VERSION}")
    x = ap.parse_args()

    scanned = scan(x.days)
    if "error" in scanned:
        print(scanned["error"], file=sys.stderr)
        return 1
    a = assess(scanned)

    if x.json:
        print(json.dumps({"version": VERSION, "transcripts": scanned["files"],
                          "days": x.days, **a}, indent=2))
        return 0
    report(scanned, a, x.days, tty=sys.stdout.isatty())
    return 0


if __name__ == "__main__":
    sys.exit(main())
