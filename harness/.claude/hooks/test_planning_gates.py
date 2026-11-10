"""Хуки планирования PLAN-145 на временных git-репозиториях (по образцу test_main_push_guard.py).

Запуск: python3 .claude/hooks/test_planning_gates.py
Блокирует = exit 2, пропускает = exit 0. Для каждого правила — сценарий нарушения и сценарий нормы.
"""

# Герметичность: переменные среды Claude Code/git-хука не должны течь в подпроцессы фикстур (хуки делают
# `cd "${CLAUDE_PROJECT_DIR:-.}"` и ушли бы в настоящий репозиторий).
import os as _os
for _v in [k for k in _os.environ if k.startswith("GIT_") or k == "CLAUDE_PROJECT_DIR"]:
    _os.environ.pop(_v, None)

import json
import os
import shutil
import sys
import subprocess
import tempfile
import time
import unittest
from pathlib import Path

HOOKS = Path(__file__).resolve().parent
sys.path.insert(0, str(HOOKS))
SCRIPTS = HOOKS.parent / "scripts"
REAL_ROOT = HOOKS.parent.parent

RM_HEAD = "| RM | Название | Статус | Дата | Триггер / → PLAN-N |\n|---|---|---|---|---|\n"


class GateCase(unittest.TestCase):
    """Временный репозиторий с копиями хуков; ветка feature/PLAN-145-x по умолчанию."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.repo = Path(self.tmp.name) / "repo"
        self.repo.mkdir()
        self.git("init", "-q", "-b", "main")
        self.git("config", "user.email", "t@e.invalid")
        self.git("config", "user.name", "t")
        self.git("config", "core.hooksPath", ".githooks")
        self.git("commit", "-q", "--allow-empty", "-m", "init")
        dest = self.repo / ".claude"
        shutil.copytree(HOOKS, dest / "hooks", ignore=shutil.ignore_patterns("test_*", "__pycache__"))
        (dest / "scripts").mkdir()
        shutil.copy2(SCRIPTS / "registry.sh", dest / "scripts")
        self.branch("feature/PLAN-145-x")

    def git(self, *args):
        return subprocess.run(["git", "-C", str(self.repo), *args], check=True, capture_output=True, text=True).stdout

    def branch(self, name):
        self.git("checkout", "-q", "-B", name)

    def stage(self, path, content="x\n"):
        target = self.repo / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content)
        self.git("add", "-f", path)

    def owner_ok(self, kind, ident):
        """Слово владельца (E10/E11) для текущей ветки — файл маркера, как его пишет owner-ok.sh."""
        branch = self.git("rev-parse", "--abbrev-ref", "HEAD").strip()
        marker = self.repo / ".claude/state/owner-ok" / ("%s-%s@%s" % (kind, ident, branch.replace("/", "%2F")))
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text("kind=%s\nid=%s\nbranch=%s\nsha=x\ntarget=main\nissued=%d\n" % (kind, ident, branch, time.time()))

    def hook(self, name, payload, **env):
        return subprocess.run(
            ["bash", str(self.repo / ".claude/hooks" / name)], input=json.dumps(payload), text=True,
            capture_output=True, cwd=str(self.repo),
            env=dict(os.environ, CLAUDE_PROJECT_DIR=str(self.repo), **env),
        )

    def commit(self, command="git commit -m x"):
        return self.hook("commit-gate.sh", {"tool_input": {"command": command}})

    def assertBlocked(self, result, text=None):
        self.assertEqual(2, result.returncode, result.stderr)
        if text:
            self.assertIn(text, result.stderr)

    def assertAllowed(self, result):
        self.assertEqual(0, result.returncode, result.stderr)


def plan_doc(resume_lines=3, resume=True, pad=0, waiver=False):
    head = "# PLAN-145 — x\n" + ("<!-- size-waiver: тест -->\n" if waiver else "") + "\n"
    body = "## Резюме\n" + "строка\n" * resume_lines + "\n" if resume else ""
    return head + body + "## Дальше\n" + "z" * pad + "\n"


class CommitGateTest(GateCase):
    def test_e2_code_on_wrong_branch_blocked(self):
        self.branch("feature/RM-9-x")
        self.stage("app/a.php")
        self.assertBlocked(self.commit(), "E2")

    def test_commit_on_main_blocked_by_name_even_with_tag_named_main(self):
        # refs/tags/main: `rev-parse --abbrev-ref HEAD` давал heads/main, и сообщение называло несуществующую ветку
        self.branch("main")
        self.git("tag", "main")
        self.stage("app/a.php")
        self.assertBlocked(self.commit(), "'main'")

    def test_e2_hooks_dir_is_code(self):
        self.branch("feature/RM-9-x")
        self.stage(".claude/hooks/x.sh")
        self.assertBlocked(self.commit(), "E2")

    def test_e2_code_on_plan_and_hotfix_allowed(self):
        self.stage("app/a.php")
        self.assertAllowed(self.commit())
        self.branch("hotfix/y")
        self.assertAllowed(self.commit())

    def test_e2_roadmap_idea_allowed_on_rm_branch(self):
        self.branch("feature/RM-9-x")
        self.stage("planning/roadmap/RM-99-x.md", "# RM-99\n")
        self.owner_ok("rm-add", "RM-99")
        self.assertAllowed(self.commit())

    def test_unclassified_root_is_fail_closed(self):
        self.stage("newroot/a.txt")
        self.assertBlocked(self.commit(), "paths.conf")

    def test_e4_e5_bad_roadmap_status_blocked(self):
        self.stage("planning/ROADMAP.md", "# R\n\n" + RM_HEAD + "| [RM-1](roadmap/RM-1-x.md) | Тема | готово | 2026-10-16 | нет |\n")
        self.stage("planning/roadmap/RM-1-x.md", "# RM-1\n\n- **Статус:** готово\n")
        self.owner_ok("rm-add", "RM-1")
        self.assertBlocked(self.commit(), "registry.sh check")

    def test_e4_e5_clean_roadmap_allowed(self):
        self.stage("planning/ROADMAP.md", "# R\n\n" + RM_HEAD + "| [RM-1](roadmap/RM-1-x.md) | Тема | идея | 2026-10-16 | нет |\n")
        self.stage("planning/roadmap/RM-1-x.md", "# RM-1\n\n- **Статус:** идея\n")
        self.owner_ok("rm-add", "RM-1")
        self.assertAllowed(self.commit())

    def test_e7_new_plan_without_summary_blocked(self):
        self.stage("planning/plans/PLAN-145-x.md", plan_doc(resume=False))
        self.assertBlocked(self.commit(), "Резюме")

    def test_e7_summary_too_long_blocked_and_ok_allowed(self):
        self.stage("planning/plans/PLAN-146-x.md", plan_doc(resume_lines=20))
        self.assertBlocked(self.commit(), "20 строк")
        self.stage("planning/plans/PLAN-146-x.md", plan_doc(resume_lines=15))
        self.assertAllowed(self.commit())

    def test_e7_old_plan_without_summary_allowed(self):
        self.stage("planning/plans/PLAN-100-x.md", plan_doc(resume=False))
        self.assertAllowed(self.commit())

    def test_e8_over_80kb_blocked_waiver_allows_45kb_warns(self):
        self.stage("planning/plans/PLAN-146-x.md", plan_doc(pad=90 * 1024))
        self.assertBlocked(self.commit(), "80 КБ")
        self.stage("planning/plans/PLAN-146-x.md", plan_doc(pad=90 * 1024, waiver=True))
        self.assertAllowed(self.commit())
        self.stage("planning/plans/PLAN-146-x.md", plan_doc(pad=45 * 1024))
        result = self.commit()
        self.assertAllowed(result)
        self.assertIn("Предупреждение", result.stderr)

    def test_e13_claude_md_over_36kb_blocked(self):
        """Предел проверяем функцией: CLAUDE.md под E18 (`e18 on`), коммит через commit-gate потребовал бы маркер hooks-edit."""
        import commit_checks
        self.assertIn("36864", commit_checks.start_limit_problem("CLAUDE.md", b"x" * (36 * 1024 + 1)))
        self.assertIsNone(commit_checks.start_limit_problem("CLAUDE.md", b"x" * (36 * 1024)))

    def test_e13_status_file_is_gone_from_limits_and_root_whitelist(self):
        """Файла STATUS.md нет: лимита на него нет, а в корне planning/ он больше не допустим (E9)."""
        import commit_checks
        self.assertEqual(set(commit_checks.START_LIMITS), {"CLAUDE.md"})
        self.stage("planning/STATUS.md", "# S\n")
        self.assertBlocked(self.commit(), "E9")

    def test_e8_old_plan_over_limit_only_warns(self):
        self.stage("planning/plans/PLAN-103-x.md", plan_doc(resume=False, pad=233 * 1024))
        result = self.commit()
        self.assertAllowed(result)
        self.assertIn("Предупреждение", result.stderr)

    def test_e9_random_file_in_planning_root_blocked(self):
        self.stage("planning/random.md")
        self.assertBlocked(self.commit(), "E9")

    def test_e9_service_and_nested_paths_allowed(self):
        self.stage("planning/README.md")
        self.stage("planning/plans/PLAN-9-x.md")
        self.stage("planning/roadmap/RM-99-x.md")
        self.owner_ok("rm-add", "RM-99")
        self.assertAllowed(self.commit())

    def test_e16_no_verify_and_n_blocked(self):
        for command in ["git commit -n -m x", "git commit --no-verify -m x", "git commit -nm x",
                        "git push --no-verify origin feature/PLAN-145-x", "git add . && git commit -a -n",
                        'eval "git commit --no-verify -m x"', 'echo "$(git commit -n -m x)"', "`git commit --no-verify -m x`"]:
            self.assertBlocked(self.commit(command), "E16")

    def test_e16_normal_commands_pass(self):
        for command in ["git commit -m x", 'git commit -m "mention -n and --no-verify in text"',
                        "git push -n origin x", "git status"]:
            self.assertAllowed(self.commit(command))

    # --- B1: удаление старого неклассифицированного файла не блокируется
    def test_b1_deleting_unclassified_tracked_file_allowed(self):
        self.stage(".DS_Store")
        self.stage("oldroot/a.txt")
        self.git("-c", "core.hooksPath=/dev/null", "commit", "-q", "-m", "legacy")
        self.git("rm", "-q", ".DS_Store", "oldroot/a.txt")
        self.assertAllowed(self.commit())

    def test_b1_rename_into_unclassified_root_blocked(self):
        self.stage("app/a.php")
        self.git("-c", "core.hooksPath=/dev/null", "commit", "-q", "-m", "a")
        self.git("mv", "app/a.php", "newroot_a.php")
        self.assertBlocked(self.commit(), "paths.conf")

    # --- B2: строки данных не команды
    def test_b2_data_strings_pass(self):
        for command in ["python3 -c \"print('git commit -n')\"", 'echo "git commit --no-verify"',
                        'git commit -t "-n" -m x', "grep -- 'git push --no-verify' file",
                        "cat <<'EOF'\ngit commit -n\nEOF"]:
            self.assertAllowed(self.commit(command))

    def test_b2_real_bypasses_blocked(self):
        for command in ["git commit -a -n", 'bash -c "git commit --no-verify"', "git push --no-verify",
                        "sh -c 'git push --no-verify origin x'", "git add .\ngit commit -n", "git commit -m x --no-verify"]:
            self.assertBlocked(self.commit(command), "E16")

    # --- I1: каталог и обход через конфиг
    def make_worktree(self, branch):
        wt = Path(self.tmp.name) / "wt"
        self.git("worktree", "add", "-q", "-b", branch, str(wt))
        return wt

    def test_i1_dash_c_uses_that_worktrees_branch(self):
        wt = self.make_worktree("feature/RM-9-x")
        (wt / "app").mkdir()
        (wt / "app/a.php").write_text("x")
        subprocess.run(["git", "-C", str(wt), "add", "app/a.php"], check=True)
        self.assertBlocked(self.commit("git -C %s commit -m x" % wt), "E2")
        self.assertBlocked(self.commit("cd %s && git commit -m x" % wt), "E2")
        self.assertAllowed(self.commit("git commit -m x"))  # свой индекс пуст, ветка PLAN

    def test_i1_dash_c_to_plan_worktree_allowed_from_rm_branch(self):
        wt = self.make_worktree("feature/PLAN-7-w")
        (wt / "app").mkdir()
        (wt / "app/a.php").write_text("x")
        subprocess.run(["git", "-C", str(wt), "add", "app/a.php"], check=True)
        self.branch("feature/RM-9-x")
        self.assertAllowed(self.commit("git -C %s commit -m x" % wt))

    def test_payload_cwd_is_the_base_of_a_bare_commit(self):
        # Хук стартует в основном чекауте, команда идёт из worktree (HF-174): база разбора — cwd из payload.
        wt = self.make_worktree("feature/RM-9-x")
        (wt / "app").mkdir()
        (wt / "app/a.php").write_text("x")
        subprocess.run(["git", "-C", str(wt), "add", "app/a.php"], check=True)
        self.assertBlocked(self.hook("commit-gate.sh", {"cwd": str(wt), "tool_input": {"command": "git commit -m x"}}), "E2")

    def test_unparsed_cd_falls_back_to_payload_cwd(self):
        wt = self.make_worktree("feature/RM-9-x")
        (wt / "app").mkdir()
        (wt / "app/a.php").write_text("x")
        subprocess.run(["git", "-C", str(wt), "add", "app/a.php"], check=True)
        payload = {"cwd": str(wt), "tool_input": {"command": 'cd "$(pwd)" && git commit -m x'}}
        self.assertBlocked(self.hook("commit-gate.sh", payload), "E2")

    def test_secret_scanner_is_not_taken_from_the_tree_being_committed(self):
        wt = self.make_worktree("feature/PLAN-7-w")
        scanner = self.repo / ".claude/scripts/scan-secrets.sh"
        scanner.write_text("#!/bin/sh\nexit 1\n")
        scanner.chmod(0o755)
        self.assertBlocked(self.commit("git -C %s commit -m x" % wt), "секрет")

    def test_gate_is_trusted_and_checks_the_tree_being_committed(self):
        # Гейт из каталога хука смотрит на дерево коммита; `exit 0` в самом дереве его не заменяет (HF-174).
        def script(root, body):
            gate = root / ".claude/scripts/quality-gate.sh"
            gate.parent.mkdir(parents=True, exist_ok=True)
            gate.write_text("#!/bin/sh\n" + body)
            gate.chmod(0o755)

        wt = self.make_worktree("feature/PLAN-7-w")
        script(wt, "exit 0\n")
        script(self.repo, 'echo "gate at $CLAUDE_PROJECT_DIR"\nexit 1\n')
        self.assertBlocked(self.commit("git -C %s commit -m x" % wt), "gate at %s" % wt.resolve())

    def test_i1_hooks_path_tampering_blocked(self):
        for command in ["git -c core.hooksPath=/dev/null commit -m x",
                        "GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=core.hooksPath GIT_CONFIG_VALUE_0=/dev/null git commit -m x",
                        "git config core.hooksPath /dev/null", "git config --unset core.hooksPath",
                        "git -c core.hooksPath=/dev/null push origin x"]:
            self.assertBlocked(self.commit(command), "E16")
        self.assertAllowed(self.commit("git config core.hooksPath"))
        self.assertAllowed(self.commit("git config core.hooksPath .githooks"))

    # --- I2: команда сама меняет индекс -> суперсет грязного дерева
    def test_i2_add_and_commit_checks_unstaged_files(self):
        self.branch("feature/RM-9-x")
        (self.repo / "app").mkdir()
        (self.repo / "app/a.php").write_text("x")  # untracked, не staged
        self.assertAllowed(self.commit("git commit -m x"))
        self.assertBlocked(self.commit("git add -A && git commit -m x"), "E2")

    def test_i2_commit_a_and_paths_check_modified_tracked(self):
        self.stage("app/t.php")
        self.git("-c", "core.hooksPath=/dev/null", "commit", "-q", "-m", "t")
        self.branch("feature/RM-9-x")
        (self.repo / "app/t.php").write_text("changed")
        self.assertAllowed(self.commit("git commit -m x"))
        self.assertBlocked(self.commit("git commit -am x"), "E2")
        self.assertBlocked(self.commit("git commit -m x app/t.php"), "E2")

    # --- контрольный проход
    def test_heredoc_delimiter_with_dash_and_underscore(self):
        for word in ["COMMIT-MSG", "MSG_1"]:
            command = "git commit -m \"$(cat <<'%s'\nnote: git push --no-verify\n%s\n)\"" % (word, word)
            self.assertAllowed(self.commit(command))

    def test_data_strings_with_git_commit_on_main_pass_real_commit_blocked(self):
        self.branch("main")
        for command in ['echo "example git commit -m fix"', "grep 'git commit' f",
                        "python3 -c \"print('git commit -m x')\""]:
            self.assertAllowed(self.commit(command))
        self.assertBlocked(self.commit("git commit -m x"), "Коммит в ветку 'main'")

    def checks(self, *args, path=None):
        env = dict(os.environ)
        if path is not None:
            env["PATH"] = path
        return subprocess.run([sys.executable, str(self.repo / ".claude/hooks/commit_checks.py"), *args],
                              capture_output=True, text=True, cwd=str(self.repo), env=env)

    def test_non_utf8_staged_path_no_traceback(self):
        blob = subprocess.run(["git", "-C", str(self.repo), "hash-object", "-w", "--stdin"],
                              input=b"x", capture_output=True).stdout.strip()
        # индекс держит любые байты в имени, независимо от файловой системы
        subprocess.run(["git", "-C", str(self.repo).encode(), "update-index", "--add", "--cacheinfo",
                        b"100644," + blob + b",app/\xff.php"], check=True)
        ok = self.checks("staged", "feature/PLAN-145-x")
        self.assertEqual(0, ok.returncode, ok.stderr)
        self.assertNotIn("Traceback", ok.stderr)
        bad = self.checks("staged", "feature/RM-9-x")
        self.assertEqual(2, bad.returncode, bad.stderr)
        self.assertNotIn("Traceback", bad.stderr)

    def test_missing_git_fails_open_with_message(self):
        empty = Path(self.tmp.name) / "emptybin"
        empty.mkdir()
        result = self.checks("staged", "feature/PLAN-145-x", path=str(empty))
        self.assertEqual(0, result.returncode)
        self.assertIn("hook internal error", result.stderr)
        self.assertNotIn("Traceback", result.stderr)

    def test_config_reads_not_blocked_writes_blocked(self):
        for command in ["git config get core.hooksPath", "git config --get core.hooksPath",
                        "git config --get-all core.hooksPath", "git config --list", "git config -l"]:
            self.assertAllowed(self.commit(command))
        for command in ["git config set core.hooksPath /dev/null", "git config --add core.hooksPath /dev/null",
                        "git config --replace-all core.hooksPath /dev/null", "git config unset core.hooksPath",
                        "git config --unset-all core.hooksPath"]:
            self.assertBlocked(self.commit(command), "E16")

    def test_main_commit_still_blocked(self):
        self.branch("main")
        self.assertBlocked(self.commit())


class BigReadGuardTest(GateCase):
    def read(self, path):
        return self.hook("big-read-guard.sh", {"tool_name": "Read", "tool_input": {"file_path": str(path)}})

    def test_over_40kb_blocked_with_registry_hint(self):
        path = self.repo / "wide.txt"
        path.write_text("x" * 100 + "\n" * 100 + "y" * 50000)
        result = self.read(path)
        self.assertBlocked(result, "registry.sh show")

    def test_over_300_lines_blocked(self):
        path = self.repo / "long.txt"
        path.write_text("a\n" * 301)
        self.assertBlocked(self.read(path))

    def test_median_file_allowed_and_ranged_read_allowed(self):
        path = self.repo / "mid.txt"
        path.write_text(("y" * 100 + "\n") * 200)  # 20 КБ, 200 строк
        self.assertAllowed(self.read(path))
        big = self.repo / "big.txt"
        big.write_text("a\n" * 500)
        ranged = self.hook("big-read-guard.sh", {"tool_name": "Read", "tool_input": {"file_path": str(big), "limit": 50}})
        self.assertAllowed(ranged)

    def test_excluded_files_not_blocked(self):
        for name in ["composer.lock", "package-lock.json", "vendor/x/a.php", "node_modules/p/i.js", "app.min.js", "a.min.css", "p.png", "d.pdf"]:
            path = self.repo / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("a\n" * 5000)
            self.assertAllowed(self.read(path))

    def test_cat_over_40kb_blocked(self):
        path = self.repo / "wide.txt"
        path.write_text(("y" * 1000 + "\n") * 45)
        result = self.hook("big-read-guard.sh", {"tool_name": "Bash", "tool_input": {"command": "cat %s" % path}})
        self.assertBlocked(result)


class RegistryGuardTest(GateCase):
    def edit(self, path):
        return self.hook("registry-guard.sh", {"tool_name": "Edit", "tool_input": {"file_path": str(self.repo / path)}})

    def test_roadmap_edit_blocked(self):
        self.assertBlocked(self.edit("planning/ROADMAP.md"), "registry.sh")

    def test_notebook_path_is_read_too(self):
        result = self.hook("registry-guard.sh", {"tool_name": "NotebookEdit",
                                                 "tool_input": {"notebook_path": str(self.repo / "planning/ROADMAP.md")}})
        self.assertBlocked(result, "registry.sh")

    def test_plan_document_and_idea_files_allowed(self):
        self.assertAllowed(self.edit("planning/plans/PLAN-1-x.md"))
        self.assertAllowed(self.edit("planning/roadmap/RM-1-x.md"))

    def test_stage4_indexes_not_guarded_yet(self):
        for name in ["PLANS.md", "ACTIVE_PLANS.md", "HOTFIXES.md", "JOURNAL.md"]:
            self.assertAllowed(self.edit("planning/" + name))

    def test_stage4_guard_turns_on_only_with_new_structure(self):
        (self.repo / "planning").mkdir()
        for name in ["PLANS.md", "ACTIVE_PLANS.md"]:
            self.assertAllowed(self.edit("planning/" + name))
        (self.repo / "planning/plans/closed").mkdir(parents=True)
        for name in ["PLANS.md", "ACTIVE_PLANS.md"]:
            self.assertBlocked(self.edit("planning/" + name), "registry.sh")
        self.assertAllowed(self.edit("planning/HOTFIXES.md"))
        (self.repo / "planning/hotfixes").mkdir()
        for name in ["HOTFIXES.md", "JOURNAL.md"]:
            self.assertBlocked(self.edit("planning/" + name), "registry.sh")

    def test_lowercase_plans_md_is_guarded_and_not_a_valid_root_name(self):
        """PLANS.md uppercase is the only name: a lowercase twin (distinct file on Linux) is blocked."""
        (self.repo / "planning/plans/closed").mkdir(parents=True)
        self.assertBlocked(self.edit("planning/plans.md"), "registry.sh")
        paths = str(HOOKS / "paths.py")
        run = lambda p: subprocess.run(["python3", paths, "planning-root-ok", p, "--root", str(self.repo)]).returncode
        self.assertEqual(0, run("planning/PLANS.md"))
        self.assertNotEqual(0, run("planning/plans.md"))

    def test_stage4_list_is_declared(self):
        conf = (HOOKS / "paths.conf").read_text()
        for name in ["PLANS.md", "ACTIVE_PLANS.md", "HOTFIXES.md", "JOURNAL.md"]:
            self.assertIn("guard-stage4 " + name, conf)


class BranchGuardTest(GateCase):
    def edit(self, path):
        return self.hook("branch-guard.sh", {"tool_name": "Edit", "tool_input": {"file_path": str(self.repo / path)}})

    def test_code_edit_on_rm_branch_blocked_planning_allowed(self):
        self.branch("feature/RM-9-x")
        (self.repo / "app").mkdir()
        self.assertBlocked(self.edit("app/a.php"), "E2")
        (self.repo / "planning/roadmap").mkdir(parents=True)
        self.assertAllowed(self.edit("planning/roadmap/RM-9-x.md"))

    def test_code_edit_on_plan_branch_allowed(self):
        (self.repo / "app").mkdir()
        self.assertAllowed(self.edit("app/a.php"))


class PathsConfTest(unittest.TestCase):
    def test_every_real_root_element_is_classified(self):
        """Энумерация T15: каждый корневой элемент git ls-files имеет класс в paths.conf."""
        out = subprocess.run(["python3", str(HOOKS / "paths.py"), "unclassified", "--root", str(REAL_ROOT)],
                             capture_output=True, text=True, check=True).stdout
        self.assertEqual("", out, "неклассифицированные корневые элементы: " + out)


class PlansDriftTest(GateCase):
    def setUp(self):
        super().setUp()
        self.stage("planning/ACTIVE_PLANS.md", "# A\n")
        self.stage("planning/PLANS.md", "# P\n")
        self.git("commit", "-q", "-m", "PLAN-145 fixture")

    def drift(self, **env):
        env = dict({"HARNESS_MEMORY_INDEX": "/nonexistent", "HOME": str(self.repo)}, **env)
        return subprocess.run(["bash", str(self.repo / ".claude/hooks/plans-drift.sh")], capture_output=True, text=True,
                              cwd=str(self.repo), env=dict(os.environ, **env))

    def test_clean_is_silent_and_exit_zero(self):
        result = self.drift()
        self.assertEqual(0, result.returncode)
        self.assertEqual("", result.stdout)

    def test_over_budget_prints_e13_line_exit_zero(self):
        (self.repo / "CLAUDE.md").write_text("x" * 60000)
        result = self.drift()
        self.assertEqual(0, result.returncode)
        self.assertIn("E13", result.stdout)

    def test_budget_counts_memory_index(self):
        memory = self.repo / "MEMORY.md"
        memory.write_text("m" * 60000)
        self.assertIn("E13", self.drift(HARNESS_MEMORY_INDEX=str(memory)).stdout)

    def test_hooks_not_installed_is_loud(self):
        self.git("config", "--unset", "core.hooksPath")
        result = self.drift()
        self.assertEqual(0, result.returncode)
        self.assertIn("install-githooks.sh", result.stdout)


REDIRECTIONS = [
    "2>&1", "2>/dev/null", "2> /dev/null", ">f", "> f", ">>f", ">> f", "&>f", "&> f", "&>>f", "&>> f", "1>f", "2>>f",
    ">&2", "2>&-", "<f", "< f", "<<<word", "<<< 'a b'", ">|f", "2>&1 | cat", "|& cat", "2>&1 && true", ">f 2>&1",
]
SUBS = {
    "merge": "git merge --no-ff --no-edit hotfix/x",
    "push": "git push origin hotfix/x",
    "commit": "git commit -m msg --allow-empty",
    "pull": "git pull --ff-only origin main",
    "checkout": "git checkout -b hotfix/y",
}


class RedirectionParsingTest(unittest.TestCase):
    """HF-150: перенаправления - не позиционные аргументы. Для каждой формы x каждой подкоманды разбор равен разбору без неё."""

    @staticmethod
    def shape(command):
        import commit_checks
        return [(c["sub"], c["args"]) for c in commit_checks.parse(command, "/")]

    def test_every_redirection_form_leaves_arguments_unchanged(self):
        for sub, base in SUBS.items():
            want = self.shape(base)
            self.assertEqual(sub, want[0][0])
            for form in REDIRECTIONS:
                with self.subTest(sub=sub, form=form):
                    head, _, tail = base.partition(" " + sub)
                    trailing = self.shape("%s %s" % (base, form))[0]
                    self.assertEqual(want[0], trailing)
                    if "&&" not in form and "|" not in form:  # конвейер/&& заканчивает команду - после подкоманды не вставить
                        infix = self.shape("%s %s %s%s" % (head, sub, form, tail))[0]
                        self.assertEqual(want[0], infix)

    def test_quoted_operators_stay_arguments(self):
        self.assertEqual([("commit", ["-m", "a > b 2>&1"])], self.shape("git commit -m 'a > b 2>&1' 2>&1"))
        self.assertEqual([("merge", ["x", "2"])], self.shape("git merge x 2 >f"))  # `2` отдельным словом - обычный аргумент

    def test_nested_git_in_redirection_target_still_seen(self):
        self.assertEqual({"merge", "pull"}, {c[0] for c in self.shape("git merge a > $(git pull x)")})
        self.assertEqual("merge", self.shape("diff <(git merge a) x")[0][0])

    def test_unparseable_nested_git_still_fails_closed(self):
        import commit_checks
        with self.assertRaises(ValueError):
            commit_checks.parse("bash -c 'git merge \"a' 2>&1", "/")


if __name__ == "__main__":
    unittest.main()
