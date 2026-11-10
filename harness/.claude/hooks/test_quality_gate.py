#!/usr/bin/env python3
"""quality-gate.sh --dusk-plan: когда --merge пропускает Dusk. Временные репо, реальный git."""
import os as _os

_os.environ["COMPOSE_PROJECT_NAME"] = "app"  # gate derives <project>-horizon-1 from it


for _v in [k for k in _os.environ if k.startswith("GIT_") or k == "CLAUDE_PROJECT_DIR"]:
    _os.environ.pop(_v, None)

import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

GATE = Path(__file__).resolve().parents[1] / "scripts" / "quality-gate.sh"


class DuskPlanTest(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.dir, True)
        self.git("init", "-q", "-b", "main")
        self.write("README.md", "x")
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "init")
        self.git("checkout", "-q", "-b", "feature/x")

    def git(self, *a):
        return subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *a], cwd=self.dir,
                              capture_output=True, text=True, check=True)

    def write(self, rel, text="y"):
        p = self.dir / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)

    def plan(self, *files):
        for f in files:
            self.write(f)
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "work")
        return subprocess.run([str(GATE), "--dusk-plan"], cwd=self.dir, capture_output=True, text=True).stdout.strip()

    def test_merge_mark_from_a_worktree_lands_in_the_main_checkout(self):
        # HF-177: гейт идёт в worktree, merge-gate читает отметку из основного чекаута. docker - заглушка.
        self.plan("planning/x.md")
        tip = self.git("rev-parse", "HEAD").stdout.strip()
        self.git("checkout", "-q", "main")
        wt = self.dir / ".claude/worktrees/w"
        self.git("worktree", "add", "-q", str(wt), "feature/x")
        (wt / "vendor").mkdir()
        self.write("storage/app/.keep")
        self.write("bin/docker", '#!/bin/sh\n[ "$1" = ps ] && echo app-horizon-1\nexit 0\n')
        (self.dir / "bin/docker").chmod(0o755)
        r = subprocess.run([str(GATE), "--merge"], cwd=wt, capture_output=True, text=True,
                           env=dict(_os.environ, PATH="%s:%s" % (self.dir / "bin", _os.environ["PATH"])))
        self.assertEqual(0, r.returncode, r.stdout + r.stderr)
        self.assertEqual(tip + "\n", (self.dir / ".claude/state/gates/feature_x.merge-passed").read_text())
        self.assertFalse((wt / ".claude/state/gates").exists())

    def test_code_diff_without_node_modules_gets_no_merge_mark(self):
        # HF-177: без node_modules нет eslint и свежей сборки, такая отметка не должна открыть мерж. docker - заглушка.
        self.plan("app/Foo.php")
        self.write("bin/docker", '#!/bin/sh\n[ "$1" = ps ] && echo app-horizon-1\nexit 0\n')
        (self.dir / "bin/docker").chmod(0o755)
        self.write("storage/app/.keep")
        (self.dir / "vendor").mkdir()
        r = subprocess.run([str(GATE), "--merge"], cwd=self.dir, capture_output=True, text=True,
                           env=dict(_os.environ, PATH="%s:%s" % (self.dir / "bin", _os.environ["PATH"])))
        self.assertNotEqual(0, r.returncode, r.stdout)
        self.assertIn("нет node_modules", r.stdout + r.stderr)
        self.assertFalse((self.dir / ".claude/state/gates/feature_x.merge-passed").exists())

    def test_docs_only_skips(self):
        out = self.plan("planning/plans/PLAN-1-x.md", ".claude/hooks/h.py", ".githooks/pre-push", "docs/readme.md", "CLAUDE.md")
        self.assertTrue(out.startswith("dusk: skip"), out)

    def test_one_code_file_runs(self):
        out = self.plan("app/Foo.php")
        self.assertTrue(out.startswith("dusk: run"), out)

    def test_mixed_runs(self):
        for extra in ("tests/Browser/XTest.php", "resources/views/a.blade.php", "composer.json", "package.json", "vite.config.js", "config/app.php", "routes/web.php"):
            with self.subTest(extra=extra):
                out = self.plan("planning/a.md", extra)
                self.assertTrue(out.startswith("dusk: run"), out)

    def test_deleting_code_file_runs(self):
        self.git("checkout", "-q", "main")
        self.write("app/Foo.php")
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "code")
        self.git("checkout", "-q", "-b", "feature/y")
        self.git("rm", "-q", "app/Foo.php")
        self.git("commit", "-q", "-m", "del")
        out = subprocess.run([str(GATE), "--dusk-plan"], cwd=self.dir, capture_output=True, text=True).stdout.strip()
        self.assertTrue(out.startswith("dusk: run"), out)

    def test_diff_error_runs(self):
        self.write("planning/a.md")
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "docs")
        self.git("branch", "-q", "-m", "main", "trunk")  # ветки main нет — diff main...HEAD падает
        out = subprocess.run([str(GATE), "--dusk-plan"], cwd=self.dir, capture_output=True, text=True).stdout.strip()
        self.assertTrue(out.startswith("dusk: run"), out)

    def test_filter_failure_runs(self):
        # grep падает с rc=2 и молчит: пустой вывод не должен читаться как «всё в белом списке»
        self.write("app/Foo.php")
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "code")
        fake = self.dir / "fakebin"
        fake.mkdir()
        (fake / "grep").write_text("#!/bin/sh\nexit 2\n")
        (fake / "grep").chmod(0o755)
        env = {**__import__("os").environ, "PATH": f"{fake}:{__import__('os').environ['PATH']}"}
        out = subprocess.run([str(GATE), "--dusk-plan"], cwd=self.dir, capture_output=True, text=True, env=env).stdout.strip()
        self.assertTrue(out.startswith("dusk: run"), out)

    def test_empty_diff_runs(self):
        out = subprocess.run([str(GATE), "--dusk-plan"], cwd=self.dir, capture_output=True, text=True).stdout.strip()
        self.assertTrue(out.startswith("dusk: run"), out)


class DuskShardPlanTest(unittest.TestCase):
    """Класс мимо шарда не выполнился бы молча: каждый *Test.php обязан попасть ровно в один шард."""

    def test_every_class_lands_in_exactly_one_shard(self):
        root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, root, True)
        names = {"ATest", "BTest", "CTest", "NestedTest", "NoMethodsTest"}
        for name in names:
            sub = "Deep/" if name == "NestedTest" else ""
            path = root / "tests/Browser" / (sub + name + ".php")
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("" if name == "NoMethodsTest" else "function test_a() {} function test_b() {}")
        (root / "tests/Browser/Helper.php").write_text("function test_not_a_test_class() {}")
        script = GATE.parent / "dusk-shards.sh"
        for shards in (1, 2, 4, 7):
            with self.subTest(shards=shards):
                out = subprocess.run([str(script), "--plan", str(shards)], cwd=root, capture_output=True, text=True, check=True).stdout
                lines = out.splitlines()
                self.assertEqual(len(lines), shards)
                placed = [n for line in lines for n in line.split("|") if n]
                self.assertEqual(sorted(placed), sorted(names))


class WorktreePintTest(unittest.TestCase):
    def test_pint_gets_git_paths_that_exist_inside_the_container(self):
        # В `.git` worktree записан путь хоста, в контейнере его нет: `pint --dirty` падал (HF-174).
        root = Path(tempfile.mkdtemp()).resolve()
        self.addCleanup(shutil.rmtree, root, True)
        wt = root / ".claude/worktrees/wt"

        def git(*a):
            subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *a], cwd=root, capture_output=True, check=True)

        git("init", "-q", "-b", "main")
        git("commit", "-q", "--allow-empty", "-m", "i")
        git("worktree", "add", "-q", "-b", "hotfix/x", str(wt))
        (wt / "vendor").mkdir()
        log = root / "docker.log"
        fake = root / "bin/docker"
        fake.parent.mkdir()
        fake.write_text('#!/bin/sh\n[ "$1" = ps ] && { echo app-horizon-1; exit 0; }\necho "$*" >> "%s"\n' % log)
        fake.chmod(0o755)
        env = {k: v for k, v in _os.environ.items() if k != "CLAUDE_PROJECT_DIR"}
        env["PATH"] = "%s:%s" % (fake.parent, env["PATH"])
        subprocess.run([str(GATE), "--fast"], cwd=wt, env=env, capture_output=True, text=True)
        pint = next(line for line in log.read_text().splitlines() if "pint" in line)
        self.assertIn("GIT_DIR=/var/www/html/.git/worktrees/wt ", pint)
        self.assertIn("GIT_WORK_TREE=/var/www/html/.claude/worktrees/wt ", pint)


if __name__ == "__main__":
    unittest.main()
