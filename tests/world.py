#!/usr/bin/env python3
"""
A synthetic world for testing tare.

Builds a complete fake home directory — transcripts, config, agents, skills,
repos — so every code path can be exercised against known ground truth instead
of against whatever happens to be on the developer's machine.

Nothing here touches the real ~/.claude anything.
"""
from __future__ import annotations
import json
import os
import re
import shutil
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import harness as H          # noqa: E402
import rulecheck as R        # noqa: E402
import tare as T             # noqa: E402

DAY = 86400


def slug(p) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "-", str(p))


class World:
    """A disposable fake $HOME. Use as a context manager."""

    def __init__(self, compact_json: bool = True):
        self.compact = compact_json
        # resolve(): macOS symlinks /tmp -> /private/tmp, and the slug is built
        # from a resolved path. Without this the fake world's transcript dirs
        # never match, which looks exactly like a tool bug.
        self.dir = Path(tempfile.mkdtemp(prefix="tare-world-")).resolve()
        self.home = self.dir / "home"
        self.projects = self.home / ".claude" / "projects"
        self.agents = self.home / ".claude" / "agents"
        self.skills = self.home / ".claude" / "skills"
        self.config = self.home / ".claude.json"
        for d in (self.projects, self.agents, self.skills):
            d.mkdir(parents=True, exist_ok=True)
        self._conf = {"mcpServers": {}, "projects": {}}
        self._saved = {}

    # ---------------------------------------------------------------- content

    def repo(self, name: str) -> Path:
        p = self.home / "work" / name
        p.mkdir(parents=True, exist_ok=True)
        return p

    def claude_md(self, repo: Path, text: str) -> None:
        (repo / "CLAUDE.md").write_text(text)

    def mcp(self, name: str, project: Path | None = None) -> None:
        """Configure a server, globally or scoped to a project."""
        spec = {"command": f"{name}-server"}
        if project is None:
            self._conf["mcpServers"][name] = spec
        else:
            self._conf["projects"].setdefault(str(project), {}) \
                .setdefault("mcpServers", {})[name] = spec
        self.write_config()   # tests configure servers after entering the world

    def known_project(self, path: Path) -> None:
        """Claude Code records every project you open. tare will only move a
        server to a path it can verify against that record."""
        self._conf["projects"].setdefault(str(path), {})
        self.write_config()

    def agent(self, name: str) -> None:
        (self.agents / f"{name}.md").write_text(f"# {name}\n")

    def skill(self, name: str) -> None:
        d = self.skills / name
        d.mkdir(parents=True, exist_ok=True)
        (d / "SKILL.md").write_text(f"# {name}\n")

    def session(self, project: Path, calls: list[tuple[str, dict]],
                age_days: float = 0, name: str | None = None,
                mention: list[str] | None = None) -> Path:
        """Write one transcript. calls is [(tool_name, input_dict), ...]."""
        d = self.projects / slug(project)
        d.mkdir(parents=True, exist_ok=True)
        f = d / (name or f"s{len(list(d.glob('*.jsonl')))}.jsonl")

        sep = (",", ":") if self.compact else None
        lines = []
        for tool, inp in calls:
            rec = {"type": "assistant",
                   "message": {"content": [
                       {"type": "tool_use", "id": "t1", "name": tool, "input": inp}]}}
            lines.append(json.dumps(rec, separators=sep) if sep
                         else json.dumps(rec))
        # tool names that merely APPEAR (a listing), never called
        for m in (mention or []):
            lines.append(json.dumps({"type": "system", "text": m}))
        f.write_text("\n".join(lines) + "\n")

        if age_days:
            t = time.time() - age_days * DAY
            os.utime(f, (t, t))
        return f

    def raw_session(self, project: Path, text: str, name="raw.jsonl") -> Path:
        d = self.projects / slug(project)
        d.mkdir(parents=True, exist_ok=True)
        f = d / name
        f.write_text(text)
        return f

    def write_config(self) -> None:
        self.config.write_text(json.dumps(self._conf, indent=2))

    # ------------------------------------------------------------- activation

    def __enter__(self) -> "World":
        self.write_config()
        self._saved = {
            "H.HOME": H.HOME, "H.PROJECTS": H.PROJECTS, "H.CONFIG": H.CONFIG,
            "H.AGENTS_DIR": H.AGENTS_DIR, "H.SKILLS_DIR": H.SKILLS_DIR,
            "H._HOME_SLUG": H._HOME_SLUG, "R.HISTORY": R.HISTORY,
            "T.HOME_BACKUP": T.HOME_BACKUP, "R.PROJECTS": R.PROJECTS,
        }
        R.PROJECTS = self.projects
        H.HOME = self.home
        H.PROJECTS = self.projects
        H.CONFIG = self.config
        H.AGENTS_DIR = self.agents
        H.SKILLS_DIR = self.skills
        H._HOME_SLUG = slug(self.home)
        R.HISTORY = self.home / ".tare" / "history.jsonl"
        T.HOME_BACKUP = self.home / ".tare" / "backups"
        return self

    def __exit__(self, *a) -> None:
        H.HOME = self._saved["H.HOME"]
        H.PROJECTS = self._saved["H.PROJECTS"]
        H.CONFIG = self._saved["H.CONFIG"]
        H.AGENTS_DIR = self._saved["H.AGENTS_DIR"]
        H.SKILLS_DIR = self._saved["H.SKILLS_DIR"]
        H._HOME_SLUG = self._saved["H._HOME_SLUG"]
        R.HISTORY = self._saved["R.HISTORY"]
        R.PROJECTS = self._saved["R.PROJECTS"]
        T.HOME_BACKUP = self._saved["T.HOME_BACKUP"]
        shutil.rmtree(self.dir, ignore_errors=True)

    # ----------------------------------------------------------------- helpers

    def rows(self, title: str) -> dict:
        """assess() rows for one group, keyed by name."""
        a = H.assess(H.scan(None))
        for g in a["groups"]:
            if g["title"] == title:
                return {r["name"]: r for r in g["rows"]}
        return {}

    def read_config(self) -> dict:
        return json.loads(self.config.read_text())
