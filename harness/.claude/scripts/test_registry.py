"""Поведение .claude/scripts/registry.sh на временных каталогах.

Запуск: python3 .claude/scripts/test_registry.py
Коды: 0 чисто, 1 нарушения, 2 неверные аргументы.
"""

# Герметичность: переменные среды Claude Code/git-хука не должны течь в подпроцессы фикстур (хуки делают
# `cd "${CLAUDE_PROJECT_DIR:-.}"` и ушли бы в настоящий репозиторий).
import os as _os
for _v in [k for k in _os.environ if k.startswith("GIT_") or k == "CLAUDE_PROJECT_DIR"]:
    _os.environ.pop(_v, None)

import os
import re
import subprocess
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent / "registry.sh"
REAL_ROOT = SCRIPT.parent.parent.parent

RM_HEAD = "| RM | Название | Статус | Дата | Триггер / → PLAN-N |\n|---|---|---|---|---|\n"
PLAN_HEAD = "| PLAN | Название | Статус | Дата | Влит-в | Автор |\n|---|---|---|---|---|---|\n"


def rm_row(n, status="идея", title="Тема", slug="x"):
    return f"| [RM-{n}](roadmap/RM-{n}-{slug}.md) | {title} | {status} | 2026-10-16 | нет |\n"


def plan_row(n, status="в работе"):
    return f"| [PLAN-{n}](plans/PLAN-{n}-x.md) | Тема | {status} | 2026-10-16 | abc | Claude |\n"


class RegistryTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.pl = self.root / "planning"
        (self.pl / "roadmap").mkdir(parents=True)

    def tearDown(self):
        self.tmp.cleanup()

    def run_reg(self, *args, env=None):
        return subprocess.run([str(SCRIPT), "--root", str(self.root), *args],
                              capture_output=True, text=True, env={**os.environ, **(env or {})})

    def rm(self, rows, files):
        (self.pl / "ROADMAP.md").write_text("# R\n\n" + RM_HEAD + "".join(rows))
        for n in files:
            (self.pl / "roadmap" / f"RM-{n}-x.md").write_text(f"# RM-{n}\n\n- **Статус:** идея\n\nтело\n")

    def plan_tree(self, active, closed_idx, docs=(), closed=()):
        (self.pl / "plans" / "closed").mkdir(parents=True)
        (self.pl / "ACTIVE_PLANS.md").write_text("# A\n\n" + PLAN_HEAD + "".join(active))
        (self.pl / "PLANS.md").write_text("# P\n\n" + PLAN_HEAD + "".join(closed_idx))
        for n in docs:
            (self.pl / "plans" / f"PLAN-{n}-x.md").write_text("x")
        for n in closed:
            (self.pl / "plans" / "closed" / f"PLAN-{n}.md").write_text("x")

    def assertViolation(self, r, id_, code=1):
        self.assertEqual(r.returncode, code, r.stdout + r.stderr)
        self.assertIn(id_, r.stdout)

    # --- RM ---
    def test_clean_rm(self):
        self.rm([rm_row(1), rm_row(2, "стала PLAN-7")], [1, 2])
        self.assertEqual(self.run_reg("check", "--registry", "rm").returncode, 0)

    def test_duplicate_row(self):
        self.rm([rm_row(1), rm_row(1)], [1])
        self.assertViolation(self.run_reg("check", "--registry", "rm"), "RM-1")

    def test_row_without_file(self):
        self.rm([rm_row(1), rm_row(2)], [1])
        self.assertViolation(self.run_reg("check", "--registry", "rm"), "RM-2")

    def test_file_without_row(self):
        self.rm([rm_row(1)], [1, 3])
        self.assertViolation(self.run_reg("check", "--registry", "rm"), "RM-3")

    def test_status_outside_vocabulary(self):
        self.rm([rm_row(1, "готово")], [1])
        self.assertViolation(self.run_reg("check", "--registry", "rm"), "RM-1")

    def test_too_long(self):
        self.rm([rm_row(1, title="я" * 200)], [1])
        self.assertViolation(self.run_reg("check", "--registry", "rm"), "RM-1")

    def test_two_files_same_id(self):
        self.rm([rm_row(1)], [1])
        (self.pl / "roadmap" / "RM-1-other.md").write_text("x")
        self.assertViolation(self.run_reg("check", "--registry", "rm"), "RM-1")

    def test_bad_args(self):
        self.assertEqual(self.run_reg("check", "--registry", "zzz").returncode, 2)
        self.assertEqual(self.run_reg("bogus").returncode, 2)

    # --- PLAN / HF ---
    def test_missing_registries_skipped(self):
        self.rm([rm_row(1)], [1])
        r = self.run_reg("check")
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn("реестр ещё не создан", r.stdout)

    def test_plan_doc_and_closed_entry_legal(self):
        self.plan_tree([], [plan_row(5, "закрыт")], docs=[5], closed=[5])
        r = self.run_reg("check", "--registry", "plan")
        self.assertEqual(r.returncode, 0, r.stdout)

    def test_plan_two_docs(self):
        self.plan_tree([plan_row(5)], [], docs=[5])
        (self.pl / "plans" / "PLAN-5-y.md").write_text("x")
        self.assertViolation(self.run_reg("check", "--registry", "plan"), "PLAN-5")

    def test_plan_duplicate_row_across_indexes(self):
        self.plan_tree([plan_row(5)], [plan_row(5, "закрыт")], docs=[5], closed=[5])
        self.assertViolation(self.run_reg("check", "--registry", "plan"), "PLAN-5")

    def test_plan_doc_without_row(self):
        self.plan_tree([], [], docs=[9])
        self.assertViolation(self.run_reg("check", "--registry", "plan"), "PLAN-9")

    def test_plan_closed_row_needs_archive(self):
        self.plan_tree([], [plan_row(5, "закрыт")])
        self.assertViolation(self.run_reg("check", "--registry", "plan"), "PLAN-5")

    def test_hf_two_files(self):
        (self.pl / "hotfixes").mkdir()
        (self.pl / "HOTFIXES.md").write_text("# H\n\n| HF | Н | С | Д | В | А |\n|---|---|---|---|---|---|\n"
                                             "| [HF-1](hotfixes/HF-1-a.md) | т | влит | 2026-10-16 | abc | Claude |\n")
        (self.pl / "hotfixes" / "HF-1-a.md").write_text("x")
        (self.pl / "hotfixes" / "HF-1-b.md").write_text("x")
        self.assertViolation(self.run_reg("check", "--registry", "hf"), "HF-1")

    # --- команды ---
    def test_next_id_and_add(self):
        self.rm([rm_row(1), rm_row(4)], [1, 4])
        self.assertEqual(self.run_reg("next-id", "RM").stdout.strip(), "RM-5")
        r = self.run_reg("add", "RM", "auto", "Новая идея", "--date", "2026-10-16")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.run_reg("check", "--registry", "rm").returncode, 0)
        self.assertEqual(self.run_reg("next-id", "RM").stdout.strip(), "RM-6")
        self.assertEqual(self.run_reg("add", "RM", "RM-5", "Дубль").returncode, 2)

    def test_add_hf_creates_registry(self):
        self.assertEqual(self.run_reg("next-id", "HF").stdout.strip(), "HF-1")
        r = self.run_reg("add", "HF", "auto", "Fix thing", "--trigger", "abc123")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.run_reg("check", "--registry", "hf").returncode, 0)

    def test_set_status_keeps_body(self):
        self.rm([rm_row(1)], [1])
        f = self.pl / "roadmap" / "RM-1-x.md"
        before = f.read_text().split("\n")
        r = self.run_reg("set-status", "RM-1", "отложена")
        self.assertEqual(r.returncode, 0, r.stderr)
        after = f.read_text().split("\n")
        self.assertEqual([a for a, b in zip(before, after) if a != b], ["- **Статус:** идея"])
        self.assertEqual(before[3:], after[3:])  # тело после метаданных побайтово то же
        self.assertIn("отложена", self.run_reg("show", "RM-1").stdout)
        self.assertEqual(self.run_reg("set-status", "RM-1", "готово").returncode, 2)

    # --- ревью Codex: ячейки, CRLF, валидация, блокировка ---
    def index_cells(self, path, id_):
        for line in path.read_bytes().decode().split("\n"):
            if line.startswith(f"| [{id_}]"):
                return [c.strip() for c in line.strip().strip("|").split("|")]

    def test_set_status_changes_only_status_cell_crlf(self):
        self.rm([rm_row(1), rm_row(2)], [1, 2])
        idx = self.pl / "ROADMAP.md"
        idx.write_bytes(idx.read_bytes().replace(b"\n", b"\r\n"))
        f = self.pl / "roadmap" / "RM-1-x.md"
        f.write_bytes(f.read_bytes().replace(b"\n", b"\r\n"))
        i0, f0 = idx.read_bytes(), f.read_bytes()
        c0 = self.index_cells(idx, "RM-1")
        r = self.run_reg("set-status", "RM-1", "отложена")
        self.assertEqual(r.returncode, 0, r.stderr)
        c1 = self.index_cells(idx, "RM-1")
        self.assertEqual(c0[2], "идея")
        self.assertEqual(c1[2], "отложена")
        self.assertEqual(c0[:2] + c0[3:], c1[:2] + c1[3:])  # название и прочее не тронуты
        d = [(a, b) for a, b in zip(i0.split(b"\n"), idx.read_bytes().split(b"\n")) if a != b]
        self.assertEqual(len(d), 1)
        self.assertTrue(d[0][1].endswith(b"\r"))
        self.assertEqual(i0.count(b"\r\n"), idx.read_bytes().count(b"\r\n"))
        d = [(a, b) for a, b in zip(f0.split(b"\n"), f.read_bytes().split(b"\n")) if a != b]
        self.assertEqual(d, [("- **Статус:** идея\r".encode(), "- **Статус:** отложена\r".encode())])

    def test_plan_annulled_without_archive(self):
        self.plan_tree([plan_row(5, "аннулирован")], [], docs=[5])
        self.assertViolation(self.run_reg("check", "--registry", "plan"), "PLAN-5")

    def test_length_boundary(self):
        base = len(rm_row(1, title="").rstrip("\n").split("|", 2)[2])
        pad = 160 - base
        self.rm([rm_row(1, title="я" * pad)], [1])
        self.assertEqual(self.run_reg("check", "--registry", "rm").returncode, 0)
        self.rm([rm_row(1, title="я" * (pad + 1))], [1])
        self.assertViolation(self.run_reg("check", "--registry", "rm"), "RM-1")

    def test_set_trigger_changes_only_trigger_cell(self):
        self.rm([rm_row(1)], [1])
        idx = self.pl / "ROADMAP.md"
        before = self.index_cells(idx, "RM-1")
        r = self.run_reg("set-trigger", "RM-1", "→ PLAN-9")
        self.assertEqual(r.returncode, 0, r.stderr)
        after = self.index_cells(idx, "RM-1")
        self.assertEqual(after[:4], before[:4])
        self.assertEqual(after[4], "→ PLAN-9")

    def test_set_trigger_shortens_long_row_so_status_change_passes_check(self):
        self.rm([rm_row(1, title="Тема", slug="x").replace("| нет |", "| " + "я" * 150 + " |")], [1])
        self.assertViolation(self.run_reg("check", "--registry", "rm"), "RM-1")
        self.assertEqual(self.run_reg("set-trigger", "RM-1", "→ PLAN-7").returncode, 0)
        self.assertEqual(self.run_reg("set-status", "RM-1", "стала PLAN-7").returncode, 0)
        self.assertEqual(self.run_reg("check", "--registry", "rm").returncode, 0)

    def test_set_trigger_rejects_bad_input_and_too_long(self):
        self.rm([rm_row(1)], [1])
        before = (self.pl / "ROADMAP.md").read_text()
        for args in (("RM-1", "a|b"), ("RM-1", " "), ("RM-1", "я" * 200), ("PLAN-1", "x"), ("RM-9", "x")):
            self.assertEqual(self.run_reg("set-trigger", *args).returncode, 2, args)
        self.assertEqual((self.pl / "ROADMAP.md").read_text(), before)

    def test_add_rejects_bad_fields_without_writing(self):
        self.rm([rm_row(1)], [1])
        before = (self.pl / "ROADMAP.md").read_bytes()
        for args in (["a|b"], ["a\nb"], ["ok", "--trigger", "x|y"], ["ok", "--date", "16.10.2026"],
                     ["я" * 200]):
            self.assertEqual(self.run_reg("add", "RM", "auto", *args).returncode, 2, args)
        self.assertEqual((self.pl / "ROADMAP.md").read_bytes(), before)
        self.assertEqual(len(list((self.pl / "roadmap").iterdir())), 1)

    def test_add_inserts_in_id_order(self):
        self.rm([rm_row(1), rm_row(5)], [1, 5])
        self.assertEqual(self.run_reg("add", "RM", "RM-3", "Середина").returncode, 0)
        ids = re.findall(r"^\| \[(RM-\d+)\]", (self.pl / "ROADMAP.md").read_text(), re.M)
        self.assertEqual(ids, ["RM-1", "RM-3", "RM-5"])

    def test_non_utf8_index(self):
        self.rm([rm_row(1)], [1])
        (self.pl / "ROADMAP.md").write_bytes(b"\xff\xfe| bad")
        r = self.run_reg("check", "--registry", "rm")
        self.assertEqual(r.returncode, 2)
        self.assertNotIn("Traceback", r.stderr)

    def test_concurrent_add(self):
        self.rm([rm_row(1)], [1])
        ps = [subprocess.Popen([str(SCRIPT), "--root", str(self.root), "add", "RM", "auto", f"Т{n}"],
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) for n in range(6)]
        outs = [p.communicate()[0].split()[0] for p in ps]
        self.assertEqual(len(set(outs)), 6, outs)
        self.assertEqual(self.run_reg("check", "--registry", "rm").returncode, 0)
        self.assertEqual(len(re.findall(r"^\| \[RM-", (self.pl / "ROADMAP.md").read_text(), re.M)), 7)

    def test_escaped_pipe_in_title(self):
        self.rm([rm_row(1, title="а \\| б"), rm_row(2)], [1, 2])
        idx = self.pl / "ROADMAP.md"
        self.assertEqual(self.run_reg("check", "--registry", "rm").returncode, 0)
        r = self.run_reg("set-status", "RM-1", "отложена")
        self.assertEqual(r.returncode, 0, r.stderr)
        line = [ln for ln in idx.read_text().split("\n") if ln.startswith("| [RM-1]")][0]
        self.assertEqual(line, "| [RM-1](roadmap/RM-1-x.md) | а \\| б | отложена | 2026-10-16 | нет |")
        self.assertEqual(self.run_reg("check", "--registry", "rm").returncode, 0)

    def test_second_table_without_header_not_edited(self):
        self.rm([rm_row(1)], [1])
        idx = self.pl / "ROADMAP.md"
        idx.write_text(idx.read_text() + "\nтекст\n\n| [RM-2](roadmap/RM-2-x.md) | Т | идея | 2026-10-16 | нет |\n")
        (self.pl / "roadmap" / "RM-2-x.md").write_text("# RM-2\n\n- **Статус:** идея\n")
        before = idx.read_bytes()
        self.assertEqual(self.run_reg("set-status", "RM-2", "отложена").returncode, 2)
        self.assertEqual(idx.read_bytes(), before)
        self.assertViolation(self.run_reg("check", "--registry", "rm"), "RM-2")

    def test_set_status_invalid_record_file_leaves_index(self):
        self.rm([rm_row(1)], [1])
        (self.pl / "roadmap" / "RM-1-x.md").write_bytes(b"\xff\xfe")
        idx = self.pl / "ROADMAP.md"
        before = idx.read_bytes()
        self.assertEqual(self.run_reg("set-status", "RM-1", "отложена").returncode, 2)
        self.assertEqual(idx.read_bytes(), before)

    def test_backslash_parity(self):
        # `\\|` = экранированный слеш + настоящий разделитель (без пробела перед «|»); `\|` = экранированный «|»
        r1 = "| [RM-1](roadmap/RM-1-x.md) | а \\\\| идея | 2026-10-16 | нет |\n"
        r2 = "| [RM-2](roadmap/RM-2-x.md) | б \\| в | идея | 2026-10-16 | нет |\n"
        self.rm([r1, r2], [1, 2])
        idx = self.pl / "ROADMAP.md"
        self.assertEqual(self.run_reg("check", "--registry", "rm").returncode, 0)
        self.assertEqual(self.run_reg("set-status", "RM-1", "отложена").returncode, 0)
        self.assertEqual(self.run_reg("set-status", "RM-2", "отложена").returncode, 0)
        lines = idx.read_text().split("\n")
        self.assertIn("| [RM-1](roadmap/RM-1-x.md) | а \\\\| отложена | 2026-10-16 | нет |", lines)
        self.assertIn("| [RM-2](roadmap/RM-2-x.md) | б \\| в | отложена | 2026-10-16 | нет |", lines)

    def test_strict_row_shape(self):
        good = "| [RM-2](roadmap/RM-2-x.md) | Т | идея | 2026-10-16 | нет |"
        bad_rows = {
            "fewer": "| [RM-2](roadmap/RM-2-x.md) | Т | идея | 2026-10-16 |",
            "more": good[:-1] + "| лишняя |",
            "no_trailing": good[:-1].rstrip(),
            "no_leading": good[1:].lstrip(),
        }
        for name, row in bad_rows.items():
            with self.subTest(name):
                self.rm([rm_row(1)], [1, 2])
                idx = self.pl / "ROADMAP.md"
                idx.write_text(idx.read_text() + row + "\n")
                before = idx.read_bytes()
                r = self.run_reg("check", "--registry", "rm")
                self.assertViolation(r, "RM-2")
                self.assertEqual(self.run_reg("set-status", "RM-1", "отложена").returncode, 2)
                self.assertEqual(self.run_reg("add", "RM", "auto", "Новая").returncode, 2)
                self.assertEqual(idx.read_bytes(), before)

    def test_rollback_on_second_replace_failure(self):
        self.rm([rm_row(1)], [1])
        idx, f = self.pl / "ROADMAP.md", self.pl / "roadmap" / "RM-1-x.md"
        i0, f0 = idx.read_bytes(), f.read_bytes()
        r = self.run_reg("set-status", "RM-1", "отложена", env={"REGISTRY_FAIL_REPLACE_N": "2"})
        self.assertEqual(r.returncode, 2, r.stderr)
        self.assertEqual((idx.read_bytes(), f.read_bytes()), (i0, f0))
        self.assertEqual(list(self.pl.rglob("*.tmp")), [])

    def test_add_rollback_removes_created_file(self):
        self.rm([rm_row(1)], [1])
        idx = self.pl / "ROADMAP.md"
        i0 = idx.read_bytes()
        r = self.run_reg("add", "RM", "auto", "Новая", env={"REGISTRY_FAIL_REPLACE_N": "2"})
        self.assertEqual(r.returncode, 2, r.stderr)
        self.assertEqual(idx.read_bytes(), i0)
        self.assertEqual(len(list((self.pl / "roadmap").iterdir())), 1)

    # --- PLAN: aliases, карта миграции, add/закрытие, миграция (этап 4a) ---
    def map_tsv(self, *rows):
        (self.pl / "plans" / "closed" / "_map.tsv").write_text(
            "heading\tfile\tids\tregistry_row\tflags\n" + "".join("\t".join(r) + "\n" for r in rows))

    def test_plan_alias_doc_resolves_to_composite_row(self):
        self.plan_tree([], [plan_row(84, "закрыт")], docs=[85], closed=[84])
        self.map_tsv(("PLAN-84 / PLAN-85 — x", "PLAN-84.md", "PLAN-84 PLAN-85", "yes", ""))
        (self.pl / "PLANS.md").write_text("# P\n\n" + PLAN_HEAD + plan_row(84, "закрыт").replace("plans/PLAN-84-x.md", "plans/closed/PLAN-84.md"))
        r = self.run_reg("check", "--registry", "plan")
        self.assertEqual(r.returncode, 0, r.stdout)

    def test_plan_map_row_yes_without_index_row(self):
        self.plan_tree([], [], closed=[7])
        self.map_tsv(("PLAN-7 — x", "PLAN-7.md", "PLAN-7", "yes", ""))
        self.assertViolation(self.run_reg("check", "--registry", "plan"), "PLAN-7.md")

    def test_plan_map_row_no_allows_archive_without_row(self):
        self.plan_tree([], [], closed=[27])
        self.map_tsv(("PLAN-27 — x", "PLAN-27.md", "PLAN-27", "no", ""))
        self.assertEqual(self.run_reg("check", "--registry", "plan").returncode, 0)

    def test_plan_closed_file_outside_map_flagged(self):
        self.plan_tree([], [], closed=[])
        self.map_tsv()
        (self.pl / "plans" / "closed" / "stray.md").write_text("x")
        self.assertViolation(self.run_reg("check", "--registry", "plan"), "stray.md")

    def test_add_plan_registers_existing_doc_and_creates_new(self):
        self.plan_tree([], [], docs=[9])
        r = self.run_reg("add", "PLAN", "PLAN-9", "Тема", "--status", "в работе")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual((self.pl / "plans" / "PLAN-9-x.md").read_text(), "x")  # документ не перезаписан
        r = self.run_reg("add", "PLAN", "auto", "Новый", "--slug", "new")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("## Резюме", (self.pl / "plans" / "PLAN-10-new.md").read_text())
        self.assertEqual(self.run_reg("check", "--registry", "plan").returncode, 0)

    def test_set_status_closed_moves_row_to_plans_md(self):
        self.plan_tree([plan_row(5)], [])
        r = self.run_reg("set-status", "PLAN-5", "закрыт")
        self.assertNotEqual(r.returncode, 0)  # нет closed/PLAN-5.md
        (self.pl / "plans" / "closed" / "PLAN-5.md").write_text("## PLAN-5\n")
        r = self.run_reg("set-status", "PLAN-5", "закрыт")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertNotIn("PLAN-5", (self.pl / "ACTIVE_PLANS.md").read_text())
        row = [l for l in (self.pl / "PLANS.md").read_text().splitlines() if "PLAN-5" in l][0]
        self.assertIn("(plans/closed/PLAN-5.md)", row)
        # HF-150: закрытие дописывает строку в _map.tsv (heading из записи, registry_row=yes)
        rows = (self.pl / "plans" / "closed" / "_map.tsv").read_text().split("\n")
        self.assertIn("PLAN-5\tPLAN-5.md\tPLAN-5\tyes\t", rows[-2] if rows[-1] == "" else rows[-1])
        self.assertEqual(self.run_reg("check", "--registry", "plan").returncode, 0)

    def test_close_with_tab_in_heading_keeps_map_valid(self):
        """HF-150: TAB в заголовке записи не добавляет колонку в _map.tsv."""
        self.plan_tree([plan_row(5)], [])
        (self.pl / "plans" / "closed" / "PLAN-5.md").write_text("## PLAN-5 — A\tB\r\n")
        self.assertEqual(self.run_reg("set-status", "PLAN-5", "закрыт").returncode, 0)
        last = [l for l in (self.pl / "plans" / "closed" / "_map.tsv").read_text().split("\n") if l][-1]
        self.assertEqual(5, len(last.split("\t")), last)
        self.assertEqual(self.run_reg("check", "--registry", "plan").returncode, 0)

    def test_migrate_roundtrip_on_temp_repo(self):
        git = lambda *a: subprocess.run(["git", "-C", str(self.root), *a], capture_output=True, text=True, check=True).stdout
        git("init", "-q")
        src = ("# Лог\n\n---\n\n## PLAN-1 — Один (закрыт 2026-06-04, merge `abcdef1`)\n\n- a\n\n"
               "## PLAN-2 / PLAN-3 — Два\n\n- b\n\n## PLAN-2 (часть) — Дубль\n\nтело\n\n"
               "## Записи без номера PLAN-N\n\n## UX-1 — Без номера\n\nтело\n\n## Pending\n\nждёт\n")
        (self.pl / "plans.md").write_text(src)  # legacy source name
        git("add", "-A"); git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "src")
        sha = git("rev-parse", "HEAD").strip()
        r = self.run_reg("migrate", "plans", "--sha", sha)
        self.assertEqual(r.returncode, 0, r.stderr)
        closed = self.pl / "plans" / "closed"
        order = (closed / "_order.txt").read_text().split()
        self.assertEqual(order, ["PLAN-1.md", "PLAN-2.md", "_dup-PLAN-2-2.md", "_seam-unnumbered.md", "_unnumbered-ux-1.md", "_unnumbered-pending.md"])
        self.assertEqual((closed / "_preamble.md").read_bytes() + b"".join((closed / f).read_bytes() for f in order), src.encode())
        rows = [l for l in (self.pl / "PLANS.md").read_text().splitlines() if l.startswith("| [")]
        self.assertEqual(len(rows), 4)  # без разделителя и Pending
        self.assertIn("abcdef1", rows[0])
        self.assertEqual(self.run_reg("check", "--registry", "plan").returncode, 0)
        self.assertNotEqual(self.run_reg("migrate", "plans", "--sha", sha).returncode, 0)  # повторно нельзя

    def test_migrate_refuses_crlf_source(self):
        git = lambda *a: subprocess.run(["git", "-C", str(self.root), *a], capture_output=True, text=True, check=True).stdout
        git("init", "-q")
        (self.pl / "plans.md").write_bytes(b"# x\r\n\r\n## PLAN-1 \xe2\x80\x94 a\r\n")
        git("add", "-A"); git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "src")
        r = self.run_reg("migrate", "plans", "--sha", git("rev-parse", "HEAD").strip())
        self.assertNotEqual(r.returncode, 0)
        self.assertFalse((self.pl / "plans" / "closed").exists())

    # --- HF: миграция журнала (этап 4b) ---
    def test_migrate_journal_roundtrip_on_temp_repo(self):
        git = lambda *a: subprocess.run(["git", "-C", str(self.root), *a], capture_output=True, text=True, check=True).stdout
        git("init", "-q")
        src = ("# Журнал\n\nправила\n\n---\n\n## 2026-08\n\n- 2026-08-02 · `fafe153` · Claude — первая | с чертой\n"
               "- 2026-08-03 · hotfix/x · человек — вторая\n  продолжение строки\n\n## 2026-09\n\n"
               "- 2026-09-01 · (не закоммичено) · Codex — третья\n")
        (self.pl / "JOURNAL.md").write_text(src)
        git("add", "-A"); git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "src")
        sha = git("rev-parse", "HEAD").strip()
        r = self.run_reg("migrate", "journal", "--sha", sha)
        self.assertEqual(r.returncode, 0, r.stderr)
        out = self.pl / "hotfixes"
        order = (out / "_order.txt").read_text().split()
        self.assertEqual(order, ["_seam-1.md", "HF-1-fafe153.md", "HF-2-journal.md", "_seam-2.md", "HF-3-journal.md"])
        self.assertEqual((out / "_preamble.md").read_bytes() + b"".join((out / f).read_bytes() for f in order), src.encode())
        self.assertIn("продолжение строки", (out / "HF-2-journal.md").read_text())  # многострочная запись целиком
        self.assertEqual(self.run_reg("check", "--registry", "hf").returncode, 0)
        self.assertEqual(self.run_reg("next-id", "HF").stdout.strip(), "HF-4")
        self.assertNotEqual(self.run_reg("migrate", "journal", "--sha", sha).returncode, 0)

if __name__ == "__main__":
    unittest.main()
