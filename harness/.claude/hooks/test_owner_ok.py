#!/usr/bin/env python3
"""Маркеры слова владельца E10/E11 (PLAN-145, этап 3a): owner-ok.sh, commit-gate, pre-commit, merge-gate,
чистка SessionStart. Временные репозитории, реальный git. Запуск: python3 .claude/hooks/test_owner_ok.py"""
# Герметичность: переменные среды Claude Code/git-хука не должны течь в подпроцессы фикстур (хуки делают
# `cd "${CLAUDE_PROJECT_DIR:-.}"` и ушли бы в настоящий репозиторий).
import os as _os
for _v in [k for k in _os.environ if k.startswith("GIT_") or k == "CLAUDE_PROJECT_DIR"]:
    _os.environ.pop(_v, None)

import json
import os
import shutil
import subprocess
import tempfile
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
HEAD = "# R\n\n| RM | Название | Статус | Дата | Триггер |\n|---|---|---|---|---|\n"
ROW = "| [RM-%d](roadmap/RM-%d-x.md) | Идея | идея | 2026-10-17 | нет |\n"
FILES = (".githooks", ".claude/hooks/merge_checks.py", ".claude/hooks/branch-guard.sh", ".claude/hooks/money-paths.txt", ".claude/hooks/paths.py", ".claude/hooks/paths.conf", ".claude/hooks/commit_checks.py",
         ".claude/hooks/owner_ok.py", ".claude/hooks/owner-ok-guard.sh", ".claude/hooks/commit-gate.sh", ".claude/hooks/merge-gate.sh",
         ".claude/hooks/plans-drift.sh", ".claude/scripts/registry.sh", ".claude/scripts/owner-ok.sh", ".claude/scripts/mark-reviewed.sh", ".claude/scripts/merge-ready.sh")
BRANCH = "feature/PLAN-145-x"


class OwnerCase(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.dir, True)
        self.git("init", "-q", "-b", "main")
        for rel in FILES:
            src, dst = REPO / rel, self.dir / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(src, dst) if src.is_dir() else shutil.copy2(src, dst)
        self.write(".gitignore", "/.claude/state/\n")
        self.write("planning/ROADMAP.md", HEAD + ROW % (1, 1))
        self.write("planning/roadmap/RM-1-x.md", "# RM-1\n\n- **Статус:** идея\n")
        self.write("planning/ACTIVE_PLANS.md", "# Active\n\n## PLAN-145 — x\n\n**Статус:** в работе\n\n## PLAN-146 — y\n\n**Статус:** в работе\n")
        self.write("planning/PLANS.md", "# Plans\n\n## PLAN-1 — Старый\n\nтело\n")
        self.git("add", "-A")
        self.git("commit", "-q", "--no-verify", "-m", "init")
        self.git("config", "core.hooksPath", ".githooks")
        self.git("checkout", "-q", "-b", BRANCH)

    # --- помощники
    def write(self, rel, text):
        p = self.dir / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")

    def git(self, *args):
        r = subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *args], cwd=self.dir, capture_output=True, text=True)
        self.assertEqual(0, r.returncode, r.stderr)
        return r.stdout.strip()

    def stage(self, rel, text):
        self.write(rel, text)
        self.git("add", rel)

    def stage_rm(self, n=9):
        self.stage("planning/roadmap/RM-%d-x.md" % n, "# RM-%d\n\n- **Статус:** идея\n" % n)
        self.stage("planning/ROADMAP.md", HEAD + ROW % (1, 1) + ROW % (n, n))

    def stage_legacy_close(self, n=2):
        self.stage("planning/PLANS.md", "# Plans\n\n## PLAN-1 — Старый\n\nтело\n\n## PLAN-%d — Новый\n\nтело\n" % n)

    def owner(self, *args):
        return subprocess.run(["bash", str(self.dir / ".claude/scripts/owner-ok.sh"), *args], cwd=self.dir, capture_output=True, text=True)

    def marker(self, name):
        return self.dir / ".claude/state/owner-ok" / name

    def hook(self, name, command):
        return subprocess.run(["bash", str(self.dir / ".claude/hooks" / name)], input=json.dumps({"tool_input": {"command": command}}),
                              text=True, capture_output=True, cwd=self.dir, env=dict(os.environ, CLAUDE_PROJECT_DIR=str(self.dir)))

    def commit_gate(self):
        return self.hook("commit-gate.sh", "git commit -m 'x PLAN-145'")

    def real_commit(self):
        return subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "x PLAN-145"],
                              cwd=self.dir, capture_output=True, text=True)

    def assertBlocked(self, r, text="owner-ok.sh"):
        self.assertIn(r.returncode, (1, 2), r.stderr)
        self.assertIn(text, r.stderr)

    def assertAllowed(self, r):
        self.assertEqual(0, r.returncode, r.stdout + r.stderr)

    # --- merge-gate: ветка с коммитом, зелёные гейт и ревью на вершине, затем checkout main
    def commit_all(self, msg="c PLAN-145"):
        self.git("add", "-A")
        self.git("commit", "-q", "--no-verify", "-m", msg)

    def green(self, branch=BRANCH):
        tip = self.git("rev-parse", branch)
        key = branch.replace("/", "_")
        for rel in (".claude/state/gates/%s.merge-passed" % key, ".claude/state/reviews/%s.full.codex" % key):
            self.write(rel, tip + "\n")

    def merge_gate(self, branch=BRANCH):
        return self.hook("merge-gate.sh", "git merge " + branch)


class ScriptTest(OwnerCase):
    def test_issue_marker_content(self):
        r = self.owner("rm-add", "RM-9")
        self.assertEqual(0, r.returncode, r.stderr)
        data = dict(l.split("=", 1) for l in self.marker("rm-add-RM-9@feature%2FPLAN-145-x").read_text().splitlines())
        self.assertEqual(self.git("rev-parse", BRANCH), data["sha"])
        self.assertEqual({"kind": "rm-add", "id": "RM-9", "branch": BRANCH, "target": "main"}, {k: data[k] for k in ("kind", "id", "branch", "target")})
        self.assertLess(abs(int(data["issued"]) - time.time()), 30)

    def test_explicit_branch_and_close_plan(self):
        self.git("branch", "feature/other")
        self.assertEqual(0, self.owner("close-plan", "PLAN-7", "feature/other").returncode)
        self.assertTrue(self.marker("close-plan-PLAN-7@feature%2Fother").is_file())

    def test_bad_arguments_rc2(self):
        for args in (("bogus", "RM-1"), ("rm-add", "PLAN-1"), ("close-plan", "RM-1"), ("rm-add",), ("rm-add", "RM-1", "no-such-branch"), ()):
            self.assertEqual(2, self.owner(*args).returncode, args)


class E11Test(OwnerCase):
    def test_new_rm_without_marker_blocked_in_both_hooks(self):
        self.stage_rm()
        self.assertBlocked(self.commit_gate(), "owner-ok.sh rm-add RM-9")
        self.assertBlocked(self.real_commit(), "owner-ok.sh rm-add RM-9")

    def test_new_rm_with_marker_allowed(self):
        self.stage_rm()
        self.owner("rm-add", "RM-9")
        self.assertAllowed(self.commit_gate())
        self.assertAllowed(self.real_commit())
        self.assertTrue(self.marker("rm-add-RM-9@feature%2FPLAN-145-x").is_file())  # коммит маркер не расходует

    def test_row_only_without_file_detected(self):
        self.stage("planning/ROADMAP.md", HEAD + ROW % (1, 1) + ROW % (9, 9))
        self.assertBlocked(self.commit_gate(), "RM-9")

    def test_marker_for_other_rm_blocked(self):
        self.stage_rm()
        self.owner("rm-add", "RM-8")
        self.assertBlocked(self.commit_gate(), "RM-9")

    def test_marker_other_branch_blocked(self):
        self.stage_rm()
        self.git("branch", "feature/PLAN-146-y")
        self.owner("rm-add", "RM-9", "feature/PLAN-146-y")
        self.assertBlocked(self.commit_gate(), "RM-9")

    def test_expired_marker_blocked(self):
        self.stage_rm()
        self.owner("rm-add", "RM-9")
        path = self.marker("rm-add-RM-9@feature%2FPLAN-145-x")
        old = time.time() - 25 * 3600
        path.write_text(path.read_text().replace("issued=", "issued=0#"))  # битый issued = просрочен
        self.assertBlocked(self.commit_gate(), "24 ч")
        path.write_text("kind=rm-add\nid=RM-9\nbranch=%s\nsha=x\ntarget=main\nissued=%d\n" % (BRANCH, old))
        self.assertBlocked(self.commit_gate(), "24 ч")
        path.write_text(path.read_text().replace(str(int(old)), str(int(time.time()))))
        os.utime(path, (old, old))  # свежий issued, но старый mtime
        self.assertBlocked(self.commit_gate(), "24 ч")

    def test_edit_existing_rm_needs_no_marker(self):
        self.stage("planning/roadmap/RM-1-x.md", "# RM-1\n\n- **Статус:** идея\n\nправка\n")
        self.assertAllowed(self.commit_gate())
        self.assertAllowed(self.real_commit())


class E10Test(OwnerCase):
    def test_legacy_heading_blocked_then_allowed(self):
        self.stage_legacy_close(2)
        self.assertBlocked(self.commit_gate(), "owner-ok.sh close-plan PLAN-2")
        self.assertBlocked(self.real_commit(), "close-plan PLAN-2")
        self.owner("close-plan", "PLAN-2")
        self.assertAllowed(self.commit_gate())
        self.assertAllowed(self.real_commit())

    def test_legacy_edit_of_existing_heading_needs_no_marker(self):
        self.stage("planning/PLANS.md", "# Plans\n\n## PLAN-1 — Старый\n\nтело поправлено\n")
        self.assertAllowed(self.commit_gate())

    def test_new_format_closed_row_blocked_then_allowed(self):
        index = "# Plans\n\n| План | Название | Статус |\n|---|---|---|\n| PLAN-5 | x | %s |\n"
        self.write("planning/PLANS.md", index % "в работе")
        self.commit_all()
        self.stage("planning/PLANS.md", index % "закрыт")
        self.assertBlocked(self.commit_gate(), "close-plan PLAN-5")
        self.owner("close-plan", "PLAN-5")
        self.assertAllowed(self.commit_gate())

    def test_new_format_closed_archive_file_blocked(self):
        self.stage("planning/plans/closed/PLAN-5.md", "# PLAN-5\n")

        def checks():  # registry.sh потребует строку индекса — здесь проверяем только E10
            return subprocess.run(["python3", ".claude/hooks/commit_checks.py", "staged", BRANCH, "staged"], cwd=self.dir, capture_output=True, text=True)
        self.assertBlocked(checks(), "close-plan PLAN-5")
        self.owner("close-plan", "PLAN-5")
        self.assertAllowed(checks())

    def test_new_format_row_already_closed_not_new(self):
        index = "# Plans\n\n| План | Название | Статус |\n|---|---|---|\n| PLAN-5 | x | аннулирован |\n"
        self.write("planning/PLANS.md", index)
        self.commit_all()
        self.stage("planning/PLANS.md", index.replace("| x |", "| y |"))
        self.assertAllowed(self.commit_gate())

    # --- реальный формат индекса этапа 4a: `| [PLAN-N](plans/closed/PLAN-N.md) | Название | закрыт | дата | влит | автор |`
    REAL_HEAD = "| PLAN | Название | Статус | Дата | Влит-в | Автор |\n|---|---|---|---|---|---|\n"

    def real_row(self, n, status="закрыт"):
        return "| [PLAN-%s](plans/closed/PLAN-%s.md) | Тема | %s | 2026-10-17 | — | Claude |\n" % (n, n, status)

    def staged_checks(self):
        return subprocess.run(["python3", ".claude/hooks/commit_checks.py", "staged", BRANCH, "staged"], cwd=self.dir, capture_output=True, text=True)

    def test_real_format_migration_of_legacy_headings_needs_no_marker(self):
        self.write("planning/PLANS.md", "# Plans\n\n## PLAN-1 — Старый\n\nтело\n\n## PLAN-62 / PLAN-63 — Составной\n\nтело\n")
        self.commit_all()
        self.stage("planning/PLANS.md", "# Закрытые\n\n" + self.REAL_HEAD + self.real_row(1) + self.real_row(62))
        self.stage("planning/plans/closed/PLAN-1.md", "## PLAN-1 — Старый\n\nтело\n")
        self.stage("planning/plans/closed/PLAN-62.md", "## PLAN-62 / PLAN-63 — Составной\n\nтело\n")
        self.assertAllowed(self.staged_checks())

    def git_rename(self, src, dst):
        # two steps: on a case-insensitive filesystem a one-step case-only rename is a no-op
        self.git("mv", src, src + ".tmp")
        self.git("mv", src + ".tmp", dst)

    def test_case_rename_of_closed_index_is_not_a_new_closing(self):
        """plans.md -> PLANS.md: the same closed rows under a new name need no close-plan marker."""
        self.write("planning/PLANS.md", "# Закрытые\n\n" + self.REAL_HEAD + self.real_row(1) + self.real_row(62))
        self.git("add", "-A")
        self.git_rename("planning/PLANS.md", "planning/plans.md")
        self.commit_all()
        self.git_rename("planning/plans.md", "planning/PLANS.md")
        self.assertAllowed(self.staged_checks())
        # control: a row that was not there before still needs the marker
        self.stage("planning/PLANS.md", "# Закрытые\n\n" + self.REAL_HEAD + self.real_row(1) + self.real_row(62) + self.real_row(9))
        self.assertBlocked(self.staged_checks(), "PLAN-9")

    def test_real_format_new_closed_row_after_migration_blocked(self):
        self.write("planning/PLANS.md", "# Закрытые\n\n" + self.REAL_HEAD + self.real_row(1))
        self.commit_all()
        self.stage("planning/PLANS.md", "# Закрытые\n\n" + self.REAL_HEAD + self.real_row(1) + self.real_row(9))
        self.assertBlocked(self.commit_gate(), "close-plan PLAN-9")
        self.owner("close-plan", "PLAN-9")
        self.assertAllowed(self.commit_gate())

    def test_real_format_escaped_pipe_in_title_still_detects_closing(self):
        """I3: `\\|` в названии не сдвигает колонки — переход в закрыт виден."""
        active = "# Активные\n\n" + self.REAL_HEAD + "| [PLAN-6](plans/PLAN-6-x.md) | Тема \\| с чертой | %s | 2026-10-17 | — | Claude |\n"
        self.write("planning/ACTIVE_PLANS.md", active % "в работе")
        self.commit_all()
        self.stage("planning/ACTIVE_PLANS.md", active % "закрыт")
        self.assertBlocked(self.commit_gate(), "close-plan PLAN-6")

    def test_real_format_active_row_to_closed_blocked(self):
        active = "# Активные\n\n" + self.REAL_HEAD + "| [PLAN-5](plans/PLAN-5-x.md) | Тема | %s | 2026-10-17 | — | Claude |\n"
        self.write("planning/ACTIVE_PLANS.md", active % "в работе")
        self.commit_all()
        self.stage("planning/ACTIVE_PLANS.md", active % "закрыт")
        self.assertBlocked(self.commit_gate(), "close-plan PLAN-5")


class MergeGateTest(OwnerCase):
    def setup_rm_branch(self):
        self.stage_rm()
        self.owner("rm-add", "RM-9")
        self.commit_all()
        self.owner("rm-add", "RM-9")  # SHA вершины после коммита
        self.green()
        self.git("checkout", "-q", "main")

    def test_merge_with_marker_claims_it(self):
        self.setup_rm_branch()
        self.assertAllowed(self.merge_gate())
        self.assertFalse(self.marker("rm-add-RM-9@feature%2FPLAN-145-x").exists())
        self.assertTrue(self.marker("claimed/rm-add-RM-9@feature%2FPLAN-145-x").exists())

    def test_merge_without_marker_blocked(self):
        self.setup_rm_branch()
        self.marker("rm-add-RM-9@feature%2FPLAN-145-x").unlink()
        self.assertBlocked(self.merge_gate(), "RM-9")

    def test_sha_mismatch_blocked(self):
        self.stage_rm()
        self.owner("rm-add", "RM-9")
        self.commit_all()  # вершина ушла после выдачи
        self.green()
        self.git("checkout", "-q", "main")
        r = self.merge_gate()
        self.assertBlocked(r, "SHA")
        self.assertTrue(self.marker("rm-add-RM-9@feature%2FPLAN-145-x").exists())  # не сожжён

    def test_target_not_main_does_not_claim(self):
        self.setup_rm_branch()
        self.git("checkout", "-q", "-b", "feature/PLAN-146-other", "main")
        self.assertAllowed(self.merge_gate())
        self.assertTrue(self.marker("rm-add-RM-9@feature%2FPLAN-145-x").exists())

    def test_second_merge_with_same_marker_blocked(self):
        self.setup_rm_branch()
        self.assertAllowed(self.merge_gate())
        self.assertBlocked(self.merge_gate(), "уже использовано")

    def test_parallel_gates_exactly_one_passes(self):
        self.setup_rm_branch()
        with ThreadPoolExecutor(6) as pool:
            codes = sorted(r.returncode for r in pool.map(lambda _: self.merge_gate(), range(6)))
        self.assertEqual([0, 2, 2, 2, 2, 2], codes)

    def test_legacy_close_needs_close_marker(self):
        self.stage_legacy_close(2)
        self.commit_all()
        self.green()
        self.git("checkout", "-q", "main")
        self.assertBlocked(self.merge_gate(), "close-plan PLAN-2")
        self.git("checkout", "-q", BRANCH)
        self.owner("close-plan", "PLAN-2")
        self.git("checkout", "-q", "main")
        self.assertAllowed(self.merge_gate())
        self.assertTrue(self.marker("claimed/close-plan-PLAN-2@feature%2FPLAN-145-x").exists())

    def test_branch_without_triggers_needs_nothing(self):
        self.stage("README.md", "x")
        self.commit_all()
        self.green()
        self.git("checkout", "-q", "main")
        self.assertAllowed(self.merge_gate())


ACTIVE = "# Active\n\n## PLAN-7 — Дело\n\n**Статус:** %s\n\nтекст\n"


class DetectorTest(OwnerCase):
    """B1/B2/I1/I2/I3/M1: что считается новой записью в roadmap и закрытием плана."""

    def checks(self):
        return subprocess.run(["python3", ".claude/hooks/commit_checks.py", "staged", BRANCH, "staged"], cwd=self.dir, capture_output=True, text=True)

    def test_b1_active_plans_section_status_flip(self):
        self.write("planning/ACTIVE_PLANS.md", ACTIVE % "в работе")
        self.commit_all()
        self.stage("planning/ACTIVE_PLANS.md", ACTIVE % "закрыт 2026-10-17")
        self.assertBlocked(self.commit_gate(), "close-plan PLAN-7")
        self.owner("close-plan", "PLAN-7")
        self.assertAllowed(self.commit_gate())

    def test_b1_annulled_and_unrelated_edit(self):
        self.write("planning/ACTIVE_PLANS.md", ACTIVE % "аннулирован")
        self.commit_all()
        self.stage("planning/ACTIVE_PLANS.md", (ACTIVE % "аннулирован") + "ещё строка\n")
        self.assertAllowed(self.commit_gate())  # уже закрыт в HEAD
        self.stage("planning/ACTIVE_PLANS.md", ACTIVE % "в работе")
        self.assertAllowed(self.commit_gate())  # переоткрытие - не закрытие

    def test_b2_compound_heading_all_ids(self):
        self.stage("planning/PLANS.md", "# Plans\n\n## PLAN-1 — Старый\n\nтело\n\n## PLAN-144 / PLAN-999 — Оба\n\nтело\n")
        self.owner("close-plan", "PLAN-144")
        self.assertBlocked(self.commit_gate(), "close-plan PLAN-999")
        self.owner("close-plan", "PLAN-999")
        self.assertAllowed(self.commit_gate())

    def test_b2_appended_id_to_existing_heading(self):
        self.stage("planning/PLANS.md", "# Plans\n\n## PLAN-1 / PLAN-55 — Старый\n\nтело\n")
        r = self.commit_gate()
        self.assertBlocked(r, "close-plan PLAN-55")
        self.assertNotIn("close-plan PLAN-1`", r.stderr)

    def test_i1_wider_archive_name(self):
        self.stage("planning/plans/closed/PLAN-9-topic.md", "# PLAN-9\n")
        self.assertBlocked(self.checks(), "close-plan PLAN-9")

    def test_i3_existing_archive_does_not_suppress_transition(self):
        index = "# Plans\n\n| План | Название | Статус |\n|---|---|---|\n| PLAN-9 | x | %s |\n"
        self.write("planning/PLANS.md", index % "в работе")
        self.write("planning/plans/closed/PLAN-9.md", "# PLAN-9\n")
        self.commit_all()
        self.stage("planning/PLANS.md", index % "закрыт")
        self.assertBlocked(self.commit_gate(), "close-plan PLAN-9")

    def test_m1_only_status_column_counts(self):
        index = "# Plans\n\n| План | Название | Статус |\n|---|---|---|\n| PLAN-9 | %s | %s |\n"
        self.write("planning/PLANS.md", index % ("вопрос", "в работе"))
        self.commit_all()
        self.stage("planning/PLANS.md", index % ("закрыт: название", "на паузе"))
        self.assertAllowed(self.commit_gate())

    def test_i2_rm_case_insensitive(self):
        self.stage("planning/roadmap/rm-999-x.md", "# RM-999\n")
        self.assertBlocked(self.checks(), "rm-add RM-999")
        self.git("reset", "-q")
        self.stage("planning/ROADMAP.md", HEAD + ROW % (1, 1) + "| [rm-998](roadmap/rm-998-x.md) | Идея | идея | 2026-10-17 | нет |\n")
        self.assertBlocked(self.checks(), "rm-add RM-998")


class MarkerNameTest(OwnerCase):
    """I6: имена без коллизий, забранные маркеры не затирают живые."""

    def test_i6_branches_with_slash_and_underscore_differ(self):
        self.git("branch", "feature/PLAN-145-a/b")
        self.git("branch", "feature/PLAN-145-a_b")
        self.owner("rm-add", "RM-9", "feature/PLAN-145-a/b")
        self.owner("rm-add", "RM-9", "feature/PLAN-145-a_b")
        names = sorted(p.name for p in (self.dir / ".claude/state/owner-ok").iterdir())
        self.assertEqual(["rm-add-RM-9@feature%2FPLAN-145-a%2Fb", "rm-add-RM-9@feature%2FPLAN-145-a%5Fb"], names)

    def test_i6_claim_does_not_overwrite_live_marker(self):
        self.stage_rm()
        self.commit_all()
        self.owner("rm-add", "RM-9")
        self.green()
        self.git("checkout", "-q", "main")
        self.assertAllowed(self.merge_gate())
        self.git("checkout", "-q", BRANCH)
        self.owner("rm-add", "RM-9")  # новая выдача рядом с уже забранной
        self.assertTrue(self.marker("rm-add-RM-9@feature%2FPLAN-145-x").exists())
        self.assertTrue(self.marker("claimed/rm-add-RM-9@feature%2FPLAN-145-x").exists())


class GuardTest(OwnerCase):
    """I7: агент не выдаёт слово владельца сам."""

    def guard(self, cmd):
        return self.hook("owner-ok-guard.sh", cmd)

    def test_blocked_commands(self):
        for cmd in (".claude/scripts/owner-ok.sh rm-add RM-9", "bash .claude/scripts/owner-ok.sh close-plan PLAN-1",
                    "bash -c 'cd x && .claude/scripts/owner-ok.sh rm-add RM-9'", "sh -c \"owner-ok.sh rm-add RM-9\"",
                    "echo kind=rm-add > .claude/state/owner-ok/rm-add-RM-9@x", "touch .claude/state/owner-ok/x",
                    "cat > .claude/state/owner-ok/x <<EOF\nkind=rm-add\nEOF", "cp a .claude/state/owner-ok/b",
                    "python3 .claude/hooks/owner_ok.py cleanup", "rm .claude/state/owner-ok/x"):
            self.assertBlocked(self.guard(cmd), "владелец")

    def test_i4_shell_via_git_blocked(self):
        for cmd in ("git -c alias.m='!sh -c id' m", "git config alias.m '!git merge x'", "git --exec-path=/tmp/x status",
                    "git -c core.pager='sh -c id' log", "git -c user.name='a!b' status", "git -calias.x=!sh x",
                    "git config core.editor 'sh -c id'", "git config --global alias.q status"):
            self.assertBlocked(self.guard(cmd), "I4")

    def test_i4_ordinary_git_config_allowed(self):
        for cmd in ("git -c user.name=x -c user.email=y commit -m z", "git config --get alias.m", "git config user.name x", "git config --list"):
            self.assertAllowed(self.guard(cmd))

    def test_allowed_commands(self):
        for cmd in ("ls .claude/state/owner-ok", "grep -rn owner-ok.sh planning", "git add .claude/scripts/owner-ok.sh && git commit -m 'x owner-ok.sh'",
                    "python3 .claude/hooks/test_owner_ok.py", "git status", "cat .claude/scripts/owner-ok.sh",
                    "git commit -m \"$(cat <<'EOF'\nmention owner-ok.sh in body\nEOF\n)\""):
            self.assertAllowed(self.guard(cmd))


class MergeGateHardeningTest(OwnerCase):
    def rm_branch(self, branch=BRANCH, n=9):
        self.stage_rm(n)
        self.commit_all()
        self.owner("rm-add", "RM-%d" % n, branch)
        self.green(branch)

    def test_b3_corrupt_marker_blocks(self):
        self.rm_branch()
        self.marker("rm-add-RM-9@feature%2FPLAN-145-x").write_bytes(b"kind=rm-add\nid=\xff\xfe\n")
        self.git("checkout", "-q", "main")
        self.assertBlocked(self.merge_gate(), "RM-9")

    def test_b3_internal_error_is_fail_closed(self):
        r = subprocess.run(["python3", ".claude/hooks/owner_ok.py", "merge-claim"], cwd=self.dir, capture_output=True, text=True)
        self.assertEqual(2, r.returncode)

    def test_b4_checkout_main_chain_not_bypass(self):
        self.rm_branch()  # текущая ветка - feature, не main
        r = self.hook("merge-gate.sh", "git checkout main && git merge " + BRANCH)
        self.assertEqual(0, r.returncode, r.stderr)  # маркер есть - пропуск, и он забран
        self.assertTrue(self.marker("claimed/rm-add-RM-9@feature%2FPLAN-145-x").exists())

    def test_b4_checkout_main_chain_without_marker_blocked(self):
        self.rm_branch()
        self.marker("rm-add-RM-9@feature%2FPLAN-145-x").unlink()
        self.assertBlocked(self.hook("merge-gate.sh", "git switch main; git merge " + BRANCH), "RM-9")

    def test_b4_merge_into_other_branch_no_markers(self):
        self.rm_branch()
        self.marker("rm-add-RM-9@feature%2FPLAN-145-x").unlink()
        self.assertAllowed(self.merge_gate())  # текущая ветка feature, без checkout main

    def test_b5_origin_ref_is_what_gets_checked(self):
        self.rm_branch()
        old = self.git("rev-parse", BRANCH + "~1")
        self.git("update-ref", "refs/remotes/origin/" + BRANCH, old)
        self.git("checkout", "-q", "main")
        r = self.hook("merge-gate.sh", "git merge origin/" + BRANCH)
        self.assertBlocked(r, "гейта")  # штампы стоят на локальной вершине, у origin/... другой SHA

    def test_i4_octopus_blocked_and_nothing_claimed(self):
        self.rm_branch()
        self.git("checkout", "-q", "-b", "feature/PLAN-146-y", "main")
        self.stage_rm(8)
        self.commit_all()
        self.green("feature/PLAN-146-y")
        self.git("checkout", "-q", "main")
        r = self.hook("merge-gate.sh", "git merge %s feature/PLAN-146-y" % BRANCH)
        self.assertBlocked(r, "octopus")
        self.assertTrue(self.marker("rm-add-RM-9@feature%2FPLAN-145-x").exists())
        self.assertFalse(self.marker("claimed/rm-add-RM-9@feature%2FPLAN-145-x").exists())

    def test_i4_claim_items_all_or_nothing(self):
        """Общий откат набора маркеров (CLI merge-claim для нескольких ссылок)."""
        self.rm_branch()
        self.git("checkout", "-q", "-b", "feature/PLAN-146-y", "main")
        self.stage_rm(8)
        self.commit_all()
        self.git("checkout", "-q", "main")
        r = subprocess.run(["python3", ".claude/hooks/owner_ok.py", "merge-claim", "1", BRANCH, "feature/PLAN-146-y"], cwd=self.dir, capture_output=True, text=True)
        self.assertEqual(2, r.returncode)
        self.assertTrue(self.marker("rm-add-RM-9@feature%2FPLAN-145-x").exists())
        self.assertFalse(self.marker("claimed/rm-add-RM-9@feature%2FPLAN-145-x").exists())


class CleanupTest(OwnerCase):
    def drift(self):
        return subprocess.run(["bash", str(self.dir / ".claude/hooks/plans-drift.sh")], cwd=self.dir, capture_output=True, text=True,
                              env=dict(os.environ, CLAUDE_PROJECT_DIR=str(self.dir)))

    def test_cleanup_removes_claimed_expired_merged_keeps_live(self):
        self.owner("rm-add", "RM-9")
        live = self.marker("rm-add-RM-9@feature%2FPLAN-145-x")
        claimed = self.marker("claimed/rm-add-RM-8@feature%2FPLAN-145-x")
        claimed.parent.mkdir(parents=True, exist_ok=True)
        claimed.write_text(live.read_text())
        expired = self.marker("rm-add-RM-7@feature%2FPLAN-145-x")
        expired.write_text("kind=rm-add\nid=RM-7\nbranch=%s\nsha=x\ntarget=main\nissued=1\n" % BRANCH)
        self.stage("README.md", "y")
        self.commit_all()
        self.owner("close-plan", "PLAN-3")  # ветка пока не влита
        r = self.drift()
        self.assertEqual(0, r.returncode)
        self.assertTrue(live.exists())
        self.assertFalse(expired.exists())
        # claimed живой ветки (не влита, не просрочен) остаётся до мержа
        self.assertTrue(claimed.exists())
        self.git("checkout", "-q", "main")
        self.git("merge", "-q", "--no-verify", BRANCH)
        r = self.drift()
        self.assertEqual(0, r.returncode)
        # RM-9 выдан до коммита (sha != вершины, ветка влита) и claimed уходят; PLAN-3 выдан на вершине - только по сроку
        left = sorted(p.name for p in (self.dir / ".claude/state/owner-ok").rglob("*") if p.is_file())
        self.assertEqual(["close-plan-PLAN-3@feature%2FPLAN-145-x"], left)

    def test_fresh_branch_marker_without_commits_kept(self):
        self.owner("rm-add", "RM-9")  # tip ветки == tip main
        self.assertEqual(0, self.drift().returncode)
        self.assertTrue(self.marker("rm-add-RM-9@feature%2FPLAN-145-x").exists())


if __name__ == "__main__":
    unittest.main()
