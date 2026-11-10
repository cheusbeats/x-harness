#!/usr/bin/env bash
# plans-drift.sh — информатор расхождений реестров планирования с git (SPEC п.5).
#
# Планы пишут руками, код коммитят разные сессии и агенты. Раз индекс не привязан
# к git, он молча устаревает. Хук печатает только находки и всегда выходит с 0:
# это информатор, а не гейт.
#
# Проверки:
#   1. код-коммит по CODE_ROOTS с токеном PLAN-N/HF-M новее последнего упоминания
#      токена в индексах (или токена там нет) — «план отстал»;
#   2. токен PLAN-N в коде без записи в реестре (нет строки индекса и тела плана);
#   3. токен HF-M в коде без записи в HOTFIXES.md;
#   4. коммиты с кодом после последней правки HOTFIXES.md без единого PLAN-N/HF-M —
#      кандидаты в реестр хотфиксов;
#   5. лишнее в корне planning/ относительно PLANNING_ROOT_ALLOWED;
#   6. не подключены git-хуки (core.hooksPath != .githooks);
#   7. DRIFT_MEMORY_INDEX задан, а файла нет (пусто — проверка выключена).
#
# Запуск: SessionStart (.claude/settings.json) или руками. Выход всегда 0.
set -uo pipefail

repo="$(git rev-parse --show-toplevel 2>/dev/null)" || exit 0
cd "$repo" || exit 0
command -v python3 >/dev/null 2>&1 || exit 0

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../scripts/planning-lib.sh
. "$SCRIPT_DIR/../scripts/planning-lib.sh"
planning_load_conf

# Без реестра планов сверять нечего (профиль ещё не инициализирован).
[ -f planning/ACTIVE_PLANS.md ] || exit 0

roots="$(planning_code_roots | tr '\n' ' ')"

python3 - "$DRIFT_HORIZON_DAYS" "$DRIFT_MEMORY_INDEX" "$roots" "$MAIN_BRANCH" "$PLANNING_ROOT_ALLOWED" <<'PY'
import glob
import os
import re
import subprocess
import sys
from pathlib import Path

horizon_arg, memory_index, roots_arg, main_branch, root_allowed = sys.argv[1:6]
try:
    horizon = int(horizon_arg)
except ValueError:
    horizon = 90
roots = roots_arg.split()
allowed = set(root_allowed.split())

token_re = re.compile(r"PLAN-\d+(?:\.\d+)*|HF-\d+")
plan_re = re.compile(r"PLAN-\d+(?:\.\d+)*")
hf_re = re.compile(r"HF-\d+")
INDEX_FILES = ["planning/ACTIVE_PLANS.md", "planning/PLANS.md", "planning/HOTFIXES.md", "planning/ROADMAP.md"]


def git(*args):
    return subprocess.run(["git", *args], capture_output=True)


def git_text(*args):
    return git(*args).stdout.decode("utf-8", "replace")


def records(text):
    """Коммиты формата %H%x01%ct%x01%s%x01%b%x02 -> (sha, ts, subject, body)."""
    for rec in text.split("\x02"):
        rec = rec.strip("\n")
        if not rec.strip():
            continue
        parts = rec.split("\x01", 3)
        if len(parts) < 4:
            continue
        yield parts[0], parts[1], parts[2], parts[3]


def read(path):
    try:
        return Path(path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def known_token(token, text, plan_docs):
    """Есть ли токен в текущем реестре: упоминание в индексах или тело плана."""
    if plan_re.fullmatch(token):
        if token in plan_docs:
            return True
        pattern = r"(?<![\w-])" + re.escape(token) + r"(?!\d|\.\d)"
    else:
        pattern = r"(?<![\w-])" + re.escape(token) + r"(?!\d)"
    return re.search(pattern, text) is not None


drift, unregistered, hf_missing, unlogged, extra = [], [], [], [], []
registry_text = "".join(read(path) + "\n" for path in INDEX_FILES)
hotfixes_text = read("planning/HOTFIXES.md")
plan_docs = set()
for found in glob.glob("planning/plans/PLAN-*.md") + glob.glob("planning/plans/closed/PLAN-*.md"):
    m = plan_re.search(os.path.basename(found))
    if m:
        plan_docs.add(m.group(0))
plan_docs |= set(plan_re.findall(read("planning/plans/closed/_map.tsv")))

if roots:
    # Код: токен ищем в заголовке коммита; тело — резерв для коммитов с безымянным заголовком.
    code_map = {}
    log = git_text("log", "--first-parent", "--since=%d.days.ago" % horizon,
                   "--format=%H%x01%ct%x01%s%x01%b%x02", "--", *roots)
    for sha, ts, subject, body in records(log):
        try:
            stamp = int(ts)
        except ValueError:
            continue
        tokens = set(token_re.findall(subject)) or set(token_re.findall(body))
        for token in tokens:
            if token not in code_map or stamp > code_map[token][0]:
                code_map[token] = (stamp, sha, subject.strip())

    # Индексы: токен ищем в ДОБАВЛЕННЫХ строках диффа — строка могла появиться без
    # переиздания номера в сообщении коммита.
    idx_map = {}
    patch = git_text("log", "-p", "--format=COMMIT%x01%H%x01%ct%x02%n", "--", *INDEX_FILES)
    cur_ts = cur_sha = None
    for line in patch.splitlines():
        if line.startswith("COMMIT\x01"):
            parts = line.split("\x01")
            cur_sha = parts[1]
            cur_ts = int(parts[2].split("\x02")[0])
            continue
        if line.startswith("+++") or line.startswith("---"):
            continue
        if line.startswith("+"):
            for token in set(token_re.findall(line)):
                if cur_ts is not None and (token not in idx_map or cur_ts > idx_map[token][0]):
                    idx_map[token] = (cur_ts, cur_sha)

    def index_newer(idx_entry, code_entry):
        """Упоминание в индексе новее код-коммита. При равной секунде решает история:
        если код-коммит — предок индексного, значит индекс правили ПОСЛЕ кода."""
        if idx_entry[0] != code_entry[0]:
            return idx_entry[0] > code_entry[0]
        if idx_entry[1] == code_entry[1]:
            return False
        return git("merge-base", "--is-ancestor", code_entry[1], idx_entry[1]).returncode == 0

    for token in sorted(code_map):
        stamp, sha, subject = code_map[token]
        if token not in idx_map or not index_newer(idx_map[token], (stamp, sha)):
            drift.append((token, sha[:7], subject[:70]))
        if plan_re.fullmatch(token) and not known_token(token, registry_text, plan_docs):
            unregistered.append((token, sha[:7]))
        elif hf_re.fullmatch(token) and not re.search(
                r"(?<![\w-])" + re.escape(token) + r"(?!\d)", hotfixes_text):
            hf_missing.append((token, sha[:7]))

    # Кандидаты в реестр хотфиксов: код после последней правки HOTFIXES.md без токена.
    sync = git_text("log", "-1", "--format=%H", "--", "planning/HOTFIXES.md").strip()
    args = ["log", "--first-parent", "--format=%H%x01%ct%x01%s%x01%b%x02"]
    args.append(sync + "..HEAD" if sync else "--since=%d.days.ago" % horizon)
    args += ["--", *roots]
    for sha, _ts, subject, body in records(git_text(*args)):
        if not token_re.search(subject + "\n" + body):
            unlogged.append((sha[:7], subject.strip()[:70]))

# Лишнее в корне planning/: допустимы только PLANNING_ROOT_ALLOWED.
for path in git_text("ls-files", "-co", "--exclude-standard", "-z").split("\0"):
    if not path.startswith("planning/"):
        continue
    name = path[len("planning/"):].split("/", 1)[0]
    if name and name not in allowed:
        if name not in extra:
            extra.append(name)

warnings = []
hooks = git_text("config", "core.hooksPath").strip()
if hooks != ".githooks":
    warnings.append("git-хуки не подключены: .claude/scripts/install-githooks.sh (core.hooksPath сейчас '%s')"
                    % (hooks or "<не задан>"))
if memory_index:
    if not Path(os.path.expanduser(memory_index)).exists():
        warnings.append("DRIFT_MEMORY_INDEX задан, но файла нет: %s (пустое значение выключает проверку)"
                        % memory_index)

if not any((drift, unregistered, hf_missing, unlogged, extra, warnings)):
    sys.exit(0)

print("СВЕРКА ПЛАНОВ (окно %d д по коду, токен коммита против индексов):" % horizon)

if drift:
    print()
    print("  Код по плану новее, чем последнее упоминание токена в индексе (или там его нет):")
    for token, sha, subject in drift:
        print("    %s — %s %s" % (token, sha, subject))
    print("  Проверь planning/ACTIVE_PLANS.md и planning/PLANS.md: план мог закрыться")
    print("  или просто ждать своей строки. Сверься с кодом и git log, не только с формулировкой плана.")

if unregistered:
    print()
    print("  Токен PLAN-N в коде без записи в реестре (нет строки индекса и тела плана):")
    for token, sha in unregistered:
        print("    %s — коммит %s" % (token, sha))
    print("  Заведи запись через .claude/scripts/registry.sh add PLAN ... или убери токен из коммита.")

if hf_missing:
    print()
    print("  Токен HF-M в коде без записи в planning/HOTFIXES.md:")
    for token, sha in hf_missing:
        print("    %s — коммит %s" % (token, sha))
    print("  Заведи запись через .claude/scripts/registry.sh add HF ...")

if unlogged:
    print()
    print("  Коммиты с кодом после последней правки HOTFIXES.md без единого PLAN-N/HF-M")
    print("  (кандидаты в реестр хотфиксов: .claude/scripts/registry.sh add HF ...):")
    for sha, subject in unlogged[:5]:
        print("    %s %s" % (sha, subject))
    if len(unlogged) > 5:
        print("    ...ещё %d" % (len(unlogged) - 5))

if extra:
    print()
    print("  Лишнее в корне planning/ (допустимы только служебные файлы и каталоги plans/ roadmap/ hotfixes/):")
    for name in extra:
        print("    planning/%s — перенеси в тело плана, идеи или хотфикса" % name)

if warnings:
    print()
    print("  Окружение:")
    for line in warnings:
        print("    " + line)

print()
print("Актуализируй planning/ прежде чем браться за новое (правило — AGENTS.md, «Три реестра»).")
sys.exit(0)
PY
exit 0
