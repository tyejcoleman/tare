# Changelog

## tare 0.1.0 — 2026-07-26

Renamed from `rulecheck`, and the scope moved to where the measurement is actually strong.

`rulecheck` measured whether `CLAUDE.md` rules fire. That works, but it leans on literal
matching against prose, and most rules have no machine-checkable anchor at all — so the
headline number rested on an inference a sharp reader could dismiss. The transcripts contain
something far more exact: **every MCP server, subagent and skill you configured, against every
one you actually invoked.** A tool call is a recorded fact, not an inference.

- **`tare`** — audit this machine: configured vs. ever invoked, split into never used / cold / live.
- **`tare why <name>`** — the receipt behind any verdict: calls, tools, projects, recency.
- **`tare trim`** — the plan, as an exact change. Dry run by default. `--apply` backs up
  `~/.claude.json` to `~/.tare/backups/` and writes atomically.
- **Dead vs. misplaced.** A server configured globally but only ever called in one project is
  not dead, it's misplaced — moving it there keeps the capability and removes the cost
  everywhere else. Scoping to the home directory is excluded; that isn't scoping.
- **Tools exposed vs. used** — `linear: 1/56 tools used`. Counted from tool names seen in
  transcripts, which is a floor on what a server exposes, not a live schema read.
- **`tare rules`** — the former `rulecheck`, now one panel.
- Windowed runs say `unused in 30d`, never `NEVER USED`.

## rulecheck 0.3.0 — 2026-07-26

**Correctness fix: prohibitions were being reported backwards.**

`Never force-push` extracts a literal, never matches a session, and 0.2.0 called that a dead
letter — telling you to delete your own guardrail, when silence is exactly what a working
prohibition looks like. Obligations and prohibitions are measured in opposite directions and
0.2.0 conflated them.

- New **GUARDRAIL** verdict: a prohibition with no violation observed. Reported in its own
  section, excluded from dead letters and from the dead-letter percentage.
- Rules now carry `kind` — `obligation` or `prohibition` — in `--json`.
- A prohibition that *did* match is marked `!` in the active list, with the caveat stated
  inline: engagement is not proof of violation.
- `--history` no longer lists quiet prohibitions as never-fired; it counts them separately.
- Report copy no longer implies UNOBSERVABLE means worthless. The claim is that you cannot
  find out either way, which is a different and defensible statement.

## rulecheck 0.2.0 — 2026-07-26

Packaged for installation by someone who is not the author.

- **Claude Code plugin.** `/plugin marketplace add tyejcoleman/rulecheck` then
  `/plugin install rulecheck`. Ships `/rulecheck:check` and `/rulecheck:history`.
- **`SessionEnd` hook** records one line per session to `~/.rulecheck/history.jsonl`, so the
  measurement accrues past the lifetime of the transcripts it was derived from. Every failure
  path exits 0 — the hook can never interfere with a session.
- **`--history`** reports the accrued record: which rules have never fired across the whole
  recorded window, and when each of the rest was last seen.
- Rules now carry a **stable key** (hash of the rule text) rather than only a positional id, so
  history stays attached to the rule when the file is edited around it. Rewording a rule
  correctly resets its track record.
- `--version`.

## rulecheck 0.1.0 — 2026-07-26

First working version. Classifies every rule in `CLAUDE.md` / `AGENTS.md` as **FIRED**,
**DORMANT**, or **UNOBSERVABLE** by literal-matching against recorded tool calls. No model in
the judging path. Refuses to report a dead-letter rate under 150 recorded tool calls.
