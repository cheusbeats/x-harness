"""Integration tests for Codex's adapter to the original Claude hooks."""

# Герметичность: переменные среды Claude Code/git-хука не должны течь в подпроцессы фикстур (хуки делают
# `cd "${CLAUDE_PROJECT_DIR:-.}"` и ушли бы в настоящий репозиторий).
import os as _os
for _v in [k for k in _os.environ if k.startswith("GIT_") or k == "CLAUDE_PROJECT_DIR"]:
    _os.environ.pop(_v, None)

import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import tomllib
import unittest


PROJECT = Path(__file__).resolve().parents[2]
HOOKS = {"plans-drift", "branch-guard", "commit-gate", "merge-gate", "main-push-guard", "db-wipe-guard", "big-read-guard", "registry-guard", "owner-ok-guard"}


class ClaudeCompatTest(unittest.TestCase):
    def test_codex_rules_and_all_skills_resolve_to_claude_sources(self):
        agents = PROJECT / "AGENTS.md"
        skills = PROJECT / ".agents/skills"
        self.assertTrue(agents.is_symlink())
        self.assertEqual(agents.resolve(), (PROJECT / "CLAUDE.md").resolve())
        self.assertTrue(skills.is_symlink())
        self.assertEqual(skills.resolve(), (PROJECT / ".claude/skills").resolve())
        for source in (PROJECT / ".claude/skills").iterdir():
            if source.is_dir():
                with self.subTest(skill=source.name):
                    self.assertEqual((skills / source.name).resolve(), source.resolve())

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.repo = Path(self.temp.name) / "repo"
        self.repo.mkdir()
        self.git("init", "-b", "main")
        self.git("config", "user.email", "test@example.invalid")
        self.git("config", "user.name", "Hook Test")
        self.git("-c", "core.hooksPath=/dev/null", "commit", "--allow-empty", "-m", "fixture")
        hooks = self.repo / ".claude/hooks"
        hooks.mkdir(parents=True)
        for name in HOOKS:
            shutil.copy2(PROJECT / ".claude/hooks" / (name + ".sh"), hooks)
        for helper in ("paths.py", "paths.conf", "commit_checks.py", "owner_ok.py", "merge_checks.py", "db_wipe_checks.py", "money-paths.txt"):
            shutil.copy2(PROJECT / ".claude/hooks" / helper, hooks)
        if not shutil.which("jq"):
            self.fail("Original hooks require jq")

    def git(self, *args):
        return subprocess.run(["git", "-C", str(self.repo), *args], check=True,
                              capture_output=True, text=True).stdout.strip()

    def run_hook(self, name, tool="exec_command", command="", **tool_input):
        payload = {"cwd": str(self.repo), "tool_name": tool,
                   "tool_input": {"cmd": command, **tool_input}}
        env = dict(os.environ)
        env.pop("BIG_READ_MIN_LINES", None)
        return subprocess.run([sys.executable, "-B", str(PROJECT / ".codex/hooks/claude-compat.py"), name],
                              input=json.dumps(payload), capture_output=True, text=True, env=env)

    def assert_status(self, result, status):
        self.assertEqual(result.returncode, status, result.stdout + result.stderr)

    def script(self, name, content):
        path = self.repo / ".claude/scripts" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("#!/bin/sh\n" + content)
        path.chmod(0o755)

    def test_branch_guard_blocks_main_and_allows_feature(self):
        for branch, status in [("main", 2), ("feature/test", 0)]:
            if branch != "main":
                self.git("checkout", "-b", branch)
            self.assert_status(self.run_hook("branch-guard", "apply_patch",
                                            "*** Add File: new/nested/file.txt\n+x"), status)

    def test_patch_checks_each_file_and_move_destination_in_other_worktree(self):
        self.git("checkout", "-b", "feature/test")
        other = Path(self.temp.name) / "main-worktree"
        self.git("worktree", "add", str(other), "main")
        for directive in ["Add File", "Update File", "Delete File", "Move to"]:
            with self.subTest(directive=directive):
                patch = ("*** Add File: allowed.txt\n+x\n"
                         f"*** {directive}: {other}/new/nested/blocked.txt\n+x")
                self.assert_status(self.run_hook("branch-guard", "apply_patch", patch), 2)

    def test_registry_guard_blocks_index_patch_and_allows_plan(self):
        self.git("checkout", "-b", "feature/PLAN-1-x")
        self.assert_status(self.run_hook("registry-guard", "apply_patch",
                                         "*** Update File: planning/ROADMAP.md\n+x"), 2)
        self.assert_status(self.run_hook("registry-guard", "apply_patch",
                                         "*** Add File: planning/plans/PLAN-1-x.md\n+x"), 0)

    def test_db_wipe_guard_blocks_dev_database_and_allows_testing(self):
        self.assert_status(self.run_hook("db-wipe-guard", command="docker exec c php artisan db:wipe"), 2)
        self.assert_status(self.run_hook("db-wipe-guard", command="docker exec -e DB_DATABASE=testing c php artisan db:wipe"), 0)

    def test_commit_gate_blocks_no_verify(self):
        self.git("checkout", "-b", "feature/PLAN-1-x")
        self.assert_status(self.run_hook("commit-gate", command="git commit -n -m x"), 2)

    def test_commit_gate_blocks_main(self):
        self.assert_status(self.run_hook("commit-gate", command="git commit -m test"), 2)

    def test_commit_gate_judges_workdir_not_session_cwd(self):
        self.git("checkout", "-q", "-b", "feature/PLAN-1-x")
        wt = Path(self.temp.name) / "wt"
        self.git("worktree", "add", "-q", str(wt), "main")
        shutil.copytree(self.repo / ".claude", wt / ".claude")
        self.assert_status(self.run_hook("commit-gate", command="git commit -m test", workdir=str(wt)), 2)

    def test_commit_gate_blocks_secret_scanner_failure(self):
        self.git("checkout", "-b", "feature/test")
        self.script("scan-secrets.sh", "cat >/dev/null\necho secret-fixture\nexit 1\n")
        result = self.run_hook("commit-gate", command="git commit -m test")
        self.assert_status(result, 2)
        self.assertIn("secret-fixture", result.stderr)

    def test_commit_gate_runs_fast_gate_and_blocks_failure(self):
        self.git("checkout", "-b", "feature/test")
        self.script("quality-gate.sh", 'echo "$1"\nexit 1\n')
        result = self.run_hook("commit-gate", command="git commit -m test")
        self.assert_status(result, 2)
        self.assertIn("--fast", result.stderr)

    def test_merge_requires_gate_and_review_stamps(self):
        self.git("branch", "feature/test")
        result = self.run_hook("merge-gate", command="git merge feature/test")
        self.assert_status(result, 2)
        tip = self.git("rev-parse", "feature/test")
        for directory, suffix in [("gates", "merge-passed"), ("reviews", "full.codex")]:
            stamp = self.repo / f".claude/state/{directory}/feature_test.{suffix}"
            stamp.parent.mkdir(parents=True, exist_ok=True)
            stamp.write_text(tip + "\n")
        self.assert_status(self.run_hook("merge-gate", command="git merge feature/test"), 0)

    def test_big_read_threshold_and_targeted_sed(self):
        path = self.repo / "large.txt"
        path.write_text("line\n" * 300)
        self.assert_status(self.run_hook("big-read-guard", command=f"cat {path}"), 0)
        path.write_text("line\n" * 301)
        self.assert_status(self.run_hook("big-read-guard", command=f"cat {path}"), 2)
        self.assert_status(self.run_hook("big-read-guard", command=f"sed -n '1,40p' {path}"), 0)

    def test_session_hook_calls_original_plans_drift(self):
        planning = self.repo / "planning"
        (planning / "plans").mkdir(parents=True)
        (planning / "ACTIVE_PLANS.md").write_text("")
        (planning / "PLANS.md").write_text("")
        (planning / "plans/PLAN-999-test.md").write_text("orphan fixture\n")
        self.git("add", "planning")
        self.git("-c", "core.hooksPath=/dev/null", "commit", "-m", "planning fixture")
        result = self.run_hook("plans-drift", "SessionStart")
        self.assert_status(result, 0)
        self.assertIn("PLAN-999", result.stdout)

    def test_all_original_hooks_are_registered_in_codex(self):
        claude = json.loads((PROJECT / ".claude/settings.json").read_text())
        codex = json.loads((PROJECT / ".codex/hooks.json").read_text())
        original = set(re.findall(r"/([a-z-]+)\.sh", json.dumps(claude["hooks"])))
        commands = [hook["command"] for groups in codex["hooks"].values()
                    for group in groups for hook in group["hooks"]]
        registered = {name for name in HOOKS
                      if any(re.search(r"\b" + re.escape(name) + r"\b", command)
                             for command in commands)}
        self.assertEqual(original, HOOKS)
        self.assertEqual(registered, original)


class CodexParityTest(unittest.TestCase):
    """Каждая роль и каждое правило Claude обязаны дойти до Codex: пропуск валит тест."""

    def test_every_claude_role_has_a_codex_role_pointing_to_its_instructions(self):
        sources = {path.stem for path in (PROJECT / ".claude/agents").glob("*.md")}
        roles = {path.stem: path for path in (PROJECT / ".codex/agents").glob("*.toml")}
        self.assertTrue(sources)
        self.assertEqual(set(roles), sources)
        for name, path in roles.items():
            with self.subTest(role=name):
                role = tomllib.loads(path.read_text())
                self.assertEqual(role.get("name"), name)
                self.assertTrue(role.get("description", "").strip())
                self.assertIn(f".claude/agents/{name}.md", role.get("developer_instructions", ""))

    def test_every_claude_rule_reaches_codex_session_context(self):
        codex = json.loads((PROJECT / ".codex/hooks.json").read_text())
        hooks = [hook for group in codex["hooks"]["SessionStart"] for hook in group["hooks"]
                 if re.search(r"claude-compat\.py\" rules$", hook["command"])]
        self.assertEqual(len(hooks), 1)
        result = subprocess.run([sys.executable, "-B", str(PROJECT / ".codex/hooks/claude-compat.py"), "rules"],
                                input="{}", capture_output=True, text=True, encoding="utf-8", check=True)
        output = json.loads(result.stdout)["hookSpecificOutput"]
        self.assertEqual(output["hookEventName"], "SessionStart")
        rules = sorted((PROJECT / ".claude/rules").glob("*.md"))
        self.assertTrue(rules)
        for rule in rules:
            with self.subTest(rule=rule.name):
                self.assertIn(rule.read_text(encoding="utf-8").strip(), output["additionalContext"])
        # лимит Codex — в токенах; токенов не больше символов, так что символы под лимитом не обрежутся
        self.assertLessEqual(len(output["additionalContext"]), hooks[0]["additionalContextLimit"])


if __name__ == "__main__":
    unittest.main()
