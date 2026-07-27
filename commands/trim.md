---
description: Turn the tare audit into the exact change — dry run first
allowed-tools: ["Bash", "Read"]
---

# tare trim

Show precisely what would change to pay down the harness debt, and apply it only if the user
says so.

## Steps

1. **Always dry-run first**, with no arguments:

   ```bash
   python3 "${CLAUDE_PLUGIN_ROOT}/tare.py" trim
   ```

2. Show the plan. Explain the three groups in one line each:
   - **REMOVE** — never invoked in any recorded session.
   - **MOVE** — used, but only in one project. Scoping it there keeps the capability and stops
     every other project paying for it. This is usually the better option, and users often
     don't realise it exists.
   - **DELETE BY HAND** — agent and skill files. `tare` never deletes files; list them and let
     the user decide.

3. **Ask before applying.** Do not run `--apply` on your own initiative, and never in the same
   turn as the dry run. If they confirm:

   ```bash
   python3 "${CLAUDE_PLUGIN_ROOT}/tare.py" trim --apply
   ```

   It writes a timestamped backup to `~/.tare/backups/` before touching anything, and writes
   atomically. Tell the user where the backup is and that Claude Code needs a restart.

4. If anything looks wrong to them, `/tare:why <name>` shows the evidence behind that verdict.
   Trust their judgement over the tool's — a low count can mean the measurement has a gap.

## Important

This is the only part of `tare` that writes anything outside its own directory. Treat the
user's config as theirs: show the change, get a yes, keep the backup.
