#!/usr/bin/env python3
"""
Every case tare claims to handle, tested against a synthetic world.

Run:  python3 tests/test_tare.py

The bar: tare tells people what to delete from their config, and --apply writes
to it. A silently wrong answer here costs someone a working setup. So the tests
assert the WRONG answers are impossible, not just that the right ones appear.
"""
from __future__ import annotations
import io
import json
import os
import subprocess
import sys
import time
import unittest
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from world import World, H, R, T, ROOT, slug, DAY   # noqa: E402


def run(fn, *a, **kw) -> tuple[int, str]:
    """Call something that prints, capture stdout."""
    buf = io.StringIO()
    with redirect_stdout(buf), redirect_stderr(buf):
        rc = fn(*a, **kw)
    return rc, buf.getvalue()


# ══════════════════════════════════════════════════════ harness: what's dead

class TestHarnessDetection(unittest.TestCase):

    def test_configured_never_called_is_dead(self):
        with World() as w:
            w.mcp("ghost")
            w.mcp("live")
            p = w.repo("app")
            w.session(p, [("mcp__live__do", {})])
            rows = w.rows("MCP servers")
            self.assertEqual(rows["ghost"]["calls"], 0)
            self.assertIsNone(rows["ghost"]["days"])
            self.assertEqual(rows["live"]["calls"], 1)

    def test_call_counts_are_exact(self):
        with World() as w:
            w.mcp("a")
            p = w.repo("app")
            w.session(p, [("mcp__a__x", {})] * 7)
            self.assertEqual(w.rows("MCP servers")["a"]["calls"], 7)

    def test_uncalled_server_not_in_config_is_not_reported(self):
        """We report on what you configured, never on what we happened to see."""
        with World() as w:
            w.mcp("a")
            p = w.repo("app")
            w.session(p, [("mcp__a__x", {}), ("mcp__stranger__y", {})])
            self.assertNotIn("stranger", w.rows("MCP servers"))

    def test_cold_vs_live(self):
        with World() as w:
            w.mcp("old"); w.mcp("new")
            p = w.repo("app")
            w.session(p, [("mcp__old__x", {})], age_days=40, name="old.jsonl")
            w.session(p, [("mcp__new__x", {})], age_days=0, name="new.jsonl")
            rows = w.rows("MCP servers")
            self.assertGreaterEqual(rows["old"]["days"], H.COLD_DAYS)
            self.assertLess(rows["new"]["days"], H.COLD_DAYS)

    def test_agents_and_skills_counted(self):
        with World() as w:
            w.agent("used"); w.agent("unused")
            w.skill("used-skill"); w.skill("unused-skill")
            p = w.repo("app")
            w.session(p, [("Task", {"subagent_type": "used"}),
                          ("Skill", {"skill": "used-skill"})])
            ag = w.rows("Subagents"); sk = w.rows("Skills")
            self.assertEqual(ag["used"]["calls"], 1)
            self.assertEqual(ag["unused"]["calls"], 0)
            self.assertEqual(sk["used-skill"]["calls"], 1)
            self.assertEqual(sk["unused-skill"]["calls"], 0)

    def test_tools_exposed_counts_mentions_not_just_calls(self):
        with World() as w:
            w.mcp("srv")
            p = w.repo("app")
            w.session(p, [("mcp__srv__alpha", {})],
                      mention=["mcp__srv__beta mcp__srv__gamma"])
            r = w.rows("MCP servers")["srv"]
            self.assertEqual(r["tools_used"], 1)
            self.assertEqual(r["tools_exposed"], 3)


# ══════════════════════════════════════════════════════ harness: misplaced

class TestMisplaced(unittest.TestCase):

    def test_single_project_global_server_is_misplaced(self):
        with World() as w:
            w.mcp("only-here")
            p = w.repo("one")
            w.session(p, [("mcp__only-here__x", {})])
            self.assertTrue(w.rows("MCP servers")["only-here"]["misplaced"])

    def test_two_projects_is_not_misplaced(self):
        with World() as w:
            w.mcp("shared")
            for n in ("one", "two"):
                w.session(w.repo(n), [("mcp__shared__x", {})])
            self.assertFalse(w.rows("MCP servers")["shared"]["misplaced"])

    def test_home_directory_is_not_a_project(self):
        """Scoping to ~ hides it everywhere — that is not scoping."""
        with World() as w:
            w.mcp("homey")
            w.session(w.home, [("mcp__homey__x", {})])
            self.assertFalse(w.rows("MCP servers")["homey"]["misplaced"])

    def test_project_scoped_server_is_never_misplaced(self):
        with World() as w:
            p = w.repo("one")
            w.mcp("scoped", project=p)
            w.session(p, [("mcp__scoped__x", {})])
            self.assertFalse(w.rows("MCP servers")["scoped"]["misplaced"])

    def test_dead_server_is_not_also_misplaced(self):
        with World() as w:
            w.mcp("ghost")
            w.session(w.repo("one"), [("Read", {"file_path": "x"})])
            r = w.rows("MCP servers")["ghost"]
            self.assertEqual(r["calls"], 0)
            self.assertFalse(r["misplaced"])


# ══════════════════════════════════════════════════════ harness: robustness

class TestHarnessRobustness(unittest.TestCase):

    def test_spaced_json_still_matches(self):
        """A transcript written with standard JSON spacing must not read as zero
        calls — that would tell someone to delete a server they use daily."""
        with World(compact_json=False) as w:
            w.mcp("srv")
            w.session(w.repo("app"), [("mcp__srv__x", {})] * 3)
            self.assertEqual(w.rows("MCP servers")["srv"]["calls"], 3)

    def test_corrupt_transcript_does_not_crash(self):
        with World() as w:
            w.mcp("srv")
            p = w.repo("app")
            w.session(p, [("mcp__srv__x", {})])
            w.raw_session(p, '{"broken": [[[\n\x00\xff not json at all\n')
            self.assertEqual(w.rows("MCP servers")["srv"]["calls"], 1)

    def test_empty_transcript_dir(self):
        with World() as w:
            w.mcp("srv")
            rows = w.rows("MCP servers")
            self.assertEqual(rows["srv"]["calls"], 0)

    def test_missing_projects_dir_errors_cleanly(self):
        with World() as w:
            import shutil
            shutil.rmtree(w.projects)
            self.assertIn("error", H.scan(None))

    def test_unreadable_config_is_survivable(self):
        with World() as w:
            w.config.write_text("{ not json")
            self.assertEqual(H.configured_mcp(), {})

    def test_oversized_transcript_is_skipped_not_read(self):
        with World() as w:
            w.mcp("srv")
            p = w.repo("app")
            f = w.session(p, [("mcp__srv__x", {})])
            os.truncate(f, H.MAX_FILE + 1)
            self.assertEqual(w.rows("MCP servers")["srv"]["calls"], 0)


# ══════════════════════════════════════════════════════ harness: windowing

class TestWindow(unittest.TestCase):

    def test_days_window_excludes_older_sessions(self):
        with World() as w:
            w.mcp("srv")
            w.session(w.repo("app"), [("mcp__srv__x", {})], age_days=60)
            self.assertEqual(H.scan(None)["mcp_calls"].get("srv"), 1)
            self.assertIsNone(H.scan(7)["mcp_calls"].get("srv"))

    def test_windowed_report_never_says_never(self):
        """'NEVER USED' is a lie about a record we only partly read."""
        with World() as w:
            w.mcp("srv")
            w.session(w.repo("app"), [("mcp__srv__x", {})], age_days=60)
            scanned = H.scan(7)
            _, out = run(H.report, scanned, H.assess(scanned), 7, tty=False)
            self.assertIn("unused in 7d", out)
            self.assertNotIn("NEVER USED", out)

    def test_windowed_summary_does_not_claim_it_gives_nothing_back(self):
        """Over a window we only know it didn't come up — not that it's useless."""
        with World() as w:
            w.mcp("srv")
            w.session(w.repo("app"), [("mcp__srv__x", {})], age_days=60)
            scanned = H.scan(7)
            _, out = run(H.report, scanned, H.assess(scanned), 7, tty=False)
            self.assertNotIn("giving nothing back", out)
            self.assertIn("did not come up once", out)

    def test_unwindowed_summary_does_make_the_strong_claim(self):
        with World() as w:
            w.mcp("srv")
            w.session(w.repo("app"), [("Read", {"file_path": "x"})])
            scanned = H.scan(None)
            _, out = run(H.report, scanned, H.assess(scanned), None, tty=False)
            self.assertIn("giving nothing back", out)

    def test_barely_used_is_not_called_earning_its_place(self):
        """Two projects, so it is not 'misplaced' — just hardly ever used.
        One call four months ago must not read as earning its keep."""
        with World() as w:
            w.mcp("rare")
            for n in ("one", "two"):
                w.session(w.repo(n), [("mcp__rare__x", {})])
            _, out = run(T.cmd_why, "rare", False)
            self.assertNotIn("Earning its place", out)
            self.assertIn("Barely used", out)

    def test_well_used_is_called_earning_its_place(self):
        with World() as w:
            w.mcp("busy")
            for n in ("one", "two"):
                w.session(w.repo(n), [("mcp__busy__x", {})] * 5)
            _, out = run(T.cmd_why, "busy", False)
            self.assertIn("Earning its place", out)

    def test_rules_panel_is_branded_tare_not_rulecheck(self):
        with World() as w:
            p = w.repo("app")
            w.claude_md(p, "- You must update `docs/changelog.md` every single time.\n")
            rules = R.parse_rules(p)
            sessions = [{"id": "s", "text": "x", "tool_calls": 500}]
            R.evaluate(rules, sessions)
            _, out = run(R.report, p, rules, sessions, tty=False)
            self.assertIn("tare · rules", out)
            self.assertNotIn("rulecheck", out)

    def test_unwindowed_report_does_say_never(self):
        with World() as w:
            w.mcp("srv")
            w.session(w.repo("app"), [("Read", {"file_path": "x"})])
            scanned = H.scan(None)
            _, out = run(H.report, scanned, H.assess(scanned), None, tty=False)
            self.assertIn("NEVER USED", out)


# ══════════════════════════════════════════════════════ trim: the writing path

class TestTrim(unittest.TestCase):

    def _world(self):
        w = World().__enter__()
        w.mcp("dead")
        w.mcp("scoped-elsewhere")
        w.mcp("busy")
        one = w.repo("one")
        w.known_project(one)
        w.session(one, [("mcp__scoped-elsewhere__x", {})])
        for n in ("one", "two"):
            w.session(w.repo(n), [("mcp__busy__x", {})], name="busy.jsonl")
        w.write_config()
        return w, one

    def test_dry_run_changes_nothing(self):
        w, _ = self._world()
        try:
            before = w.config.read_text()
            rc, out = run(T.cmd_trim, False, False)
            self.assertEqual(rc, 0)
            self.assertEqual(w.config.read_text(), before)
            self.assertIn("Dry run", out)
            self.assertFalse(T.HOME_BACKUP.exists())
        finally:
            w.__exit__()

    def test_plan_separates_dead_from_misplaced(self):
        w, one = self._world()
        try:
            drop, scope, _, _u = T._plan(H.scan(None))
            self.assertIn("dead", drop)
            self.assertNotIn("scoped-elsewhere", drop)
            self.assertEqual(scope, [("scoped-elsewhere", str(one))])
        finally:
            w.__exit__()

    def test_apply_removes_dead_and_moves_misplaced(self):
        w, one = self._world()
        try:
            rc, _ = run(T.cmd_trim, True, False)
            self.assertEqual(rc, 0)
            conf = w.read_config()
            self.assertNotIn("dead", conf["mcpServers"])
            self.assertNotIn("scoped-elsewhere", conf["mcpServers"])
            self.assertIn("busy", conf["mcpServers"])
            moved = conf["projects"][str(one)]["mcpServers"]
            self.assertIn("scoped-elsewhere", moved)
            self.assertEqual(moved["scoped-elsewhere"],
                             {"command": "scoped-elsewhere-server"})
        finally:
            w.__exit__()

    def test_apply_writes_a_backup_first(self):
        w, _ = self._world()
        try:
            before = w.config.read_text()
            run(T.cmd_trim, True, False)
            backups = list(T.HOME_BACKUP.glob("claude.json.*"))
            self.assertEqual(len(backups), 1)
            self.assertEqual(backups[0].read_text(), before)
        finally:
            w.__exit__()

    def test_apply_never_deletes_files(self):
        w, _ = self._world()
        try:
            w.agent("never-used")
            w.skill("never-used-skill")
            run(T.cmd_trim, True, False)
            self.assertTrue((w.agents / "never-used.md").exists())
            self.assertTrue((w.skills / "never-used-skill" / "SKILL.md").exists())
        finally:
            w.__exit__()

    def test_unused_files_are_listed_for_the_human(self):
        w, _ = self._world()
        try:
            w.agent("never-used")
            _, out = run(T.cmd_trim, False, False)
            self.assertIn("DELETE BY HAND", out)
            self.assertIn("never-used.md", out)
        finally:
            w.__exit__()

    def test_unplaceable_server_is_surfaced_never_silently_dropped(self):
        """The slug is lossy. If we cannot verify the path we say so out loud —
        silently omitting it would read as 'nothing to do here'."""
        with World() as w:
            w.mcp("orphan")                       # no known_project() for it
            w.session(w.repo("nowhere"), [("mcp__orphan__x", {})])
            drop, scope, _f, unresolved = T._plan(H.scan(None))
            self.assertEqual(scope, [])
            self.assertEqual(drop, [])
            self.assertEqual([n for n, _ in unresolved], ["orphan"])
            _, out = run(T.cmd_trim, False, False)
            self.assertIn("MOVE BY HAND", out)
            self.assertIn("orphan", out)

    def test_unplaceable_server_is_never_moved_by_apply(self):
        with World() as w:
            w.mcp("orphan")
            w.session(w.repo("nowhere"), [("mcp__orphan__x", {})])
            run(T.cmd_trim, True, False)
            self.assertIn("orphan", w.read_config()["mcpServers"])

    def test_nothing_to_trim_says_so(self):
        with World() as w:
            w.mcp("busy")
            for n in ("one", "two"):
                w.session(w.repo(n), [("mcp__busy__x", {})])
            _, out = run(T.cmd_trim, False, False)
            self.assertIn("Nothing to trim", out)

    def test_apply_is_idempotent(self):
        w, _ = self._world()
        try:
            run(T.cmd_trim, True, False)
            first = w.read_config()
            run(T.cmd_trim, True, False)
            self.assertEqual(w.read_config()["mcpServers"], first["mcpServers"])
        finally:
            w.__exit__()

    def test_config_stays_valid_json_after_apply(self):
        w, _ = self._world()
        try:
            run(T.cmd_trim, True, False)
            json.loads(w.config.read_text())      # raises if we corrupted it
            self.assertFalse(list(w.home.glob("*.tare-tmp")))
        finally:
            w.__exit__()


# ══════════════════════════════════════════════════════ rules: classification

class TestRules(unittest.TestCase):

    def _rules(self, w, body):
        p = w.repo("app")
        w.claude_md(p, body)
        return p, R.parse_rules(p)

    def test_obligation_never_matched_is_dormant(self):
        with World() as w:
            p, rules = self._rules(w, "- You must update `docs/changelog.md` every time.\n")
            R.evaluate(rules, [{"id": "s", "text": "unrelated", "tool_calls": 5}])
            self.assertEqual(rules[0]["status"], "DORMANT")

    def test_prohibition_never_matched_is_a_guardrail(self):
        """Silence is what a working prohibition looks like."""
        with World() as w:
            p, rules = self._rules(w, "- Never run `git push --force` on main.\n")
            self.assertEqual(rules[0]["kind"], "prohibition")
            R.evaluate(rules, [{"id": "s", "text": "unrelated", "tool_calls": 5}])
            self.assertEqual(rules[0]["status"], "GUARDRAIL")

    def test_prohibition_matched_is_fired_not_guardrail(self):
        with World() as w:
            p, rules = self._rules(w, "- Never run `git push --force` on main.\n")
            R.evaluate(rules, [{"id": "s", "text": "git push --force", "tool_calls": 5}])
            self.assertEqual(rules[0]["status"], "FIRED")

    def test_leading_no_counts_as_prohibition(self):
        with World() as w:
            p, rules = self._rules(w, "- **No service-role key in `src/client.ts`.**\n")
            self.assertEqual(rules[0]["kind"], "prohibition")

    def test_prose_rule_without_anchor_is_unobservable(self):
        with World() as w:
            p, rules = self._rules(w, "- You must always prefer clarity over cleverness.\n")
            R.evaluate(rules, [{"id": "s", "text": "x", "tool_calls": 5}])
            self.assertEqual(rules[0]["status"], "UNOBSERVABLE")
            self.assertEqual(rules[0]["literals"], [])

    def test_code_fences_are_not_rules(self):
        with World() as w:
            p, rules = self._rules(
                w, "```bash\nyou must never do this\n```\n- Real rule: never touch `db/x.sql`.\n")
            self.assertEqual(len(rules), 1)

    def test_hard_wrapped_prose_is_one_rule_not_fragments(self):
        with World() as w:
            p, rules = self._rules(
                w, "Provider credentials must never enter the repository, prompts,\n"
                   "logs, artifacts, or child test environments under `config/`.\n")
            self.assertEqual(len(rules), 1)
            self.assertIn("child test environments", rules[0]["text"])

    def test_bold_directive_without_a_modal_is_still_a_rule(self):
        with World() as w:
            p, rules = self._rules(w, "- **Migrations are forward-only in `db/migrate/`.**\n")
            self.assertEqual(len(rules), 1)

    def test_duplicates_collapse(self):
        with World() as w:
            line = "- You must update `docs/changelog.md` every time.\n"
            p, rules = self._rules(w, line + line)
            self.assertEqual(len(rules), 1)

    def test_key_is_stable_across_position_and_changes_with_text(self):
        with World() as w:
            a = self._rules(w, "- Never touch `db/x.sql` directly.\n")[1][0]
            b = self._rules(w, "- Filler must exist in `z/y.md`.\n"
                               "- Never touch `db/x.sql` directly.\n")[1][1]
            self.assertEqual(a["key"], b["key"])
            c = self._rules(w, "- Never touch `db/other.sql` directly.\n")[1][0]
            self.assertNotEqual(a["key"], c["key"])

    def test_backticked_prose_is_not_a_literal(self):
        with World() as w:
            p, rules = self._rules(w, "- You must always `be careful here` when editing.\n")
            self.assertEqual(rules[0]["literals"], [])


# ══════════════════════════════════════════════════════ rules: paths & guards

class TestRulesPlumbing(unittest.TestCase):

    def test_project_dir_resolves_paths_with_spaces(self):
        with World() as w:
            p = w.repo("Hotel Portal")
            w.session(p, [("Read", {"file_path": "x"})])
            self.assertEqual(R.project_dir_for(p), w.projects / slug(p))

    def test_low_evidence_suppresses_the_dead_letter_rate(self):
        with World() as w:
            p = w.repo("app")
            w.claude_md(p, "- You must update `docs/changelog.md`.\n")
            rules = R.parse_rules(p)
            R.evaluate(rules, [{"id": "s", "text": "x", "tool_calls": 3}])
            _, out = run(R.report, p, rules, [{"tool_calls": 3, "id": "s"}], tty=False)
            self.assertIn("LOW EVIDENCE", out)
            self.assertNotIn("have never once applied", out)

    def test_enough_evidence_reports_the_rate(self):
        with World() as w:
            p = w.repo("app")
            w.claude_md(p, "- You must update `docs/changelog.md`.\n")
            rules = R.parse_rules(p)
            sessions = [{"id": "s", "text": "x", "tool_calls": 500}]
            R.evaluate(rules, sessions)
            _, out = run(R.report, p, rules, sessions, tty=False)
            self.assertNotIn("LOW EVIDENCE", out)
            self.assertIn("have never once applied", out)

    def test_guardrails_excluded_from_the_dead_letter_count(self):
        with World() as w:
            p = w.repo("app")
            w.claude_md(p, "- Never run `git push --force`.\n"
                           "- You must update `docs/changelog.md`.\n")
            rules = R.parse_rules(p)
            sessions = [{"id": "s", "text": "nothing", "tool_calls": 500}]
            R.evaluate(rules, sessions)
            _, out = run(R.report, p, rules, sessions, tty=False)
            self.assertIn("50% of your obligations", out)

    def test_no_rule_file_is_an_error_not_an_empty_report(self):
        with World() as w:
            p = w.repo("bare")
            sys.argv = ["tare", str(p)]
            rc, out = run(R.main)
            self.assertEqual(rc, 1)
            self.assertIn("No rule file found", out)

    def test_missing_directory_is_rejected(self):
        with World() as w:
            sys.argv = ["tare", str(w.home / "nope")]
            rc, out = run(R.main)
            self.assertEqual(rc, 2)
            self.assertIn("not a directory", out)


# ══════════════════════════════════════════════════════ hook: must never break

class TestHook(unittest.TestCase):
    HOOK = ROOT / "hooks" / "session_record.py"

    def _run(self, payload: str, env_home: Path) -> int:
        env = dict(os.environ, HOME=str(env_home))
        p = subprocess.run([sys.executable, str(self.HOOK)], input=payload,
                           text=True, capture_output=True, env=env, timeout=60)
        return p.returncode

    def test_every_bad_input_exits_zero(self):
        with World() as w:
            for payload in ("", "not json", "{}", '{"cwd":"/nope"}',
                            '{"cwd":"/tmp","transcript_path":"/nope/x.jsonl"}',
                            '{"cwd":null,"transcript_path":null}',
                            '[1,2,3]'):
                self.assertEqual(self._run(payload, w.home), 0, payload)

    def test_repo_without_rules_writes_nothing(self):
        with World() as w:
            p = w.repo("bare")
            f = w.session(p, [("Read", {"file_path": "a"})])
            self._run(json.dumps({"cwd": str(p), "transcript_path": str(f),
                                  "session_id": "abc"}), w.home)
            self.assertFalse((w.home / ".tare" / "history.jsonl").exists())

    def test_records_one_line_with_the_rules_it_engaged(self):
        with World() as w:
            p = w.repo("app")
            w.claude_md(p, "- Never touch the file `db/x.sql` directly, ever.\n"
                           "- You must update `docs/changelog.md` every single time.\n")
            f = w.session(p, [("Edit", {"file_path": "db/x.sql"})])
            rc = self._run(json.dumps({"cwd": str(p), "transcript_path": str(f),
                                       "session_id": "abcdef12"}), w.home)
            self.assertEqual(rc, 0)
            lines = (w.home / ".tare" / "history.jsonl").read_text().strip().split("\n")
            self.assertEqual(len(lines), 1)
            row = json.loads(lines[0])
            self.assertEqual(row["rules"], 2)
            self.assertEqual(row["tool_calls"], 1)
            self.assertEqual(len(row["fired"]), 1)

    def test_session_with_no_tool_calls_records_nothing(self):
        with World() as w:
            p = w.repo("app")
            w.claude_md(p, "- Never touch the file `db/x.sql` directly, ever.\n")
            f = w.raw_session(p, '{"type":"assistant","message":{"content":[]}}\n')
            self._run(json.dumps({"cwd": str(p), "transcript_path": str(f),
                                  "session_id": "x"}), w.home)
            self.assertFalse((w.home / ".tare" / "history.jsonl").exists())


# ══════════════════════════════════════════════════════ history

class TestHistory(unittest.TestCase):

    def test_quiet_prohibitions_are_not_listed_as_never_fired(self):
        with World() as w:
            p = w.repo("app")
            w.claude_md(p, "- Never run `git push --force`.\n"
                           "- You must update `docs/changelog.md`.\n")
            rules = R.parse_rules(p)
            R.HISTORY.parent.mkdir(parents=True, exist_ok=True)
            R.HISTORY.write_text(json.dumps({
                "ts": "2026-07-01T00:00:00+00:00", "session": "a",
                "repo": str(p), "rules": 2, "checkable": 2,
                "tool_calls": 300, "fired": []}) + "\n")
            _, out = run(R.history_report, p, rules, R.load_history(p), tty=False)
            self.assertIn("changelog", out)
            self.assertIn("prohibitions also never fired", out)
            self.assertNotIn("git push --force", out.split("LAST SEEN")[0])

    def test_history_for_another_repo_is_ignored(self):
        with World() as w:
            p, q = w.repo("app"), w.repo("other")
            R.HISTORY.parent.mkdir(parents=True, exist_ok=True)
            R.HISTORY.write_text(json.dumps({"ts": "2026-07-01T00:00:00+00:00",
                                             "repo": str(q), "fired": []}) + "\n")
            self.assertEqual(R.load_history(p), [])

    def test_corrupt_history_lines_are_skipped(self):
        with World() as w:
            p = w.repo("app")
            R.HISTORY.parent.mkdir(parents=True, exist_ok=True)
            R.HISTORY.write_text("{bad\n" + json.dumps(
                {"ts": "2026-07-01T00:00:00+00:00", "repo": str(p), "fired": []}) + "\n")
            self.assertEqual(len(R.load_history(p)), 1)


# ══════════════════════════════════════════════════════ determinism & CLI

class TestDeterminismAndCLI(unittest.TestCase):

    def test_same_world_gives_identical_json_twice(self):
        with World() as w:
            w.mcp("a"); w.agent("b"); w.skill("c")
            w.session(w.repo("app"), [("mcp__a__x", {})])
            a = json.dumps(H.assess(H.scan(None)), sort_keys=True)
            b = json.dumps(H.assess(H.scan(None)), sort_keys=True)
            self.assertEqual(a, b)

    def test_reported_totals_match_the_rows(self):
        """The headline number must equal what the table shows."""
        with World() as w:
            for n in ("d1", "d2", "live"):
                w.mcp(n)
            w.session(w.repo("app"), [("mcp__live__x", {})])
            w.agent("dead-agent")
            scanned = H.scan(None)
            a = H.assess(scanned)
            rows = [r for g in a["groups"] for r in g["rows"]]
            dead = sum(1 for r in rows if r["calls"] == 0)
            _, out = run(H.report, scanned, a, None, tty=False)
            self.assertIn(f"{dead}  never used", out)

    def test_cli_entrypoints_all_exit_cleanly(self):
        for args in (["--version"], ["-h"]):
            p = subprocess.run([sys.executable, str(ROOT / "tare.py"), *args],
                               capture_output=True, text=True, timeout=120)
            self.assertEqual(p.returncode, 0, p.stderr)

    def test_why_on_unknown_name_fails_loudly(self):
        with World() as w:
            rc, out = run(T.cmd_why, "does-not-exist", False)
            self.assertEqual(rc, 1)
            self.assertIn("not a configured", out)

    def test_why_reports_never_for_a_dead_server(self):
        with World() as w:
            w.mcp("ghost")
            w.session(w.repo("app"), [("Read", {"file_path": "x"})])
            rc, out = run(T.cmd_why, "ghost", False)
            self.assertEqual(rc, 0)
            self.assertIn("never", out)
            self.assertIn("Never invoked", out)


if __name__ == "__main__":
    unittest.main(verbosity=2)
