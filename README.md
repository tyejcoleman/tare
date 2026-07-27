# rulecheck

**Which of your agent rules actually fire?**

You wrote rules in `CLAUDE.md`. They're loaded into context on every single run.
Nobody knows whether any of them ever apply.

`rulecheck` reads the Claude Code session transcripts already sitting on your disk
and tells you, per rule:

| | |
|---|---|
| **FIRED** | the agent really did touch what this rule governs |
| **DORMANT** | checkable, but no session ever engaged it — a dead letter paying rent in your context window |
| **GUARDRAIL** | a prohibition that has never been tripped. Never firing is what a *working* prohibition looks like — these are reported separately and never counted as dead. |
| **UNOBSERVABLE** | the rule names nothing a machine can verify. It may be good advice; it cannot be enforced or measured. |

## Install

As a Claude Code plugin:

```
/plugin marketplace add tyejcoleman/rulecheck
/plugin install rulecheck
```

Then `/rulecheck:check` in any repo, and `/rulecheck:history` once it has been running a while.

Or just run the script — it is one file with no dependencies:

```bash
curl -O https://raw.githubusercontent.com/tyejcoleman/rulecheck/main/rulecheck.py
python3 rulecheck.py
```

```bash
python3 rulecheck.py                  # current directory
python3 rulecheck.py ~/code/myrepo
python3 rulecheck.py --json           # machine-readable
python3 rulecheck.py --rule 7         # evidence for one rule
python3 rulecheck.py --history        # the accruing record (needs the plugin hook)
```

Python 3.9+. **No dependencies. No account. No network.** It reads
`~/.claude/projects/**.jsonl` and your rule files.

## The accruing record

A single run only sees the transcripts still on disk, so it can tell you *"this rule has
never fired"* but never *"this rule stopped firing five weeks ago"* — and the second one is
the useful sentence.

The plugin installs one `SessionEnd` hook that appends a single line per session to
`~/.rulecheck/history.jsonl`: which rules that session engaged, and how many tool calls it
made. The record then outlives the transcripts it came from, and `--history` shows you when
each rule was last seen.

That file is the only thing rulecheck ever writes. It stays on your machine — there is no
account, no server, and no telemetry. If you delete it, you lose the history and nothing else.

## Real output

```
rulecheck 0.1.0 · ~/Development/Hotel Portal
──────────────────────────────────────────────────────────────────
  20 rules found · 7 sessions · 1,359 recorded tool calls

  ●   8  FIRED         the agent actually reached this
  ●   6  DORMANT       checkable, but never once engaged
  ●   2  GUARDRAIL     a prohibition, never tripped — silence is the goal
  ●   4  UNOBSERVABLE  nothing here a machine can verify

  DEAD LETTERS — in your context window on every run, never applied
  ────────────────────────────────────────────────────────────────
    7  When you spot dead UI: document it in `index/80-evaluations/...`
       CLAUDE.md:27  looked for: index/80-evaluations/latent-ux-flows.md

  GUARDRAILS — prohibitions with no violation observed. Leave these alone.
  ────────────────────────────────────────────────────────────────
   19  Document, don't delete. Add an entry to `index/80-evaluations/...`
       Never firing is what a working prohibition looks like.

  30% of your obligations have never once applied. 20% of your rules
  cannot be checked at all — you have no way to tell whether they work.
```

## What it found across 9 real repos

| repo | rules | tool calls | fired | dead | guardrail | uncheckable |
|---|---:|---:|---:|---:|---:|---:|
| Hotel Portal | 20 | 1,431 | 8 | 30% | 2 | 20% |
| Skeptics | 12 | 178 | 2 | 50% | 3 | 8% |
| tokenroom | 22 | 90 | 6 | 14% | 1 | 55% |
| processyard | 17 | 1,403 | 1 | 6% | 0 | 88% |
| job-search-harness | 36 | 5,434 | 1 | 3% | 0 | 94% |
| context-graph-steward | 21 | 46 | 4 | 5% | 0 | 76% |

The headline isn't the dead letters — it's the **uncheckable** column. Most of what
people write into a rule file has no machine-observable anchor at all.

**What that number does and doesn't say.** It is not a claim that those rules are
worthless. A prose rule can steer the model perfectly well on every single run, and
rulecheck cannot see that — it only sees tool calls. What the number says is that for
88% of that file **you have no way to find out either way**: no way to know whether a
rule is working, no way to notice when it stops, and no anchor to promote it into a
hook or a check later. It measures how much of your governance is falsifiable, not how
much of it is good.

## Design

**No model in the judging path.** Every verdict is literal matching against recorded
tool calls, so the same input always gives the same answer, nothing is invented, and
you can audit any verdict with `--rule N`. This is deliberate: an earlier prototype
put a model in this position and scored below chance at telling a genuine violation
from a legitimate change.

**Low-evidence guard.** Under 150 recorded tool calls, `rulecheck` refuses to report
a dead-letter rate and says so. "Never fired" and "we barely looked" are different
claims, and conflating them would be a confident wrong answer.

## Limits (read before trusting a number)

- A rule is "fired" when its **literals** (backticked paths, commands, identifiers)
  appear in a session's tool inputs. That's engagement, **not compliance** — it does
  not prove the agent obeyed, only that it was in the neighbourhood.
- Rules written as pure prose land in UNOBSERVABLE by construction. That is the
  finding, not a parser failure.
- Only the Claude Code transcript format is supported today. Cursor and Codex are
  the obvious next adapters.
- Rule extraction is heuristic — it reads list items, bolded directives, and
  normative sentences in prose. It will miss some and over-collect others.
