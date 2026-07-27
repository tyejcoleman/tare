# Changelog

## 0.2.0 — 2026-07-26

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

## 0.1.0 — 2026-07-26

First working version. Classifies every rule in `CLAUDE.md` / `AGENTS.md` as **FIRED**,
**DORMANT**, or **UNOBSERVABLE** by literal-matching against recorded tool calls. No model in
the judging path. Refuses to report a dead-letter rate under 150 recorded tool calls.
