#!/usr/bin/env bash
# PreToolUse на Bash: агент не правит main напрямую (CLAUDE.md -> Git workflow). Решение владельца 2026-10-17:
# ПУБЛИКАЦИЯ влитых веток в main разрешена, прямые правки main и любой перезапис истории - нет.
#
# Пуш в main (`git push [origin] main`, `main:main`, `refs/heads/main`, `HEAD`/`HEAD:main` при текущей ветке main,
# голый `git push`/`git push origin` из main) разрешён ТОЛЬКО если на основной линии main нет прямых коммитов впереди
# <remote>/main: `git rev-list --first-parent --no-merges <remote>/main..main` пуст (впереди лишь мерж-коммиты веток).
# Если <remote>/main не резолвится (нет remote, он задан URL-ом, `--repo`) - блок. Блокируется как раньше: `+main`,
# `--force`/`-f`/`--force-with-lease`, `--delete`/`:main`, `--all`/`--mirror`, refspec с источником не main
# (`feature:main`, `HEAD:main` не из main), подстановки ($(..), обратные кавычки) на main, `git subtree push … main`.
# Ловит цепочки (`a && git push …`, `;`, `|`), вложенные оболочки (`bash -c "git push origin main"`),
# `cd <каталог> && git push …` (ветка берётся из того каталога), `git -C <каталог> push …`, опции со значениями
# (`--repo`, `--receive-pack`, `-o`). Пуши feature/*, hotfix/* и тегов проходят.
# Поведенческое правило поверх хука: агент пушит main только когда владелец в чате сказал пушить.
# Осознанный компромисс: команду от данных хук отличает только по regex, поэтому текст «git push origin main»
# внутри echo/grep/heredoc/сообщения коммита тоже проверяется как команда (перефразируй или положи текст в файл через Write).
# Это защита от случайности агента, а не от злого умысла. Тесты: python3 .claude/hooks/test_main_push_guard.py
#
# exit 2 = блокировка тул-колла, stderr уходит модели как причина.

GUARD_ORIG_PWD="$PWD"
GUARD_HOOK_DIR="$(cd "$(dirname "$0")" && pwd)"
export GUARD_ORIG_PWD GUARD_HOOK_DIR
cd "${CLAUDE_PROJECT_DIR:-.}" || exit 0

python3 -c '
import json, os, re, subprocess, sys

try:
    payload = json.load(sys.stdin)
    cmd = (payload.get("tool_input") or {}).get("command") or ""
except Exception:
    sys.exit(0)

if "push" not in cmd:
    sys.exit(0)

# HF-150: перенаправления (`2>&1`, `&>f`, `>|f`, `<<<w`) - не часть push; общий с остальными хуками разбор вырезает их вместе с целью.
# Не импортировалось - остаёмся на исходной строке (как до исправления).
try:
    sys.path.insert(0, os.environ["GUARD_HOOK_DIR"])
    import commit_checks
    cmd = commit_checks.strip_redirections(cmd)
except Exception:
    pass

VALUE_FLAGS = {"--repo", "--receive-pack", "--exec", "-o", "--push-option", "--prefix", "-P"}
# `git [-C dir] [-c k=v] … push …` — до конца простой команды или закрывающей кавычки.
PUSH_RE = re.compile(r"""\bgit\b(?:\s+(?:-C\s+\S+|-c\s+\S+|--[a-z-]+(?:=\S+)?))*\s+(?:subtree\s+)?push\b[^;&|\n)]*""")
CD_RE = re.compile(r"(?:^|[;&|\n(]\s*)cd\s+([^\s;&|]+)")


def current_branch(workdir):
    # symbolic-ref, а не rev-parse --abbrev-ref: при одноимённом теге (refs/tags/main) тот даёт «heads/main»,
    # и голый push из main не опознавался бы как push в main.
    try:
        full = subprocess.run(
            ["git", "-C", workdir, "symbolic-ref", "-q", "HEAD"],
            capture_output=True, text=True, timeout=5,
        ).stdout.strip()
        if full:
            return full[len("refs/heads/"):] if full.startswith("refs/heads/") else full
        out = subprocess.run(
            ["git", "-C", workdir, "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True, text=True, timeout=5,
        )
        return out.stdout.strip()
    except Exception:
        return ""


def git_out(wd, *args):
    try:
        r = subprocess.run(["git", "-C", wd, *args], capture_output=True, text=True, timeout=10)
        return r.returncode, r.stdout.strip()
    except Exception:
        return 1, ""


def main_publish_problem(wd, remote):
    """None, если публикация main допустима. База - РЕАЛЬНЫЙ серверный SHA main (`git ls-remote`, а не локальный tracking-ref,
    который может устареть); remote - только именованный из `git remote`. Ошибка/таймаут ls-remote, нет SHA локально или он не предок
    main - блок. Впереди серверного SHA на первой родительской линии не должно быть не-мерж коммитов. Имена полные
    (refs/heads/main), чтобы `git branch origin/main` не подменил ссылку."""
    if not remote or remote.startswith("-"):
        return "remote «%s» не задан или похож на опцию" % remote
    if remote not in git_out(wd, "remote")[1].split():
        return "«%s» не именованный remote из git remote (URL и пути не годятся)" % remote
    try:
        r = subprocess.run(["git", "-C", wd, "ls-remote", remote, "refs/heads/main"], capture_output=True, text=True, timeout=20,
                           env=dict(os.environ, GIT_TERMINAL_PROMPT="0"))
    except Exception:
        return "git ls-remote %s не отработал (таймаут/ошибка), серверный main не проверить" % remote
    line = r.stdout.strip().splitlines()[0] if r.returncode == 0 and r.stdout.strip() else ""
    server = line.split()[0] if line else ""
    if not re.fullmatch(r"[0-9a-f]{40,64}", server):
        return "на %s нет refs/heads/main или ls-remote вернул ошибку" % remote
    if git_out(wd, "cat-file", "-e", server + "^{commit}")[0]:
        return "серверный main %s отсутствует локально (сделай fetch и проверь)" % server[:8]
    rc, _ = git_out(wd, "rev-parse", "--verify", "--quiet", "refs/heads/main^{commit}")
    if rc:
        return "локальной ветки main нет"
    if git_out(wd, "merge-base", "--is-ancestor", server, "refs/heads/main")[0]:
        return "серверный main %s не предок локального main (расхождение истории)" % server[:8]
    rc, out = git_out(wd, "rev-list", "--first-parent", "--no-merges", "%s..refs/heads/main" % server)
    if rc:
        return "rev-list %s..main не удался" % server[:8]
    if out:
        return "на main есть прямые коммиты впереди %s (%d шт.), публиковать можно только влитые ветки" % (server[:8], len(out.split()))
    return None


def dest_is_main(spec):
    spec = spec.lstrip("+")
    dst = spec.split(":", 1)[1] if ":" in spec else spec
    dst = re.sub(r"^refs/heads/", "", dst)
    return dst == "main"


SWITCH_RE = re.compile(r"""\bgit\b(?:\s+(?:-C\s+\S+|-c\s+\S+|--[a-z-]+(?:=\S+)?))*\s+(?:checkout|switch)\b([^;&|\n)]*)""")
UNKNOWN = object()


def simulated_branch(prefix, wd):
    """Ветка, на которой окажется push, если в той же команде ДО него были checkout/switch: имя, если однозначно (-b/-c <имя>
    или существующая локальная ветка), иначе UNKNOWN. Без смены ветки - настоящая текущая ветка."""
    cur = current_branch(wd)
    for m in SWITCH_RE.finditer(prefix):
        toks = [t.strip("\"\x27") for t in m.group(1).split()]
        name = None
        for k, t in enumerate(toks):
            if t in ("-b", "-B", "-c", "-C") and k + 1 < len(toks):
                name = toks[k + 1]
                break
        if name is None:
            pos = [t for t in toks if not t.startswith("-")]
            name = pos[0] if pos and "--" not in toks else None
            if name is not None and git_out(wd, "rev-parse", "--verify", "--quiet", "refs/heads/" + name)[0]:
                name = None
        cur = name if name is not None else UNKNOWN
    return cur


def clean(token):
    return token.strip("\"\x27")


def workdir_before(position, base):
    wd = base
    for target in CD_RE.findall(cmd[:position]):
        target = os.path.expanduser(clean(target))
        wd = target if os.path.isabs(target) else os.path.normpath(os.path.join(wd, target))
    return wd


def verdict(match):
    tokens = [clean(t) for t in match.group(0).split()]
    # HF-174: из worktree хук стартует в основном чекауте, база - cwd команды.
    wd = workdir_before(match.start(), payload.get("cwd") or os.environ.get("GUARD_ORIG_PWD") or ".")
    push_at = tokens.index("push")
    head = tokens[:push_at]
    for i, t in enumerate(head):
        if t == "-C" and i + 1 < len(head):
            target = os.path.expanduser(head[i + 1])
            wd = target if os.path.isabs(target) else os.path.normpath(os.path.join(wd, target))

    flags, pos, repo_flag = [], [], False
    args = tokens[push_at + 1:]
    i = 0
    while i < len(args):
        a = args[i]
        name = a.split("=", 1)[0]
        if name == "--repo":
            repo_flag = True
        if name in VALUE_FLAGS:
            i += 1 if "=" in a else 2
            continue
        if a.startswith("-"):
            flags.append(a)
        else:
            pos.append(a)
        i += 1

    if "--all" in flags or "--mirror" in flags:
        return "git push --all/--mirror уходит и в main"
    force = any(f in ("--force", "--delete", "-f", "-d") or f.startswith("--force-with-lease") or f.startswith("--force-if-includes")
                or (re.fullmatch(r"-[a-zA-Z]+", f) and ("f" in f or "d" in f)) for f in flags)
    strict = "subtree" in head  # subtree push в main - не публикация влитых веток
    branch = simulated_branch(cmd[:match.start()], wd)
    on_main = branch == "main" or branch is UNKNOWN  # ветка после смены внутри команды не определена - считаем главной

    if repo_flag:
        remote = None
    elif pos:
        remote = pos[0]
    else:
        remote = git_out(wd, "config", "branch.main.remote")[1] or "origin"

    def publish(what):
        """Пуш main допустим только без force/delete/subtree и при чистой основной линии."""
        if force or strict:
            return "%s: force/delete/subtree в main запрещены" % what
        problem = main_publish_problem(wd, remote)
        return "%s: %s" % (what, problem) if problem else None

    refspecs = pos if repo_flag else pos[1:]
    if not refspecs:
        if "--tags" in flags:
            return None
        if on_main:
            return publish("git push без refspec из ветки main")
        return None

    j = 0
    while j < len(refspecs):
        spec = refspecs[j]
        if spec == "tag":  # `git push origin tag v1` — следующий токен тег, не ветка
            j += 2
            continue
        if "*" in spec or spec.lstrip("+") == ":":
            return "wildcard/matching refspec «%s» может затронуть main" % spec
        if "$" in spec or "`" in spec:
            if on_main:
                return "refspec «%s» подставляется на лету, а текущая ветка — main" % spec
        elif dest_is_main(spec):
            if spec.startswith("+") or (":" in spec and not spec.split(":", 1)[0]):
                return "git push в main: «%s» (force или удаление)" % spec
            src = re.sub(r"^refs/heads/", "", spec.split(":", 1)[0]) if ":" in spec else "main"
            if not (src == "main" or (src in ("HEAD", "@") and branch == "main")):
                return "git push в main из «%s»: источником может быть только main" % spec
            problem = publish("git push «%s»" % spec)
            if problem:
                return problem
        elif spec in ("HEAD", "@") and on_main:
            problem = publish("git push HEAD из ветки main")
            if problem:
                return problem
        j += 1
    return None


bad = None
for m in PUSH_RE.finditer(cmd):
    bad = verdict(m)
    if bad:
        break

if bad:
    sys.stderr.write(
        "Пуш в main заблокирован (%s).\n"
        "Правило проекта: прямых правок main нет; в main публикуются только влитые ветки (мерж-коммиты) и только "
        "по слову владельца. Работа идёт веткой feature/* или hotfix/*: git push -u origin <ветка>.\n" % bad
    )
    sys.exit(2)
'
