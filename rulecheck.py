#!/usr/bin/env python3
"""
rulecheck — which of your agent rules actually fire?

You wrote rules in CLAUDE.md / AGENTS.md. Nobody knows whether the agent
follows them, or whether anyone even reaches the code they govern.

rulecheck reads the Claude Code session transcripts already on your disk and
answers three questions per rule:

  FIRED        the rule's subject was actually touched in real sessions
  DORMANT      the rule is machine-observable, but no session ever touched it
               -> a dead letter: it costs context on every single run and has
                  never once applied
  UNOBSERVABLE the rule names nothing a machine can check (pure prose)
               -> it may be good advice, but it cannot be enforced or measured

DETERMINISTIC BY DESIGN. There is no model in the judging path. Every verdict
is literal matching against recorded tool calls, so the same input always gives
the same answer and nothing is hallucinated.

Usage:
    python3 rulecheck.py                 # current directory
    python3 rulecheck.py ~/code/myrepo
    python3 rulecheck.py --json          # machine-readable
    python3 rulecheck.py --rule 7        # show the evidence for one rule

Reads only. Never writes, never sends anything anywhere.
"""
from __future__ import annotations
import json, re, sys, argparse, hashlib
from collections import defaultdict
from pathlib import Path

VERSION = "0.3.0"

# Where the session hook accrues its record. One line per session.
HISTORY = Path.home() / ".tare" / "history.jsonl"

# ---------------------------------------------------------------- rule parsing

# A line is normative if it tells the agent what it may/must/never do.
MODAL = re.compile(
    r"\b(must not|must|never|always|do not|don't|dont|shall not|shall|"
    r"required|require|forbidden|prohibited|only ever|only|no longer|"
    r"avoid|prefer|should not|should|ensure|make sure)\b", re.I)

# A prohibition is measured backwards from an obligation. "Always update the
# changelog" never firing means the rule is dead. "Never force-push" never
# firing means it is WORKING — silence is what compliance looks like. Report
# those as dead letters and you tell people to delete their own guardrails.
NEGATIVE = re.compile(
    r"\b(never|must not|do not|don't|dont|shall not|should not|cannot|can't|"
    r"forbidden|prohibited|not allowed|avoid|no longer)\b", re.I)
NEGATIVE_LEAD = re.compile(r"^\s*no\s+\w", re.I)   # "No service-role key in the client"

# Things a machine can actually look for in a transcript.
BACKTICK = re.compile(r"`([^`\n]{2,80})`")
PATHISH = re.compile(r"\b([\w./-]+/[\w./-]+\.\w{1,6}|[\w-]+\.(?:ts|tsx|js|jsx|mjs|py|rs|go|rb|sh|sql|toml|ya?ml|json|md))\b")
CMDISH = re.compile(r"\b(npm|npx|yarn|pnpm|git|cargo|docker|make|pytest|python3?|node|gh|supabase|vercel|terraform)\s+[\w:.-]+")

# Markdown noise we never treat as a rule.
SKIP_LINE = re.compile(r"^\s*(\||#{1,6}\s*$|<|!\[|\[!)", )
MIN_RULE_LEN = 25
MAX_RULE_LEN = 400

RULE_FILES = ["CLAUDE.md", "AGENTS.md", ".claude/CLAUDE.md", ".cursorrules",
              ".cursor/rules", "AGENT.md", "CONVENTIONS.md"]


def clean(text: str) -> str:
    t = re.sub(r"^\s*([-*+]|\d+[.)])\s+", "", text)  # drop the list marker
    t = re.sub(r"\*\*|__|\*(?!\*)", "", t)
    t = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", t)   # md links -> label
    return re.sub(r"\s+", " ", t).strip(" -–—•*").strip()


def literals_of(text: str) -> set[str]:
    """Machine-checkable anchors mentioned by a rule."""
    out: set[str] = set()
    for m in BACKTICK.findall(text):
        m = m.strip()
        # a backticked path/command/flag/identifier is checkable; prose isn't
        if len(m) >= 3 and not re.fullmatch(r"[A-Za-z ]{3,}", m):
            out.add(m.lower())
    for m in PATHISH.findall(text):
        out.add(m.lower() if isinstance(m, str) else m[0].lower())
    for m in CMDISH.findall(text):
        out.add(m.lower())
    return {o for o in out if len(o) >= 3}


def parse_rules(repo: Path) -> list[dict]:
    rules, seen = [], set()
    for rel in RULE_FILES:
        f = repo / rel
        if not f.is_file():
            continue
        try:
            lines = f.read_text(errors="replace").split("\n")
        except OSError:
            continue
        in_code = False
        para: list[str] = []          # buffered prose lines
        para_line = 0                 # line number the paragraph started on

        def flush():
            """Prose rule files are common — ProcessYard states its hard rules as
            plain sentences. Markdown hard-wraps them, so a sentence spans several
            lines; buffer the paragraph and split it as one string, or every rule
            comes out as a fragment."""
            if not para:
                return
            text = " ".join(x.strip() for x in para)
            for c in re.split(r"(?<=[.!?])\s+", text):
                if MODAL.search(c):
                    _add(rules, seen, c, rel, para_line)
            para.clear()

        for i, raw in enumerate(lines, 1):
            if raw.strip().startswith("```"):
                flush()
                in_code = not in_code
                continue
            if in_code:
                continue
            if SKIP_LINE.match(raw) or not raw.strip():
                flush()
                continue
            if re.match(r"^\s*([-*+]|\d+\.)\s+|^\s*\*\*", raw):
                flush()
                _add(rules, seen, raw, rel, i)      # list items stand alone
                continue
            if not para:
                para_line = i
            para.append(raw)
        flush()
    return rules


def _add(rules: list, seen: set, raw: str, rel: str, i: int) -> None:
    """Record one candidate line as a rule, if it qualifies."""
    txt = clean(raw)
    if not (MIN_RULE_LEN <= len(txt) <= MAX_RULE_LEN):
        return
    # Normative EITHER by modal verb ("never push to main") OR by being a named
    # directive — a bolded lead like "**3. Migrations are forward-only.**" is a
    # rule even with no modal verb in it. Without the second test we silently
    # miss rules like "No service-role key in the client".
    named_directive = bool(re.match(r"^\s*(?:[-*+]|\d+[.)])?\s*\*\*", raw))
    if not (MODAL.search(txt) or named_directive):
        return
    key = txt.lower()[:90]
    if key in seen:
        return
    seen.add(key)
    rules.append({
        "id": len(rules) + 1,
        # Stable across edits elsewhere in the file, so history stays keyed to
        # the rule itself rather than to its position. Reword a rule and it
        # correctly reads as a new rule with no track record.
        "key": hashlib.sha1(key.encode()).hexdigest()[:10],
        "text": txt,
        "source": f"{rel}:{i}",
        "kind": "prohibition" if (NEGATIVE.search(txt) or NEGATIVE_LEAD.match(txt))
                else "obligation",
        "literals": sorted(literals_of(raw)),
    })


# ------------------------------------------------------------ transcript load

def project_dir_for(repo: Path) -> Path | None:
    """Claude Code encodes the project path as the transcript directory name."""
    base = Path.home() / ".claude" / "projects"
    if not base.is_dir():
        return None
    # Claude Code slugifies the absolute path: every non-alphanumeric run
    # (slashes, spaces, dots, underscores) collapses to a single dash.
    enc = re.sub(r"[^A-Za-z0-9]+", "-", str(repo.resolve()))
    for cand in (base / enc, base / enc.lstrip("-")):
        if cand.is_dir():
            return cand
    # fall back to suffix match (handles older encodings)
    tail = repo.resolve().name
    hits = [d for d in base.iterdir() if d.is_dir() and d.name.endswith(f"-{tail}")]
    return hits[0] if len(hits) == 1 else None


def _tool_evidence(inp) -> list[str]:
    """Flatten a tool_use input into searchable strings."""
    out = []
    if isinstance(inp, dict):
        for k in ("file_path", "path", "command", "pattern", "notebook_path",
                  "url", "old_string", "new_string", "content", "prompt", "query"):
            v = inp.get(k)
            if isinstance(v, str) and v:
                out.append(v)
    elif isinstance(inp, str):
        out.append(inp)
    return out


def load_sessions(tdir: Path, max_bytes=60_000_000) -> list[dict]:
    sessions = []
    for f in sorted(tdir.glob("*.jsonl")):
        try:
            if f.stat().st_size > max_bytes:
                continue
        except OSError:
            continue
        blob, tools, n = [], defaultdict(int), 0
        try:
            with f.open(errors="replace") as fh:
                for line in fh:
                    if '"tool_use"' not in line:
                        continue
                    try:
                        d = json.loads(line)
                    except Exception:
                        continue
                    if d.get("type") != "assistant":
                        continue
                    msg = d.get("message") or {}
                    content = msg.get("content")
                    if not isinstance(content, list):
                        continue
                    for b in content:
                        if not (isinstance(b, dict) and b.get("type") == "tool_use"):
                            continue
                        n += 1
                        tools[b.get("name", "?")] += 1
                        blob.extend(_tool_evidence(b.get("input")))
        except OSError:
            continue
        if n:
            sessions.append({
                "id": f.stem[:8],
                "file": f.name,
                "tool_calls": n,
                "tools": dict(tools),
                "text": "\n".join(blob).lower(),
            })
    return sessions


# ----------------------------------------------------------------- evaluation

# Below this much recorded activity, "never fired" means "we barely looked",
# not "this rule is dead". Reporting a dead-letter rate off a handful of tool
# calls would be a confident wrong answer, which is worse than no answer.
MIN_EVIDENCE_CALLS = 150


def evaluate(rules: list[dict], sessions: list[dict]) -> list[dict]:
    for r in rules:
        if not r["literals"]:
            r["status"] = "UNOBSERVABLE"
            r["hits"] = 0
            r["matched"] = []
            r["sessions"] = []
            continue
        hit_sessions, matched = [], set()
        for s in sessions:
            found = [l for l in r["literals"] if l in s["text"]]
            if found:
                hit_sessions.append(s["id"])
                matched.update(found)
        r["hits"] = len(hit_sessions)
        r["sessions"] = hit_sessions[:8]
        r["matched"] = sorted(matched)
        if hit_sessions:
            r["status"] = "FIRED"
        elif r["kind"] == "prohibition":
            # Never triggered is the desired outcome, not a dead letter.
            r["status"] = "GUARDRAIL"
        else:
            r["status"] = "DORMANT"
    return rules


# --------------------------------------------------------------------- output

BOLD, DIM, RST = "\033[1m", "\033[2m", "\033[0m"
GRN, YEL, RED, CYA = "\033[32m", "\033[33m", "\033[31m", "\033[36m"


def color(s, c, on):
    return f"{c}{s}{RST}" if on else s


def report(repo, rules, sessions, tty=True):
    fired = [r for r in rules if r["status"] == "FIRED"]
    dormant = [r for r in rules if r["status"] == "DORMANT"]
    guards = [r for r in rules if r["status"] == "GUARDRAIL"]
    unobs = [r for r in rules if r["status"] == "UNOBSERVABLE"]
    calls = sum(s["tool_calls"] for s in sessions)

    thin = calls < MIN_EVIDENCE_CALLS

    print()
    print(color(f"rulecheck {VERSION}", BOLD, tty), color(f"· {repo}", DIM, tty))
    print(color("─" * 66, DIM, tty))
    print(f"  {len(rules)} rules found · {len(sessions)} sessions · "
          f"{calls:,} recorded tool calls")
    if thin:
        print()
        print(f"  {color('LOW EVIDENCE', YEL, tty)} — only {calls} tool calls recorded here.")
        print(color("  'Never fired' below means we barely looked, not that the rule "
                    "is dead.", DIM, tty))
        print(color(f"  Treat DORMANT as unknown until this repo has ~{MIN_EVIDENCE_CALLS}+ calls.",
                    DIM, tty))
    print()
    print(f"  {color('●', GRN, tty)} {color(str(len(fired)).rjust(3), BOLD, tty)}  FIRED         "
          f"{color('the agent actually reached this', DIM, tty)}")
    print(f"  {color('●', YEL, tty)} {color(str(len(dormant)).rjust(3), BOLD, tty)}  DORMANT       "
          f"{color('checkable, but never once engaged', DIM, tty)}")
    print(f"  {color('●', CYA, tty)} {color(str(len(guards)).rjust(3), BOLD, tty)}  GUARDRAIL     "
          f"{color('a prohibition, never tripped — silence is the goal', DIM, tty)}")
    print(f"  {color('●', RED, tty)} {color(str(len(unobs)).rjust(3), BOLD, tty)}  UNOBSERVABLE  "
          f"{color('nothing here a machine can verify', DIM, tty)}")
    print()

    if dormant:
        print(color("  DEAD LETTERS", BOLD, tty),
              color("— in your context window on every run, never applied", DIM, tty))
        print(color("  " + "─" * 64, DIM, tty))
        for r in dormant[:12]:
            print(f"  {color(str(r['id']).rjust(3), YEL, tty)}  {r['text'][:74]}")
            print(f"       {color(r['source'], DIM, tty)}  "
                  f"{color('looked for: ' + ', '.join(r['literals'][:4]), DIM, tty)}")
        if len(dormant) > 12:
            print(color(f"       … {len(dormant)-12} more", DIM, tty))
        print()

    if guards:
        print(color("  GUARDRAILS", BOLD, tty),
              color("— prohibitions with no violation observed. Leave these alone.", DIM, tty))
        print(color("  " + "─" * 64, DIM, tty))
        for r in guards[:6]:
            print(f"  {color(str(r['id']).rjust(3), CYA, tty)}  {r['text'][:74]}")
        if len(guards) > 6:
            print(color(f"       … {len(guards)-6} more", DIM, tty))
        print(color("       Never firing is what a working prohibition looks like.", DIM, tty))
        print()

    if unobs:
        print(color("  UNENFORCEABLE", BOLD, tty),
              color("— no path, command or identifier to check against", DIM, tty))
        print(color("  " + "─" * 64, DIM, tty))
        for r in unobs[:8]:
            print(f"  {color(str(r['id']).rjust(3), RED, tty)}  {r['text'][:74]}")
            print(f"       {color(r['source'], DIM, tty)}")
        if len(unobs) > 8:
            print(color(f"       … {len(unobs)-8} more", DIM, tty))
        print()

    if fired:
        print(color("  ACTIVE", BOLD, tty), color("— most-engaged rules", DIM, tty))
        print(color("  " + "─" * 64, DIM, tty))
        for r in sorted(fired, key=lambda x: -x["hits"])[:8]:
            mark = color("!", YEL, tty) if r["kind"] == "prohibition" else " "
            print(f"  {color(str(r['id']).rjust(3), GRN, tty)} {mark} "
                  f"{color(f'{r['hits']:>3} sessions', CYA, tty)}  {r['text'][:58]}")
        if any(r["kind"] == "prohibition" for r in fired):
            print(color("       ! a prohibition whose subject was touched. Engagement, "
                        "not proof of violation.", DIM, tty))
        print()

    if rules:
        pct = round(100 * len(dormant) / len(rules))
        upct = round(100 * len(unobs) / len(rules))
        if thin:
            print(color(f"  {upct}% of your rules cannot be checked at all — you have no way "
                        f"to tell whether they work.", BOLD, tty))
            print(color("  Dead-letter rate needs more sessions.", DIM, tty))
        else:
            print(color(f"  {pct}% of your obligations have never once applied. "
                        f"{upct}% of your rules", BOLD, tty))
            print(color("  cannot be checked at all — you have no way to tell whether "
                        "they work.", BOLD, tty))
    print()


def load_history(repo: Path) -> list[dict]:
    """Rows the session hook recorded for this repo, oldest first."""
    if not HISTORY.is_file():
        return []
    rows = []
    try:
        with HISTORY.open(errors="replace") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    d = json.loads(line)
                except Exception:
                    continue
                if d.get("repo") == str(repo):
                    rows.append(d)
    except OSError:
        return []
    return rows


def history_report(repo, rules, rows, tty=True):
    print()
    print(color(f"rulecheck {VERSION}", BOLD, tty),
          color(f"· history · {repo}", DIM, tty))
    print(color("─" * 66, DIM, tty))

    if not rows:
        print("  Nothing recorded yet for this repo.")
        print(color("  The session hook writes one line per session to "
                    f"{HISTORY}.", DIM, tty))
        print(color("  Install the plugin, work normally for a week, then come back.",
                    DIM, tty))
        print()
        return

    first, last = rows[0].get("ts", "?"), rows[-1].get("ts", "?")
    calls = sum(r.get("tool_calls", 0) for r in rows)
    print(f"  {len(rows)} sessions recorded · {calls:,} tool calls")
    print(color(f"  {first[:10]} → {last[:10]}", DIM, tty))
    print()

    # last time each rule key was seen firing, and how often
    last_seen, counts = {}, defaultdict(int)
    for row in rows:
        for k in row.get("fired", []):
            counts[k] += 1
            last_seen[k] = row.get("ts", "")

    checkable = [r for r in rules if r["literals"]]
    # A prohibition that never fired is working, not rotting — see NEGATIVE.
    never = [r for r in checkable
             if r["key"] not in last_seen and r["kind"] == "obligation"]
    quiet_guards = sum(1 for r in checkable
                       if r["key"] not in last_seen and r["kind"] == "prohibition")
    seen = sorted((r for r in checkable if r["key"] in last_seen),
                  key=lambda r: last_seen[r["key"]])

    if never:
        print(color("  NEVER FIRED", BOLD, tty),
              color(f"— across all {len(rows)} recorded sessions", DIM, tty))
        print(color("  " + "─" * 64, DIM, tty))
        for r in never[:12]:
            print(f"  {color(str(r['id']).rjust(3), YEL, tty)}  {r['text'][:74]}")
            print(f"       {color(r['source'], DIM, tty)}")
        if len(never) > 12:
            print(color(f"       … {len(never)-12} more", DIM, tty))
        if quiet_guards:
            print(color(f"       ({quiet_guards} prohibitions also never fired — "
                        f"that is them working, and they are not listed.)", DIM, tty))
        print()

    if seen:
        print(color("  LAST SEEN", BOLD, tty),
              color("— stalest first", DIM, tty))
        print(color("  " + "─" * 64, DIM, tty))
        for r in seen[:12]:
            k = r["key"]
            print(f"  {color(str(r['id']).rjust(3), GRN, tty)}  "
                  f"{color(last_seen[k][:10], CYA, tty)}  "
                  f"{color(f'{counts[k]:>3}x', DIM, tty)}  {r['text'][:52]}")
        print()

    if len(rows) < 5:
        print(color("  Only a few sessions recorded so far — this is not yet a trend.",
                    DIM, tty))
        print()


def main():
    ap = argparse.ArgumentParser(description="Which of your agent rules actually fire?")
    ap.add_argument("repo", nargs="?", default=".")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--rule", type=int, help="show evidence for one rule id")
    ap.add_argument("--history", action="store_true",
                    help="show the accruing record from the session hook")
    ap.add_argument("--version", action="version", version=f"rulecheck {VERSION}")
    a = ap.parse_args()

    repo = Path(a.repo).expanduser().resolve()
    if not repo.is_dir():
        print(f"not a directory: {repo}", file=sys.stderr)
        return 2

    rules = parse_rules(repo)
    if not rules:
        print(f"No rule file found in {repo}. Looked for: {', '.join(RULE_FILES)}",
              file=sys.stderr)
        return 1

    if a.history:
        history_report(repo, rules, load_history(repo), tty=sys.stdout.isatty())
        return 0

    tdir = project_dir_for(repo)
    if tdir is None:
        print(f"No Claude Code transcripts found for {repo}.\n"
              f"Expected under ~/.claude/projects/", file=sys.stderr)
        return 1

    sessions = load_sessions(tdir)
    evaluate(rules, sessions)

    if a.rule:
        r = next((x for x in rules if x["id"] == a.rule), None)
        if not r:
            print(f"no rule {a.rule}", file=sys.stderr)
            return 1
        print(json.dumps(r, indent=2))
        return 0

    if a.json:
        print(json.dumps({
            "version": VERSION, "repo": str(repo),
            "sessions": len(sessions),
            "tool_calls": sum(s["tool_calls"] for s in sessions),
            "summary": {
                "fired": sum(1 for r in rules if r["status"] == "FIRED"),
                "dormant": sum(1 for r in rules if r["status"] == "DORMANT"),
                "unobservable": sum(1 for r in rules if r["status"] == "UNOBSERVABLE"),
            },
            "rules": rules,
        }, indent=2))
        return 0

    report(repo, rules, sessions, tty=sys.stdout.isatty())
    return 0


if __name__ == "__main__":
    sys.exit(main())
