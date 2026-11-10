#!/usr/bin/env python3
"""E18 (PLAN-145, этап 3c): правка защищённых путей требует маркер владельца hooks-edit — commit-gate, pre-commit,
merge-gate. Временные репозитории; в боевом paths.conf правило выключено (`e18 off`, включение - этап 5).
Запуск: python3 .claude/hooks/test_e18.py"""
# Герметичность: переменные среды Claude Code/git-хука не должны течь в подпроцессы фикстур (хуки делают
# `cd "${CLAUDE_PROJECT_DIR:-.}"` и ушли бы в настоящий репозиторий).
import os as _os
for _v in [k for k in _os.environ if k.startswith("GIT_") or k == "CLAUDE_PROJECT_DIR"]:
    _os.environ.pop(_v, None)

import re
import json
import os
import subprocess
import time
import unittest

import paths
import test_owner_ok as base

BRANCH = base.BRANCH
REQUIRED = {".claude/hooks/", ".claude/settings.json", ".claude/scripts/", ".codex/", ".agents/", ".githooks/", "CLAUDE.md", "AGENTS.md"}


def sample(pattern):
    """Конкретный путь под шаблоном guard-e18."""
    return pattern + "zz_new.sh" if pattern.endswith("/") else pattern


class E18Case(base.OwnerCase):
    state = "on"

    def setUp(self):
        super().setUp()
        self.git("checkout", "-q", "main")
        conf = self.dir / ".claude/hooks/paths.conf"
        conf.write_text(re.sub(r"(?m)^e18 (on|off)$", "e18 " + self.state, conf.read_text()))
        self.git("add", "-A")
        self.git("commit", "-q", "--allow-empty", "--no-verify", "-m", "e18 " + self.state)
        self.git("checkout", "-q", "-B", BRANCH, "main")

    def hooks_edit(self, branch=BRANCH):
        return self.owner("hooks-edit", branch, branch)


class ConfTest(unittest.TestCase):
    def test_real_conf_is_on_and_lists_every_protected_path(self):
        conf = paths.load()
        self.assertTrue(paths.e18_on(conf), "E18 включён последним коммитом этапа 5 PLAN-145")
        self.assertTrue(REQUIRED <= set(conf["guard-e18"]), REQUIRED - set(conf["guard-e18"]))

    def test_directory_root_itself_is_protected(self):
        conf = {"guard-e18": [".githooks/", ".claude/hooks/", "CLAUDE.md"], "e18": ["on"]}
        for path in (".githooks", ".claude/hooks"):  # gitlink/symlink на каталог подменяет всё содержимое
            self.assertTrue(paths.e18_protected(path, conf), path)
        for path in (".githooksx", ".claude", "CLAUDE.md/"):
            self.assertFalse(paths.e18_protected(path, conf), path)

    def test_matching(self):
        conf = {"guard-e18": [".claude/hooks/", "CLAUDE.md"], "e18": ["on"]}
        self.assertTrue(paths.e18_protected(".claude/hooks/x.sh", conf))
        self.assertTrue(paths.e18_protected("CLAUDE.md", conf))
        self.assertFalse(paths.e18_protected("CLAUDE.md.bak", conf))
        self.assertFalse(paths.e18_protected(".claude/hooksx/a", conf))
        self.assertFalse(paths.e18_protected("app/x.php", conf))


class CommitTest(E18Case):
    def test_every_protected_pattern_blocks_without_marker_and_passes_with(self):
        patterns = paths.load()["guard-e18"]
        self.assertTrue(patterns)
        for pattern in patterns:  # перебор по списку из paths.conf, не подмножество
            with self.subTest(pattern=pattern):
                self.git("reset", "-q", "--hard")
                self.git("clean", "-fdq", "-e", ".claude/state")
                self.stage(sample(pattern), "x\n")
                self.assertBlocked(self.commit_gate(), "hooks-edit")
                self.assertBlocked(self.real_commit(), "hooks-edit")
                self.hooks_edit()
                self.assertAllowed(self.commit_gate())
                self.assertAllowed(self.real_commit())
                self.git("reset", "-q", "--hard", "main")
                (self.dir / ".claude/state/owner-ok" / ("hooks-edit-feature%2FPLAN-145-x@feature%2FPLAN-145-x")).unlink()

    def test_deletion_of_protected_file_needs_marker(self):
        self.git("rm", "-q", ".claude/hooks/money-paths.txt")
        self.assertBlocked(self.commit_gate(), "hooks-edit")

    def test_unprotected_path_not_affected(self):
        self.stage("app/x.php", "<?php\n")
        self.assertAllowed(self.commit_gate())
        self.assertAllowed(self.real_commit())

    def test_marker_of_other_branch_blocked(self):
        self.git("branch", "feature/PLAN-146-y")
        self.stage(".claude/hooks/zz.sh", "x\n")
        self.owner("hooks-edit", "feature/PLAN-146-y", "feature/PLAN-146-y")
        self.assertBlocked(self.commit_gate(), "hooks-edit")
        self.assertBlocked(self.real_commit(), "hooks-edit")

    def test_expired_marker_blocked(self):
        self.stage(".claude/hooks/zz.sh", "x\n")
        self.hooks_edit()
        path = self.marker("hooks-edit-feature%2FPLAN-145-x@feature%2FPLAN-145-x")
        old = time.time() - 25 * 3600
        path.write_text("kind=hooks-edit\nid=%s\nbranch=%s\nsha=x\ntarget=main\nissued=%d\n" % (BRANCH, BRANCH, old))
        self.assertBlocked(self.commit_gate(), "24 ч")

    def test_turning_rule_off_in_same_commit_does_not_help(self):
        conf = (self.dir / ".claude/hooks/paths.conf").read_text().replace("e18 on", "e18 off")
        self.stage(".claude/hooks/paths.conf", conf)
        self.assertBlocked(self.commit_gate(), "hooks-edit")
        self.assertBlocked(self.real_commit(), "hooks-edit")

    def test_tests_of_hooks_can_be_read_and_run(self):
        self.assertAllowed(self.hook("commit-gate.sh", "python3 .claude/hooks/test_planning_gates.py"))


class EditGuardTest(E18Case):
    """branch-guard (PreToolUse Edit/Write): защищённый путь при e18 on требует маркер hooks-edit текущей ветки."""

    def edit(self, rel):
        return subprocess.run(["bash", str(self.dir / ".claude/hooks/branch-guard.sh")], text=True, capture_output=True, cwd=self.dir,
                              input=json.dumps({"tool_name": "Edit", "tool_input": {"file_path": str(self.dir / rel)}}),
                              env=dict(os.environ, CLAUDE_PROJECT_DIR=str(self.dir)))

    def test_every_protected_pattern_blocks_edit_without_marker(self):
        for pattern in paths.load()["guard-e18"]:
            with self.subTest(pattern=pattern):
                self.assertBlocked(self.edit(sample(pattern)), "E18")

    def test_marker_allows_edit_without_sha_check(self):
        self.hooks_edit()
        self.stage("README.md", "новый коммит после выдачи\n")
        self.commit_all()  # вершина ушла - Edit всё равно разрешён (SHA сверяет только merge-gate)
        for pattern in paths.load()["guard-e18"]:
            self.assertAllowed(self.edit(sample(pattern)))

    def test_other_branch_marker_blocks_and_unprotected_passes(self):
        self.git("branch", "feature/PLAN-146-y", "main")
        self.owner("hooks-edit", "feature/PLAN-146-y", "feature/PLAN-146-y")
        self.assertBlocked(self.edit("CLAUDE.md"), "E18")
        self.assertAllowed(self.edit("app/x.php"))

    def test_protected_root_symlink_path(self):
        self.assertBlocked(self.edit(".githooks"), "E18")


class UnionTest(E18Case):
    """I2: E18 включено, если включено в HEAD ИЛИ в main - ветка, созданная до `e18 on`, правило не обходит."""
    state = "on"

    def test_branch_with_old_off_conf_still_guarded_by_main_on(self):
        conf = self.dir / ".claude/hooks/paths.conf"
        conf.write_text(re.sub(r"(?m)^e18 on$", "e18 off", conf.read_text()))  # на ветке (HEAD) правило выключено, в main - включено
        self.git("add", "-A")
        self.git("commit", "-q", "--no-verify", "-m", "old branch conf PLAN-145")
        self.stage(".claude/hooks/zz.sh", "x\n")
        self.assertBlocked(self.commit_gate(), "hooks-edit")
        self.hooks_edit()
        self.assertAllowed(self.commit_gate())


class OffEditTest(E18Case):
    state = "off"

    def test_edit_silent_when_off(self):
        self.assertAllowed(EditGuardTest.edit(self, "CLAUDE.md"))


class OffTest(E18Case):
    state = "off"

    def test_rule_is_silent_when_off(self):
        self.stage(".claude/hooks/zz.sh", "x\n")
        self.stage("CLAUDE.md", "x\n")
        self.assertAllowed(self.commit_gate())
        self.assertAllowed(self.real_commit())


class MergeTest(E18Case):
    def hooks_branch(self, extra=None):
        files = {".claude/hooks/zz.sh": "x\n"}
        files.update(extra or {})
        self.git("checkout", "-q", "-B", BRANCH, "main")
        for rel, text in files.items():
            self.write(rel, text)
        self.commit_all()

    def ready(self):
        tip = self.git("rev-parse", BRANCH)
        key = BRANCH.replace("/", "_")
        for rel in (".claude/state/gates/%s.merge-passed" % key, ".claude/state/reviews/%s.full.codex" % key):
            self.write(rel, tip + "\n")
        self.git("checkout", "-q", "main")

    def merge(self):
        return self.hook("merge-gate.sh", "git merge " + BRANCH)

    def claimed(self, name):
        return self.marker("claimed/" + name).exists()

    def test_protected_change_without_marker_blocked(self):
        self.hooks_branch()
        self.ready()
        self.assertBlocked(self.merge(), "hooks-edit")

    def test_with_marker_on_tip_passes_and_claims(self):
        self.hooks_branch()
        self.hooks_edit()
        self.ready()
        self.assertAllowed(self.merge())
        self.assertTrue(self.claimed("hooks-edit-feature%2FPLAN-145-x@feature%2FPLAN-145-x"))
        self.assertBlocked(self.merge(), "уже использовано")

    def test_marker_before_last_commit_has_other_sha(self):
        self.hooks_branch()
        self.hooks_edit()
        self.write("README.md", "y\n")
        self.commit_all()
        self.ready()
        self.assertBlocked(self.merge(), "SHA")

    def test_marker_other_branch_blocked(self):
        self.hooks_branch()
        self.git("branch", "feature/PLAN-146-y", "main")
        self.owner("hooks-edit", "feature/PLAN-146-y", "feature/PLAN-146-y")
        self.ready()
        self.assertBlocked(self.merge(), "hooks-edit")

    def test_claimed_together_with_roadmap_marker_all_or_nothing(self):
        self.hooks_branch({"planning/roadmap/RM-9-x.md": "# RM-9\n", "planning/ROADMAP.md": base.HEAD + base.ROW % (1, 1) + base.ROW % (9, 9)})
        self.hooks_edit()  # слова про RM-9 нет
        self.ready()
        self.assertBlocked(self.merge(), "RM-9")
        self.assertFalse(self.claimed("hooks-edit-feature%2FPLAN-145-x@feature%2FPLAN-145-x"))
        self.git("checkout", "-q", BRANCH)
        self.owner("rm-add", "RM-9", BRANCH)
        self.hooks_edit()
        self.git("checkout", "-q", "main")
        self.assertAllowed(self.merge())
        self.assertTrue(self.claimed("hooks-edit-feature%2FPLAN-145-x@feature%2FPLAN-145-x"))
        self.assertTrue(self.claimed("rm-add-RM-9@feature%2FPLAN-145-x"))

    def test_rule_off_silent_on_merge(self):
        self.git("checkout", "-q", "main")
        conf = self.dir / ".claude/hooks/paths.conf"
        conf.write_text(conf.read_text().replace("e18 on", "e18 off"))
        self.git("add", "-A")
        self.git("commit", "-q", "--no-verify", "-m", "off")
        self.hooks_branch()
        self.ready()
        self.assertAllowed(self.merge())

    def test_turning_rule_off_inside_branch_does_not_help(self):
        conf = (self.dir / ".claude/hooks/paths.conf").read_text().replace("e18 on", "e18 off")
        self.hooks_branch({".claude/hooks/paths.conf": conf})
        self.ready()
        self.assertBlocked(self.merge(), "hooks-edit")


if __name__ == "__main__":
    unittest.main()
