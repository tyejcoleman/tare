# How this tool behaves

Four commitments. They're constraints, not features — each one costs something,
and that's the point.

**1 · No model in the verdict.**
Every number is a recorded fact or a literal match. The same input always gives the
same answer, nothing is invented, and any verdict can be audited with `tare why`.
An earlier prototype put a model in this seat and scored AUC 0.465 — below chance.
Anything that ever asks a model to adjudicate passes that kill test first.

**2 · No number it can't defend.**
Under 150 recorded tool calls it refuses to report a dead-letter rate. A windowed run
says "unused in 30d", never "never used". "We didn't look" and "it never happened" are
different claims, and conflating them is worse than saying nothing.

**3 · Your config is yours.**
It will tell you what's dead. It won't remove it. `--apply` shows the change first,
writes a timestamped backup, and never touches your files — only the config you asked
it to edit. It will not guess a path it cannot verify.

**4 · The limits are published.**
"Fired" means engagement, not compliance. "Never used" means never recorded as invoked.
Tool counts are a floor, not a schema read. Every one of these is in the README, stated
before anyone has to discover it.

Local. No account, no network, no telemetry. The only file it writes outside its own
directory is `~/.tare/history.jsonl`, on your machine.
