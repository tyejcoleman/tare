---
description: Show the accruing record — when each rule last fired
allowed-tools: ["Bash", "Read"]
---

# rulecheck history

A single run only sees the transcripts still on disk. The session hook records one compact line per
session to `~/.rulecheck/history.jsonl`, so the record keeps accruing even as transcripts age out.

## Steps

1. Run:

   ```bash
   python3 "${CLAUDE_PLUGIN_ROOT}/rulecheck.py" --history $ARGUMENTS
   ```

2. Show the output. Then say, briefly, what changed — a rule that has gone quiet, or one that has
   never fired across the whole recorded window.

3. If the history is empty or very short, say so honestly: the hook has not been running long enough
   yet, and there is nothing to conclude. A trend needs weeks, not one session.

## Important

Everything here is local. The history file is on this machine only and nothing is ever sent anywhere.
