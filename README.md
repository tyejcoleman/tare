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
| **UNOBSERVABLE** | the rule names nothing a machine can verify. It may be good advice; it cannot be enforced or measured. |

## Run it

```bash
python3 rulecheck.py                  # current directory
python3 rulecheck.py ~/code/myrepo
python3 rulecheck.py --json           # machine-readable
python3 rulecheck.py --rule 7         # evidence for one rule
```

Python 3.9+. **No dependencies. No install. No network.** It reads
`~/.claude/projects/**.jsonl` and your rule files, and writes nothing anywhere.

## Real output

```
rulecheck 0.1.0 · ~/Development/Hotel Portal
──────────────────────────────────────────────────────────────────
  20 rules found · 7 sessions · 1,359 recorded tool calls

  ●   8  FIRED         the agent actually reached this
  ●   8  DORMANT       checkable, but never once engaged
  ●   4  UNOBSERVABLE  nothing here a machine can verify

  DEAD LETTERS — in your context window on every run, never applied
  ────────────────────────────────────────────────────────────────
    1  When you spot dead UI: document it in `index/80-evaluations/...`
       CLAUDE.md:27  looked for: index/80-evaluations/latent-ux-flows.md

  40% of your rules have never once applied. 20% cannot be checked at all.
```

## What it found across 9 real repos

| repo | rules | tool calls | dead | uncheckable |
|---|---:|---:|---:|---:|
| Hotel Portal | 20 | 1,359 | 40% | 20% |
| Skeptics | 12 | 178 | 75% | 8% |
| tokenroom | 22 | 90 | 18% | 55% |
| processyard | 17 | 1,403 | 6% | 88% |
| job-search-harness | 36 | 5,434 | 3% | 94% |
| context-graph-steward | 21 | 46 | 5% | 76% |

The headline isn't the dead letters — it's the **uncheckable** column. Most of what
people write into a rule file has no machine-observable anchor at all.

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
