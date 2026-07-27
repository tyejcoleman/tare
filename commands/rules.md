---
description: Which of this repo's CLAUDE.md rules actually fire?
allowed-tools: ["Bash", "Read"]
---

# rulecheck

Audit the rule files in this repo against the Claude Code sessions already recorded on disk.

## Steps

1. Run the checker. Pass `$ARGUMENTS` as the repo path if the user gave one, otherwise use the
   current working directory:

   ```bash
   python3 "${CLAUDE_PLUGIN_ROOT}/tare.py" rules $ARGUMENTS
   ```

2. Show the report output to the user as-is. It is already formatted — do not restate the whole
   table back to them.

3. Then add a short interpretation, no more than a few sentences:
   - If the report says **LOW EVIDENCE**, say plainly that the dead-letter number is not yet
     trustworthy for this repo and more sessions are needed. Do not spin a thin sample into a finding.
   - Name the single most surprising result — usually either a rule that has never once applied
     despite sitting in context on every run, or a high UNOBSERVABLE share.
   - For UNOBSERVABLE rules, the fix is usually to name a concrete path, command, or identifier in
     the rule text. Offer one rewritten example, using their actual rule.

4. Offer, but do not perform, the obvious next step: deleting or rewriting the dead letters.
   Editing someone's CLAUDE.md is their call.

## Important

- `FIRED` means the agent touched what the rule governs. It is **engagement, not compliance** — it
  does not prove the rule was obeyed. Never describe a FIRED rule as "followed".
- Use `python3 "${CLAUDE_PLUGIN_ROOT}/tare.py" rules --rule N` to show the evidence behind any single
  verdict if the user questions one.
