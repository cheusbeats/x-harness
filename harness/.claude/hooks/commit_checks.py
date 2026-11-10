#!/usr/bin/env python3
"""Дешёвые проверки commit-gate (PLAN-145): работают по диффу, < 1 с.

  commit_checks.py inspect    команда на stdin (+ GUARD_ORIG_PWD = каталог вызова): печатает две строки —
                              корень репозитория, в котором пойдёт коммит (учтены `git -C`, `cd … &&`,
                              workdir Codex), и режим `staged` | `dirty`.
  commit_checks.py staged BRANCH [staged|dirty]
                              E2 (код только на feature/PLAN-N-* | hotfix/*), fail-closed на
                              неклассифицированный путь, E9 (корень planning/), E7 (Резюме),
                              E8 (размер плана). exit 2 + причины в stderr.
  commit_checks.py noverify   команда на stdin; exit 2, если хуки обходятся (E16): флаг обхода проверок,
                              `git commit -n`, `-c core.hooksPath=…`, `GIT_CONFIG_KEY_n=core.hooksPath`,
                              `git config core.hooksPath …`.

Команда разбирается как argv, а не regex'ом: строки-данные (echo, python3 -c, значение -m/-t) командой
не считаются; вложенные `bash|sh|zsh -c "…"` разбираются рекурсивно.

Режим `dirty` — консервативное СУПЕРМНОЖЕСТВО: если команда содержит `git add`/`commit -a`/`commit <пути>`,
индекс на момент хука ещё не тот, что уйдёт в коммит, поэтому проверяется всё грязное дерево
(`git status`). Лишний блок при посторонних грязных файлах принят. АВТОРИТЕТНАЯ проверка на реальном
индексе — git-хук pre-commit (PLAN-145, этап 2b); так же `registry.sh check` здесь идёт по рабочему
дереву, а по staged-дереву его гоняет pre-commit.

  commit_checks.py msg BRANCH FILE [PPID]     E3: токен PLAN-N/HF-N в сообщении КАЖДОГО коммита (git-хук commit-msg;
                              PreToolUse сообщение при heredoc/-F не видит). exit 2 + причина.
  commit_checks.py push-range BASE HEAD  структурные проверки диффа диапазона (git-хук pre-push), без E2.
"""
import os
import re
import shlex
import subprocess
import sys
from pathlib import Path

import owner_ok
import paths

WARN_BYTES = 40 * 1024
HARD_BYTES = 80 * 1024
NEW_PLAN_FROM = 145  # E7/E8 действуют на планы N >= 145; старые — только предупреждение по размеру

# ---------------------------------------------------------------- разбор команды

NOVERIFY_SUBS = {"commit", "push", "merge", "am", "rebase"}
DIRTYING_SUBS = {"add", "rm", "mv", "apply", "restore", "stash", "checkout"}
VALUE_LONG = {"message", "file", "template", "author", "date", "cleanup", "trailer", "fixup", "squash",
              "reuse-message", "reedit-message", "repo", "receive-pack", "exec", "push-option",
              "strategy", "strategy-option"}
VALUE_SHORT = {"commit": "mFtCc", "push": "o", "merge": "mFsX", "rebase": "sXxC", "am": "", "pull": "sX", "update-ref": "m"}
HOOKS_OK = ".githooks"
BYPASS_LONG = "no-verify"


def strip_heredocs(cmd):
    """Тела heredoc — данные, не команды: выбрасываем строки между `<<WORD` и терминатором."""
    out, word = [], None
    for line in cmd.split("\n"):
        if word is not None:
            if line.strip() == word:
                word = None
            continue
        out.append(line)
        m = re.search(r"<<-?\s*['\"]?([A-Za-z0-9_-]+)['\"]?", line)
        if m:
            word = m.group(1)
    return "\n".join(out)


def strip_comments(cmd):
    """Комментарий shell (`#` в начале слова вне кавычек) выбрасываем до конца строки. Иначе shlex сочтёт комментарием
    всё до конца команды: переводы строк к этому моменту уже стали `;`, и команды после `# …` никто не увидит."""
    out, quote, i = [], None, 0
    while i < len(cmd):
        ch = cmd[i]
        if ch == "\\" and quote != "'":
            out.append(cmd[i:i + 2])
            i += 2
            continue
        if quote:
            quote = None if ch == quote else quote
        elif ch in "\"'":
            quote = ch
        elif ch == "#" and (i == 0 or cmd[i - 1].isspace() or cmd[i - 1] in ";&|()"):
            while i < len(cmd) and cmd[i] != "\n":
                i += 1
            continue
        out.append(ch)
        i += 1
    return "".join(out)


def newlines_to_semicolons(cmd):
    """Перевод строки вне кавычек разделяет команды так же, как `;`; перевод после `\\` просто склеивает строки."""
    out, quote, escaped = [], None, False
    for ch in cmd:
        if escaped:
            escaped = False
            if ch == "\n":
                out.pop()
                continue
        elif ch == "\\" and quote != "'":
            escaped = True
        elif quote:
            quote = None if ch == quote else quote
        elif ch in "\"'":
            quote = ch
        elif ch == "\n":
            ch = " ; "
        out.append(ch)
    return "".join(out)


def join_dir(base, target):
    target = os.path.expanduser(target)
    return target if os.path.isabs(target) else os.path.normpath(os.path.join(base, target))


# Обёртки, после которых идёт настоящая команда: имя -> короткие опции, берущие значение
WRAPPERS = {"env": "uCS", "command": "", "exec": "a", "time": "", "nohup": "", "builtin": "", "nice": "n",
            "sudo": "ugCDhpRrt", "xargs": "IJLnPsEd", "timeout": "ks", "setsid": "", "ionice": "cnp"}
# Команды, для которых слово `git` в аргументах — данные, а не вызов
DATA_HEADS = {"echo", "printf", "grep", "egrep", "fgrep", "rg", "cat", "sed", "awk", "head", "tail", "less", "more",
              "ls", "wc", "man", "test", "[", "diff", "type", "which", "whereis"}


RISKY = re.compile(r"\bgit\b.*\b(merge|pull|commit|push|cherry-pick|rebase|reset|update-ref|symbolic-ref|fetch|checkout|switch|branch|tag|config)\b", re.S)


def substitutions(text):
    """Тела $(…) (со вложенностью) и `…`; пустой список, если подстановок нет."""
    found, i, single, double = [], 0, False, False
    while i < len(text):
        ch = text[i]
        if ch == "\\" and not single:
            i += 2
            continue
        if ch == "'" and not double:
            single = not single
        elif ch == '"' and not single:
            double = not double
        if single:  # '…' - данные
            i += 1
        elif text.startswith("$(", i):
            depth, j = 1, i + 2
            while j < len(text) and depth:
                depth += (text[j] == "(") - (text[j] == ")")
                j += 1
            found.append(text[i + 2:j - 1])
            found += substitutions(text[i + 2:j - 1])
            i = j
        elif text[i] == "`":
            j = text.find("`", i + 1)
            if j < 0:
                break
            found.append(text[i + 1:j])
            i = j + 1
        else:
            i += 1
    return found


def strip_wrappers(argv, env):
    """Снимает VAR=val и обёртки (`env -i`, `nice -n 5`, `sudo -u x`, `timeout 5`, …); -> argv настоящей команды."""
    while argv:
        name = os.path.basename(argv[0])
        if re.match(r"[A-Za-z_]\w*=", argv[0]):
            key, _, value = argv[0].partition("=")
            env[key] = value
            argv = argv[1:]
        elif name in WRAPPERS:
            valued, argv = WRAPPERS[name], argv[1:]
            while argv and argv[0].startswith("-") and argv[0] != "-":
                opt, argv = argv[0], argv[1:]
                if len(opt) == 2 and opt[1] in valued and argv:
                    argv = argv[1:]
            if name == "timeout" and argv:
                argv = argv[1:]  # длительность
        else:
            break
    return argv


def git_call(argv, wd, env):
    """argv начинается с `git`; -> {sub, args, wd, cfg, env, opts}. Учтены -C<dir>, -C <dir>, -c, --git-dir/--work-tree."""
    call = {"wd": wd, "cfg": [], "env": env, "opts": [], "gitdir": None, "worktree": None}
    work_tree = git_dir = None
    i = 1
    while i < len(argv) and argv[i].startswith("-"):
        a = argv[i]
        if a == "-C" and i + 1 < len(argv):
            call["wd"] = join_dir(call["wd"], argv[i + 1])
            i += 2
        elif a.startswith("-C") and len(a) > 2:
            call["wd"] = join_dir(call["wd"], a[2:])
            i += 1
        elif a == "-c" and i + 1 < len(argv):
            call["cfg"].append(argv[i + 1])
            i += 2
        elif a.startswith("-c") and len(a) > 2:
            call["cfg"].append(a[2:])
            i += 1
        elif a in ("--git-dir", "--work-tree", "--namespace") and i + 1 < len(argv):
            if a == "--work-tree":
                work_tree = argv[i + 1]
            elif a == "--git-dir":
                git_dir = argv[i + 1]
            i += 2
        elif a.startswith(("--git-dir=", "--work-tree=")):
            name, _, value = a.partition("=")
            work_tree, git_dir = (value, git_dir) if name == "--work-tree" else (work_tree, value)
            i += 1
        else:
            call["opts"].append(a)
            i += 1
    # git-контекст: --git-dir/--work-tree и GIT_DIR/GIT_WORK_TREE из окружения команды (wd остаётся каталогом запуска)
    git_dir, work_tree = git_dir or env.get("GIT_DIR"), work_tree or env.get("GIT_WORK_TREE")
    call["gitdir"] = join_dir(call["wd"], git_dir) if git_dir else None
    call["worktree"] = join_dir(call["wd"], work_tree) if work_tree else None
    call["sub"] = argv[i] if i < len(argv) else ""
    call["args"] = argv[i + 1:]
    return call


REDIR_OP = re.compile(r"&>>?|\d*(?:<<<|<<-?|<>|>>|>&|>\||<&|>|<)")


def strip_redirections(cmd):
    """Перенаправления (`2>&1`, `>f`, `>> f`, `&>f`, `<f`, `<<<w`, `N>&-`, `>|f`) — не аргументы команды: выбрасываем оператор
    вместе с целью, чтобы `git merge x 2>&1` не читалось как две ссылки. Вне кавычек; `<(…)`/`>(…)` не трогаем —
    лексер разбивает на них сегменты, и тело разбирается как отдельная команда. Номер дескриптора — только в начале слова."""
    out, quote, i, n = [], None, 0, len(cmd)
    while i < n:
        ch = cmd[i]
        if ch == "\\" and quote != "'" and i + 1 < n:
            out.append(cmd[i:i + 2])
            i += 2
            continue
        if quote:
            quote = None if ch == quote else quote
            out.append(ch)
            i += 1
            continue
        if ch in "\"'`":
            quote = ch
            out.append(ch)
            i += 1
            continue
        m = REDIR_OP.match(cmd, i) if ch in "<>&0123456789" else None
        word_start = i == 0 or cmd[i - 1].isspace() or cmd[i - 1] in ";&|()"
        if m and m.group(0)[0].isdigit() and not word_start:
            m = None
        if m and cmd.startswith("(", m.end()):
            m = None  # подстановка процесса
        if not m:
            out.append(ch)
            i += 1
            continue
        i = m.end()
        while i < n and cmd[i] in " \t":
            i += 1
        depth, tq = 0, None  # цель: слово до пробела/оператора вне кавычек и $( )
        while i < n:
            c = cmd[i]
            if c == "\\" and tq != "'":
                i += 2
                continue
            if tq:
                tq = None if c == tq else tq
            elif c in "\"'`":
                tq = c
            elif cmd.startswith("$(", i):
                depth += 1
                i += 1
            elif depth and c == ")":
                depth -= 1
            elif not depth and (c.isspace() or c in ";&|<>()"):
                break
            i += 1
        out.append(" ")
    return "".join(out)


def segments(cmd):
    """Команда -> список argv простых команд (без heredoc и перенаправлений); ValueError при битых кавычках."""
    lex = shlex.shlex(strip_redirections(newlines_to_semicolons(strip_comments(strip_heredocs(cmd)))), posix=True, punctuation_chars=True)
    lex.whitespace_split = True
    lex.commenters = ""
    found, cur = [], []
    for tok in lex:
        if re.fullmatch(r"[;&|()<>]+", tok):
            found.append(cur)
            cur = []
        else:
            cur.append(tok)
    found.append(cur)
    return found


def parse(cmd, wd):
    """-> [{sub, args, wd, cfg, env, opts}] по каждому вызову git; ValueError при битых кавычках.
    Вызов git находится и под обёрткой (`sudo -u x git …`, `xargs git …`), и после любых слов (`python x.py git merge`):
    слово `git` в аргументах команды, не относящейся к «данным» (echo, grep, cat …), считается вызовом."""
    calls = []

    def nested(text):
        """Вложенная командная строка (bash -c, eval, подстановка). Не разобралась, но похожа на git-команду — fail-closed."""
        try:
            return parse(text, wd)
        except ValueError:
            if RISKY.search(text):
                raise
            return []

    for argv in segments(cmd):
        env = {}
        argv = strip_wrappers(argv, env)
        if not argv:
            continue
        head = os.path.basename(argv[0])
        if head == "cd" and len(argv) > 1:
            wd = join_dir(wd, argv[1])
        elif head in ("bash", "sh", "zsh"):
            for i, t in enumerate(argv[1:-1], 1):
                if re.fullmatch(r"-[a-z]*c[a-z]*", t):
                    calls += nested(argv[i + 1])
                    break
        elif head == "eval":
            calls += nested(" ".join(argv[1:]))
        elif head == "git":
            calls.append(git_call(argv, wd, env))
        elif head not in DATA_HEADS:
            names = [os.path.basename(t) for t in argv]
            if "git" in names[1:]:
                calls.append(git_call(argv[names.index("git", 1):], wd, env))
    # подстановки $(…) и `…` (в том числе внутри двойных кавычек): разбираются тем же парсером
    for inner in substitutions(strip_comments(strip_heredocs(cmd))):
        for c in nested(inner):
            if not any((c["sub"], c["args"], c["wd"]) == (k["sub"], k["args"], k["wd"]) for k in calls):
                calls.append(c)
    return calls


def walk(sub, args):
    """Аргументы подкоманды -> (вид, значение): long/имя, short/символ, pos/токен. Значения опций пропущены."""
    i = 0
    while i < len(args):
        a = args[i]
        if a == "--":
            for rest in args[i + 1:]:
                yield "pos", rest
            return
        if a.startswith("--"):
            name, eq, _ = a[2:].partition("=")
            yield "long", name
            if name in VALUE_LONG and not eq and not (sub == "merge" and name == "squash"):  # у merge --squash без значения
                i += 1
        elif a.startswith("-") and len(a) > 1:
            for j, ch in enumerate(a[1:]):
                yield "short", ch
                if ch in VALUE_SHORT.get(sub, ""):
                    if j == len(a) - 2:
                        i += 1  # значение — следующий токен; иначе оно приклеено к кластеру
                    break
        else:
            yield "pos", a
        i += 1


def violations(calls):
    found = []
    for c in calls:
        sub, args = c["sub"], c["args"]
        for item in c["cfg"]:
            key, _, value = item.partition("=")
            if key.lower() == "core.hookspath" and value != HOOKS_OK:
                found.append("-c core.hooksPath подменяет git-хуки")
        for key, value in c["env"].items():
            if re.fullmatch(r"GIT_CONFIG_KEY_\d+", key) and value.lower() == "core.hookspath":
                found.append("GIT_CONFIG_KEY_n=core.hooksPath подменяет git-хуки")
        if sub == "config" and any(a.lower() == "core.hookspath" for a in args):
            plain = [a for a in args if not a.startswith("-") and a.lower() != "core.hookspath"]
            word = plain[0] if plain and plain[0] in ("get", "list", "set", "unset") else None
            if word:
                plain = plain[1:]
            reads = word in ("get", "list") or any(a in ("--get", "--get-all", "--get-regexp", "--list", "-l") for a in args)
            writes = word == "unset" or any(a.startswith("--unset") for a in args) or (plain and plain[0] != HOOKS_OK)
            if not reads and writes:
                found.append("git config core.hooksPath меняет git-хуки")
        if sub in NOVERIFY_SUBS:
            for kind, value in walk(sub, args):
                if (kind == "long" and value == BYPASS_LONG) or (kind == "short" and value == "n" and sub == "commit"):
                    found.append("git %s с флагом обхода проверок" % sub)
                    break
    return found


def commit_mode(calls):
    """`dirty`, если на момент хука индекс ещё не равен будущему коммиту."""
    for c in calls:
        if c["sub"] in DIRTYING_SUBS:
            return "dirty"
        if c["sub"] == "commit":
            for kind, value in walk("commit", c["args"]):
                if kind == "pos" or (kind == "short" and value in "aio") or (kind == "long" and value in ("all", "include", "only")):
                    return "dirty"
    return "staged"


# ---------------------------------------------------------------- проверка дерева

def run_git(*args):
    """Байты stdout. Пути могут быть не-UTF8, поэтому text=True не используем."""
    return subprocess.run(["git", *args], capture_output=True).stdout


def git(*args):
    return run_git(*args).decode("utf-8", "surrogateescape")


def staged():
    """[(статус, путь)]; переименование даёт две записи (D старого, A нового)."""
    out = git("diff", "--cached", "--name-status", "-z", "--no-renames").split("\0")
    return [(out[i], out[i + 1]) for i in range(0, len(out) - 1, 2)]


def dirty():
    """Всё, что может попасть в коммит: staged + изменённое tracked + untracked не-ignored."""
    out = git("status", "--porcelain", "-z", "-uall").split("\0")
    result, i = [], 0
    while i < len(out) and out[i]:
        xy, path = out[i][:2], out[i][3:]
        i += 1
        if "R" in xy or "C" in xy:
            result.append(("D", out[i]) if "R" in xy else ("M", out[i]))
            i += 1
        result.append(("D" if "D" in xy else "A" if xy == "??" else "M", path))
    return result


def summary_problem(text):
    lines = text.split("\n")
    head = next((i for i, l in enumerate(lines[:30]) if l.strip() == "## Резюме"), None)
    if head is None:
        return "нет «## Резюме» в первых 30 строках"
    body = []
    for l in lines[head + 1:]:
        if l.startswith("## "):
            break
        body.append(l)
    while body and not body[-1].strip():
        body.pop()
    if len(body) > 15:
        return "Резюме %d строк (максимум 15)" % len(body)
    return None


START_LIMITS = {"CLAUDE.md": 36 * 1024}  # E13 (байт)


def start_limit_problem(path, blob):
    """E13: CLAUDE.md ≤ 36 КБ (читается в начале каждой сессии). None, если в пределах."""
    limit = START_LIMITS[path]
    if len(blob) > limit:
        return "%d байт > %d: сократи, детали вынеси в .claude/reference/ или в планы" % (len(blob), limit)
    return None


def check_tree(branch, mode="staged", entries=None, rev=None):
    """branch=None — E2 не проверяется (pre-push: код в main приходит мержем, E2 — свойство коммита).
    entries/rev — диапазон pre-push: [(статус, путь)] и коммит, из которого читаются тела планов."""
    conf = paths.load()
    errors, warns = [], []
    plan_ok = branch is None or bool(re.match(r"feature/PLAN-\d+", branch)) or branch.startswith("hotfix/")
    items = entries if entries is not None else dirty() if mode == "dirty" else staged()
    for status, path in items:
        kind = paths.classify(path, conf)
        if kind == "unknown" and status != "D":  # удаление старого мусора не блокируем
            errors.append("%s: корневой элемент не классифицирован — добавь строку в .claude/hooks/paths.conf (fail-closed)" % path)
        elif kind == "code" and not plan_ok:
            errors.append("%s: код правится только на feature/PLAN-<N>-* или hotfix/*, а ветка '%s' (E2; токен RM-N права на код не даёт)" % (path, branch))
        parts = path.split("/")
        if status != "D" and parts[0] == "planning" and len(parts) >= 2 and not paths.planning_root_ok(path, conf):
            errors.append("%s: в корне planning/ допустимы только служебные файлы и каталоги plans/ roadmap/ hotfixes/ (E9)" % path)
        if status != "D" and path in START_LIMITS:  # E13: стартовый набор в бюджете
            blob = Path(path).read_bytes() if mode == "dirty" and Path(path).is_file() else run_git("show", (rev or "") + ":" + path)
            over = start_limit_problem(path, blob)
            if over:
                errors.append("%s: %s (E13)" % (path, over))
        m = re.fullmatch(r"planning/plans/PLAN-(\d+)(?:\.\d+)*-[^/]+\.md", path)
        if status == "D" or not m:
            continue
        number = int(m.group(1))
        if mode == "dirty" and Path(path).is_file():
            blob = Path(path).read_bytes()
        else:
            blob = run_git("show", (rev or "") + ":" + path)
        text = blob.decode("utf-8", "replace")
        if number >= NEW_PLAN_FROM:
            problem = summary_problem(text)
            if problem:
                errors.append("%s: %s (E7)" % (path, problem))
        waiver = "<!-- size-waiver:" in "\n".join(text.split("\n")[:30])
        if len(blob) > HARD_BYTES and number >= NEW_PLAN_FROM and not waiver:
            errors.append("%s: %d КБ > 80 КБ; раздели план или добавь `<!-- size-waiver: причина -->` в первые 30 строк (E8)" % (path, len(blob) // 1024))
        elif len(blob) > WARN_BYTES:
            warns.append("%s: %d КБ (порог предупреждения 40 КБ, E8)" % (path, len(blob) // 1024))
    if branch is not None and entries is None:
        # E10/E11: новый RM и закрытие плана — только по слову владельца (маркер читаем, не расходуем)
        def read_new(path):
            if mode == "dirty":
                return Path(path).read_text(encoding="utf-8", errors="replace") if Path(path).is_file() else ""
            return git("show", ":" + path)
        errors += owner_ok.check_commit(owner_ok.root_dir(), branch, items, read_new)
    for w in warns:
        print("Предупреждение: " + w, file=sys.stderr)
    for e in errors:
        print(e, file=sys.stderr)
    return 2 if errors else 0


def in_progress():
    """Идёт слияние / cherry-pick / revert / rebase — по состоянию git, не по тексту сообщения.
    В этих состояниях коммит собирает git, и E2/E3 (свойства ручного коммита) не применяются."""
    for name in ("MERGE_HEAD", "CHERRY_PICK_HEAD", "REVERT_HEAD", "rebase-merge", "rebase-apply"):
        if Path(git("rev-parse", "--git-path", name).strip()).exists():
            return True
    return False


def is_amend(ppid):
    """git commit --amend: родитель хука — процесс git; по argv видно флаг (ps есть на macOS и Linux)."""
    try:
        args = subprocess.run(["ps", "-o", "args=", "-p", str(ppid)], capture_output=True, text=True).stdout
    except OSError:
        return False
    return "--amend" in args.split()


def amended_paths():
    """Файлы коммита, который переписывает --amend, относительно его родителя."""
    out = git("diff-tree", "-r", "--root", "--name-only", "--no-renames", "-z", "HEAD", "--no-commit-id").split("\0")
    return [p for p in out if p]


def check_message(branch, msgfile, ppid=None):
    """E3 (git-хук commit-msg): токен в сообщении КАЖДОГО коммита. exit 2 + причина в stderr."""
    text = Path(msgfile).read_text(encoding="utf-8", errors="replace")
    msg = "\n".join(l for l in text.split("\n") if not l.startswith("#")).strip()
    # «Merge …» освобождён только по состоянию git (in_progress) или по строгому формату сообщения самого git;
    # произвольное «Merge arbitrary change» обычным коммитом токен обязан нести.
    if re.match(r"(Revert |fixup! |squash! |Merge (branch|remote-tracking branch|pull request|tag) )", msg) or in_progress():
        return 0
    names = [p for _, p in staged()]
    if ppid and is_amend(ppid):
        names = sorted(set(names) | set(amended_paths()))
    roadmap_only = bool(names) and all(p == "planning/ROADMAP.md" or p.startswith("planning/roadmap/") for p in names)

    def has(pattern):
        # граница идентификатора: PLAN-145 не матчится в PLAN-1450 и PLAN-145.1, но «PLAN-145.» (точка фразы) проходит
        return re.search(r"(?<![\w-])" + pattern + r"(?!\d|\.\d)", msg) is not None

    plan = re.match(r"feature/PLAN-(\d+(?:\.\d+)*)(?:-|$)", branch)
    if plan:
        need, hint = "PLAN-" + plan.group(1), "PLAN-%s (номер плана ветки)" % plan.group(1)
        ok = has(re.escape(need))
    elif branch.startswith("hotfix/"):
        # ponytail: после этапа 4 — registry.sh show HF-<M> (существование записи); пока только форма токена
        need, hint = "HF-<M>", "HF-<число> хотфикса"
        ok = has(r"HF-\d+")
    else:
        return 0  # main и прочие ветки: код и так блокирует E2 (pre-commit / commit-gate)
    if ok or (roadmap_only and has(r"RM-\d+")):
        return 0
    print("Сообщение коммита должно содержать %s (E3, ветка '%s')." % (hint, branch), file=sys.stderr)
    if roadmap_only:
        print("Коммит только по planning/roadmap/** может нести RM-<N> вместо этого.", file=sys.stderr)
    else:
        print("RM-<N> годится лишь для коммита, где staged только planning/roadmap/** или ROADMAP.md.", file=sys.stderr)
    return 2


def base_pwd():
    return os.environ.get("GUARD_ORIG_PWD") or os.getcwd()


def main():
    action = sys.argv[1]
    if action == "staged":
        # --hook (git-хук pre-commit): при слиянии/cherry-pick/revert/rebase E2 не применяется, структура — да
        branch = None if "--hook" in sys.argv and in_progress() else sys.argv[2]
        return check_tree(branch, sys.argv[3] if len(sys.argv) > 3 and sys.argv[3] != "--hook" else "staged")
    if action == "msg":
        return check_message(sys.argv[2], sys.argv[3], sys.argv[4] if len(sys.argv) > 4 else None)
    if action == "push-range":  # BASE HEAD — структурные проверки диапазона (pre-push), без E2
        out = git("diff", "--name-status", "-z", "--no-renames", sys.argv[2], sys.argv[3]).split("\0")
        return check_tree(None, entries=[(out[i], out[i + 1]) for i in range(0, len(out) - 1, 2)], rev=sys.argv[3])
    cmd = sys.stdin.read()
    try:
        calls, parsed = parse(cmd, base_pwd()), True
    except ValueError:
        calls, parsed = [], False
    if action == "noverify":
        if parsed:
            bad = violations(calls)
        else:  # кавычки не сошлись — консервативный regex (тела heredoc — данные, из проверки исключены)
            bad = ["команда не разобрана"] if re.search(r"\bgit\b[^\n]*\b(commit|push)\b[^\n]*(--no-verify|\s-n\b)", strip_heredocs(cmd)) else []
        if bad:
            print("Обход хуков запрещён (E16): %s. Обход — только владелец в своём терминале." % "; ".join(sorted(set(bad))), file=sys.stderr)
            return 2
        return 0
    if action == "inspect":
        # строки: корень репозитория коммита, режим, «есть ли вызов git commit» (1/0)
        commits = [c for c in calls if c["sub"] == "commit"]
        if parsed:
            has_commit = bool(commits)
        else:
            has_commit = bool(re.search(r"\bgit\b[^\n]*\bcommit\b", strip_heredocs(cmd)))
        wd = (commits[0]["worktree"] or commits[0]["gitdir"] or commits[0]["wd"]) if commits else base_pwd()
        # `cd "$(pwd)"` парсер не раскрывает: такой каталог не найден, база — cwd команды (HF-174)
        top = (run_git("-C", wd, "rev-parse", "--show-toplevel") or run_git("-C", base_pwd(), "rev-parse", "--show-toplevel")).decode("utf-8", "surrogateescape").strip()
        print(top)
        print(commit_mode(calls) if commits else "staged")
        print(1 if has_commit else 0)
        return 0
    return 2


if __name__ == "__main__":
    sys.stderr.reconfigure(errors="backslashreplace")
    try:
        sys.exit(main())
    except Exception as exc:  # noqa: BLE001
        # fail-open: сбой самого хука (нет git, битый ввод) не должен парализовать работу;
        # авторитетную проверку делает git-хук pre-commit (PLAN-145, этап 2b).
        print("hook internal error: %s: %s" % (type(exc).__name__, exc), file=sys.stderr)
        sys.exit(0)
