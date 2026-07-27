#!/usr/bin/env python3
"""
tare — what is your agent harness actually carrying?

Tare is the weight of the empty container: the part you subtract to find out
what is really there. Every MCP server you connect, every subagent and skill you
add, every rule you write loads into context on every session — and none of it
is ever removed. Harnesses accumulate debt exactly like codebases do, except
nobody has ever measured it.

tare reads the session transcripts already on your disk and compares what you
have CONFIGURED against what you have actually INVOKED.

    tare                  what your harness is carrying
    tare why linear       the evidence behind one verdict
    tare rules [repo]     the same question, asked of a CLAUDE.md
    tare history [repo]   the accruing record

Deterministic. Every verdict is a recorded fact, not an inference, so the same
input always gives the same answer. Reads only; never edits your config.
"""
from __future__ import annotations
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import harness as H            # noqa: E402
import rulecheck as R          # noqa: E402

VERSION = "0.1.0"

USAGE = """tare — what is your agent harness actually carrying?

  tare                     audit this machine
  tare --days 30           only count the last N days
  tare --json

  tare why <name>          evidence behind one verdict
  tare trim                show exactly what you would change (dry run)
  tare trim --apply        make those changes, after backing up your config
  tare rules [repo]        audit a repo's CLAUDE.md instead
  tare history [repo]      the accruing record for a repo

Read-only unless you pass --apply, and even then it backs up first."""


def cmd_why(name: str, tty: bool) -> int:
    scanned = H.scan(None)
    if "error" in scanned:
        print(scanned["error"], file=sys.stderr)
        return 1

    cfg_mcp, cfg_ag, cfg_sk = (H.configured_mcp(), H.configured_agents(),
                               H.configured_skills())
    c = H.color

    if name in cfg_mcp:
        kind, where = "MCP server", cfg_mcp[name]
        calls = scanned["mcp_calls"].get(name, 0)
        tools = scanned["mcp_tools"].get(name, [])
        projs = scanned["mcp_projects"].get(name, [])
        ts = scanned["last"].get("mcp:" + name)
    elif name in cfg_ag:
        kind, where = "subagent", cfg_ag[name]
        calls, tools, projs = scanned["agents"].get(name, 0), [], []
        ts = scanned["last"].get("agent:" + name)
    elif name in cfg_sk:
        kind, where = "skill", cfg_sk[name]
        calls, tools, projs = scanned["skills"].get(name, 0), [], []
        ts = scanned["last"].get("skill:" + name)
    else:
        print(f"'{name}' is not a configured MCP server, subagent or skill.",
              file=sys.stderr)
        return 1

    import time
    print()
    print(c(f"tare · {name}", H.BOLD, tty), c(f"· {kind} · configured {where}", H.DIM, tty))
    print(c("─" * 68, H.DIM, tty))
    print(f"  invocations   {calls:,}")
    if ts:
        print(f"  last used     {int((time.time()-ts)//86400)} days ago")
    else:
        print(f"  last used     {c('never', H.RED, tty)}")
    print(f"  scanned       {scanned['files']:,} transcripts")
    if tools:
        print(f"  tools used    {len(tools)}")
        print(c("                " + ", ".join(tools[:12]), H.DIM, tty))
    if projs:
        print(f"  used in       {len(projs)} project(s)")
        for p in projs[:8]:
            print(c(f"                {H._pretty(p)}", H.DIM, tty))
    print()
    if calls == 0:
        print(c("  Never invoked in any recorded session.", H.RED, tty))
        print(c("  It loads into context every time you start Claude Code.", H.DIM, tty))
    elif where == "global" and len(projs) == 1:
        print(c(f"  Configured globally, but only ever used in "
                f"{H._pretty(projs[0])}.", H.CYA, tty))
        print(c("  Scoping it to that project keeps the capability and stops "
                "every other", H.DIM, tty))
        print(c("  project paying for it.", H.DIM, tty))
    elif calls <= 2:
        # One call four months ago is not "earning its place", and saying so
        # would be the tool flattering the setup instead of measuring it.
        print(c(f"  Barely used — {calls} invocation"
                f"{'' if calls == 1 else 's'} in the entire record.", H.YEL, tty))
        print(c("  Not dead, but worth asking whether it should be global.", H.DIM, tty))
    else:
        print(c("  Earning its place.", H.GRN, tty))
    print()
    return 0


def _plan(scanned: dict) -> tuple[list, list, list, list]:
    """What the audit implies: servers to drop, servers to scope, files to
    delete by hand, and servers we know are misplaced but cannot place."""
    import re as _re
    cfg = H.configured_mcp()
    try:
        conf = __import__("json").loads(H.CONFIG.read_text(errors="replace"))
    except Exception:
        conf = {}
    proj_keys = list((conf.get("projects") or {}).keys())
    slug = {_re.sub(r"[^A-Za-z0-9]+", "-", k): k for k in proj_keys}

    drop, scope, unresolved = [], [], []
    for name, where in sorted(cfg.items()):
        if where != "global":
            continue
        calls = scanned["mcp_calls"].get(name, 0)
        projs = scanned["mcp_projects"].get(name, [])
        if calls == 0:
            drop.append(name)
        elif len(projs) == 1:
            # The transcript dir name is a lossy slug; recover the true path by
            # slugifying the real project keys and matching, never by unslugging.
            real = slug.get(projs[0])
            if real is None:
                # We know it belongs somewhere else but cannot prove where.
                # Say so — silently dropping it would read as "nothing to do".
                unresolved.append((name, projs[0]))
            # Scoping to the home directory is not scoping — sessions started
            # from ~ are not a project, and moving it there hides it everywhere.
            elif Path(real).resolve() != H.HOME.resolve():
                scope.append((name, real))

    files = []
    for name, _ in H.configured_agents().items():
        if scanned["agents"].get(name, 0) == 0:
            files.append(H.AGENTS_DIR / f"{name}.md")
    for name, _ in H.configured_skills().items():
        if scanned["skills"].get(name, 0) == 0:
            files.append(H.SKILLS_DIR / name / "SKILL.md")
    return drop, scope, files, unresolved


def cmd_trim(apply: bool, tty: bool) -> int:
    import json as _json, time as _time, shutil
    scanned = H.scan(None)
    if "error" in scanned:
        print(scanned["error"], file=sys.stderr)
        return 1
    drop, scope, files, unresolved = _plan(scanned)
    c = H.color

    print()
    print(c("tare trim", H.BOLD, tty),
          c("· proposed changes" if not apply else "· APPLYING", H.DIM, tty))
    print(c("─" * 68, H.DIM, tty))

    if not (drop or scope or files or unresolved):
        print("  Nothing to trim. Every configured piece has been invoked.")
        print()
        return 0

    if drop:
        print()
        print(c("  REMOVE from global mcpServers", H.BOLD, tty),
              c("— never invoked in any session", H.DIM, tty))
        for n in drop:
            print(f"    {c('-', H.RED, tty)} {n}")
    if scope:
        print()
        print(c("  MOVE to the project that uses it", H.BOLD, tty),
              c("— capability kept, cost removed elsewhere", H.DIM, tty))
        for n, path in scope:
            print(f"    {c('~', H.CYA, tty)} {n}  →  {path}")
    if unresolved:
        print()
        print(c("  MOVE BY HAND", H.BOLD, tty),
              c("— used in one project, but tare cannot prove which path", H.DIM, tty))
        for n, s in unresolved:
            print(f"    {c('?', H.YEL, tty)} {n}  →  {H._pretty(s)}")
        print(c("       The transcript folder name is a lossy encoding of the path, "
                "and", H.DIM, tty))
        print(c("       tare will not guess a path it cannot verify.", H.DIM, tty))

    if files:
        print()
        print(c("  DELETE BY HAND", H.BOLD, tty),
              c("— never invoked. tare does not delete your files.", H.DIM, tty))
        for f in files[:12]:
            print(c(f"      {f}", H.DIM, tty))
        if len(files) > 12:
            print(c(f"      … {len(files)-12} more", H.DIM, tty))

    print()
    if not apply:
        print(c("  Dry run. Nothing has been changed.", H.BOLD, tty))
        print(c("  Re-run with --apply to edit ~/.claude.json "
                "(a timestamped backup is written first).", H.DIM, tty))
        print()
        return 0

    if not (drop or scope):
        print(c("  Nothing to apply — the remaining items are files you delete yourself.",
                H.BOLD, tty))
        print()
        return 0

    try:
        conf = _json.loads(H.CONFIG.read_text(errors="replace"))
    except Exception as e:
        print(f"cannot read {H.CONFIG}: {e}", file=sys.stderr)
        return 1

    backup = HOME_BACKUP / f"claude.json.{int(_time.time())}"
    try:
        backup.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(H.CONFIG, backup)
    except OSError as e:
        print(f"refusing to edit without a backup ({e})", file=sys.stderr)
        return 1

    servers = conf.get("mcpServers") or {}
    for n in drop:
        servers.pop(n, None)
    for n, path in scope:
        spec = servers.pop(n, None)
        if spec is not None:
            conf.setdefault("projects", {}).setdefault(path, {}) \
                .setdefault("mcpServers", {})[n] = spec
    conf["mcpServers"] = servers

    tmp = H.CONFIG.with_suffix(".json.tare-tmp")
    try:
        tmp.write_text(_json.dumps(conf, indent=2))
        tmp.replace(H.CONFIG)
    except OSError as e:
        print(f"write failed, config untouched: {e}", file=sys.stderr)
        return 1

    print(c(f"  Applied. Backup at {backup}", H.GRN, tty))
    print(c("  Restart Claude Code for the change to take effect.", H.DIM, tty))
    print()
    return 0


HOME_BACKUP = H.HOME / ".tare" / "backups"


def cmd_rules(argv: list[str]) -> int:
    sys.argv = ["tare rules"] + argv
    return R.main()


def main() -> int:
    argv = sys.argv[1:]
    if argv and argv[0] in ("-h", "--help"):
        print(USAGE)
        return 0
    if argv and argv[0] == "--version":
        print(f"tare {VERSION}")
        return 0

    if argv and argv[0] == "why":
        if len(argv) < 2:
            print("usage: tare why <name>", file=sys.stderr)
            return 2
        return cmd_why(argv[1], sys.stdout.isatty())

    if argv and argv[0] == "trim":
        return cmd_trim("--apply" in argv, sys.stdout.isatty())

    if argv and argv[0] == "rules":
        return cmd_rules(argv[1:])

    if argv and argv[0] == "history":
        return cmd_rules(argv[1:] + ["--history"])

    # default: the harness audit
    sys.argv = ["tare"] + argv
    return H.main()


if __name__ == "__main__":
    sys.exit(main())
