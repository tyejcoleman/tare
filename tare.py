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
  tare rules [repo]        audit a repo's CLAUDE.md instead
  tare history [repo]      the accruing record for a repo

Reads only. Never edits your config."""


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
    else:
        print(c("  Earning its place.", H.GRN, tty))
    print()
    return 0


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

    if argv and argv[0] == "rules":
        return cmd_rules(argv[1:])

    if argv and argv[0] == "history":
        return cmd_rules(argv[1:] + ["--history"])

    # default: the harness audit
    sys.argv = ["tare"] + argv
    return H.main()


if __name__ == "__main__":
    sys.exit(main())
