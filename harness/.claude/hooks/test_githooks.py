#!/usr/bin/env python3
"""Тесты git-хуков .githooks/* и install-githooks.sh (PLAN-145, этап 2b). Временные репо, реальный git."""
# Герметичность: переменные среды Claude Code/git-хука не должны течь в подпроцессы фикстур (хуки делают
# `cd "${CLAUDE_PROJECT_DIR:-.}"` и ушли бы в настоящий репозиторий).
import os as _os
for _v in [k for k in _os.environ if k.startswith("GIT_") or k == "CLAUDE_PROJECT_DIR"]:
    _os.environ.pop(_v, None)

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
BAD_TEST = "import sys\nsys.exit(1)\n"
OK_TEST = "import sys\nsys.exit(0)\n"
ROADMAP_HEAD = "# R\n\n| RM | Название | Статус | Дата | Триггер |\n|---|---|---|---|---|\n"
ROW = "| [RM-1](roadmap/RM-1-x.md) | Идея | %s | 2026-10-17 | нет |\n"
RM_FILE = "# RM-1 — Идея\n\n- **Статус:** %s\n"


class Repo:
    def __init__(self, tc):
        self.tc = tc
        self.dir = Path(tempfile.mkdtemp())
        tc.addCleanup(shutil.rmtree, self.dir, True)
        self.git("init", "-q", "-b", "main")
        for rel in (".githooks", ".claude/hooks/paths.py", ".claude/hooks/paths.conf", ".claude/hooks/commit_checks.py", ".claude/hooks/owner_ok.py",
                    ".claude/scripts/registry.sh", ".claude/scripts/install-githooks.sh"):
            src, dst = REPO / rel, self.dir / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(src, dst) if src.is_dir() else shutil.copy2(src, dst)
        self.write("planning/ROADMAP.md", ROADMAP_HEAD + ROW % "идея")
        self.write("planning/roadmap/RM-1-x.md", RM_FILE % "идея")
        self.write("README.md", "x")
        self.git("add", "-A")
        self.commit("init", verify=False)
        self.git("config", "core.hooksPath", ".githooks")

    def write(self, rel, text):
        p = self.dir / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")

    def git(self, *args, check=True):
        r = subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *args], cwd=self.dir,
                           capture_output=True, text=True)
        if check and r.returncode:
            raise AssertionError("git %s: %s" % (args, r.stderr))
        return r

    def commit(self, msg, verify=True):
        return self.git("commit", "-q", "-m", msg, *([] if verify else ["--no-verify"]), check=False)

    def branch(self, name):
        self.git("checkout", "-q", "-b", name)

    def stage(self, rel, text):
        self.write(rel, text)
        self.git("add", rel)

    def err(self, r):
        return r.stdout + r.stderr


class CommitMsgTest(unittest.TestCase):
    def test_feature_requires_own_plan_token(self):
        r = Repo(self)
        r.branch("feature/PLAN-9-x")
        r.stage("app/a.php", "1")
        self.assertEqual(r.commit("feat: x").returncode, 1)
        self.assertIn("PLAN-9", r.err(r.commit("feat: x")))
        self.assertEqual(r.commit("feat: x PLAN-9").returncode, 0)

    def test_longer_plan_number_does_not_match(self):
        r = Repo(self)
        r.branch("feature/PLAN-9-x")
        r.stage("app/a.php", "1")
        self.assertEqual(r.commit("feat: x PLAN-90").returncode, 1)

    def test_hotfix_requires_hf_token(self):
        r = Repo(self)
        r.branch("hotfix/x")
        r.stage("app/a.php", "1")
        self.assertEqual(r.commit("fix: x").returncode, 1)
        self.assertEqual(r.commit("fix: x HF-").returncode, 1)
        self.assertEqual(r.commit("fix: x HF-12").returncode, 0)

    def test_merge_commit_exempt(self):
        r = Repo(self)
        r.branch("feature/PLAN-9-x")
        r.stage("app/a.php", "1")
        self.assertEqual(r.commit("feat: x PLAN-9").returncode, 0)
        r.git("checkout", "-q", "main")
        r.branch("feature/PLAN-8-y")
        r.stage("app/b.php", "1")
        self.assertEqual(r.commit("feat: y PLAN-8").returncode, 0)
        m = r.git("merge", "--no-ff", "-m", "Merge branch 'feature/PLAN-9-x'", "feature/PLAN-9-x", check=False)
        self.assertEqual(m.returncode, 0, r.err(m))

    def test_rm_token_only_for_roadmap_only_commit(self):
        r = Repo(self)
        r.branch("feature/PLAN-9-x")
        r.stage("planning/roadmap/RM-1-x.md", RM_FILE % "отложена")
        r.stage("planning/ROADMAP.md", ROADMAP_HEAD + ROW % "отложена")
        self.assertEqual(r.commit("docs: roadmap RM-1").returncode, 0)
        r.stage("app/a.php", "1")
        r.stage("planning/roadmap/RM-1-x.md", RM_FILE % "идея")
        r.stage("planning/ROADMAP.md", ROADMAP_HEAD + ROW % "идея")
        self.assertEqual(r.commit("docs: roadmap RM-1").returncode, 1)


    def test_identifier_boundary(self):
        r = Repo(self)
        r.branch("feature/PLAN-9-x")
        r.stage("app/a.php", "1")
        self.assertEqual(r.commit("feat: x PLAN-9.1").returncode, 1)
        self.assertEqual(r.commit("feat: x, see PLAN-9.").returncode, 0)

    def test_arbitrary_merge_prefix_not_exempt(self):
        r = Repo(self)
        r.branch("feature/PLAN-9-x")
        r.stage("app/a.php", "1")
        self.assertEqual(r.commit("Merge arbitrary change").returncode, 1)
        self.assertEqual(r.commit("Merge branch 'x' into y").returncode, 0)

    def test_amend_no_edit_on_roadmap_commit_with_rm_token(self):
        r = Repo(self)
        r.branch("feature/PLAN-9-x")
        r.stage("planning/roadmap/RM-1-x.md", RM_FILE % "отложена")
        r.stage("planning/ROADMAP.md", ROADMAP_HEAD + ROW % "отложена")
        self.assertEqual(r.commit("docs: roadmap RM-1").returncode, 0)
        res = r.git("commit", "-q", "--amend", "--no-edit", check=False)
        self.assertEqual(res.returncode, 0, r.err(res))


class PreCommitTest(unittest.TestCase):
    def conflict(self, r):
        """main и feature правят app/a.php по-разному; git merge останавливается на конфликте."""
        r.stage("app/a.php", "0")
        r.commit("base", verify=False)
        r.branch("feature/PLAN-9-x")
        r.stage("app/a.php", "2")
        r.commit("feat: PLAN-9", verify=False)
        r.git("checkout", "-q", "main")
        r.stage("app/a.php", "3")
        r.commit("main change", verify=False)
        self.assertNotEqual(r.git("merge", "--no-commit", "--no-ff", "feature/PLAN-9-x", check=False).returncode, 0)
        r.write("app/a.php", "resolved")
        r.git("add", "app/a.php")

    def test_conflict_merge_on_main_passes(self):
        r = Repo(self)
        self.conflict(r)
        res = r.git("commit", "--no-edit", check=False)
        self.assertEqual(res.returncode, 0, r.err(res))

    def test_conflict_merge_still_checks_structure(self):
        r = Repo(self)
        self.conflict(r)
        r.stage("planning/plans/PLAN-145-x.md", "# PLAN-145\n\nбез резюме\n")
        res = r.git("commit", "--no-edit", check=False)
        self.assertEqual(res.returncode, 1)
        self.assertIn("Резюме", r.err(res))

    def test_random_planning_file_blocked(self):
        r = Repo(self)
        r.branch("feature/PLAN-9-x")
        r.stage("planning/random.md", "x")
        res = r.commit("docs: x PLAN-9")
        self.assertEqual(res.returncode, 1)
        self.assertIn("planning/random.md", r.err(res))

    def test_valid_commit_and_valid_rm_pass(self):
        r = Repo(self)
        r.branch("feature/PLAN-9-x")
        r.stage("app/a.php", "1")
        self.assertEqual(r.commit("feat: x PLAN-9").returncode, 0)
        r.stage("planning/roadmap/RM-1-x.md", RM_FILE % "отложена")
        r.stage("planning/ROADMAP.md", ROADMAP_HEAD + ROW % "отложена")
        self.assertEqual(r.commit("docs: RM-1").returncode, 0)

    def test_code_on_main_blocked(self):
        r = Repo(self)
        r.stage("app/a.php", "1")
        self.assertEqual(r.commit("feat: x").returncode, 1)

    def test_staged_version_checked_not_working_tree(self):
        r = Repo(self)
        r.branch("feature/PLAN-9-x")
        r.stage("planning/ROADMAP.md", ROADMAP_HEAD + ROW % "выдуманный")  # в индексе — плохой статус
        r.write("planning/ROADMAP.md", ROADMAP_HEAD + ROW % "идея")  # в рабочем — исправлен, но не добавлен
        res = r.commit("docs: x PLAN-9")
        self.assertEqual(res.returncode, 1, r.err(res))
        self.assertIn("выдуманный", r.err(res))

    def test_internal_error_fails_open(self):
        r = Repo(self)
        r.branch("feature/PLAN-9-x")
        r.write(".claude/scripts/registry.sh", "#!/usr/bin/env bash\npython3 -c 'raise SystemExit(1/0)'\n")
        r.stage("app/a.php", "1")
        res = r.commit("feat: x PLAN-9")
        self.assertEqual(res.returncode, 0, r.err(res))
        self.assertIn("внутренняя ошибка", r.err(res))


class PrePushTest(unittest.TestCase):
    def prepare(self, test_exit):
        """Репо с заглушками наборов тестов (зелёными или красными) и origin/main на текущем коммите."""
        r = Repo(self)
        for rel in (".claude/hooks/test_planning_gates.py", ".claude/hooks/test_main_push_guard.py",
                    ".claude/hooks/test_db_wipe_guard.py", ".claude/hooks/test_owner_ok.py", ".claude/hooks/test_merge_gate.py", ".claude/hooks/test_e18.py",
                    ".claude/hooks/test_githooks.py", ".claude/hooks/test_quality_gate.py", ".claude/scripts/test_registry.py"):
            r.write(rel, test_exit)
        r.write(".codex/hooks/test_claude_compat.py",
                "import unittest\nclass T(unittest.TestCase):\n    def test_x(self):\n        %s\n"
                % ("pass" if test_exit == OK_TEST else "self.fail('boom')"))
        r.git("add", "-A")
        r.commit("init2", verify=False)
        self.head = r.git("rev-parse", "HEAD").stdout.strip()
        r.git("update-ref", "refs/remotes/origin/main", self.head)
        return r

    def range_line(self, r, rel):
        r.stage(rel, "1")
        r.commit("x", verify=False)
        new = r.git("rev-parse", "HEAD").stdout.strip()
        return "refs/heads/main %s refs/heads/main %s\n" % (new, self.head)

    def push_hook(self, r, stdin):
        return subprocess.run([str(r.dir / ".githooks/pre-push"), "origin", "x"], cwd=r.dir, input=stdin,
                              capture_output=True, text=True)

    def test_tag_and_delete_skip_everything_even_with_red_tests(self):
        r = self.prepare(BAD_TEST)
        zero = "0" * 40
        self.assertEqual(self.push_hook(r, "(delete) %s refs/heads/x %s\n" % (zero, self.head)).returncode, 0)
        self.assertEqual(self.push_hook(r, "refs/tags/v1 %s refs/tags/v1 %s\n" % (self.head, zero)).returncode, 0)

    def test_range_without_hook_paths_does_not_run_tests(self):
        r = self.prepare(BAD_TEST)
        self.assertEqual(self.push_hook(r, self.range_line(r, "app/a.php")).returncode, 0)

    def test_range_with_hook_path_runs_tests(self):
        red = self.prepare(BAD_TEST)
        res = self.push_hook(red, self.range_line(red, ".claude/hooks/x.py"))
        self.assertEqual(res.returncode, 1)
        self.assertIn("test_planning_gates.py", res.stderr)
        green = self.prepare(OK_TEST)
        self.assertEqual(self.push_hook(green, self.range_line(green, ".githooks/x")).returncode, 0)

    def test_suites_run_on_pushed_commit_not_working_tree(self):
        # рабочее дерево красное, пушимый коммит зелёный -> push проходит
        r = self.prepare(OK_TEST)
        line = self.range_line(r, ".claude/hooks/x.py")
        r.write(".claude/hooks/test_planning_gates.py", BAD_TEST)  # неотслеживаемая правка рабочего дерева
        self.assertEqual(self.push_hook(r, line).returncode, 0)
        # рабочее дерево зелёное, пушимый коммит красный -> push блокируется, в сообщении sha
        r = self.prepare(OK_TEST)
        r.stage(".claude/hooks/test_planning_gates.py", BAD_TEST)
        line = self.range_line(r, ".claude/hooks/x.py")
        r.write(".claude/hooks/test_planning_gates.py", OK_TEST)
        res = self.push_hook(r, line)
        self.assertEqual(res.returncode, 1)
        self.assertIn(line.split()[1][:8], res.stderr)

    def test_suites_do_not_inherit_claude_or_git_env(self):
        """Hotfix prepush-test-env: CLAUDE_PROJECT_DIR/GIT_* из окружения терминала Claude Code не доходят до наборов на worktree."""
        probe = ("import os, sys\n"
                 "sys.exit(1 if any(k == 'CLAUDE_PROJECT_DIR' or k.startswith('GIT_') for k in os.environ) else 0)\n")
        r = self.prepare(probe)
        r.stage(".codex/hooks/test_claude_compat.py", "import unittest\nclass T(unittest.TestCase):\n    def test_x(self):\n        pass\n")
        r.commit("seed", verify=False)
        self.head = r.git("rev-parse", "HEAD").stdout.strip()
        r.git("update-ref", "refs/remotes/origin/main", self.head)
        line = self.range_line(r, ".claude/hooks/x.py")
        env = {**os.environ, "CLAUDE_PROJECT_DIR": str(r.dir), "GIT_INDEX_FILE": str(r.dir / "nope"), "GIT_CONFIG_COUNT": "1",
               "GIT_CONFIG_KEY_0": "core.hooksPath", "GIT_CONFIG_VALUE_0": "/dev/null", "GIT_CONFIG_PARAMETERS": "'x.y=z'",
               "GIT_COMMON_DIR": str(r.dir / ".git"), "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_NOSYSTEM": "1"}
        res = subprocess.run([str(r.dir / ".githooks/pre-push"), "origin", "x"], cwd=r.dir, input=line, capture_output=True, text=True, env=env)
        self.assertEqual(res.returncode, 0, res.stderr)

    def test_suites_get_git_context_and_worktree_is_removed(self):
        """Наборы идут на git worktree пушимого коммита: git ls-files работает, дерево целое; после push следа нет."""
        probe = ("import subprocess, sys\n"
                 "r = subprocess.run(['git', 'ls-files'], capture_output=True, text=True)\n"
                 "sys.exit(0 if r.returncode == 0 and 'README.md' in r.stdout.split() and 'app/a.php' in r.stdout.split() else 1)\n")
        r = self.prepare(probe)
        r.stage(".codex/hooks/test_claude_compat.py", "import unittest\nclass T(unittest.TestCase):\n    def test_x(self):\n        pass\n")
        r.stage("app/a.php", "1")
        r.commit("seed", verify=False)
        self.head = r.git("rev-parse", "HEAD").stdout.strip()
        r.git("update-ref", "refs/remotes/origin/main", self.head)
        res = self.push_hook(r, self.range_line(r, ".claude/hooks/x.py"))
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertEqual(r.git("worktree", "list", "--porcelain").stdout.count("worktree "), 1)

    def with_verifier(self, exit_code):
        """prepare + закоммиченный верификатор миграции, который сразу возвращает exit_code; origin/main на этом коммите."""
        r = self.prepare(OK_TEST)
        r.write(".claude/scripts/verify-plans-migration.sh", "#!/usr/bin/env bash\necho diverged-from-source\nexit %d\n" % exit_code)
        os.chmod(r.dir / ".claude/scripts/verify-plans-migration.sh", 0o755)
        r.git("add", "-A")
        r.commit("verifier", verify=False)
        self.head = r.git("rev-parse", "HEAD").stdout.strip()
        r.git("update-ref", "refs/remotes/origin/main", self.head)
        return r

    def test_migration_verifier_blocks_when_closed_records_touched(self):
        for rel in ("planning/plans/closed/PLAN-1.md", "planning/hotfixes/HF-1-x.md", ".claude/scripts/verify-journal-migration.sh"):
            with self.subTest(rel=rel):
                r = self.with_verifier(1)
                res = self.push_hook(r, self.range_line(r, rel))
                self.assertEqual(res.returncode, 1, res.stderr)
                self.assertIn("verify-plans-migration.sh", res.stderr)
                self.assertIn("diverged-from-source", res.stderr)

    def test_migration_verifier_green_passes_and_unrelated_range_skips_it(self):
        r = self.with_verifier(0)
        self.assertEqual(self.push_hook(r, self.range_line(r, ".claude/scripts/verify-journal-migration.sh")).returncode, 0)
        r = self.with_verifier(1)  # красный верификатор не мешает диапазону, который закрытых записей не трогает
        self.assertEqual(self.push_hook(r, self.range_line(r, "app/a.php")).returncode, 0)

    def test_structure_violation_in_range_blocks(self):
        r = self.prepare(OK_TEST)
        res = self.push_hook(r, self.range_line(r, "planning/random.md"))
        self.assertEqual(res.returncode, 1)
        self.assertIn("planning/random.md", res.stderr)

    def test_unknown_range_warns_not_silent(self):
        r = self.prepare(OK_TEST)
        r.git("update-ref", "-d", "refs/remotes/origin/main")
        zero = "0" * 40
        res = self.push_hook(r, "refs/heads/f %s refs/heads/f %s\n" % (self.head, zero))
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertIn("не вычислен", res.stderr)


class InstallGithooksTest(unittest.TestCase):
    def test_idempotent(self):
        r = Repo(self)
        r.git("config", "--unset", "core.hooksPath")
        run = lambda: subprocess.run(["bash", ".claude/scripts/install-githooks.sh"], cwd=r.dir, capture_output=True, text=True)
        first = run()
        self.assertIn("ok", first.stdout)
        self.assertEqual(r.git("config", "core.hooksPath").stdout.strip(), ".githooks")
        second = run()
        self.assertIn("уже подключено", second.stdout)
        self.assertEqual(second.returncode, 0)


if __name__ == "__main__":
    unittest.main()
