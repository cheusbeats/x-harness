#!/usr/bin/env python3
"""strict-checks.py — строгий слой планировочного профиля (SPEC §9).

Режимы (exit 2 — блокировка события-хука; exit 1 — git-хук/merge-ready):
  branch-guard-file PATH   PreToolUse Edit|Write|NotebookEdit: E2 (ветки) и E18 (защищённые пути)
  commit                   PreToolUse Bash: E16 (обходы), ветка коммита, ранние planning-checks + registry check
  merge                    PreToolUse Bash: мерж в MAIN_BRANCH (ветка, токены всех коммитов, реестры,
                           GATE_MERGE, маркер владельца merge)
  push                     PreToolUse Bash: защита main при push, без сети
  push-hook                stdin git-хука pre-push: non-fast-forward, удаление main, push main из не-main,
                           прямые (не-мерж) коммиты впереди remote/main
  --preflight BRANCH       merge-ready: сухой прогон merge-gate (READY / NOT READY + причины)

STRICT=off — все режимы молча выходят 0. Внутренняя ошибка разбора/хука — fail-open (0)
с сообщением в stderr: владельца не парализует баг хука, авторитетная проверка — git-хуки.
"""
import hashlib
import importlib.util
import io
import json
import os
import re
import shlex
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
PLANNING_CHECKS = HERE / "planning-checks.py"
BT = chr(96)


def load_planning_checks():
    spec = importlib.util.spec_from_file_location("planning_checks", str(PLANNING_CHECKS))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


try:
    pc = load_planning_checks()
except Exception as exc:  # noqa: BLE001
    pc = None
    _PC_ERROR = "%s: %s" % (type(exc).__name__, exc)


# ---------------------------------------------------------------- git

def git_in(wd, *args):
    try:
        return subprocess.run(["git", "-C", str(wd), *args], capture_output=True)
    except OSError:
        return subprocess.CompletedProcess(["git"], 1, b"", b"")


def git_text_in(wd, *args):
    return git_in(wd, *args).stdout.decode("utf-8", "replace").strip()


def repo_in(wd):
    return git_text_in(wd, "rev-parse", "--show-toplevel")


def branch_in(wd):
    full = git_text_in(wd, "symbolic-ref", "--quiet", "HEAD")
    if full.startswith("refs/heads/"):
        return full[len("refs/heads/"):]
    if full:
        return full
    return git_text_in(wd, "rev-parse", "--abbrev-ref", "HEAD")


def in_progress_in(wd):
    for name in ("MERGE_HEAD", "CHERRY_PICK_HEAD", "REVERT_HEAD", "rebase-merge", "rebase-apply"):
        path = git_text_in(wd, "rev-parse", "--git-path", name)
        if not path:
            continue
        full = Path(path) if os.path.isabs(path) else Path(wd) / path
        if full.exists():
            return True
    return False


def zero(sha):
    return re.fullmatch(r"0+", sha or "") is not None


def is_ancestor(wd, ancestor, descendant):
    return git_in(wd, "merge-base", "--is-ancestor", ancestor, descendant).returncode == 0


def rel_to_root(path, root):
    """Путь относительно корня проекта (учитывает симлинки). None — вне корня."""
    try:
        real_root = os.path.realpath(root)
        if os.path.exists(path):
            target = os.path.realpath(path)
        else:
            target = os.path.join(os.path.realpath(os.path.dirname(os.path.abspath(path))),
                                  os.path.basename(path))
    except OSError:
        return None
    if target == real_root:
        return "."
    if target.startswith(real_root + os.sep):
        return os.path.relpath(target, real_root)
    return None


def project_conf():
    root = pc.repo_root()
    return root, pc.load_conf(root)


# ---------------------------------------------------------------- разбор команды
# Эвристический argv-разбор: команда, а не regex по сырой строке. Тела heredoc —
# данные; кавычки, цепочки ; & |, вложенные bash -c и подстановки разбираются.

NOVERIFY_SUBS = {"commit", "push", "merge", "am", "rebase"}
HOOKS_OK = ".githooks"
BYPASS_LONG = "no-verify"
VALUE_LONG = {"message", "file", "template", "author", "date", "cleanup", "trailer", "fixup", "squash",
              "reuse-message", "reedit-message", "repo", "receive-pack", "exec", "push-option",
              "strategy", "strategy-option"}
VALUE_SHORT = {"commit": "mFtCc", "push": "o", "merge": "mFsX", "rebase": "sXxC", "am": "", "pull": "sX",
               "update-ref": "m"}
WRAPPERS = {"env": "uCS", "command": "", "exec": "a", "time": "", "nohup": "", "builtin": "", "nice": "n",
            "sudo": "ugCDhpRrt", "xargs": "IJLnPsEd", "timeout": "ks", "setsid": "", "ionice": "cnp"}
DATA_HEADS = {"echo", "printf", "grep", "egrep", "fgrep", "rg", "cat", "sed", "awk", "head", "tail", "less",
              "more", "ls", "wc", "man", "test", "[", "diff", "type", "which", "whereis"}
REDIR_OP = re.compile(r"&>>?|\d*(?:<<<|<<-?|<>|>>|>&|>\||<&|>|<)")


def strip_heredocs(cmd):
    """Тела heredoc — данные, не команды."""
    out, word = [], None
    for line in cmd.split("\n"):
        if word is not None:
            if line.strip() == word:
                word = None
            continue
        out.append(line)
        match = re.search(r"<<-?\s*['\"]?([A-Za-z0-9_-]+)['\"]?", line)
        if match:
            word = match.group(1)
    return "\n".join(out)


def newlines_to_semicolons(cmd):
    out, quote, escaped = [], None, False
    for ch in cmd:
        if escaped:
            escaped = False
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


def strip_redirections(cmd):
    """Перенаправления и их цели — не аргументы команды."""
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
        if ch in "\"'":
            quote = ch
            out.append(ch)
            i += 1
            continue
        match = REDIR_OP.match(cmd, i) if ch in "<>&0123456789" else None
        word_start = i == 0 or cmd[i - 1].isspace() or cmd[i - 1] in ";&|()"
        if match and match.group(0)[0].isdigit() and not word_start:
            match = None
        if match and cmd.startswith("(", match.end()):
            match = None
        if not match:
            out.append(ch)
            i += 1
            continue
        i = match.end()
        while i < n and cmd[i] in " \t":
            i += 1
        depth, tq = 0, None
        while i < n:
            cur = cmd[i]
            if cur == "\\" and tq != "'":
                i += 2
                continue
            if tq:
                tq = None if cur == tq else tq
            elif cur in "\"'":
                tq = cur
            elif cmd.startswith("$(", i):
                depth += 1
                i += 1
            elif depth and cur == ")":
                depth -= 1
            elif not depth and (cur.isspace() or cur in ";&|<>()"):
                break
            i += 1
        out.append(" ")
    return "".join(out)


def substitutions(text):
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
        if single:
            i += 1
        elif text.startswith("$(", i):
            depth, j = 1, i + 2
            while j < len(text) and depth:
                depth += (text[j] == "(") - (text[j] == ")")
                j += 1
            found.append(text[i + 2:j - 1])
            found += substitutions(text[i + 2:j - 1])
            i = j
        elif text[i] == BT:
            j = text.find(BT, i + 1)
            if j < 0:
                break
            found.append(text[i + 1:j])
            i = j + 1
        else:
            i += 1
    return found


def strip_wrappers(argv, env):
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
                argv = argv[1:]
        else:
            break
    return argv


def git_call(argv, wd, env):
    call = {"wd": wd, "cfg": [], "env": env, "opts": [], "gitdir": None, "worktree": None}
    work_tree = git_dir = None
    i = 1
    while i < len(argv) and argv[i].startswith("-"):
        arg = argv[i]
        if arg == "-C" and i + 1 < len(argv):
            call["wd"] = join_dir(call["wd"], argv[i + 1])
            i += 2
        elif arg.startswith("-C") and len(arg) > 2:
            call["wd"] = join_dir(call["wd"], arg[2:])
            i += 1
        elif arg == "-c" and i + 1 < len(argv):
            call["cfg"].append(argv[i + 1])
            i += 2
        elif arg.startswith("-c") and len(arg) > 2:
            call["cfg"].append(arg[2:])
            i += 1
        elif arg in ("--git-dir", "--work-tree", "--namespace") and i + 1 < len(argv):
            if arg == "--work-tree":
                work_tree = argv[i + 1]
            elif arg == "--git-dir":
                git_dir = argv[i + 1]
            i += 2
        elif arg.startswith(("--git-dir=", "--work-tree=")):
            name, _, value = arg.partition("=")
            if name == "--work-tree":
                work_tree = value
            else:
                git_dir = value
            i += 1
        else:
            call["opts"].append(arg)
            i += 1
    git_dir, work_tree = git_dir or env.get("GIT_DIR"), work_tree or env.get("GIT_WORK_TREE")
    call["gitdir"] = join_dir(call["wd"], git_dir) if git_dir else None
    call["worktree"] = join_dir(call["wd"], work_tree) if work_tree else None
    call["sub"] = argv[i] if i < len(argv) else ""
    call["args"] = argv[i + 1:]
    return call


def parse(cmd, wd):
    lex = shlex.shlex(strip_redirections(newlines_to_semicolons(strip_heredocs(cmd))),
                      posix=True, punctuation_chars=True)
    lex.whitespace_split = True
    segments, cur = [], []
    for token in lex:
        if re.fullmatch(r"[;&|()<>]+", token):
            segments.append(cur)
            cur = []
        else:
            cur.append(token)
    segments.append(cur)

    calls = []

    def nested(text):
        try:
            return parse(text, wd)
        except ValueError:
            if re.search(r"\bgit\b", text):
                raise
            return []

    for argv in segments:
        env = {}
        argv = strip_wrappers(argv, env)
        if not argv:
            continue
        head = os.path.basename(argv[0])
        if head == "cd" and len(argv) > 1:
            wd = join_dir(wd, argv[1])
        elif head in ("bash", "sh", "zsh"):
            for index, token in enumerate(argv[1:-1], 1):
                if re.fullmatch(r"-[a-z]*c[a-z]*", token):
                    calls += nested(argv[index + 1])
                    break
        elif head == "eval":
            calls += nested(" ".join(argv[1:]))
        elif head == "git":
            calls.append(git_call(argv, wd, env))
        elif head not in DATA_HEADS:
            names = [os.path.basename(token) for token in argv]
            if "git" in names[1:]:
                calls.append(git_call(argv[names.index("git", 1):], wd, env))
    for inner in substitutions(strip_heredocs(cmd)):
        for call in nested(inner):
            if not any((c["sub"], c["args"], c["wd"]) == (call["sub"], call["args"], call["wd"]) for c in calls):
                calls.append(call)
    return calls


def walk(sub, args):
    i = 0
    while i < len(args):
        arg = args[i]
        if arg == "--":
            for rest in args[i + 1:]:
                yield "pos", rest
            return
        if arg.startswith("--"):
            name, eq, _ = arg[2:].partition("=")
            yield "long", name
            if name in VALUE_LONG and not eq and not (sub == "merge" and name == "squash"):
                i += 1
        elif arg.startswith("-") and len(arg) > 1:
            for index, ch in enumerate(arg[1:]):
                yield "short", ch
                if ch in VALUE_SHORT.get(sub, ""):
                    if index == len(arg) - 2:
                        i += 1
                    break
        else:
            yield "pos", arg
        i += 1


def violations(calls):
    """E16: обход git-хуков и подмена core.hooksPath."""
    found = []
    for call in calls:
        sub, args = call["sub"], call["args"]
        for item in call["cfg"]:
            key, _, value = item.partition("=")
            if key.lower() == "core.hookspath" and value != HOOKS_OK:
                found.append("-c core.hooksPath подменяет git-хуки")
        for key, value in call["env"].items():
            if re.fullmatch(r"GIT_CONFIG_KEY_\d+", key) and value.lower() == "core.hookspath":
                found.append("GIT_CONFIG_KEY_n=core.hooksPath подменяет git-хуки")
        if sub == "config" and any(arg.lower() == "core.hookspath" for arg in args):
            plain = [arg for arg in args if not arg.startswith("-") and arg.lower() != "core.hookspath"]
            word = plain[0] if plain and plain[0] in ("get", "list", "set", "unset") else None
            if word:
                plain = plain[1:]
            reads = word in ("get", "list") or any(
                arg in ("--get", "--get-all", "--get-regexp", "--list", "-l") for arg in args)
            writes = word == "unset" or any(arg.startswith("--unset") for arg in args) or (
                plain and plain[0] != HOOKS_OK)
            if not reads and writes:
                found.append("git config core.hooksPath меняет git-хуки")
        if sub in NOVERIFY_SUBS:
            for kind, value in walk(sub, args):
                if (kind == "long" and value == BYPASS_LONG) or (
                        kind == "short" and value == "n" and sub == "commit"):
                    found.append("git %s с флагом обхода проверок" % sub)
                    break
    return sorted(set(found))


def base_pwd():
    return os.environ.get("GUARD_ORIG_PWD") or os.getcwd()


def flags(call):
    short, long_, pos = set(), set(), []
    for kind, value in walk(call["sub"], call["args"]):
        if kind == "short":
            short.add(value)
        elif kind == "long":
            long_.add(value)
        else:
            pos.append(value)
    return short, long_, pos


# ---------------------------------------------------------------- вывод

def deny(errors):
    for error in errors:
        print(error, file=sys.stderr)
    print("strict-checks: действие заблокировано строгим слоем планировочного профиля (SPEC §9).", file=sys.stderr)
    return 2


def fail_open(why):
    print("strict-checks: %s — проверка пропущена (fail-open)." % why, file=sys.stderr)
    return 0


# ---------------------------------------------------------------- E3 на ветке / merge

MOVING_REFS = {"HEAD", "FETCH_HEAD", "ORIG_HEAD", "MERGE_HEAD", "CHERRY_PICK_HEAD"}


def conventional_branch(name, conf):
    return bool(re.match(conf.get("FEATURE_BRANCH_RE", r"^feature/PLAN-([0-9]+(\.[0-9]+)*)(?:-|$)"), name)) \
        or bool(re.match(conf.get("HOTFIX_BRANCH_RE", r"^hotfix/"), name))


def has_token(text, pattern):
    return re.search(r"(?<![\w-])" + pattern + r"(?!\d|\.\d)", text) is not None


def branch_name_for_ref(target, ref, sha, conf):
    candidate = re.sub(r"^origin/", "", ref)
    if conventional_branch(candidate, conf):
        return candidate
    names = set()
    out = git_text_in(target, "for-each-ref", "--points-at", sha, "--format=%(refname)", "refs/heads", "refs/remotes")
    for line in out.splitlines():
        bare = re.sub(r"^refs/(heads|remotes/[^/]+)/", "", line.strip())
        if conventional_branch(bare, conf):
            names.add(bare)
    if len(names) == 1:
        return names.pop()
    return None


def token_errors(target, sha, name, conf):
    """E3 на ветке: каждый не-мерж коммит ветки несёт свой токен (roadmap-only — RM-N)."""
    feature = re.match(conf.get("FEATURE_BRANCH_RE", r"^feature/PLAN-([0-9]+(\.[0-9]+)*)(?:-|$)"), name)
    if feature:
        pattern = r"PLAN-" + re.escape(feature.group(1))
        hint = "PLAN-" + feature.group(1)
    elif re.match(conf.get("HOTFIX_BRANCH_RE", r"^hotfix/"), name):
        pattern, hint = r"HF-\d+", "HF-<число>"
    else:
        return []
    main = conf.get("MAIN_BRANCH", "main")
    base = git_text_in(target, "merge-base", "refs/heads/" + main, sha)
    if not base:
        return ["Мерж '%s' заблокирован: нет общей базы с '%s' (fail-closed)." % (name, main)]
    commits = git_text_in(target, "rev-list", "--no-merges", "%s..%s" % (base, sha)).split()
    errors = []
    for commit in commits:
        message = git_text_in(target, "log", "-1", "--format=%B", commit)
        if has_token(message, pattern):
            continue
        files = [f for f in git_text_in(target, "show", "--name-only", "--format=", commit).splitlines() if f]
        roadmap_only = bool(files) and all(
            f == "planning/ROADMAP.md" or f.startswith("planning/roadmap/") for f in files)
        if roadmap_only and has_token(message, r"RM-\d+"):
            continue
        subject = message.strip().splitlines()[0] if message.strip() else "(без сообщения)"
        errors.append("Коммит %s ветки '%s' не несёт токен %s (E3 на ветке): %s"
                      % (commit[:7], name, hint, subject[:80]))
    return errors


def merge_registry_errors(target, sha, main):
    """Реестры на дереве результата слияния main + sha (E17), без сети и без мержа."""
    registry = Path(target) / ".claude/scripts/registry.sh"
    if not registry.is_file():
        return ["registry.sh отсутствует: реестры слияния не проверены (fail-closed)."]
    res = git_in(target, "merge-tree", "--write-tree", "--no-messages", "refs/heads/" + main, sha)
    tree = res.stdout.decode("utf-8", "replace").splitlines()[0].strip() if res.stdout.strip() else ""
    if res.returncode != 0 or not re.fullmatch(r"[0-9a-f]{40,64}", tree or ""):
        return ["Реестры на дереве слияния не проверены: git merge-tree не построил бесконфликтное дерево (fail-closed)."]
    packed = git_in(target, "archive", "--format=tar", tree, "planning")
    if packed.returncode != 0:
        return ["Реестры на дереве слияния не проверены: git archive planning завершился ошибкой (fail-closed)."]
    with tempfile.TemporaryDirectory() as tmp:
        try:
            with tarfile.open(fileobj=io.BytesIO(packed.stdout)) as tar:
                for member in tar.getmembers():
                    if member.isfile() and not member.name.startswith(("/", "..")):
                        tar.extract(member, tmp, **({"filter": "data"} if hasattr(tarfile, "data_filter") else {}))
        except (tarfile.TarError, OSError) as exc:
            return ["Реестры на дереве слияния не проверены: распаковка planning/ не удалась (%s)." % exc]
        out = subprocess.run(["bash", str(registry), "check", "--registry", "all", "--root", tmp],
                             capture_output=True, text=True)
    if out.returncode == 0:
        return []
    if out.returncode != 1:
        return ["registry.sh на дереве слияния вернул %d — мерж блокирован (fail-closed)." % out.returncode]
    lines = [line for line in out.stdout.splitlines() if " — " in line and "пропуск" not in line][:8]
    return ["Реестры RM/PLAN/HF на дереве слияния нарушены: " + "; ".join(lines)]


def gate_errors(target, name, sha, conf):
    """GATE_MERGE и отметка полного гейта на вершине ветки обязательны."""
    if not conf.get("GATE_MERGE", "").strip():
        return ["GATE_MERGE не задан: настроить команду проверки и запустить quality-gate.sh --merge"]
    key = name.replace("/", "_")
    stamp = Path(target) / ".claude/state/gates" / (key + ".merge-passed")
    try:
        first = stamp.read_text(encoding="utf-8", errors="replace").splitlines()[:2]
    except OSError:
        first = []
    command_hash = hashlib.sha256(conf["GATE_MERGE"].encode()).hexdigest()
    if first != [sha, command_hash]:
        return ["Мерж '%s': нет зелёного GATE_MERGE на вершине %s. На ветке (чистое дерево) запусти: "
                ".claude/scripts/quality-gate.sh --merge" % (name, sha[:7])]
    return []


def merge_errors(call, target, cur, conf):
    """Мерж именно в MAIN_BRANCH: ветка, токены, реестры, GATE_MERGE, маркер merge."""
    main = conf.get("MAIN_BRANCH", "main")
    if cur != main:
        return []  # мерж не в main — гейт не требуется
    short, long_, pos = flags(call)
    if long_ & {"abort", "continue", "quit", "skip"}:
        return []
    refs = list(dict.fromkeys(pos))
    if not refs:
        return ["Мерж в '%s' без ссылки заблокирован: укажи ветку явно, git merge feature/PLAN-N-slug." % main]
    if len(refs) > 1:
        return ["Мерж нескольких ссылок (octopus) в '%s' заблокирован: мержи по одной ветке." % main]
    ref = refs[0]
    if ref.upper() in MOVING_REFS:
        return ["Мерж '%s' в '%s' заблокирован: подвижная ссылка не годится, укажи ветку или SHA." % (ref, main)]
    sha = git_text_in(target, "rev-parse", "--verify", "--quiet", ref + "^{commit}")
    if not sha:
        return ["Мерж '%s' в '%s' заблокирован: ссылка не резолвится в коммит (fail-closed)." % (ref, main)]
    name = branch_name_for_ref(target, ref, sha, conf)
    if not name:
        return ["Мерж в '%s' разрешён только из feature/PLAN-N-* или hotfix/*: '%s' (вершина %s) не такая ветка."
                % (main, ref, sha[:7])]
    errors = token_errors(target, sha, name, conf)
    errors += merge_registry_errors(target, sha, main)
    errors += gate_errors(target, name, sha, conf)
    problem = pc.marker_problem(target, conf, "merge", name, name, sha=sha)
    if problem:
        errors.append("Мерж '%s' в '%s' заблокирован: %s" % (name, main, problem))
    return errors


def protected_main_errors(call, cur, conf):
    """Агент не двигает main в обход мержа (cherry-pick/rebase/reset/update-ref/branch -f/…)."""
    main = conf.get("MAIN_BRANCH", "main")
    if cur != main:
        return []
    sub = call["sub"]
    short, long_, pos = flags(call)
    bad = None
    if sub in ("cherry-pick", "rebase"):
        bad = "git %s на '%s'" % (sub, main)
    elif sub == "reset" and (short & {"hard", "merge", "keep"} or long_ & {"hard", "merge", "keep"}):
        bad = "git reset с потерей истории на '%s'" % main
    elif sub == "update-ref" and ("stdin" in long_ or (pos[:1] and pos[0] in ("refs/heads/" + main, main))
                                  or pos[:1] == ["HEAD"]):
        bad = "git update-ref (main/HEAD)"
    elif sub == "branch" and (short & {"f", "M"} or "force" in long_) and pos[:1] == [main]:
        bad = "git branch -f " + main
    elif sub in ("checkout", "switch") and (short & {"B", "C"} or "force-create" in long_) and pos[:1] == [main]:
        bad = "пересоздание '%s'" % main
    elif sub == "symbolic-ref" and len(pos) >= 2 and (cur == main or pos[1].endswith(main)):
        bad = "git symbolic-ref (смена HEAD)"
    return ["Заблокировано: %s — '%s' меняется только мержем по слову владельца (SPEC §9)." % (bad, main)] if bad else []


# ---------------------------------------------------------------- режим commit

def touches_planning(target):
    staged = git_text_in(target, "diff", "--cached", "--name-only").splitlines()
    dirty = [line[3:] for line in git_text_in(target, "status", "--porcelain").splitlines() if len(line) > 3]
    return any(path.startswith("planning/") for path in staged + dirty)


def mode_commit():
    root, conf = project_conf()
    if not pc.is_strict(conf):
        return 0
    command = sys.stdin.read()
    try:
        calls = parse(command, base_pwd())
    except ValueError:
        return fail_open("команда не разобрана")
    bad = violations(calls)
    if bad:
        return deny(["Обход git-хуков запрещён (E16): %s." % "; ".join(bad),
                     "Обход — только владелец в своём терминале."])
    commits = [call for call in calls if call["sub"] == "commit"]
    if not commits:
        return 0
    call = commits[0]
    workdir = call["worktree"] or call["gitdir"] or call["wd"]
    if not workdir or not os.path.isdir(workdir):
        return fail_open("каталог коммита не найден")
    target = repo_in(workdir)
    if not target:
        return fail_open("git-репозиторий коммита не определён")
    tconf = pc.load_conf(target)
    if not pc.is_strict(tconf):
        return 0
    if in_progress_in(target):
        return 0  # merge/rebase/cherry-pick собирает git
    branch = branch_in(target)
    main = tconf.get("MAIN_BRANCH", "main")
    errors = []
    if not tconf.get("GATE_FAST", "").strip():
        errors.append("GATE_FAST не задан: настроить проверку перед коммитом (fail-closed).")
    if branch == main:
        errors.append("Коммит в ветку '%s' запрещён (E2): в main попадают только мержи по слову владельца." % main)
        errors.append("Правки сохранятся: git checkout -b feature/PLAN-N-slug (или hotfix/slug) — и коммить туда.")
    elif not conventional_branch(branch, tconf):
        errors.append("Коммит в ветку '%s' заблокирован: допустимы только feature/PLAN-N-* и hotfix/* (E2)." % branch)
        errors.append("Переименуй: git branch -m feature/PLAN-N-slug.")

    checks = Path(target) / ".claude/hooks/planning-checks.py"
    if checks.is_file():
        result = subprocess.run([sys.executable, str(checks), "staged", branch], cwd=target)
        if result.returncode == 2:
            errors.append("Ранняя проверка planning-checks.py не прошла (причины выше) — коммит заблокирован.")
    if touches_planning(target):
        registry = Path(target) / ".claude/scripts/registry.sh"
        if registry.is_file():
            out = subprocess.run(["bash", str(registry), "check", "--registry", "all"],
                                 cwd=target, capture_output=True, text=True)
            if out.returncode == 1:
                errors.append("registry.sh check нашёл нарушения реестров — коммит заблокирован:")
                errors += ["  " + line for line in out.stdout.splitlines()[:10]]
            elif out.returncode != 0:
                print("commit-gate: внутренняя ошибка registry.sh (код %d) — проверка реестров пропущена"
                      % out.returncode, file=sys.stderr)
    if errors:
        return deny(errors)
    return 0


# ---------------------------------------------------------------- режим merge

def mode_merge():
    root, conf = project_conf()
    if not pc.is_strict(conf):
        return 0
    try:
        calls = parse(sys.stdin.read(), base_pwd())
    except ValueError:
        return fail_open("команда не разобрана")
    errors = []
    for call in calls:
        if call["sub"] not in ("merge", "pull", "cherry-pick", "rebase", "reset", "update-ref",
                               "branch", "checkout", "switch", "symbolic-ref"):
            continue
        workdir = call["worktree"] or call["gitdir"] or call["wd"]
        if not workdir or not os.path.isdir(workdir):
            continue
        target = repo_in(workdir)
        if not target:
            continue
        tconf = pc.load_conf(target)
        if not pc.is_strict(tconf):
            continue
        cur = branch_in(target)
        main = tconf.get("MAIN_BRANCH", "main")
        errors += protected_main_errors(call, cur, tconf)
        if call["sub"] == "merge":
            errors += merge_errors(call, target, cur, tconf)
        elif call["sub"] == "pull" and cur == main:
            errors.append("git pull в '%s' заблокирован: это fetch+merge в обход merge-gate. "
                          "Используй git fetch и git merge <ветка>." % main)
    if errors:
        return deny(errors)
    return 0


# ---------------------------------------------------------------- режим push

PUSH_VALUE_FLAGS = {"--repo", "--receive-pack", "--exec", "-o", "--push-option", "--prefix", "-P"}


def push_args(call):
    flags, pos, repo_flag, i = [], [], False, 0
    args = call["args"]
    while i < len(args):
        arg = args[i]
        name = arg.split("=", 1)[0]
        if name == "--repo":
            repo_flag = True
        if name in PUSH_VALUE_FLAGS:
            i += 1 if "=" in arg else 2
            continue
        if arg.startswith("-"):
            flags.append(arg)
        else:
            pos.append(arg)
        i += 1
    return flags, pos, repo_flag


def dest_is_main(spec, main):
    dest = spec.split(":", 1)[1] if ":" in spec else spec
    dest = re.sub(r"^refs/heads/", "", dest)
    return dest == main


def push_remote(target, call, pos, repo_flag):
    if repo_flag:
        return None
    if pos:
        return pos[0]
    cur = branch_in(target)
    configured = git_text_in(target, "config", "branch.%s.remote" % cur)
    return configured or "origin"


def publish_errors(target, remote, main):
    if not remote or remote.startswith("-"):
        return ["git push: remote не задан или похож на опцию — публикацию '%s' не проверить, заблокировано." % main]
    remotes = git_text_in(target, "remote").split()
    if remote not in remotes:
        return ["git push: '%s' не именованный remote (git remote) — прямые коммиты в '%s' не проверить, "
                "заблокировано." % (remote, main)]
    tracking = "refs/remotes/%s/%s" % (remote, main)
    server = git_text_in(target, "rev-parse", "--verify", "--quiet", tracking)
    if not server:
        return ["git push в '%s': нет '%s' — сделай git fetch; без локальной точки публикацию не проверить."
                % (main, tracking)]
    local = "refs/heads/" + main
    if not git_text_in(target, "rev-parse", "--verify", "--quiet", local):
        return ["git push: локальной ветки '%s' нет." % main]
    if not is_ancestor(target, server, local):
        return ["git push в '%s': '%s' не предок локальной ветки — расхождение истории, публикация запрещена."
                % (main, tracking)]
    ahead = git_text_in(target, "rev-list", "--first-parent", "--no-merges", "%s..%s" % (server, local)).split()
    if ahead:
        return ["git push в '%s': впереди '%s' %d прямых (не-мерж) коммит(ов) — публикуй только влитые ветки."
                % (main, tracking, len(ahead))]
    return []


def push_errors(call):
    workdir = call["worktree"] or call["gitdir"] or call["wd"]
    if not workdir or not os.path.isdir(workdir):
        return []
    target = repo_in(workdir)
    if not target:
        return []
    conf = pc.load_conf(target)
    if not pc.is_strict(conf):
        return []
    main = conf.get("MAIN_BRANCH", "main")
    flags, pos, repo_flag = push_args(call)
    errors = []
    if "--all" in flags or "--mirror" in flags:
        errors.append("git push --all/--mirror может затронуть '%s' — заблокировано (SPEC §9)." % main)
    force = any(
        flag in ("--force", "--delete", "-f", "-d") or flag.startswith("--force-with-lease")
        or flag.startswith("--force-if-includes")
        or (re.fullmatch(r"-[A-Za-z]+", flag) and ("f" in flag or "d" in flag))
        for flag in flags)
    if force:
        errors.append("git push с force/delete запрещён (E19): история не переписывается; "
                      "force — только владелец в своём терминале.")
    cur = branch_in(target)
    remote = push_remote(target, call, pos, repo_flag)
    refspecs = [] if repo_flag else (pos[1:] if pos else [])
    if not refspecs:
        if "--tags" in flags:
            return errors
        if cur == main:
            errors += publish_errors(target, remote, main)
        return errors
    index = 0
    while index < len(refspecs):
        spec = refspecs[index]
        if spec == "tag":
            index += 2
            continue
        index += 1
        if "*" in spec:
            errors.append("git push: wildcard/matching refspec «%s» может затронуть '%s' — заблокировано." % (spec, main))
            continue
        if spec.startswith("+"):
            errors.append("git push: refspec «%s» с '+' — force запрещён (E19)." % spec)
            continue
        if spec.startswith(":"):
            if dest_is_main(spec[1:], main):
                errors.append("git push: удаление '%s' запрещено (E19)." % main)
            continue
        src, _, dst = spec.partition(":")
        dst = dst or src
        src_bare = re.sub(r"^refs/heads/", "", src)
        if dest_is_main(dst, main):
            if src_bare not in (main, "HEAD", "@") or (src_bare in ("HEAD", "@") and cur != main):
                errors.append("git push в '%s' из '%s' запрещён: в main публикуется только влитая ветка "
                              "(мерж-коммит) из main." % (main, src_bare))
            else:
                errors += publish_errors(target, remote, main)
        elif src_bare in ("HEAD", "@") and cur == main:
            errors += publish_errors(target, remote, main)
    return errors


def mode_push():
    root, conf = project_conf()
    if not pc.is_strict(conf):
        return 0
    try:
        calls = parse(sys.stdin.read(), base_pwd())
    except ValueError:
        return fail_open("команда не разобрана")
    errors = []
    for call in calls:
        if call["sub"] == "push":
            errors += push_errors(call)
    if errors:
        return deny(errors)
    return 0


# ---------------------------------------------------------------- pre-push (git-хук)

def mode_push_hook():
    root, conf = project_conf()
    if not pc.is_strict(conf):
        return 0
    main = conf.get("MAIN_BRANCH", "main")
    errors = []
    for line in sys.stdin.read().splitlines():
        parts = line.split()
        if len(parts) < 4:
            continue
        local_ref, local_sha, remote_ref, remote_sha = parts[:4]
        if local_ref.startswith("refs/tags/") or remote_ref.startswith("refs/tags/"):
            continue  # теги не трогаем
        if zero(local_sha):
            if remote_ref == "refs/heads/" + main:
                errors.append("Удаление '%s' запрещено (E19)." % main)
            continue
        if not zero(remote_sha) and not is_ancestor(root, remote_sha, local_sha):
            errors.append("Non-fast-forward push «%s» (force) запрещён (E19)." % local_ref)
        if remote_ref == "refs/heads/" + main:
            if local_ref != "refs/heads/" + main:
                errors.append("Push в '%s' из '%s' запрещён: в main публикуется только main." % (main, local_ref))
            elif zero(remote_sha):
                pass  # первый push main: удалённой точки ещё нет, прямых коммитов впереди не существует
            else:
                ahead = git_text_in(root, "rev-list", "--first-parent", "--no-merges",
                                    "%s..%s" % (remote_sha, local_sha)).split()
                if ahead:
                    errors.append("Push в '%s': %d прямых (не-мерж) коммит(ов) впереди '%s' — публикуй только "
                                  "влитые ветки (E19)." % (main, len(ahead), remote_sha[:8]))
    for error in errors:
        print(error, file=sys.stderr)
    if errors:
        print("pre-push: push заблокирован строгим слоем (SPEC §9).", file=sys.stderr)
        return 1
    return 0


# ---------------------------------------------------------------- branch-guard / preflight

def mode_branch_guard_file(path):
    root, conf = project_conf()
    if not pc.is_strict(conf):
        return 0
    rel = rel_to_root(path, root)
    if rel is None or rel == ".":
        return 0
    if in_progress_in(root):
        return 0  # merge/rebase/cherry-pick правят файлы по своей логике
    branch = branch_in(root)
    if branch == "HEAD":
        return 0  # отсоединённый HEAD (rebase/worktree) — не наш случай
    main = conf.get("MAIN_BRANCH", "main")
    if branch == main:
        print("Ветка '%s': правки напрямую запрещены (E2)." % main, file=sys.stderr)
        print("Создай ветку: git checkout -b feature/PLAN-N-slug (или hotfix/slug) — и правь там.", file=sys.stderr)
        return 2
    if pc.is_protected(rel, conf):
        problem = pc.marker_problem(root, conf, "hooks-edit", branch, branch)
        if problem:
            print("E18: %s — правка защищённых путей только по слову владельца: %s" % (rel, problem), file=sys.stderr)
            return 2
        return 0
    if not conventional_branch(branch, conf) and pc.is_code(rel, conf):
        print("Ветка '%s' без PLAN-токена: код правится только на feature/PLAN-<N>-* или hotfix/* (E2)." % branch,
              file=sys.stderr)
        print("Файл %s — код. Допустимы только planning/, docs/, *.md и не-код." % rel, file=sys.stderr)
        return 2
    return 0


def mode_preflight(ref):
    root, conf = project_conf()
    if not pc.is_strict(conf):
        print("strict off: STRICT=off в .claude/planning.conf — strict-проверки merge-gate выключены")
        return 0
    main = conf.get("MAIN_BRANCH", "main")
    sha = git_text_in(root, "rev-parse", "--verify", "--quiet", ref + "^{commit}")
    if not sha:
        print("merge-ready: ссылка '%s' не резолвится в коммит" % ref)
        return 2
    name = branch_name_for_ref(root, ref, sha, conf)
    problems, words = [], []
    if not name:
        problems.append("'%s' (вершина %s) не ветка feature/PLAN-N-* или hotfix/*" % (ref, sha[:7]))
    else:
        problems += token_errors(root, sha, name, conf)
        problems += merge_registry_errors(root, sha, main)
        problems += gate_errors(root, name, sha, conf)
        problem = pc.marker_problem(root, conf, "merge", name, name, sha=sha)
        if problem:
            words.append(problem)
        behind = git_text_in(root, "rev-list", "--count", "%s..refs/heads/%s" % (sha, main))
        if behind not in ("", "0"):
            problems.append("ветка отстаёт от '%s' на %s коммит(ов): подтяни main в ветку" % (main, behind))
        if git_text_in(root, "status", "--porcelain"):
            problems.append("рабочее дерево не чистое: гейт относится к закоммиченной вершине")
    if problems:
        print("NOT READY: %s (вершина %s)" % (ref, sha[:7]))
        for problem in problems:
            print("  - " + problem)
    else:
        print("READY (кроме слов владельца)" if words else "READY")
    for word in words:
        print("  слово владельца: .claude/scripts/planning-owner-ok.sh merge " + (name or ref))
    return 1 if problems else 0


# ---------------------------------------------------------------- CLI

def usage():
    print("usage: strict-checks.py branch-guard-file PATH | commit | merge | push | push-hook | --preflight BRANCH",
          file=sys.stderr)
    return 2


def main(argv):
    if pc is None:
        print("strict-checks: не загрузился planning-checks.py (%s) — проверка пропущена (fail-open)." % _PC_ERROR,
              file=sys.stderr)
        return 0
    if not argv:
        return usage()
    if argv[0] == "--preflight" and len(argv) >= 2:
        return mode_preflight(argv[1])
    if argv[0] == "branch-guard-file" and len(argv) >= 2:
        return mode_branch_guard_file(argv[1])
    modes = {"commit": mode_commit, "merge": mode_merge, "push": mode_push, "push-hook": mode_push_hook}
    action = modes.get(argv[0])
    if action is None:
        return usage()
    return action()


if __name__ == "__main__":
    try:
        sys.stderr.reconfigure(errors="backslashreplace")
    except AttributeError:
        pass
    try:
        sys.exit(main(sys.argv[1:]))
    except Exception as exc:  # noqa: BLE001 — fail-open: баг хука не должен парализовать владельца
        print("strict-checks: внутренняя ошибка хука: %s: %s (проверка пропущена, fail-open)"
              % (type(exc).__name__, exc), file=sys.stderr)
        sys.exit(0)
