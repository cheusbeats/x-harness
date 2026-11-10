#!/usr/bin/env python3
"""Проверки merge-gate (PLAN-145, этап 3b): T16, E12, E3 (hotfix/план), E17, слово владельца (E10/E11).

Вход — JSON тул-колла на stdin (как у остальных хуков). exit 2 + причины в stderr = мерж блокируется.

Команда разбирается как argv (commit_checks.parse): для КАЖДОЙ позиционной ссылки `git merge` берётся SHA
(`rev-parse --verify`, не резолвится — блок) и всё считается по диффу `merge-base main..SHA`. Имя ветки —
лишь ярлык для отметок гейта/ревью/маркеров, и только когда на этом SHA стоит ровно одна ветка feature/*|hotfix/*.
"""
import fnmatch
import io
import json
import os
import re
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

import commit_checks as cc
import owner_ok
import paths

HERE = Path(__file__).resolve().parent
REVIEWERS = ("opus", "codex")
BRANCH_RE = re.compile(r"(feature|hotfix)/")
PLAN_BRANCH = re.compile(r"feature/PLAN-(\d+(?:\.\d+)*)(?:-|$)")


# Полное имя ветки: короткое «main» может затенить одноимённый тег (refs/tags/main), и проверка пошла бы не от той базы.
MAIN_REF = "refs/heads/main"


def short_branch(full):
    """refs/heads/x -> x (всё остальное без изменений)."""
    return full[len("refs/heads/"):] if full.startswith("refs/heads/") else full


def current_branch():
    """Текущая ветка по `symbolic-ref HEAD`, а не `rev-parse --abbrev-ref`: тот при одноимённом теге (refs/tags/main)
    даёт heads/main, и хук принял бы мерж в main за мерж в другую ветку. Отсоединённый HEAD -> "HEAD"."""
    full = cc.git("symbolic-ref", "--quiet", "HEAD").strip()
    return short_branch(full) if full else "HEAD"


def fail(ref, msg, errors):
    errors.append("Мерж '%s' заблокирован: %s" % (ref, msg))


def money_patterns():
    lines = (HERE / "money-paths.txt").read_text(encoding="utf-8").splitlines() if (HERE / "money-paths.txt").is_file() else []
    return [l.strip() for l in lines if l.strip() and not l.lstrip().startswith("#")]


def is_money(path, patterns):
    return any(path.startswith(p) if p.endswith("/") else fnmatch.fnmatch(path, p) for p in patterns)


def branch_names(sha):
    """Ветки feature/*|hotfix/* (локальные и origin/…), чья вершина — ровно этот SHA."""
    names = set()
    for ref in cc.git("for-each-ref", "--points-at", sha, "--format=%(refname)", "refs/heads", "refs/remotes").split():
        name = re.sub(r"^refs/(heads|remotes/[^/]+)/", "", ref)
        if BRANCH_RE.match(name):
            names.add(name)
    return sorted(names)


def stamps_dir(name):
    """Отметки гейта и ревью общие на репозиторий: лежат в основном чекауте, откуда бы ни шли гейт и мерж (HF-177).
    Тот же путь, что у mark-reviewed.sh и quality-gate.sh. Сбой git = отказ: main() превращает исключение в блокировку."""
    common = cc.git("rev-parse", "--path-format=absolute", "--git-common-dir").strip()
    if not common:
        raise RuntimeError("git не назвал --git-common-dir")
    return Path(common).parent / ".claude/state" / name


def review_problem(key, by, tip):
    """None, если отметка ревьюера `by` закрывает вершину (полное на вершине | полное на предке + дельта до вершины)."""
    reviews = stamps_dir("reviews")
    full, delta = reviews / ("%s.full.%s" % (key, by)), reviews / ("%s.delta.%s" % (key, by))
    if not full.is_file():
        return "нет полного ревью (%s)" % by
    full_sha = full.read_text(encoding="utf-8", errors="replace").splitlines()[0:1]
    full_sha = full_sha[0] if full_sha else ""
    if full_sha == tip:
        return None
    if subprocess.run(["git", "merge-base", "--is-ancestor", full_sha, tip], capture_output=True).returncode != 0:
        return "полное ревью (%s) %s не предок вершины — история переписана" % (by, full_sha[:7])
    lines = delta.read_text(encoding="utf-8", errors="replace").splitlines() if delta.is_file() else []
    if lines[:2] == [tip, full_sha]:
        return None
    return "после полного ревью (%s) %s есть непроверенные правки до %s" % (by, full_sha[:7], tip[:7])


def stamp_errors(name, tip, money):
    errors, key = [], name.replace("/", "_")
    gate = stamps_dir("gates") / ("%s.merge-passed" % key)
    if not gate.is_file() or gate.read_text(encoding="utf-8", errors="replace").splitlines()[:1] != [tip]:
        errors.append("нет зелёного полного гейта на вершине %s. Запусти на этой ветке (чистое дерево): .claude/scripts/quality-gate.sh --merge" % tip[:7])
    problems = {by: review_problem(key, by, tip) for by in REVIEWERS}
    if money:
        for by, why in problems.items():
            if why:
                errors.append("деньги (money-paths.txt): нужны отметки ревью opus И codex — %s. Затем: .claude/scripts/mark-reviewed.sh --full|--delta --by %s %s \"итог\"" % (why, by, name))
    elif all(problems.values()):
        errors.append("нет ревью итоговой ветки (нужна хотя бы одна отметка, opus или codex): %s. Затем: .claude/scripts/mark-reviewed.sh --full|--delta --by codex %s \"итог\" "
                      "(ревью правок после полного — только разница, полное не повторяем)" % ("; ".join(problems.values()), name))
    return errors


def hotfix_errors(base, tip, entries):
    """E3 для hotfix/*: запись хотфикса. Реестр HF есть (HOTFIXES.md в main) — файл HF-N-*.md + строка индекса;
    до миграции этапа 4 — добавленная строка JOURNAL.md."""
    if subprocess.run(["git", "cat-file", "-e", MAIN_REF + ":planning/HOTFIXES.md"], capture_output=True).returncode == 0:
        files = {m.group(1) for s, p in entries for m in [re.fullmatch(r"planning/hotfixes/HF-(\d+)-[^/]+\.md", p)] if m and s == "A"}
        rows_new = set(re.findall(r"^\|\s*\[?HF-(\d+)\b", cc.git("show", "%s:planning/HOTFIXES.md" % tip), re.M))
        rows_old = set(re.findall(r"^\|\s*\[?HF-(\d+)\b", cc.git("show", "%s:planning/HOTFIXES.md" % base), re.M))
        if not files:
            return ["hotfix/* обязан добавить planning/hotfixes/HF-N-*.md (E3)"]
        missing = files - (rows_new - rows_old)
        if missing:
            return ["у хотфикса %s нет новой строки в planning/HOTFIXES.md (E3)" % ", ".join("HF-" + m for m in sorted(missing))]
        return []
    journal = cc.git("diff", "-U0", base, tip, "--", "planning/JOURNAL.md")
    if not any(l.startswith("+") and not l.startswith("+++") for l in journal.splitlines()):
        return ["hotfix/* обязан добавить запись в planning/JOURNAL.md (реестра HF ещё нет, E3)"]
    return []


def plan_errors(number, tip):
    """E3 для feature/PLAN-N-*: план N есть в реестре (строка/секция индекса или документ)."""
    token = re.compile(r"(?<![\w-])PLAN-" + re.escape(number) + r"(?!\d|\.\d)")
    for index in ("planning/ACTIVE_PLANS.md", "planning/PLANS.md"):
        if token.search(cc.git("show", "%s:%s" % (tip, index))):
            return []
    docs = cc.git("ls-tree", "-r", "--name-only", tip, "--", "planning/plans").splitlines()
    if any(re.fullmatch(r"planning/plans/(PLAN-%s-[^/]+\.md|closed/PLAN-%s\.md)" % (re.escape(number), re.escape(number)), d) for d in docs):
        return []
    return ["плана PLAN-%s нет в реестре (E3)" % number]


def merge_tree_errors(tip):
    """E17: структурная проверка реестров на дереве результата слияния main + tip (registry.sh check)."""
    registry = Path(".claude/scripts/registry.sh")
    if not registry.is_file():
        return []
    res = subprocess.run(["git", "merge-tree", "--write-tree", "--no-messages", MAIN_REF, tip], capture_output=True, text=True)
    tree = res.stdout.split("\n", 1)[0].strip()
    if res.returncode > 1 or not re.fullmatch(r"[0-9a-f]{40,64}", tree):
        return ["дерево слияния не построено (git merge-tree): %s" % res.stderr.strip()[:200]]
    packed = subprocess.run(["git", "archive", "--format=tar", tree, "planning"], capture_output=True)
    if packed.returncode != 0:
        return []  # в результате слияния нет planning/ — проверять нечего
    with tempfile.TemporaryDirectory() as tmp:
        with tarfile.open(fileobj=io.BytesIO(packed.stdout)) as tar:
            for member in tar.getmembers():
                if member.isfile() and not member.name.startswith(("/", "..")):
                    tar.extract(member, tmp, **({"filter": "data"} if hasattr(tarfile, "data_filter") else {}))
        out = subprocess.run(["bash", str(registry), "check", "--registry", "all", "--root", tmp], capture_output=True, text=True)
    if out.returncode == 0:
        return []
    lines = [l for l in out.stdout.splitlines() if " — " in l and "пропуск" not in l] or out.stderr.splitlines()[:3] or ["registry.sh вернул %d" % out.returncode]
    return ["реестры RM/PLAN/HF на дереве слияния нарушены (E17): " + "; ".join(lines[:8])]


def deny(errors):
    for e in errors:
        print(e, file=sys.stderr)
    return 2


RELEVANT = {"merge", "pull", "cherry-pick", "rebase", "reset", "update-ref", "symbolic-ref", "branch", "push",
            "fetch", "checkout", "switch", "tag"}
MOVING_REFS = {"FETCH_HEAD", "ORIG_HEAD", "MERGE_HEAD", "CHERRY_PICK_HEAD"}
PROTECT = "правила проекта: работа ведётся в ветках feature/* и hotfix/*, main меняется только мержем владельца"


def flags(call):
    """({короткие}, {длинные}, [позиционные]) аргументов подкоманды."""
    short, long_, pos = set(), set(), []
    for kind, value in cc.walk(call["sub"], call["args"]):
        {"short": short.add, "long": long_.add, "pos": pos.append}[kind](value)
    return short, long_, pos


def to_main_refspec(pos):
    return any(re.search(r"(^|:)(refs/heads/)?main$", p) for p in pos[1:] if ":" in p or p == "main")


def protected_errors(call, cur):
    """Агент не двигает main в обход мержа: cherry-pick/rebase/reset --hard на main, update-ref/branch -f/push . в main."""
    sub = call["sub"]
    short, long_, pos = flags(call)
    on_main = cur == "main"
    bad = None
    if sub in ("cherry-pick", "rebase") and on_main:
        bad = "git %s на main" % sub
    elif sub == "reset" and on_main and (long_ & {"hard", "merge", "keep"} or before_dashes(call) not in ([], ["HEAD"])):
        bad = "git reset на main (допустим только no-op: reset [HEAD] [-- путь])"
    elif sub == "update-ref" and (
            "stdin" in long_ or (pos[:1] and pos[0] in ("refs/heads/main", "main")) or (on_main and pos[:1] == ["HEAD"])):
        bad = "git update-ref (--stdin, main или HEAD на main)"
    elif sub == "branch" and (short & {"f", "M"} or long_ & {"force"}) and pos[:1] == ["main"]:
        bad = "git branch -f main"
    elif sub == "push" and pos[:1] == ["."] and to_main_refspec(pos):
        bad = "git push . с целевой ссылкой main"
    elif sub == "fetch" and to_main_refspec(pos):
        bad = "git fetch с обновлением локального main"
    elif sub == "symbolic-ref" and len(pos) >= 2 and (on_main or pos[1].endswith("main")):
        bad = "git symbolic-ref (смена HEAD) на main"
    elif sub in ("checkout", "switch") and (short & {"B", "C"} or long_ & {"force-create"}) and pos[:1] == ["main"]:
        bad = "пересоздание main (%s -B/-C/--force-create main)" % sub
    return ["Заблокировано: %s — %s." % (bad, PROTECT)] if bad else []


def before_dashes(call):
    """Позиционные аргументы до `--` (после `--` идут пути)."""
    args = call["args"]
    args = args[:args.index("--")] if "--" in args else args
    return [a for a in args if not a.startswith("-")]


def mutates_refs(call):
    """Команда, которая в той же цепочке может подменить ссылку, что потом уйдёт в merge/pull на main."""
    short, long_, pos = flags(call)
    sub = call["sub"]
    return (sub in ("fetch", "update-ref", "reset", "pull")
            or (sub == "branch" and bool(short & {"f", "D", "d", "M", "m"} or long_ & {"force", "delete"}))
            or (sub == "tag" and bool(short & {"f", "d"} or long_ & {"force", "delete"}))
            or (sub in ("checkout", "switch") and bool(short & {"B", "C"} or long_ & {"force-create"}))
            or (sub == "push" and pos[:1] == ["."]))


def switched(call, cur):
    """Ветка после `git checkout|switch …` (-b/-B/-c/-C — новая ветка; иначе первая позиционная, если это ветка)."""
    short, long_, pos = flags(call)
    if not pos:
        return "HEAD" if "detach" in long_ else cur
    if short & {"b", "B", "c", "C"} or long_ & {"create", "force-create", "orphan"}:
        return pos[0]
    if pos[0] == "-" or pos[0].startswith("@{-"):
        # предыдущая ветка; не определилась - считаем целью main (fail-closed)
        previous = short_branch(cc.git("rev-parse", "--symbolic-full-name", "@{-1}").strip())
        return previous if previous and previous != "HEAD" else "main"
    if cc.git("rev-parse", "--verify", "--quiet", "refs/heads/" + pos[0]).strip():
        return pos[0]
    return cur


def enter(call):
    """Переходит в рабочий каталог вызова и выставляет GIT_DIR/GIT_WORK_TREE из разбора команды.
    -> (корень репозитория, ключ состояния) или (None, None), если репозиторий определить нельзя."""
    for name in ("GIT_DIR", "GIT_WORK_TREE"):
        os.environ.pop(name, None)
    base = call["worktree"] or call["wd"]
    if not os.path.isdir(base):
        return None, None
    os.chdir(base)
    if call["gitdir"]:
        os.environ["GIT_DIR"] = call["gitdir"]
    if call["worktree"]:
        os.environ["GIT_WORK_TREE"] = call["worktree"]
    out = subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True)
    if out.returncode == 0:
        top = out.stdout.strip()
    elif call["gitdir"] and subprocess.run(["git", "rev-parse", "--git-dir"], capture_output=True).returncode == 0:
        top = base  # репозиторий найден по --git-dir, но дерева нет (bare): стейты и правила - от каталога вызова
    else:
        return None, None
    os.chdir(top)
    return top, (top, call["gitdir"])


def check_ref(ref, to_main, conf, patterns, errors):
    """T16 и далее для одной ссылки merge. -> (sha, имя ветки) для захвата маркеров или None."""
    sha = cc.git("rev-parse", "--verify", "--quiet", ref + "^{commit}").strip()
    if not sha:
        fail(ref, "ссылка не резолвится в коммит (fail-closed)", errors)
        return None
    base = cc.git("merge-base", MAIN_REF, sha).strip()
    if not base:
        fail(ref, "нет общей базы с main", errors)
        return None
    out = cc.git("diff", "--name-status", "-z", "--no-renames", base, sha).split("\0")
    entries = [(out[i], out[i + 1]) for i in range(0, len(out) - 1, 2)]
    names = branch_names(sha)
    name = names[0] if len(names) == 1 else None
    if entries and len(names) > 1:
        fail(ref, "вершина %s у нескольких веток (%s) — мержи по одной, имя ветки неоднозначно" % (sha[:7], ", ".join(names)), errors)
        return None

    # T16: правила путей по диффу. Допустима ветка feature/PLAN-N-* или hotfix/*; остальное — только planning/
    allowed = bool(names) and all(PLAN_BRANCH.match(n) or n.startswith("hotfix/") for n in names)
    for status, path in entries:
        kind = paths.classify(path, conf)
        if kind == "unknown" and status != "D":
            fail(ref, "%s: корневой элемент не классифицирован — добавь строку в .claude/hooks/paths.conf (fail-closed)" % path, errors)
        elif kind != "planning" and not allowed:
            fail(ref, "%s ('%s'): вне planning/ мержится только ветка feature/PLAN-N-* или hotfix/*, а ссылка даёт %s" % (
                path, kind, ", ".join(names) if names else "ни одной такой ветки"), errors)

    # гейт и ревью (E12) — по каждой ветке на этом SHA. Ветка, где менялся ТОЛЬКО planning/ (закрытие плана, правка
    # реестров), кода не несёт: полный гейт и ревью ей не нужны. Остальные проверки (имя ветки, реестры на дереве
    # слияния, E3, слово владельца) не снимаются. Один путь вне planning/ (в т.ч. удаление) возвращает строгие правила.
    # Ветка обязана содержать актуальный main: иначе merge применит её правки к файлам, которые main успела переименовать
    # (rename detection), и «planning/x» из диффа окажется кодом в результате слияния.
    all_planning = bool(entries) and all(paths.classify(p, conf) == "planning" for _, p in entries)
    contains_main = subprocess.run(["git", "merge-base", "--is-ancestor", MAIN_REF, sha], capture_output=True).returncode == 0
    docs_only = all_planning and contains_main
    if all_planning and not contains_main and not names:
        # без имени feature/*|hotfix/* штампов не требуется вовсе, а merge может перенести правки на переименованный main файл
        fail(ref, "ветка отстаёт от main и не принадлежит feature/*|hotfix/*: при слиянии правки planning/ могут переехать в код "
                  "(rename detection). Подтяни main в ветку и повтори", errors)
    money = any(is_money(p, patterns) for _, p in entries)
    for n in names:
        if docs_only:
            continue
        for e in stamp_errors(n, sha, money):
            fail(n, e, errors)
    if not (to_main and entries):
        return None

    # E3: запись хотфикса / план в реестре — только для однозначной ветки
    if name and name.startswith("hotfix/"):
        for e in hotfix_errors(base, sha, entries):
            fail(name, e, errors)
    plan = PLAN_BRANCH.match(name or "")
    if plan:
        for e in plan_errors(plan.group(1), sha):
            fail(name, e, errors)
    # E17: реестры на дереве результата слияния
    for e in merge_tree_errors(sha):
        fail(ref, e, errors)
    # E10/E11: слово владельца привязано к имени ветки; без однозначного имени его не к чему привязать
    wanted = owner_ok.needed(entries, lambda p, t=sha: cc.git("show", "%s:%s" % (t, p)), old=base, branch=name or "?")
    if wanted and not name:
        fail(ref, "нужно слово владельца (%s), а вершина %s не принадлежит ровно одной ветке feature/*|hotfix/*" % (
            ", ".join("%s %s" % w for w in sorted(wanted)), sha[:7]), errors)
    elif name:
        return sha, name
    return None


def handle_merge(call, cur, mutated, conf, patterns, errors, items):
    _, long_, pos = flags(call)
    if long_ & {"abort", "continue", "quit"}:
        return
    refs = list(dict.fromkeys(pos))
    if cur != "main":
        for ref in refs:  # цель не main: штампы и правила путей, маркеры не нужны
            check_ref(ref, False, conf, patterns, errors)
        return
    if not refs:
        errors.append("Мерж в main без ссылки (upstream/--ff-only) заблокирован: укажи ветку явно, git merge <feature/…> (T16).")
    elif len(refs) > 1:
        errors.append("Мерж нескольких ссылок в main (octopus) заблокирован: мержи по одной ветке.")
    elif refs[0] in MOVING_REFS:
        errors.append("Мерж '%s' в main заблокирован: подвижная ссылка не годится, укажи ветку или SHA." % refs[0])
    elif mutated:
        errors.append("Мерж '%s' в main заблокирован: в той же команде раньше меняются ссылки (%s) — разбей на отдельные команды." % (refs[0], ", ".join(mutated)))
    else:
        item = check_ref(refs[0], True, conf, patterns, errors)
        if item:
            items.append(item)


def handle_pull(call, cur, mutated, errors):
    """pull в main - это fetch+merge в обход гейта. Допустимо только `git pull --ff-only` (upstream origin/main)
    и `git pull [--ff-only] <именованный remote> main`; --rebase, URL/путь, прочие ссылки - блок."""
    if cur != "main":
        return
    short, long_, pos = flags(call)
    remotes = cc.git("remote").split()
    if short - {"q", "v"} or long_ - {"ff-only", "quiet", "verbose", "no-edit"}:
        why = "опции pull (допустимы только --ff-only)"
    elif pos == [] and "ff-only" in long_:
        upstream = re.fullmatch(r"refs/remotes/([^/]+)/main", cc.git("rev-parse", "--symbolic-full-name", "@{u}").strip())
        why = None if upstream and upstream.group(1) in remotes else "upstream ветки main не <remote>/main"
    elif len(pos) == 2 and pos[1] == "main" and pos[0] in remotes:
        why = None
    else:
        why = "ссылки pull (%s)" % (" ".join(pos) or "голый pull")
    if why:
        errors.append("git pull в main заблокирован: %s - это мерж в обход гейта. Разрешено: git pull --ff-only | git pull [--ff-only] <remote> main." % why)
    elif mutated:
        errors.append("git pull в main после изменения ссылок в той же команде (%s) заблокирован - разбей на отдельные команды." % ", ".join(mutated))


def preflight(ref):
    """merge-ready.sh: сухой прогон merge-gate для ветки БЕЗ захвата маркеров и без мержа. Печатает READY (всё, кроме слов
    владельца, пройдено; недостающие слова перечислены) или NOT READY со списком недостающего. exit 0 / 1 / 2 (ошибка)."""
    # Побочный эффект: merge_tree_errors (git merge-tree --write-tree) создаёт git-объекты - для сухого прогона это допустимо.
    top = cc.git("rev-parse", "--show-toplevel").strip()
    if not top:
        print("merge-ready: не git-репозиторий", file=sys.stderr)
        return 2
    os.chdir(top)
    errors, problems = [], []
    item = check_ref(ref, True, paths.load(), money_patterns(), errors)
    sha = cc.git("rev-parse", "--verify", "--quiet", ref + "^{commit}").strip()
    problems += [re.sub(r"^Мерж '[^']*' заблокирован: ", "", e) for e in errors]
    if sha:
        behind = cc.git("rev-list", "--count", "%s..%s" % (sha, MAIN_REF)).strip()
        if behind not in ("", "0"):
            problems.append("ветка отстаёт от main на %s коммит(ов): подтяни main в ветку (гейт и ревью придётся повторить)" % behind)
        if cc.git("status", "--porcelain").strip():
            problems.append("рабочее дерево не чистое: гейт и ревью относятся к закоммиченной вершине")
    words = []
    if item:
        words = [(k, i, name, err) for k, i, name, err, _ in owner_ok.word_checks([item]) if err]
    if problems:
        print("NOT READY: %s (вершина %s)" % (ref, sha[:7]))
        for p in problems:
            print("  - " + p)
    else:
        print("READY" if not words else "READY (кроме слов владельца)")
    for k, i, name, err in words:
        print("  слово владельца: .claude/scripts/owner-ok.sh %s %s %s   # привязано к вершине %s" % (k, i, name, sha[:7]))
    return 1 if problems else 0


def main():
    if len(sys.argv) == 3 and sys.argv[1] == "--preflight":
        return preflight(sys.argv[2])
    payload = json.loads(sys.stdin.read() or "{}")
    tool_input = payload.get("tool_input") or {}
    cmd = tool_input.get("command") or tool_input.get("cmd") or ""
    try:
        # HF-174: из worktree хук стартует в основном чекауте, база — cwd команды.
        calls = cc.parse(cmd, payload.get("cwd") or cc.base_pwd())
    except ValueError:
        if re.search(r"\bgit\b[^\n]*\b(merge|pull|cherry-pick|rebase|reset|update-ref|symbolic-ref)\b", cc.strip_heredocs(cmd)):
            return deny(["Заблокировано: команда git не разобрана (fail-closed), упрости её."])
        return 0
    if not any(c["sub"] in RELEVANT for c in calls):
        return 0

    conf, patterns = paths.load(), money_patterns()
    errors, items, state, mutated = [], [], {}, []
    for call in calls:
        if call["sub"] not in RELEVANT:
            continue
        top, key = enter(call)
        if not top:
            if call["sub"] in ("merge", "pull") or call["gitdir"]:
                errors.append("git %s: не удалось определить репозиторий (%s) - fail-closed." % (call["sub"], call["gitdir"] or call["worktree"] or call["wd"]))
            continue
        cur = state.setdefault(key, current_branch())
        sub = call["sub"]
        errors += protected_errors(call, cur)
        if sub == "merge":
            handle_merge(call, cur, mutated, conf, patterns, errors, items)
        elif sub == "pull":
            handle_pull(call, cur, mutated, errors)
        if sub in ("checkout", "switch"):
            state[key] = switched(call, cur)
        if mutates_refs(call):
            mutated.append(sub)
    if errors:
        return deny(errors)
    return owner_ok.claim_items(items) if items else 0


if __name__ == "__main__":
    sys.stderr.reconfigure(errors="backslashreplace")
    try:
        sys.exit(main())
    except Exception as exc:  # noqa: BLE001
        # мерж — условие допуска в main: сбой самой проверки = отказ (fail-closed)
        print("Мерж заблокирован: внутренняя ошибка merge_checks.py: %s: %s" % (type(exc).__name__, exc), file=sys.stderr)
        sys.exit(2)
