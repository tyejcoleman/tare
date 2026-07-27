---
description: What is your agent harness actually carrying?
allowed-tools: ["Bash", "Read"]
---

# tare

Audit this machine's harness: every MCP server, subagent and skill that is configured, against
what has actually been invoked in recorded sessions.

## Steps

1. Run it. Pass `$ARGUMENTS` through if the user gave any (e.g. `--days 30`):

   ```bash
   python3 "${CLAUDE_PLUGIN_ROOT}/tare.py" $ARGUMENTS
   ```

2. Show the output as-is. It is already formatted — do not restate the table.

3. Add a short interpretation, a few sentences at most:
   - Lead with the single most striking line. Usually that is something they built or connected
     themselves and have never once invoked.
   - Separate **dead** from **misplaced**. A server used in exactly one project doesn't want
     deleting, it wants scoping to that project — they keep the capability and stop every other
     project paying for it. Say which is which.
   - If nothing is dead, say so plainly rather than manufacturing a finding.

4. Offer `/tare:why <name>` for anything they question, and offer to show them the exact config
   edit for anything they want to remove. **Never edit their config yourself without being asked
   and showing the change first.**

## Important

- "Never used" means never *recorded as invoked*. A skill loaded some other way, or used before
  it was added to the config, will not appear. Say so if a user is surprised by a result.
- These are facts from transcripts, not judgements. Do not soften them, and do not inflate them.
