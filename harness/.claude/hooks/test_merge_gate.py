#!/usr/bin/env python3
"""merge-gate, этап 3b (PLAN-145): T16 (ссылки -> SHA, правила путей), E12 (ревью opus/codex, деньги),
E17 (уникальность номеров на дереве слияния), E3 (hotfix/* и план в реестре), mark-reviewed.sh --by.
Временные репозитории, реальный git. Запуск: python3 .claude/hooks/test_merge_gate.py"""
# Герметичность: переменные среды Claude Code/git-хука не должны течь в подпроцессы фикстур (хуки делают
# `cd "${CLAUDE_PROJECT_DIR:-.}"` и ушли бы в настоящий репозиторий).
import os as _os
for _v in [k for k in _os.environ if k.startswith("GIT_") or k == "CLAUDE_PROJECT_DIR"]:
    _os.environ.pop(_v, None)
# Байткод в фикстурах: __pycache__ внутри временных репозиториев делает дерево «грязным» (preflight) и попадает в коммит
# фикстуры как правка .claude/hooks (E18). Дочерние процессы наследуют переменную. Без неё набор падает там, где Python
# пишет байткод (терминал владельца, pre-push), и проходит там, где нет (PYTHONDONTWRITEBYTECODE=1 в среде агента).
_os.environ["PYTHONDONTWRITEBYTECODE"] = "1"

import json
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

import test_owner_ok as base

REPO = base.REPO
FEATURE = base.BRANCH
HOTFIX = "hotfix/fix-x"
HOTFIXES_HEAD = "# HF\n\n| HF | Название | Статус | Дата | Влит-в | Автор |\n|---|---|---|---|---|---|\n"


class MergeCase(base.OwnerCase):
    def gate(self, branch):
        """Только штамп зелёного полного гейта на вершине (ревью - отдельно, по ревьюеру)."""
        tip = self.git("rev-parse", branch)
        self.write(".claude/state/gates/%s.merge-passed" % branch.replace("/", "_"), tip + "\n")

    def branch_with(self, name, files, start="main"):
        """Ветка от start с одним коммитом; остаёмся на main."""
        self.git("checkout", "-q", "-B", name, start)
        for rel, text in files.items():
            self.write(rel, text)
        self.commit_all()
        self.git("checkout", "-q", "main")
        return self.git("rev-parse", name)

    def review(self, branch, *bys):
        for by in bys:
            r = subprocess.run(["bash", ".claude/scripts/mark-reviewed.sh", "--full", "--by", by, branch, "ok"],
                               cwd=self.dir, capture_output=True, text=True)
            self.assertEqual(0, r.returncode, r.stderr)

    def ready(self, branch, *bys):
        """Гейт на вершине + отметки ревью (по умолчанию codex)."""
        self.gate(branch)
        self.review(branch, *(bys or ("codex",)))

    def merge(self, args):
        return self.hook("merge-gate.sh", "git merge " + args)


class PreflightTest(MergeCase):
    """merge-ready.sh: сухой прогон merge-gate без захвата маркеров и без мержа."""

    def preflight(self, branch=FEATURE):
        return subprocess.run(["bash", ".claude/scripts/merge-ready.sh", branch], cwd=self.dir, capture_output=True, text=True)

    def rm_branch(self):
        return self.branch_with(FEATURE, {"planning/roadmap/RM-9-x.md": "# RM-9\n\n- **Статус:** идея\n",
                                          "planning/ROADMAP.md": base.HEAD + base.ROW % (1, 1) + base.ROW % (9, 9)})

    def test_ready_when_everything_passed(self):
        self.branch_with(FEATURE, {"README.md": "x\n"})
        self.ready(FEATURE)
        r = self.preflight()
        self.assertEqual((0, "READY\n"), (r.returncode, r.stdout), r.stdout + r.stderr)

    def test_no_gate_stamp_listed(self):
        self.branch_with(FEATURE, {"README.md": "x\n"})
        self.review(FEATURE, "codex")
        r = self.preflight()
        self.assertEqual(1, r.returncode)
        self.assertIn("NOT READY", r.stdout)
        self.assertIn("полного гейта", r.stdout)
        self.assertNotIn("ревью итоговой ветки", r.stdout)

    def test_no_review_mark_listed(self):
        self.branch_with(FEATURE, {"README.md": "x\n"})
        self.gate(FEATURE)
        r = self.preflight()
        self.assertEqual(1, r.returncode)
        self.assertIn("нет ревью", r.stdout)
        self.assertNotIn("полного гейта", r.stdout)

    def test_money_branch_needs_both_reviewers(self):
        self.branch_with(FEATURE, {"app/Services/PaymentGateway.php": "<?php\n"})
        self.ready(FEATURE, "codex")
        r = self.preflight()
        self.assertEqual(1, r.returncode)
        self.assertIn("opus", r.stdout)

    def test_missing_owner_word_listed_with_exact_command_and_nothing_consumed(self):
        self.rm_branch()
        self.ready(FEATURE)
        r = self.preflight()
        self.assertEqual(0, r.returncode, r.stdout + r.stderr)
        self.assertIn("READY (кроме слов владельца)", r.stdout)
        self.assertIn(".claude/scripts/owner-ok.sh rm-add RM-9 " + FEATURE, r.stdout)
        # владелец выдал слово: preflight его видит, НЕ расходует, и настоящий merge-gate потом пропускает
        self.assertEqual(0, self.owner("rm-add", "RM-9", FEATURE).returncode)
        marker = self.marker("rm-add-RM-9@feature%2FPLAN-145-x")
        self.assertTrue(marker.exists())
        for _ in range(2):
            r = self.preflight()
            self.assertEqual("READY\n", r.stdout, r.stdout + r.stderr)
            self.assertTrue(marker.exists())
        self.assertFalse(self.marker("claimed/rm-add-RM-9@feature%2FPLAN-145-x").exists())
        self.assertAllowed(self.merge(FEATURE))
        self.assertTrue(self.marker("claimed/rm-add-RM-9@feature%2FPLAN-145-x").exists())

    def test_word_for_old_tip_is_reported_missing(self):
        self.rm_branch()
        self.owner("rm-add", "RM-9", FEATURE)
        self.git("checkout", "-q", FEATURE)
        self.write("README.md", "y\n")
        self.commit_all()
        self.git("checkout", "-q", "main")
        self.ready(FEATURE)
        r = self.preflight()
        self.assertIn("owner-ok.sh rm-add RM-9", r.stdout)  # SHA вершины изменился - слово нужно заново

    def test_branch_behind_main_listed(self):
        self.branch_with(FEATURE, {"README.md": "x\n"})
        self.ready(FEATURE)
        self.write("docs/m.md", "m\n")
        self.commit_all("main moves PLAN-145")
        r = self.preflight()
        self.assertEqual(1, r.returncode)
        self.assertIn("отстаёт от main", r.stdout)

    def test_dirty_tree_listed(self):
        self.branch_with(FEATURE, {"README.md": "x\n"})
        self.ready(FEATURE)
        self.write("scratch.txt", "dirty\n")
        r = self.preflight()
        self.assertEqual(1, r.returncode)
        self.assertIn("не чистое", r.stdout)

    def test_planning_only_branch_needs_no_gate_and_no_review(self):
        # закрытие плана и правки реестров: код не менялся, полный гейт и ревью не требуются
        self.branch_with(FEATURE, {"planning/README.md": "x\n"})
        r = self.preflight()
        self.assertEqual((0, "READY\n"), (r.returncode, r.stdout), r.stdout + r.stderr)
        self.assertAllowed(self.merge(FEATURE))

    def test_planning_plus_code_branch_still_needs_gate_and_review(self):
        self.branch_with(FEATURE, {"planning/README.md": "x\n", "README.md": "y\n"})
        r = self.preflight()
        self.assertEqual(1, r.returncode)
        self.assertIn("полного гейта", r.stdout)
        self.assertIn("нет ревью", r.stdout)

    def test_planning_branch_deleting_a_file_outside_planning_still_needs_gate(self):
        self.git("checkout", "-q", "main")
        self.write("app/old.php", "<?php\n")
        self.commit_all("add app/old.php")
        self.git("checkout", "-q", "-B", FEATURE, "main")
        self.git("rm", "-q", "app/old.php")
        self.write("planning/README.md", "x\n")
        self.commit_all()
        self.git("checkout", "-q", "main")
        r = self.preflight()
        self.assertEqual(1, r.returncode)
        self.assertIn("полного гейта", r.stdout)

    def test_planning_only_branch_still_needs_the_owner_word(self):
        # быстрый путь снимает только гейт и ревью: слова владельца он не отменяет
        self.rm_branch()
        r = self.preflight()
        self.assertEqual(0, r.returncode, r.stdout + r.stderr)
        self.assertIn("READY (кроме слов владельца)", r.stdout)
        self.assertIn("owner-ok.sh rm-add RM-9", r.stdout)

    def test_planning_only_branch_behind_main_needs_gate_again(self):
        # отставшая ветка быстрого пути не получает: проверенный дифф может не совпасть с результатом слияния
        self.branch_with(FEATURE, {"planning/README.md": "x\n"})
        self.write("docs/m.md", "m\n")
        self.commit_all("main moves PLAN-145")
        r = self.preflight()
        self.assertEqual(1, r.returncode)
        self.assertIn("полного гейта", r.stdout)

    def test_non_feature_branch_with_code_listed(self):
        self.branch_with("topic/x", {"app/a.php": "<?php\n"})
        r = self.preflight("topic/x")
        self.assertEqual(1, r.returncode)
        self.assertIn("app/a.php", r.stdout)


class RefResolutionTest(MergeCase):
    """T16: каждая ссылка -> SHA, правила путей по диффу; имя ветки не доверяется."""

    def test_unresolvable_ref_blocked(self):
        self.assertBlocked(self.merge("no-such-ref"), "не резолвится")

    def test_code_from_non_feature_branch_blocked(self):
        self.branch_with("topic/x", {"app/a.php": "<?php\n"})
        self.assertBlocked(self.merge("topic/x"), "app/a.php")

    def test_tag_and_abbreviated_sha_of_non_feature_blocked(self):
        sha = self.branch_with("topic/x", {"app/a.php": "<?php\n"})
        self.git("tag", "v1", sha)
        self.assertBlocked(self.merge("v1"), "app/a.php")
        self.assertBlocked(self.merge(sha[:8]), "app/a.php")

    def test_sha_of_feature_branch_resolves_to_its_stamps(self):
        sha = self.branch_with(FEATURE, {"app/a.php": "<?php\n"})
        self.assertBlocked(self.merge(sha), "гейта")  # по SHA найдена ветка и потребованы её штампы
        self.ready(FEATURE)
        self.assertAllowed(self.merge(sha))

    def test_options_and_message_are_not_refs(self):
        self.branch_with(FEATURE, {"README.md": "x\n"})
        self.ready(FEATURE)
        self.assertAllowed(self.merge('--no-ff -m "see topic/zzz" --log=3 -- ' + FEATURE))

    def test_redirections_are_not_refs(self):
        """HF-150: `git merge … 2>&1` - одна ссылка, а не две; octopus по-прежнему блокируется."""
        self.branch_with(FEATURE, {"README.md": "x\n"})
        self.ready(FEATURE)
        self.branch_with("topic/x", {"app/a.php": "<?php\n"})
        for form in ("2>&1", "2>/dev/null", ">f", "> f", ">>f", "&>f", "&>>f", ">&2", "2>&-", "<f", "<<<word", ">|f", "2>&1 | cat"):
            with self.subTest(form=form):
                self.assertAllowed(self.merge("--no-ff --no-edit %s %s" % (FEATURE, form)))
                self.assertBlocked(self.merge("%s topic/x %s" % (FEATURE, form)), "octopus")

    def test_squash_and_many_refs_each_checked(self):
        self.branch_with(FEATURE, {"README.md": "x\n"})
        self.ready(FEATURE)
        self.branch_with("topic/x", {"app/a.php": "<?php\n"})
        self.assertAllowed(self.merge("--squash " + FEATURE))
        self.assertBlocked(self.merge("%s topic/x" % FEATURE), "octopus")  # в main - по одной ветке
        self.git("checkout", "-q", "-b", "feature/PLAN-146-y", "main")
        self.assertBlocked(self.merge("%s topic/x" % FEATURE), "app/a.php")  # не в main - каждая ссылка проверяется

    def test_unclassified_root_blocked_even_on_feature_branch(self):
        self.branch_with(FEATURE, {"zzz/new.txt": "x\n"})
        self.ready(FEATURE)
        self.assertBlocked(self.merge(FEATURE), "paths.conf")

    def test_planning_edit_renamed_into_code_by_main_is_not_waved_through(self):
        # main переименовала planning/x.md в код; git перенесёт правку ветки в app/x.php, хотя дифф ветки - только planning/
        self.git("checkout", "-q", "main")
        self.write("planning/x.md", "a\n")
        self.commit_all("add planning/x.md")
        self.branch_with(FEATURE, {"planning/x.md": "a\nb\n"})
        (self.dir / "app").mkdir(exist_ok=True)
        self.git("mv", "planning/x.md", "app/x.php")
        self.commit_all("main renames planning/x.md into code")
        self.assertBlocked(self.merge(FEATURE), "гейта")

    def test_planning_only_plain_branch_behind_main_blocked(self):
        # безымянная (не feature/hotfix) ветка штампов не требует, но отставшая может уехать в код через rename
        self.git("checkout", "-q", "main")
        self.write("planning/x.md", "a\n")
        self.commit_all("add planning/x.md")
        self.branch_with("topic/y", {"planning/x.md": "a\nb\n"})
        (self.dir / "app").mkdir(exist_ok=True)
        self.git("mv", "planning/x.md", "app/x.php")
        self.commit_all("main renames planning/x.md into code")
        self.assertBlocked(self.merge("topic/y"), "отстаёт от main")

    def test_tag_named_main_does_not_hide_that_we_are_on_main(self):
        # refs/tags/main меняет вывод `rev-parse --abbrev-ref HEAD` на heads/main: хук считал бы, что мы НЕ на main,
        # и пропускал pull чужой ветки и merge без аргументов. Ветку берём из symbolic-ref.
        self.git("checkout", "-q", "main")
        self.git("tag", "main", self.git("rev-parse", "main"))
        self.assertBlocked(self.hook("merge-gate.sh", "git pull origin foo"), "pull")
        self.assertBlocked(self.merge(""), "без ссылки")

    def test_tag_named_main_does_not_shadow_the_base_of_the_check(self):
        # старый тег main + отставшая ветка: база и «содержит ли ветка main» считаются от refs/heads/main
        self.git("checkout", "-q", "main")
        old = self.git("rev-parse", "HEAD")
        self.branch_with(FEATURE, {"planning/README.md": "x\n"})
        self.write("docs/m.md", "m\n")
        self.commit_all("main moves PLAN-145")
        self.git("tag", "main", old)
        self.assertBlocked(self.merge(FEATURE), "гейта")

    def test_planning_only_from_plain_branch_allowed(self):
        self.branch_with("topic/y", {"planning/README.md": "x\n"})
        self.assertAllowed(self.merge("topic/y"))

    def test_two_feature_branches_on_same_tip_ambiguous(self):
        self.branch_with(FEATURE, {"README.md": "x\n"})
        self.git("branch", "feature/PLAN-146-y", FEATURE)
        self.ready(FEATURE)
        self.assertBlocked(self.merge(FEATURE), "неоднозначн")


class ReviewTest(MergeCase):
    """E12: деньги — opus И codex; остальное — любая одна; отметка привязана к вершине."""

    def money_branch(self):
        self.branch_with(FEATURE, {"app/Services/PaymentGateway.php": "<?php\n"})
        self.gate(FEATURE)

    def test_money_needs_both(self):
        self.money_branch()
        self.review(FEATURE, "opus")
        self.assertBlocked(self.merge(FEATURE), "codex")
        self.review(FEATURE, "codex")
        self.assertAllowed(self.merge(FEATURE))

    def test_money_with_only_codex_blocked(self):
        self.money_branch()
        self.review(FEATURE, "codex")
        self.assertBlocked(self.merge(FEATURE), "opus")

    def test_non_money_one_review_enough(self):
        for by in ("codex", "opus"):
            self.branch_with(FEATURE, {"README.md": by})
            self.ready(FEATURE, by)
            self.assertAllowed(self.merge(FEATURE))
            self.git("branch", "-q", "-D", FEATURE)
            shutil.rmtree(self.dir / ".claude/state/reviews")

    def test_no_review_blocked(self):
        self.branch_with(FEATURE, {"README.md": "x\n"})
        self.gate(FEATURE)
        self.assertBlocked(self.merge(FEATURE), "mark-reviewed.sh")

    def test_review_bound_to_tip(self):
        self.branch_with(FEATURE, {"README.md": "x\n"})
        self.review(FEATURE, "codex")
        self.git("checkout", "-q", FEATURE)
        self.write("README.md", "y\n")
        self.commit_all()
        self.git("checkout", "-q", "main")
        self.gate(FEATURE)
        self.assertBlocked(self.merge(FEATURE), "непроверенные правки")
        subprocess.run(["bash", ".claude/scripts/mark-reviewed.sh", "--delta", "--by", "codex", FEATURE, "ok"], cwd=self.dir, check=True, capture_output=True)
        self.assertAllowed(self.merge(FEATURE))

    def test_marks_made_in_a_worktree_open_the_merge_from_the_main_checkout(self):
        # HF-177: ревью идёт в worktree, мерж - из основного чекаута. Отметка одна на репозиторий и по-прежнему привязана к вершине.
        self.branch_with(FEATURE, {"README.md": "x\n"})
        wt = Path(tempfile.mkdtemp()) / "wt"
        self.addCleanup(shutil.rmtree, wt.parent, True)
        self.git("worktree", "add", "-q", str(wt), FEATURE)
        r = subprocess.run(["bash", str(self.dir / ".claude/scripts/mark-reviewed.sh"), "--full", "--by", "codex", FEATURE, "ok"],
                           cwd=wt, capture_output=True, text=True)
        self.assertEqual(0, r.returncode, r.stderr)
        self.assertFalse((wt / ".claude/state/reviews").exists())
        self.gate(FEATURE)
        ready = subprocess.run(["bash", ".claude/scripts/merge-ready.sh", FEATURE], cwd=wt, capture_output=True, text=True)
        self.assertEqual((0, "READY\n"), (ready.returncode, ready.stdout), ready.stdout + ready.stderr)
        self.assertAllowed(self.merge(FEATURE))
        subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "--allow-empty", "-m", "PLAN-145 next"], cwd=wt, check=True)
        self.assertBlocked(self.merge(FEATURE), "гейта на вершине")

    def test_mark_reviewed_requires_by(self):
        self.branch_with(FEATURE, {"README.md": "x\n"})
        r = subprocess.run(["bash", ".claude/scripts/mark-reviewed.sh", "--full", FEATURE, "ok"], cwd=self.dir, capture_output=True, text=True)
        self.assertNotEqual(0, r.returncode)
        self.assertIn("--by", r.stderr)
        self.review(FEATURE, "opus", "codex")
        names = sorted(p.name for p in (self.dir / ".claude/state/reviews").iterdir())
        self.assertEqual(["feature_PLAN-145-x.full.codex", "feature_PLAN-145-x.full.opus"], names)

    def test_every_money_path_pattern_is_live(self):
        """Перебор money-paths.txt: у каждой строки есть образец пути, который она ловит."""
        import merge_checks as mc
        samples = {}
        for pattern in mc.money_patterns():
            self.assertFalse(mc.is_money("README.md", [pattern]), pattern)
            if pattern.endswith("/"):
                self.assertTrue(mc.is_money(samples.get(pattern) or pattern + "y.php", [pattern]), pattern)
        existing = [p for p in mc.money_patterns() if not p.endswith("/") and "*" not in p]
        for path in existing:
            self.assertTrue((REPO / path).exists(), "money-paths.txt: нет файла " + path)


class TreeUniquenessTest(MergeCase):
    """E17: гонка номеров между ветками ловится на дереве результата слияния."""

    def rm_files(self, n, slug):
        return {"planning/roadmap/RM-%d-%s.md" % (n, slug): "# RM-%d\n\n- **Статус:** идея\n" % n,
                "planning/ROADMAP.md": base.HEAD + base.ROW % (1, 1) + (base.ROW % (n, n)).replace("RM-%d-x.md" % n, "RM-%d-%s.md" % (n, slug))}

    def test_same_rm_number_in_two_branches_blocked(self):
        self.branch_with("feature/PLAN-145-a", self.rm_files(50, "a"))
        self.branch_with(FEATURE, self.rm_files(50, "b"))
        self.git("merge", "-q", "--no-verify", "feature/PLAN-145-a")  # первая ветка уже в main
        self.owner("rm-add", "RM-50", FEATURE)
        self.ready(FEATURE)
        r = self.merge(FEATURE)
        self.assertBlocked(r, "E17")
        self.assertTrue(self.marker("rm-add-RM-50@feature%2FPLAN-145-x").exists())  # слово владельца не сожжено

    def test_distinct_numbers_pass(self):
        self.branch_with("feature/PLAN-145-a", self.rm_files(50, "a"))
        self.git("merge", "-q", "--no-verify", "feature/PLAN-145-a")
        current = (self.dir / "planning/ROADMAP.md").read_text()
        self.branch_with(FEATURE, {"planning/roadmap/RM-51-x.md": "# RM-51\n\n- **Статус:** идея\n",
                                   "planning/ROADMAP.md": current + base.ROW % (51, 51)})
        self.owner("rm-add", "RM-51", FEATURE)
        self.ready(FEATURE)
        self.assertAllowed(self.merge(FEATURE))


class HotfixAndPlanTest(MergeCase):
    """E3 на merge-gate."""

    def test_hotfix_without_journal_entry_blocked_then_allowed(self):
        self.branch_with(HOTFIX, {"app/h.php": "<?php\n"})
        self.ready(HOTFIX)
        self.assertBlocked(self.merge(HOTFIX), "JOURNAL.md")
        self.git("checkout", "-q", HOTFIX)
        self.write("planning/JOURNAL.md", "- 2026-10-17 hotfix x\n")
        self.commit_all()
        self.git("checkout", "-q", "main")
        self.ready(HOTFIX)
        self.assertAllowed(self.merge(HOTFIX))

    def hotfix_registry(self):
        self.write("planning/HOTFIXES.md", HOTFIXES_HEAD)
        self.write("planning/hotfixes/.gitkeep", "")
        self.commit_all("hf registry PLAN-145")
        self.git("checkout", "-q", "main")

    def test_hotfix_with_registry_needs_file_and_row(self):
        self.git("checkout", "-q", "main")
        self.write("planning/HOTFIXES.md", HOTFIXES_HEAD)
        self.write("planning/hotfixes/.gitkeep", "")
        self.git("add", "-A")
        self.git("commit", "-q", "--no-verify", "-m", "hf registry")
        self.branch_with(HOTFIX, {"app/h.php": "<?php\n"})
        self.ready(HOTFIX)
        self.assertBlocked(self.merge(HOTFIX), "HF-N-*.md")
        self.git("checkout", "-q", HOTFIX)
        r = subprocess.run(["bash", ".claude/scripts/registry.sh", "add", "HF", "auto", "fix"], cwd=self.dir, capture_output=True, text=True)
        self.assertEqual(0, r.returncode, r.stdout + r.stderr)
        self.commit_all()
        self.git("checkout", "-q", "main")
        self.ready(HOTFIX)
        self.assertAllowed(self.merge(HOTFIX))

    def test_plan_branch_for_unknown_plan_blocked(self):
        self.branch_with("feature/PLAN-777-z", {"README.md": "x\n"})
        self.ready("feature/PLAN-777-z")
        self.assertBlocked(self.merge("feature/PLAN-777-z"), "PLAN-777")


class BypassTest(MergeCase):
    """Обходы merge-gate: merge без ref, pull, обёртки, цепочки, octopus, -C, симуляция веток (3b review)."""

    def main_ready(self):
        self.branch_with(FEATURE, {"README.md": "x\n"})
        self.ready(FEATURE)

    def test_b1_merge_without_ref_on_main_blocked(self):
        self.main_ready()
        self.assertBlocked(self.hook("merge-gate.sh", "git merge"), "укажи ветку")
        self.assertBlocked(self.hook("merge-gate.sh", "git merge --ff-only"), "укажи ветку")

    def test_b1_abort_continue_quit_pass(self):
        self.main_ready()
        for opt in ("--abort", "--continue", "--quit"):
            self.assertAllowed(self.hook("merge-gate.sh", "git merge " + opt))

    def with_origin(self):
        """Локальный bare-remote origin с main и upstream origin/main."""
        remote = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, remote, True)
        subprocess.run(["git", "init", "-q", "--bare", str(remote)], check=True)
        self.git("remote", "add", "origin", str(remote))
        self.git("-c", "core.hooksPath=/dev/null", "push", "-q", "-u", "origin", "main")

    def test_b2_pull_only_main(self):
        self.main_ready()
        self.with_origin()
        self.assertBlocked(self.hook("merge-gate.sh", "git pull origin " + FEATURE), "pull")
        self.assertBlocked(self.hook("merge-gate.sh", "git pull origin main " + FEATURE), "pull")
        for ok in ("git pull --ff-only", "git pull origin main", "git pull --ff-only origin main", "git pull -q --ff-only origin main"):
            self.assertAllowed(self.hook("merge-gate.sh", ok))

    def test_pull_strict_forms_blocked(self):
        self.main_ready()
        self.with_origin()
        for cmd in ("git pull", "git pull origin", "git pull /tmp/unreviewed main", "git pull --rebase origin main",
                    "git pull --rebase", "git pull https://example.invalid/x.git main", "git pull --no-ff origin main", "git pull nosuch main"):
            self.assertBlocked(self.hook("merge-gate.sh", cmd), "pull")

    def test_pull_ff_only_needs_upstream_origin_main(self):
        self.main_ready()
        self.assertBlocked(self.hook("merge-gate.sh", "git pull --ff-only"), "upstream")  # нет upstream

    def test_b2_pull_on_feature_branch_allowed(self):
        self.main_ready()
        self.git("checkout", "-q", FEATURE)
        self.assertAllowed(self.hook("merge-gate.sh", "git pull origin whatever"))

    def test_b3_wrappers_and_fallback_find_git(self):
        self.main_ready()
        for cmd in ("env -i FOO=1 git merge", "command git merge", "nice -n 5 git merge", "sudo -u nobody git merge",
                    "xargs git merge", "timeout 5 git merge", "python3 x.py git merge", "bash -c 'git merge'", "exec git pull origin " + FEATURE):
            self.assertBlocked(self.hook("merge-gate.sh", cmd), "")

    def test_b3_data_mentions_are_not_commands(self):
        self.main_ready()
        for cmd in ("echo git merge", "grep -rn 'git merge' planning", "cat notes-git-merge.txt"):
            self.assertAllowed(self.hook("merge-gate.sh", cmd))

    def test_b4_ref_mutation_before_merge_blocked(self):
        self.main_ready()
        for pre in ("git fetch origin", "git update-ref refs/heads/zz HEAD", "git branch -f zz HEAD", "git tag -f t HEAD",
                    "git reset --soft HEAD", "git pull"):
            self.assertBlocked(self.hook("merge-gate.sh", "%s && git merge %s" % (pre, FEATURE)), "отдельные команды")

    def test_b4_moving_refs_blocked(self):
        self.main_ready()
        for ref in ("FETCH_HEAD", "ORIG_HEAD", "MERGE_HEAD", "CHERRY_PICK_HEAD"):
            self.assertBlocked(self.hook("merge-gate.sh", "git merge " + ref), "подвижная")

    def test_b4_mutation_on_feature_target_is_fine(self):
        self.main_ready()
        self.git("checkout", "-q", "-b", "topic/q", "main")
        self.assertAllowed(self.hook("merge-gate.sh", "git fetch origin && git merge main"))

    def test_b5_octopus_into_main_blocked(self):
        self.main_ready()
        self.branch_with("feature/PLAN-146-y", {"README.md": "y\n"})
        self.assertBlocked(self.hook("merge-gate.sh", "git merge %s feature/PLAN-146-y" % FEATURE), "octopus")

    def test_i1_joined_C_and_git_dir_forms(self):
        self.main_ready()
        for cmd in ("git -C%s merge" % self.dir, "git -C %s merge" % self.dir,
                    "git --git-dir=%s/.git --work-tree=%s merge" % (self.dir, self.dir), "cd %s && git merge" % self.dir):
            self.assertBlocked(self.hook("merge-gate.sh", cmd), "укажи ветку")

    def test_i1_each_merge_checked_in_its_own_wd(self):
        self.main_ready()
        other = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, other, True)
        subprocess.run(["git", "init", "-q", "-b", "main"], cwd=other, check=True)
        subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "--allow-empty", "-m", "i"], cwd=other, check=True)
        # первая merge-команда - в другом репозитории (там main и merge без ссылки), вторая - в проекте
        self.assertBlocked(self.hook("merge-gate.sh", "git -C %s merge && git merge %s" % (other, FEATURE)), "укажи ветку")

    def test_payload_cwd_is_the_base_of_a_bare_merge(self):
        # Хук стартует в чекауте на feature, merge идёт из worktree на main (HF-174): цель даёт cwd из payload.
        self.main_ready()
        self.git("checkout", "-q", "-B", "hotfix/elsewhere")
        wt = Path(tempfile.mkdtemp()) / "wt"
        self.addCleanup(shutil.rmtree, wt.parent, True)
        self.git("worktree", "add", "-q", str(wt), "main")
        r = subprocess.run(["bash", str(self.dir / ".claude/hooks/merge-gate.sh")],
                           input=json.dumps({"cwd": str(wt), "tool_input": {"command": "git merge"}}),
                           text=True, capture_output=True, cwd=self.dir, env=dict(_os.environ, CLAUDE_PROJECT_DIR=str(self.dir)))
        self.assertBlocked(r, "укажи ветку")

    def test_i2_switch_to_feature_makes_target_feature(self):
        self.branch_with(FEATURE, {"planning/roadmap/RM-9-x.md": "# RM-9\n", "planning/ROADMAP.md": base.HEAD + base.ROW % (1, 1) + base.ROW % (9, 9)})
        self.owner("rm-add", "RM-9", FEATURE)
        self.ready(FEATURE)
        self.git("branch", "feature/PLAN-146-y", "main")
        r = self.hook("merge-gate.sh", "git switch feature/PLAN-146-y && git merge " + FEATURE)
        self.assertAllowed(r)
        self.assertTrue(self.marker("rm-add-RM-9@feature%2FPLAN-145-x").exists())  # цель не main: маркер цел

    def test_i2_checkout_new_branch_then_main_again(self):
        self.main_ready()
        self.git("checkout", "-q", FEATURE)
        r = self.hook("merge-gate.sh", "git checkout -b topic/z && git checkout main && git merge")
        self.assertBlocked(r, "укажи ветку")

    def test_protected_commands_blocked_on_main(self):
        self.main_ready()
        for cmd in ("git cherry-pick abc", "git rebase topic", "git reset --hard HEAD~1", "git reset --merge", "git reset --keep",
                    "git update-ref refs/heads/main HEAD", "git branch -f main HEAD", "git push . HEAD:main",
                    "git symbolic-ref HEAD refs/heads/main", "git fetch origin topic:main", "git checkout -B main", "git switch -C main"):
            self.assertBlocked(self.hook("merge-gate.sh", cmd), "правила проекта")

    def test_protected_commands_allowed_on_feature_and_soft_reset(self):
        self.main_ready()
        self.git("checkout", "-q", FEATURE)
        for cmd in ("git cherry-pick abc", "git rebase main", "git reset --hard HEAD", "git branch -f zz HEAD", "git symbolic-ref --short HEAD"):
            self.assertAllowed(self.hook("merge-gate.sh", cmd))
        self.git("checkout", "-q", "main")
        for ok in ("git reset --soft HEAD", "git reset", "git reset -q HEAD", "git reset HEAD -- README.md", "git reset -- README.md"):
            self.assertAllowed(self.hook("merge-gate.sh", ok))

    def test_update_ref_of_main_blocked_even_on_feature(self):
        self.main_ready()
        self.git("checkout", "-q", FEATURE)
        self.assertBlocked(self.hook("merge-gate.sh", "git update-ref refs/heads/main HEAD"), "правила проекта")


    def test_substitution_and_eval_hide_nothing(self):
        self.main_ready()
        for cmd in ('eval "git merge"', 'echo "$(git merge)"', "`git merge`", 'x=$(git merge)', 'eval "git pull /tmp/x main"'):
            self.assertBlocked(self.hook("merge-gate.sh", cmd), "")

    def test_unparsable_nested_git_merge_fails_closed(self):
        self.main_ready()
        self.assertBlocked(self.hook("merge-gate.sh", 'echo "$(git merge \'bad)"'), "fail-closed")

    def test_git_dir_and_env_context(self):
        self.main_ready()
        for cmd in ("git --git-dir=.git merge nosuch", "GIT_DIR=.git git merge nosuch", "git --git-dir=%s/.git --work-tree=%s merge nosuch" % (self.dir, self.dir),
                    "env GIT_DIR=.git git merge nosuch"):
            self.assertBlocked(self.hook("merge-gate.sh", cmd), "не резолвится")

    def test_unknown_repository_is_refusal_not_skip(self):
        self.main_ready()
        self.assertBlocked(self.hook("merge-gate.sh", "git --git-dir=/nonexistent merge x"), "не удалось определить")
        self.assertBlocked(self.hook("merge-gate.sh", "cd /nonexistent-dir && git merge x"), "не удалось определить")

    def test_reset_variants_blocked_on_main(self):
        self.main_ready()
        for cmd in ("git reset --soft HEAD~1", "git reset --mixed HEAD~1", "git reset HEAD~1", "git reset abc123", "git reset --hard",
                    "git reset --soft=x HEAD~1"):
            self.assertBlocked(self.hook("merge-gate.sh", cmd), "reset")

    def test_long_options_and_update_ref_stdin(self):
        self.main_ready()
        for cmd in ("git switch --force-create main", "git checkout -B main", "git update-ref --stdin", "git update-ref -m why refs/heads/main HEAD"):
            self.assertBlocked(self.hook("merge-gate.sh", cmd), "")
        self.git("checkout", "-q", FEATURE)
        self.assertBlocked(self.hook("merge-gate.sh", "git update-ref --stdin"), "update-ref")  # --stdin - всегда
        self.assertAllowed(self.hook("merge-gate.sh", "git update-ref refs/heads/zz HEAD"))

    def test_switch_dash_and_reflog_refs(self):
        self.main_ready()
        self.git("checkout", "-q", "main")
        self.git("checkout", "-q", FEATURE)  # @{-1} = main
        for cmd in ("git switch - && git merge", "git checkout - && git merge", "git checkout @{-1} && git merge"):
            self.assertBlocked(self.hook("merge-gate.sh", cmd), "укажи ветку")
        # @{-9} не определён - цель считается main
        self.assertBlocked(self.hook("merge-gate.sh", "git switch @{-9} && git merge"), "укажи ветку")


class ParseTest(unittest.TestCase):
    def test_wrappers_joined_C_and_git_dir(self):
        import commit_checks as cc
        cases = {
            "env -i A=1 git merge x": ("merge", "/w"),
            "nice -n 5 git merge x": ("merge", "/w"),
            "sudo -u u git -C/r merge x": ("merge", "/r"),
            "git -C /r merge x": ("merge", "/r"),
            "cd /c && git merge x": ("merge", "/c"),
            "python3 s.py git merge x": ("merge", "/w"),
        }
        for cmd, (sub, wd) in cases.items():
            calls = cc.parse(cmd, "/w")
            self.assertEqual([(sub, wd)], [(c["sub"], c["wd"]) for c in calls], cmd)
        self.assertEqual([], cc.parse("echo git merge x; grep 'git pull' f", "/w"))
        call = cc.parse("git --git-dir=.g --work-tree=/t merge x", "/w")[0]
        self.assertEqual(("/w/.g", "/t", "/w"), (call["gitdir"], call["worktree"], call["wd"]))
        call = cc.parse("GIT_DIR=/g GIT_WORK_TREE=/t git merge x", "/w")[0]
        self.assertEqual(("/g", "/t"), (call["gitdir"], call["worktree"]))

    def test_substitutions_and_eval(self):
        import commit_checks as cc
        for cmd in ('eval "git merge bad"', 'echo "$(git merge bad)"', "`git merge bad`", 'x=$(git merge bad)',
                    'echo "$(echo $(git merge bad))"', 'eval git merge bad', r'bash -c "eval \"git merge bad\""'):
            self.assertEqual(["merge"], [c["sub"] for c in cc.parse(cmd, "/w")][:1], cmd)
        self.assertEqual(["commit"], [c["sub"] for c in cc.parse('eval "git commit --no-verify"', "/w")])
        self.assertEqual([], cc.parse("echo '$(git merge bad)' '`git merge bad`'", "/w"))
        self.assertEqual([], cc.parse('echo "$(date)"', "/w"))
        with self.assertRaises(ValueError):  # не разбирается, но похоже на git merge - fail-closed
            cc.parse('echo "$(git merge \'bad)"', "/w")


class MoneyEnumerationTest(unittest.TestCase):
    """I3: каждый файл приложения с денежным словом в пути - денежный путь (исключения перечислены явно)."""

    KEYWORDS = re.compile(r"price|balance|payment|refund|tariff|invoice|billing|subscription", re.I)
    EXCEPTIONS = {}  # путь -> почему не деньги

    def test_every_money_keyword_file_is_money(self):
        import merge_checks as mc
        patterns = mc.money_patterns()
        tracked = subprocess.run(["git", "ls-files", "app", "database/factories", "database/migrations", "config"], cwd=REPO,
                                 capture_output=True, text=True).stdout.split()
        missed = []
        for path in tracked:
            word = self.KEYWORDS.search(path)
            if not word:
                continue
            if path not in self.EXCEPTIONS and not mc.is_money(path, patterns):
                missed.append(path)
        self.assertEqual([], missed, "денежные файлы вне money-paths.txt")

    def test_template_classifies_typical_paths(self):
        import merge_checks as mc
        patterns = mc.money_patterns()
        for path in ("app/Services/Billing/BalanceService.php", "app/Models/Invoice.php",
                     "database/migrations/2026_01_01_create_payments_table.php", "config/billing.php"):
            self.assertTrue(mc.is_money(path, patterns), path)
        for path in ("app/Http/Controllers/PlanetAvatarController.php", "README.md"):
            self.assertFalse(mc.is_money(path, patterns), path)

if __name__ == "__main__":
    unittest.main()
