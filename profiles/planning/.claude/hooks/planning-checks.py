#!/usr/bin/env python3
"""Проверки планировочного профиля x-harness (SPEC п.5-7).

Режимы (exit 2 = блокировка, причины в stderr; внутренняя ошибка хука = fail-open, exit 0):

  staged BRANCH        git-хук pre-commit: E7 (резюме плана), E8 (размер плана),
                       E9-лайт (что лежит в корне planning/), маркер владельца для
                       новой идеи RM и для закрытия плана (plans/closed/PLAN-N.md).
  msg MSGFILE BRANCH   git-хук commit-msg: токен PLAN-N / HF-M в сообщении коммита.

Авторитетная проверка — git-хуки; сбой самого хука не должен парализовать работу.
"""
import os
import re
import subprocess
import sys
import time
from pathlib import Path

# Дефолты SPEC п.4: без .claude/planning.conf действуют ровно они.
DEFAULTS = {
    "MAIN_BRANCH": "main",
    "CODE_ROOTS": "app src lib",
    "FEATURE_BRANCH_RE": r"^feature/PLAN-([0-9]+(\.[0-9]+)*)(?:-|$)",
    "HOTFIX_BRANCH_RE": r"^hotfix/",
    "TOKEN_REQUIRED": "on",
    "PLAN_SUMMARY_MIN_NUMBER": "1",
    "PLAN_WARN_BYTES": "40960",
    "PLAN_HARD_BYTES": "81920",
    "DRIFT_HORIZON_DAYS": "90",
    "DRIFT_MEMORY_INDEX": "",
    "OWNER_OK_TTL_HOURS": "24",
    "PLANNING_ROOT_ALLOWED": "ROADMAP.md ACTIVE_PLANS.md PLANS.md HOTFIXES.md README.md plans roadmap hotfixes",
    "STRICT": "on",
    "PROTECTED_PATHS": ".claude/hooks/ .claude/scripts/ .claude/settings.json .claude/planning.conf .githooks/ AGENTS.md .codex/",
    "CODE_FILES": "Makefile package.json pyproject.toml go.mod go.sum Cargo.toml composer.json requirements.txt",
    "GATE_FAST": "",
    "GATE_MERGE": "",
}

SUMMARY_MAX_LINES = 15
SUMMARY_HEAD_WINDOW = 30
SIZE_WAIVER = "<!-- size-waiver:"


# ---------------------------------------------------------------- конфиг

def _unquote_inner(text, quote):
    """Разворачивает содержимое кавычек так, как это сделал бы shell (минимум для conf)."""
    if quote == "'":
        return text
    out, i = [], 0
    escapes = {"n": "\n", "t": "\t", "r": "\r", "\\": "\\", '"': '"', "$": "$", "\x60": "\x60"}
    while i < len(text):
        ch = text[i]
        if ch == "\\" and i + 1 < len(text):
            nxt = text[i + 1]
            out.append(escapes.get(nxt, "\\" + nxt))
            i += 2
            continue
        out.append(ch)
        i += 1
    return "".join(out)


def parse_value(raw):
    """KEY=VALUE -> значение: кавычки снимаются, хвостовой комментарий отбрасывается."""
    raw = raw.strip()
    if raw[:1] in ("'", '"'):
        quote = raw[0]
        i = 1
        while i < len(raw):
            if quote == '"' and raw[i] == "\\":
                i += 2
                continue
            if raw[i] == quote:
                return _unquote_inner(raw[1:i], quote)
            i += 1
        return raw[1:]
    return raw.split("#", 1)[0].strip()


def load_conf(root):
    conf = dict(DEFAULTS)
    path = Path(root) / ".claude" / "planning.conf"
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return conf
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export "):].strip()
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        conf[key.strip()] = parse_value(value)
    return conf


def as_int(conf, key, default, minimum=0):
    try:
        value = int(conf.get(key, ""))
    except (TypeError, ValueError):
        return default
    return value if value >= minimum else default


def allowed_root_names(conf):
    return set(conf.get("PLANNING_ROOT_ALLOWED", "").split())


# ---------------------------------------------------------------- классификация (E2/E18)

def is_strict(conf):
    """STRICT=on по умолчанию; off выключает E2/E18 и другие новые блокировки."""
    return str(conf.get("STRICT", "on")).strip().lower() not in ("off", "0", "false", "no")


def is_protected(rel, conf):
    """Защищённый путь (E18): каталог-префикс с «/» на конце или точный файл."""
    for entry in conf.get("PROTECTED_PATHS", "").split():
        if entry.endswith("/"):
            if rel.startswith(entry):
                return True
        elif rel == entry:
            return True
    return False


def code_roots(conf, extra_paths=()):
    """Каталоги кода: существующие из CODE_ROOTS, иначе автодетект первого уровня по git.

    extra_paths — пути из staged-диффа: новый каталог кода до первого коммита ещё
    не в git ls-files, но E2 обязан его увидеть."""
    listed = [r for r in conf.get("CODE_ROOTS", "").split() if r]
    present = [r for r in listed if Path(r).is_dir()]
    if present:
        return set(present)

    def candidates(paths):
        out = set()
        for path in paths:
            if "/" not in path:
                continue
            first = path.split("/", 1)[0]
            if first.startswith(".") or first in ("planning", "node_modules", "vendor"):
                continue
            if Path(first).is_dir():
                out.add(first)
        return out

    found = candidates(git_text("ls-files", "-z").split(chr(0)))
    found |= candidates(extra_paths)
    return found


def is_code(rel, conf, roots=None):
    """Код (E2): путь под CODE_ROOTS или корневой файл из CODE_FILES.

    planning/, docs/, wiki/, *.md и PROTECTED_PATHS — не код (SPEC §9)."""
    rel = rel[2:] if rel.startswith("./") else rel
    parts = rel.split("/")
    first = parts[0]
    if first in ("planning", "docs", "wiki"):
        return False
    if rel.endswith(".md"):
        return False
    if is_protected(rel, conf):
        return False
    if roots is None:
        roots = code_roots(conf)
    if first in roots:
        return True
    if len(parts) == 1 and rel in set(conf.get("CODE_FILES", "").split()):
        return True
    return False


# ---------------------------------------------------------------- git

def git(*args):
    return subprocess.run(["git", *args], capture_output=True)


def git_text(*args):
    return git(*args).stdout.decode("utf-8", "surrogateescape")


def git_bytes(*args):
    return git(*args).stdout


def repo_root():
    return git_text("rev-parse", "--show-toplevel").strip() or os.getcwd()


def staged_entries():
    """[(статус, путь)] по индексу; переименования не разворачиваем (--no-renames)."""
    out = git_text("diff", "--cached", "--name-status", "-z", "--no-renames").split("\0")
    return [(out[i], out[i + 1]) for i in range(0, len(out) - 1, 2) if out[i]]


def staged_blob(path):
    return git_bytes("show", ":" + path)


def head_text(path):
    return git_text("show", "HEAD:" + path)


def in_progress():
    """Идёт merge/cherry-pick/revert/rebase — коммит собирает git, освобождения по сообщению мало."""
    for name in ("MERGE_HEAD", "CHERRY_PICK_HEAD", "REVERT_HEAD", "rebase-merge", "rebase-apply"):
        p = git_text("rev-parse", "--git-path", name).strip()
        if p and Path(p).exists():
            return True
    return False


# ---------------------------------------------------------------- E7/E8

def summary_problem(text):
    """None, если в плане есть раздел Резюме не длиннее 15 строк."""
    lines = text.split("\n")
    head = next((i for i, line in enumerate(lines[:SUMMARY_HEAD_WINDOW]) if line.strip() == "## Резюме"), None)
    if head is None:
        return "нет раздела «## Резюме» в первых %d строках" % SUMMARY_HEAD_WINDOW
    body = []
    for line in lines[head + 1:]:
        if line.startswith("## "):
            break
        body.append(line)
    while body and not body[-1].strip():
        body.pop()
    if len(body) > SUMMARY_MAX_LINES:
        return "Резюме %d строк (максимум %d)" % (len(body), SUMMARY_MAX_LINES)
    return None


def size_problems(path, blob, number, conf):
    """(errors, warnings) по размеру тела плана (E8)."""
    errors, warns = [], []
    hard = as_int(conf, "PLAN_HARD_BYTES", 81920)
    warn = as_int(conf, "PLAN_WARN_BYTES", 40960)
    min_number = as_int(conf, "PLAN_SUMMARY_MIN_NUMBER", 1)
    text = blob.decode("utf-8", "replace")
    head30 = "\n".join(text.split("\n")[:SUMMARY_HEAD_WINDOW])
    if len(blob) > hard and number >= min_number and SIZE_WAIVER not in head30:
        errors.append("%s: %d КБ > %d КБ; раздели план или добавь маркер size-waiver в первые %d строк (E8)"
                      % (path, len(blob) // 1024, hard // 1024, SUMMARY_HEAD_WINDOW))
    elif len(blob) > warn:
        warns.append("%s: %d КБ (порог предупреждения %d КБ, E8)" % (path, len(blob) // 1024, warn // 1024))
    return errors, warns


# ---------------------------------------------------------------- owner-ok

def enc(text):
    """Имя маркера: % / _ @ кодируются, поэтому feature/a/b и feature/a_b не сталкиваются."""
    for ch, code in (("%", "%25"), ("/", "%2F"), ("_", "%5F"), ("@", "%40")):
        text = text.replace(ch, code)
    return text


def marker_path(root, kind, ident, branch):
    return Path(root) / ".claude" / "state" / "planning-owner-ok" / ("%s-%s@%s" % (kind, enc(ident), enc(branch)))


def marker_problem(root, conf, kind, ident, branch, sha=None):
    """None, если маркер владельца принимается; иначе причина (SPEC п.6, §9).

    sha — ожидаемая вершина (по умолчанию HEAD): для merge это вершина ИСХОДНОЙ ветки."""
    what = {"rm-add": "новая идея в roadmap", "close-plan": "закрытие плана",
            "hooks-edit": "правка защищённых путей", "merge": "мерж ветки в %s" % conf.get("MAIN_BRANCH", "main")}.get(
                kind, "операция")
    how = "попроси владельца выполнить .claude/scripts/planning-owner-ok.sh %s %s" % (kind, ident)
    path = marker_path(root, kind, ident, branch)
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return "%s %s — только по слову владельца: %s (маркер в .claude/state/planning-owner-ok/)." % (what, ident, how)
    data = dict(line.split("=", 1) for line in text.splitlines() if "=" in line)
    if data.get("kind") != kind or data.get("id") != ident or data.get("branch") != branch:
        return "%s %s: маркер не относится к этой операции или ветке; %s." % (what, ident, how)
    if data.get("target") != conf.get("MAIN_BRANCH", "main"):
        return "%s %s: маркер выдан не для ветки %s; %s." % (what, ident, conf.get("MAIN_BRANCH", "main"), how)
    try:
        ttl_until = int(data.get("ttl_until", "0"))
    except ValueError:
        ttl_until = 0
    if time.time() > ttl_until:
        return "%s %s: разрешение владельца истекло (TTL %s ч); %s." % (
            what, ident, conf.get("OWNER_OK_TTL_HOURS", "24"), how)
    expected = sha if sha is not None else git_text("rev-parse", "HEAD").strip()
    if not expected or data.get("sha") != expected:
        return "%s %s: после выдачи разрешения ветка изменилась (вершина не совпала); %s." % (
            what, ident, how)
    return None


def rm_rows(text):
    """RM-N из строк таблицы ROADMAP.md (строка вида | [RM-1](...) | или | RM-1 |)."""
    return set(re.findall(r"^\|\s*\[?RM-(\d+)\b", text, re.M))


def owner_ok_errors(conf, branch, entries):
    """Причины отказа по E10/E11: новая идея RM и закрытие плана — только по слову владельца."""
    root = repo_root()
    needs = set()
    status = {path: st for st, path in entries}
    for st, path in entries:
        m = re.fullmatch(r"planning/roadmap/RM-(\d+)-[^/]+\.md", path)
        if m and st == "A":
            needs.add(("rm-add", "RM-" + m.group(1)))
        m = re.fullmatch(r"planning/plans/closed/PLAN-(\d+(?:\.\d+)*)\.md", path)
        if m and st == "A":
            needs.add(("close-plan", "PLAN-" + m.group(1)))
    if status.get("planning/ROADMAP.md") != "D":
        try:
            new_ids = rm_rows(staged_blob("planning/ROADMAP.md").decode("utf-8", "replace"))
            old_ids = rm_rows(head_text("planning/ROADMAP.md"))
            for number in new_ids - old_ids:
                needs.add(("rm-add", "RM-" + number))
        except OSError:
            pass
    errors = []
    for kind, ident in sorted(needs):
        problem = marker_problem(root, conf, kind, ident, branch)
        if problem:
            errors.append(problem)
    return errors


# ---------------------------------------------------------------- E2/E18

def strict_tree_errors(conf, branch, entries):
    """E2 (код только на feature/PLAN-N-* и hotfix/*) и E18 (PROTECTED_PATHS — с маркером hooks-edit).

    При STRICT=off и во время merge/rebase/cherry-pick не применяются: коммит собирает git."""
    if not is_strict(conf) or in_progress():
        return []
    roots = code_roots(conf, [path for _, path in entries])
    branch_ok = bool(re.match(conf.get("FEATURE_BRANCH_RE", DEFAULTS["FEATURE_BRANCH_RE"]), branch))         or bool(re.match(conf.get("HOTFIX_BRANCH_RE", DEFAULTS["HOTFIX_BRANCH_RE"]), branch))
    errors = []
    protected_reported = False
    for _status, path in entries:
        if is_protected(path, conf):
            if not protected_reported:
                problem = marker_problem(repo_root(), conf, "hooks-edit", branch, branch)
                if problem:
                    errors.append("E18: " + problem)
                protected_reported = True
            continue
        if branch_ok:
            continue
        if is_code(path, conf, roots):
            errors.append("%s: код правится только на feature/PLAN-<N>-* или hotfix/*, "
                          "а ветка '%s' (E2). Правки сохранятся: git checkout -b feature/PLAN-N-slug" % (path, branch))
    return errors


# ---------------------------------------------------------------- режим staged

def check_tree(branch):
    conf = load_conf(repo_root())
    allowed = allowed_root_names(conf)
    min_number = as_int(conf, "PLAN_SUMMARY_MIN_NUMBER", 1)
    entries = staged_entries()
    errors, warns = [], []
    errors += strict_tree_errors(conf, branch, entries)

    for status, path in entries:
        parts = path.split("/")
        # E9-лайт: в корне planning/ — только служебные файлы и каталоги реестров.
        if status != "D" and parts[0] == "planning" and len(parts) >= 2 and parts[1] not in allowed:
            errors.append("%s: в корне planning/ допустимы только служебные файлы и каталоги (%s); "
                          "тело плана — в plans/, идея — в roadmap/, хотфикс — в hotfixes/ (E9)"
                          % (path, " ".join(sorted(allowed))))
        m = re.fullmatch(r"planning/plans/PLAN-(\d+)(?:\.\d+)*-[^/]+\.md", path)
        if status == "D" or not m:
            continue
        blob = staged_blob(path)
        if not blob:
            continue  # intent-to-add или пустой файл — содержимого в индексе ещё нет
        number = int(m.group(1))
        if number >= min_number:
            problem = summary_problem(blob.decode("utf-8", "replace"))
            if problem:
                errors.append("%s: %s (E7)" % (path, problem))
        e, w = size_problems(path, blob, number, conf)
        errors += e
        warns += w

    if not in_progress():
        # при merge/rebase/cherry-pick ветка коммита не та, к которой привязан маркер
        errors += owner_ok_errors(conf, branch, entries)

    for warning in warns:
        print("Предупреждение: " + warning, file=sys.stderr)
    for error in errors:
        print(error, file=sys.stderr)
    if errors:
        print("planning-checks: правка заблокирована: исправь замечания выше.", file=sys.stderr)
        return 2
    return 0


# ---------------------------------------------------------------- режим msg

def check_message(msgfile, branch):
    conf = load_conf(repo_root())
    try:
        text = Path(msgfile).read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        print("planning-checks: не читается файл сообщения %s (%s) — проверка токена пропущена" % (msgfile, exc),
              file=sys.stderr)
        return 0
    msg = "\n".join(line for line in text.split("\n") if not line.startswith("#")).strip()
    # Слияния/revert/fixup собирает git или это не ручной коммит — токен не требуем.
    if re.match(r"(Revert |fixup! |squash! |Merge (branch|remote-tracking branch|pull request|tag) )", msg) \
            or in_progress():
        return 0
    if conf.get("TOKEN_REQUIRED", "on") == "off":
        return 0
    main_branch = conf.get("MAIN_BRANCH", "main")
    if branch == main_branch:
        return 0  # на основной ветке мерж-коммиты без токена

    names = [path for _, path in staged_entries()]
    roadmap_only = bool(names) and all(
        path == "planning/ROADMAP.md" or path.startswith("planning/roadmap/") for path in names)

    def has(pattern):
        # Граница токена: PLAN-145 не матчится в PLAN-1450 и PLAN-145.1, но «PLAN-145.» (точка фразы) проходит.
        return re.search(r"(?<![\w-])" + pattern + r"(?!\d|\.\d)", msg) is not None

    feature = re.match(conf.get("FEATURE_BRANCH_RE", DEFAULTS["FEATURE_BRANCH_RE"]), branch)
    if feature:
        need = "PLAN-" + feature.group(1)
        hint = "PLAN-%s (номер плана из имени ветки)" % feature.group(1)
        ok = has(re.escape(need))
    elif re.match(conf.get("HOTFIX_BRANCH_RE", DEFAULTS["HOTFIX_BRANCH_RE"]), branch):
        hint = "HF-<число> (номер хотфикса)"
        ok = has(r"HF-\d+")
    else:
        return 0  # ветка вне схемы feature/PLAN-N | hotfix/* — токен не наш случай

    if ok or (roadmap_only and has(r"RM-\d+")):
        return 0
    print("Сообщение коммита должно содержать %s (ветка '%s')." % (hint, branch), file=sys.stderr)
    if roadmap_only:
        print("Коммит только по planning/roadmap/** или ROADMAP.md может нести RM-<N> вместо токена плана.",
              file=sys.stderr)
    else:
        print("RM-<N> годится лишь когда в коммите только planning/roadmap/** или ROADMAP.md.", file=sys.stderr)
    print("planning-checks: коммит заблокирован.", file=sys.stderr)
    return 2


# ---------------------------------------------------------------- CLI

def usage():
    print("usage: planning-checks.py staged <ветка> | msg <файл-сообщения> <ветка>", file=sys.stderr)
    return 2


def main(argv):
    if not argv:
        return usage()
    action = argv[0]
    if action == "staged":
        return check_tree(argv[1] if len(argv) > 1 else "HEAD")
    if action == "msg" and len(argv) >= 3:
        return check_message(argv[1], argv[2])
    return usage()


if __name__ == "__main__":
    try:
        sys.stderr.reconfigure(errors="backslashreplace")
    except AttributeError:
        pass
    try:
        sys.exit(main(sys.argv[1:]))
    except Exception as exc:  # noqa: BLE001 — fail-open: баг хука не должен парализовать владельца
        print("planning-checks: внутренняя ошибка хука: %s: %s (проверка пропущена, fail-open)"
              % (type(exc).__name__, exc), file=sys.stderr)
        sys.exit(0)
