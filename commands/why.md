---
description: The evidence behind one tare verdict
allowed-tools: ["Bash", "Read"]
---

# tare why

Show the full evidence for a single MCP server, subagent or skill — invocation count, last use,
which tools were actually called, and which projects used it.

## Steps

1. Run:

   ```bash
   python3 "${CLAUDE_PLUGIN_ROOT}/tare.py" why $ARGUMENTS
   ```

2. Show the output. If the user is pushing back on a verdict, this is the receipt — walk them
   through what was and wasn't found rather than defending the number.

3. If it comes back never-invoked and they want it gone, show them the exact edit to
   `~/.claude.json` **as a diff, before touching anything**, and back the file up first.

## Important

Every number here comes from recorded tool calls. If the evidence looks wrong to the user, it is
more likely the measurement has a gap than that they are misremembering — take the report
seriously and say what the measurement can and cannot see.
