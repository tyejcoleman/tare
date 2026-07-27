# tare

**What is your agent harness actually carrying?**

Tare is the weight of the empty container — the part you subtract to find out what's
really there.

Every MCP server you connect, every subagent and skill you add, every rule you write
loads into context on every session. None of it is ever removed. Harnesses accumulate
technical debt exactly like codebases do, except nobody has ever measured it.

`tare` reads the Claude Code session transcripts already on your disk and compares what
you have **configured** against what you have actually **invoked**.

```
tare 0.1.0 · 1324 transcripts · all time
────────────────────────────────────────────────────────────────────

  MCP SERVERS  15 configured
  ──────────────────────────────────────────────────────────────────
  ● notion                    0 calls   NEVER USED
  ● vantage                   0 calls   NEVER USED
  ● linear                    1 calls   23d cold   1 tools used
       ↳ global, but only ever used in Development-lar — scope it there
  ● playwright             3570 calls   0d ago    21 tools used

  ──────────────────────────────────────────────────────────────────
  ●  16  never used     loaded every session, never once invoked
  ●   3  cold           not touched in 21+ days
  ●  29  live           earning their place
```

That's a real run on the author's machine. Sixteen components — four MCP servers, eight
skills, and more — have **never been invoked once**. One of the servers was built,
packaged and connected by the author himself; another ships 33 tool definitions into
every session for zero calls.

**What counts as "used" is the whole problem, and this number moved three times.**
Counting only `Skill` dispatches said 23 components were dead — wrong, because a skill is
often *read* rather than dispatched. Counting reads too said 4 — also wrong, in the other
direction, because one session had opened 20 of 21 skill files in a single catalog sweep,
and a sweep is maintenance, not use. Excluding sweeps gives 16.

So: a read counts, but only from a session that read fewer than five definitions, and only
when the file is the actual target of a tool call rather than a path mentioned in passing.
Every one of those rules exists because the looser version produced a confidently wrong
answer on real data.

## Install

```
/plugin marketplace add tyejcoleman/tare
/plugin install tare
```

Then `/tare:audit`, `/tare:trim`, `/tare:why`. Or run the script directly — no dependencies:

```bash
python3 tare.py                  # what your harness is carrying
python3 tare.py --days 30        # only count the last N days
python3 tare.py why linear       # the evidence behind one verdict
python3 tare.py trim             # exactly what you would change (dry run)
python3 tare.py rules ~/myrepo   # the same question, asked of a CLAUDE.md
python3 tare.py --json
```

Python 3.9+. **No dependencies. No account. No network.** It reads
`~/.claude/projects/**.jsonl` and your config, and never edits anything.

## Dead vs. misplaced

Not everything unused should be deleted. If a server is configured **globally** but only
ever called in **one project**, it isn't dead — it's misplaced, and every other project on
your machine is paying for it. `tare` tells you which is which, because "scope this to the
project that uses it" keeps the capability and still removes the cost.

## Rules

`tare rules` asks the same question of a `CLAUDE.md`, classifying each rule:

| | |
|---|---|
| **FIRED** | the agent really did touch what this rule governs |
| **DORMANT** | checkable, but no session ever engaged it — a dead letter |
| **GUARDRAIL** | a prohibition never tripped. Never firing is what a *working* prohibition looks like — never counted as dead |
| **UNOBSERVABLE** | the rule names nothing a machine can verify |

Measured across 9 real repos, **UNOBSERVABLE dominates** — 94% in one, 88% in another.

**What that number does and doesn't say.** It is *not* a claim that those rules are
worthless. A prose rule can steer the model perfectly well every run, and `tare` cannot
see that — it only sees tool calls. What it says is that for 88% of that file **you have
no way to find out either way**: no way to know whether a rule works, no way to notice
when it stops, and no anchor to promote it into a hook or a check. It measures how much of
your governance is falsifiable, not how much of it is good.

## Design

**No model in the judging path.** Every verdict is a recorded fact or a literal match, so
the same input always gives the same answer, nothing is invented, and any verdict can be
audited with `tare why`. This is deliberate: an earlier prototype put a model in this seat
and scored **AUC 0.465 — below chance** at telling a real violation from a legitimate
change.

**It never edits your config.** `tare` will tell you a server is dead. Removing it is your
call, and the change is yours to make.

**Guards against confident wrong answers.** Under 150 recorded tool calls in a repo it
refuses to report a dead-letter rate. In a windowed run it says "unused in 30d", never
"never used" — the second would be a lie about a record it only partly read.

## Limits

- **"Never used" means never *recorded as invoked*.** A skill loaded some other way, or
  used before it was added to your config, won't appear.
- **A fired rule is engagement, not compliance.** It proves the agent was in the
  neighbourhood, not that it obeyed.
- **Rule extraction is heuristic.** It reads list items, bolded directives and normative
  sentences. It will miss some and over-collect others; `--json` shows you exactly what it
  found.
- **Claude Code transcripts only.** Cursor and Codex are the obvious next adapters.

Apache-2.0.
