"""Поведение .claude/hooks/main-push-guard.sh на временном git-репозитории.

Запуск: python3 .claude/hooks/test_main_push_guard.py
Блокирует = exit 2, пропускает = exit 0.
"""

# Герметичность: переменные среды Claude Code/git-хука не должны течь в подпроцессы фикстур (хуки делают
# `cd "${CLAUDE_PROJECT_DIR:-.}"` и ушли бы в настоящий репозиторий).
import os as _os
for _v in [k for k in _os.environ if k.startswith("GIT_") or k == "CLAUDE_PROJECT_DIR"]:
    _os.environ.pop(_v, None)

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

HOOK = Path(__file__).resolve().parent / "main-push-guard.sh"


REDIRECTIONS = [
    "2>&1", "2>/dev/null", "2> /dev/null", ">f", "> f", ">>f", ">> f", "&>f", "&> f", "&>>f", "&>> f", "1>f", "2>>f",
    ">&2", "2>&-", "<f", "< f", "<<<word", "<<< 'a b'", ">|f", "2>&1 | cat", "|& cat", "2>&1 && true", ">f 2>&1",
]


class MainPushGuardTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.repo = Path(cls.tmp.name) / "repo"
        cls.other = Path(cls.tmp.name) / "other-on-main"
        cls.repo.mkdir()
        cls.git(cls.repo, "init", "-q", "-b", "main")
        cls.git(cls.repo, "-c", "user.email=a@b", "-c", "user.name=t", "commit", "-q", "--allow-empty", "-m", "init")
        cls.git(cls.repo, "worktree", "add", "-q", str(cls.other), "-b", "main-copy")
        cls.git(cls.other, "checkout", "-q", "main-copy")

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    @staticmethod
    def git(cwd, *args):
        subprocess.run(["git", "-C", str(cwd), *args], check=True, capture_output=True)

    def run_hook(self, branch, command, cwd=None, payload_cwd=None):
        self.git(self.repo, "checkout", "-q", "-B", branch)
        payload = {"tool_input": {"command": command}}
        if payload_cwd:
            payload["cwd"] = str(payload_cwd)
        payload = json.dumps(payload)
        env = dict(os.environ, CLAUDE_PROJECT_DIR=str(self.repo))
        return subprocess.run(
            ["bash", str(HOOK)], input=payload, text=True, capture_output=True,
            cwd=str(cwd or self.repo), env=env,
        ).returncode

    def assertBlocked(self, branch, command, cwd=None):
        self.assertEqual(2, self.run_hook(branch, command, cwd), "[%s] %s должен блокироваться" % (branch, command))

    def assertAllowed(self, branch, command, cwd=None):
        self.assertEqual(0, self.run_hook(branch, command, cwd), "[%s] %s должен проходить" % (branch, command))

    def test_direct_pushes_to_main_are_blocked(self):
        for command in [
            "git push origin main",
            "git push origin HEAD:main",
            "git push origin +main",
            "git push origin refs/heads/main",
            "git push origin refs/heads/x:refs/heads/main",
            "git push origin feature:main",
            "git push origin :main",
            "git push --force origin main",
            "git push --force-with-lease origin main",
            "git push --delete origin main",
            "git push --all",
            "git push --mirror origin",
        ]:
            self.assertBlocked("hotfix/x", command)

    def test_tag_named_main_does_not_hide_the_main_branch(self):
        # refs/tags/main: `rev-parse --abbrev-ref HEAD` давал heads/main, и голый push из main проходил
        self.git(self.repo, "checkout", "-q", "-B", "main")
        self.git(self.repo, "tag", "-f", "main")
        try:
            self.assertBlocked("main", "git push")
        finally:
            self.git(self.repo, "tag", "-d", "main")

    def test_bare_push_from_main_is_blocked(self):
        for command in ["git push", "git push origin", "git push origin HEAD", "git push -u origin"]:
            self.assertBlocked("main", command)

    def test_chains_and_nested_shells_are_blocked(self):
        for command in [
            "git status && git push origin main",
            "git add -A; git commit -m x; git push origin main",
            "echo ok | git push origin main",
            'bash -c "git push origin main"',
            "sh -c 'git push origin main'",
            "git -C /somewhere push origin main",
            "git -c core.x=1 push origin main",
            'git push origin "main"',
            "git push origin 'main'",
            "git subtree push --prefix=public origin main",
            "git subtree push --prefix public origin main",
        ]:
            self.assertBlocked("hotfix/x", command)

    def test_substitution_is_blocked_only_on_main(self):
        self.assertBlocked("main", "git push origin $(git branch --show-current)")
        self.assertBlocked("main", "git push origin `git branch --show-current`")
        self.assertAllowed("hotfix/x", "git push origin $(git branch --show-current)")

    def test_cd_into_another_directory_uses_that_branch(self):
        # в каталоге other стоит ветка main-copy, в корне — main
        self.assertAllowed("main", "cd %s && git push origin HEAD" % self.other)
        # из feature-ветки корня, но cd в каталог, где HEAD — main, ловится только по явному main
        self.assertBlocked("hotfix/x", "cd %s && git push origin main" % self.other)

    def test_payload_cwd_is_the_base_of_a_bare_push(self):
        # Хук стартует в основном чекауте, push идёт из worktree на main (HF-174): ветку даёт cwd из payload.
        self.git(self.repo, "checkout", "-q", "-B", "hotfix/x")
        self.git(self.other, "checkout", "-q", "main")
        self.addCleanup(self.git, self.other, "checkout", "-q", "main-copy")
        self.assertEqual(2, self.run_hook("hotfix/x", "git push origin HEAD", payload_cwd=self.other))

    def test_option_values_are_not_taken_for_refspecs(self):
        self.assertBlocked("hotfix/x", "git push --repo=origin main")
        self.assertBlocked("hotfix/x", "git push --repo origin main")
        self.assertAllowed("hotfix/x", "git push -o ci.skip origin hotfix/x")
        self.assertBlocked("main", "git push --receive-pack git-receive-pack origin")

    def test_branches_and_tags_pass(self):
        for command in [
            "git push -u origin hotfix/main-push-guard",
            "git push origin hotfix/x",
            "git push origin feature/main-fix",
            "git push origin feature/PLAN-1-a",
            "git push origin v1.0.0",
            "git push origin refs/tags/v1.0.0",
            "git push origin tag v1.0.0",
            "git push origin tag main",
            "git push --tags",
            "git push origin --delete hotfix/old",
        ]:
            self.assertAllowed("hotfix/x", command)
        self.assertAllowed("main", "git push --tags origin")

    def test_other_git_commands_and_text_pass(self):
        for command in [
            "git pull origin main",
            "git status",
            "git merge hotfix/x",
            "echo push to main",
            "git log --oneline",
            "grep push README.md",
        ]:
            self.assertAllowed("main", command)

    def test_redirections_do_not_change_verdict(self):
        """HF-150: вердикт с перенаправлением (в конце и после `push`) равен вердикту без него."""
        cases = [
            ("hotfix/x", "git push origin main"), ("hotfix/x", "git push origin hotfix/x"),
            ("hotfix/x", "git push -u origin hotfix/x"), ("main", "git push"), ("main", "git push origin"),
            ("hotfix/x", "git push --force origin main"),
        ]
        for branch, command in cases:
            want = self.run_hook(branch, command)
            for form in REDIRECTIONS:
                with self.subTest(command=command, form=form):
                    self.assertEqual(want, self.run_hook(branch, "%s %s" % (command, form)))
                    if "&&" not in form and "|" not in form:  # конвейер/&& заканчивает команду - после push не вставить
                        self.assertEqual(want, self.run_hook(branch, command.replace("push", "push %s" % form, 1)))




class MainPublishTest(unittest.TestCase):
    """Публикация main разрешена, только если впереди <remote>/main на основной линии лишь мерж-коммиты (решение владельца 2026-10-17)."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        base = Path(self.tmp.name)
        self.origin = base / "origin.git"
        self.repo = base / "repo"
        subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(self.origin)], check=True)
        self.repo.mkdir()
        self.git("init", "-q", "-b", "main")
        self.git("remote", "add", "origin", str(self.origin))
        self.commit("init")
        self.git("push", "-q", "origin", "main")  # прямой вызов git, мимо хука

    def git(self, *args):
        return subprocess.run(["git", "-c", "user.email=a@b", "-c", "user.name=t", "-C", str(self.repo), *args],
                              check=True, capture_output=True, text=True).stdout

    def commit(self, msg):
        self.git("commit", "-q", "--allow-empty", "-m", msg)

    def merged_branch(self):
        """Ветка с коммитом, влитая в main мерж-коммитом; main остаётся на ней же (HEAD)."""
        self.git("checkout", "-q", "-b", "feature/x")
        self.commit("feature work")
        self.git("checkout", "-q", "main")
        self.git("merge", "-q", "--no-ff", "-m", "Merge feature/x", "feature/x")

    def hook(self, command):
        payload = json.dumps({"tool_input": {"command": command}})
        env = dict(os.environ, CLAUDE_PROJECT_DIR=str(self.repo))
        return subprocess.run(["bash", str(HOOK)], input=payload, text=True, capture_output=True, cwd=str(self.repo), env=env).returncode

    def allowed(self, *commands):
        for c in commands:
            self.assertEqual(0, self.hook(c), "%s должен проходить" % c)

    def blocked(self, *commands):
        for c in commands:
            self.assertEqual(2, self.hook(c), "%s должен блокироваться" % c)

    PUBLISH = ["git push origin main", "git push origin main:main", "git push origin refs/heads/main", "git push origin HEAD:main",
               "git push origin HEAD", "git push", "git push origin", "git push -u origin main", "git push origin refs/heads/main:refs/heads/main"]

    def test_merge_of_branch_without_direct_commits_is_allowed(self):
        self.merged_branch()
        self.allowed(*self.PUBLISH)

    def test_nothing_ahead_is_allowed(self):
        self.allowed(*self.PUBLISH)

    def test_direct_commit_on_main_is_blocked(self):
        self.commit("direct")
        self.blocked(*self.PUBLISH)

    def test_merge_plus_direct_commit_is_blocked(self):
        self.merged_branch()
        self.commit("direct after merge")
        self.blocked(*self.PUBLISH)

    def test_direct_commit_then_merge_is_blocked(self):
        self.commit("direct before merge")
        self.merged_branch()
        self.blocked(*self.PUBLISH)

    def test_fast_forward_merge_counts_as_direct_commits(self):
        self.git("checkout", "-q", "-b", "feature/ff")
        self.commit("ff work")
        self.git("checkout", "-q", "main")
        self.git("merge", "-q", "--ff-only", "feature/ff")
        self.blocked("git push origin main")

    def test_force_and_destructive_forms_are_blocked_even_when_clean(self):
        self.merged_branch()
        self.blocked("git push origin +main", "git push --force origin main", "git push -f origin main", "git push -fu origin main",
                     "git push --force-with-lease origin main", "git push --force-with-lease=main origin main",
                     "git push --delete origin main", "git push origin :main", "git push --all", "git push --mirror origin",
                     "git push --force", "git push origin +HEAD:main")

    def test_source_must_be_main(self):
        self.merged_branch()
        self.git("checkout", "-q", "-b", "feature/y")
        self.blocked("git push origin feature/y:main", "git push origin HEAD:main", "git push origin feature/x:refs/heads/main")
        self.allowed("git push origin main")  # локальная main публикуется и с другой ветки
        self.allowed("git push origin feature/y")

    def test_unusable_remote_is_blocked(self):
        self.merged_branch()
        self.blocked("git push %s main" % self.origin, "git push --repo origin main", "git push nonexistent main")
        self.git("remote", "set-url", "origin", str(self.origin) + ".gone")  # ls-remote не отработает
        self.blocked(*self.PUBLISH)

    def test_base_is_real_server_sha_not_local_tracking_ref(self):
        """I2: устаревший tracking-ref не обманывает - база по `git ls-remote`."""
        self.merged_branch()
        self.git("update-ref", "-d", "refs/remotes/origin/main")
        self.allowed(*self.PUBLISH)  # tracking-ref не нужен: сервер отвечает, прямых коммитов впереди нет
        # другой клон добавил на сервер прямой коммит, мы его не забирали: серверного SHA локально нет
        other = Path(self.tmp.name) / "other"
        subprocess.run(["git", "clone", "-q", str(self.origin), str(other)], check=True, capture_output=True)
        subprocess.run(["git", "-c", "user.email=a@b", "-c", "user.name=t", "-C", str(other), "commit", "-q", "--allow-empty", "-m", "srv"],
                       check=True, capture_output=True)
        subprocess.run(["git", "-C", str(other), "push", "-q", "origin", "main"], check=True, capture_output=True)
        self.blocked(*self.PUBLISH)
        # забрали: серверный main не предок локального (история разошлась) - тоже блок
        self.git("fetch", "-q", "origin")
        self.blocked(*self.PUBLISH)

    def test_ambiguous_origin_main_branch_does_not_fool_the_check(self):
        """B2: `git branch origin/main` не подменяет ссылку - используются refs/heads/main и серверный SHA."""
        self.commit("direct")
        self.git("branch", "origin/main", "main")  # короткое origin/main теперь неоднозначно и указывает на локальный main
        self.blocked(*self.PUBLISH)

    def test_branch_switch_inside_command_is_resolved_or_blocked(self):
        """B1: смена ветки до push внутри той же команды."""
        self.merged_branch()
        self.git("branch", "feature/z")
        self.blocked("git switch feature/z && git push origin HEAD:main", "git checkout feature/z && git push origin HEAD:main",
                     "git checkout -b new/x && git push origin HEAD:main", "git switch -c new/x && git push origin HEAD:main",
                     "git checkout - && git push origin HEAD:main", "git checkout -- README.md && git push origin HEAD:main",
                     "git -C . switch feature/z && git push origin HEAD:main")
        self.allowed("git switch main && git push origin HEAD:main", "git checkout main; git push origin HEAD:main")
        self.allowed("git switch feature/z && git push origin HEAD")  # обычная ветка
        self.commit("direct")
        self.blocked("git switch main && git push origin HEAD:main", "git checkout main && git push")

    def test_wildcard_and_matching_refspecs_are_blocked(self):
        self.merged_branch()
        self.blocked("git push origin refs/heads/*:refs/heads/*", "git push origin 'refs/heads/*:refs/heads/*'", "git push origin :",
                     "git push origin +:", "git push origin main*", "git push origin refs/heads/main*:refs/heads/main",
                     "git push origin +refs/heads/*:refs/heads/*")

    def test_substitution_subtree_and_chains(self):
        self.merged_branch()
        self.blocked("git push origin $(git branch --show-current)", "git subtree push --prefix=public origin main")
        self.allowed("git status && git push origin main")
        self.commit("direct")
        self.blocked("git status && git push origin main", 'bash -c "git push origin main"')


if __name__ == "__main__":
    unittest.main()
