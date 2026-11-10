#!/usr/bin/env python3
"""Команда агента на stdin (JSON PreToolUse): exit 2, если она чистит базу не из разрешённых (working-rules.md).

Блокируется вне баз testing, testing_test_N и app_dusk:
  artisan migrate:fresh|refresh|reset, db:wipe, db:seed, migrate --seed; TRUNCATE и DROP через psql, artisan db, artisan tinker;
  dropdb. Dusk (artisan dusk, sail dusk) разрешён только на app_dusk: явный DB_DATABASE или .env.dusk.local.
Форма запуска не важна: docker exec, docker compose exec, sail artisan, sail exec, sh -c, ssh, $(…), shell с heredoc.

База считается той, что дойдёт до процесса: VAR= перед docker exec и sail в контейнер не попадает, а -e и `env VAR=` попадают.
`artisan --env=testing` и `--database=` базу не задают (.env.testing нет, --database это имя подключения), поэтому не спасают.
Строки-данные (echo, grep, git commit -m, gh) командой не считаются: разбор как argv, общий с commit-gate (commit_checks.py).

Защита от случайности, не от умысла. ponytail: SQL из файла (`psql -f`), `\\c` внутри heredoc, `echo … | bash`, `bash <<<`
и `export VAR=` не разбираются: export даёт лишний блок, остальное проходит. Догонять, если такое случится на деле.
Тесты: python3 .claude/hooks/test_db_wipe_guard.py
"""
import json
import os
import re
import shlex
import subprocess
import sys
from pathlib import Path

import commit_checks as cc

SAFE_DB = re.compile(r"testing(_test_\d+)?|app_dusk")
WIPE = {"migrate:fresh", "migrate:refresh", "migrate:reset", "db:wipe", "db:seed"}
DUSK = {"dusk", "dusk:fails"}
# Быстрый выход и признак вложенной команды в аргументе. Без этих слов команда не наша.
WORDS = re.compile(r"migrate:(fresh|refresh|reset)|db:wipe|db:seed|--seed|dusk|truncate|drop", re.I)
RUNNERS = re.compile(r"artisan|\bsail\b|psql|dropdb")
KILL_SQL = re.compile(r"\b(truncate|drop(ifexists|alltables|columns?)?)\b", re.I)
DROP_DB = re.compile(r"\bdrop\s+database\s+(?:if\s+exists\s+)?\"?(\w+)", re.I)
# docker exec и sail запускают процесс в контейнере: окружение хоста до него не доходит.
REMOTE = {"docker", "docker-compose", "podman", "kubectl", "sail", "ssh"}
DATA_HEADS = cc.DATA_HEADS | {"git", "gh", "jq"}
PSQL_VALUE_FLAGS = {"-U", "-h", "-p", "-c", "-f", "-v", "-o", "-P", "-T", "-L", "-F", "-R", "--username", "--host", "--port",
                    "--command", "--file", "--variable", "--set", "--output", "--pset", "--log-file", "--maintenance-db"}
SHELL_WORDS = {"if", "then", "else", "elif", "while", "until", "do", "!", "{"}
SHELL_HEREDOC = re.compile(r"(?:^|[\s/])(?:bash|sh|zsh|ssh)\s[^|;&]*<<-?\s*['\"]?([A-Za-z0-9_-]+)")


def safe(db):
    return bool(db and SAFE_DB.fullmatch(db))


def reaching(before, env, key):
    """Значение key, которое дойдёт до процесса; None, если не задано. Каждая граница запуска (docker, sail, ssh) обнуляет
    окружение: считается только заданное после последней из них."""
    remote = [i for i, t in enumerate(before) if os.path.basename(t) in REMOTE]
    value = None if remote else env.get(key)
    for token in before[remote[-1] + 1 if remote else 0:]:
        m = re.fullmatch(r"(?:-e|--env=)?%s=(.*)" % key, token)
        if m:
            value = m.group(1)
    return value


def conn_db(value):
    """Имя базы из `testing`, `postgresql://u@h:5432/testing?x=1` или `host=h dbname=testing`."""
    m = re.match(r"postgres(?:ql)?://[^/]*/([^?]*)", value) or re.search(r"\bdbname=(\S+)", value)
    return m.group(1) if m else value


def psql_db(args, env_db):
    """База psql и dropdb: последний -d/--dbname, иначе первый позиционный аргумент, иначе PGDATABASE."""
    named, positional, i = None, None, 0
    while i < len(args):
        a = args[i]
        if a in ("-d", "--dbname"):
            named = args[i + 1] if i + 1 < len(args) else named
            i += 2
            continue
        if a in PSQL_VALUE_FLAGS:
            i += 2
            continue
        if a.startswith("--dbname="):
            named = a.partition("=")[2]
        elif re.match(r"-d.", a):
            named = a[2:]
        elif not a.startswith("-") and positional is None:
            positional = a
        i += 1
    db = named or positional
    return conn_db(db) if db else env_db


def artisan_sub(args):
    """Подкоманда artisan: первый аргумент без минуса; значение `--env local` подкомандой не считается."""
    i = 0
    while i < len(args):
        if args[i] == "--env":
            i += 2
        elif args[i].startswith("-"):
            i += 1
        else:
            return args[i]
    return ""


def dusk_env_db():
    """DB_DATABASE из .env.dusk.local: каталог проекта, иначе основной чекаут (sail всегда идёт в него)."""
    common = subprocess.run(["git", "rev-parse", "--path-format=absolute", "--git-common-dir"], capture_output=True, text=True).stdout.strip()
    for base in (Path.cwd(), Path(common).parent if common else None):
        path = base / ".env.dusk.local" if base else None
        if path and path.is_file():
            m = re.search(r"^DB_DATABASE=(.*)$", path.read_text(errors="replace"), re.M)
            return m.group(1).strip().strip("\"'") if m else None
    return None


def sql_problem(what, db, root):
    """Что не так с SQL, который пойдёт через psql/artisan db/tinker. root - вся команда: SQL бывает в heredoc и пайпе."""
    for name in DROP_DB.findall(root):
        if not safe(name):
            return "%s: DROP DATABASE %s" % (what, name)
    if KILL_SQL.search(DROP_DB.sub("", root)) and not safe(db):
        return "%s: TRUNCATE/DROP на базе «%s»" % (what, db or "по умолчанию")
    return None


def check_argv(argv, env, root):
    names = [os.path.basename(t) for t in argv]
    for i, name in enumerate(names):
        before, rest = argv[:i], argv[i + 1:]
        after_sail = i > 0 and names[i - 1] == "sail"
        if name == "artisan" or (after_sail and name in ("art", "a")):
            db = reaching(before, env, "DB_DATABASE")
            sub = artisan_sub(rest)
            if (WIPE & set(rest) or ("migrate" in rest and "--seed" in rest)) and not safe(db):
                return "artisan %s на базе «%s»" % (sub, db or "из .env")
            if sub in DUSK:
                db = db or dusk_env_db()
                if db != "app_dusk":
                    return "artisan dusk на базе «%s»" % (db or "неизвестна")
            if sub in ("db", "tinker"):
                bad = sql_problem("artisan " + sub, db, root)
                if bad:
                    return bad
        elif after_sail and name in DUSK:
            db = dusk_env_db()
            if db != "app_dusk":
                return "sail dusk на базе «%s»" % (db or "неизвестна")
        elif after_sail and name == "tinker":
            bad = sql_problem("sail tinker", None, root)
            if bad:
                return bad
        elif name == "psql":
            # `sail psql` аргументы отбрасывает и всегда идёт в POSTGRES_DB, то есть в рабочую базу.
            db = None if after_sail else psql_db(rest, reaching(before, env, "PGDATABASE"))
            bad = sql_problem("psql", db, root)
            if bad:
                return bad
        elif name == "dropdb" and rest and not safe(psql_db(rest, None)):
            return "dropdb %s" % psql_db(rest, None)
    inherited = {"DB_DATABASE": reaching(argv, env, "DB_DATABASE"), "PGDATABASE": reaching(argv, env, "PGDATABASE")}
    for token in argv[1:]:
        if re.search(r"\s", token) and WORDS.search(token):
            bad = check_text(token, {k: v for k, v in inherited.items() if v}, root)
            if bad:
                return bad
    return None


def shell_heredocs(cmd):
    """Тела heredoc, которые читает оболочка: `bash <<EOF`, `docker exec -i c sh <<'EOF'`. Остальные heredoc - данные."""
    bodies, word, cur = [], None, []
    for line in cmd.split("\n"):
        if word is not None:
            if line.strip() == word:
                bodies.append("\n".join(cur))
                word, cur = None, []
            else:
                cur.append(line)
            continue
        m = SHELL_HEREDOC.search(line)
        if m:
            word = m.group(1)
    return bodies


def check_text(text, inherited=None, root=None):
    """Не разобралось (битые кавычки): блок, только если похоже на запуск нашей команды, а не на данные с апострофом."""
    try:
        return check(text, inherited, root)
    except ValueError:
        return "команду не разобрать, а в ней запуск и слова очистки базы" if RUNNERS.search(text) else None


def check(cmd, inherited=None, root=None):
    """Причина блокировки или None; ValueError при битых кавычках."""
    root = root if root is not None else cmd
    for argv in cc.segments(cmd):
        env = dict(inherited or {})
        while argv and argv[0] in SHELL_WORDS:
            argv = argv[1:]
        argv = cc.strip_wrappers(argv, env)
        if not argv or os.path.basename(argv[0]) in DATA_HEADS:
            continue
        bad = check_argv(argv, env, root)
        if bad:
            return bad
    for inner in cc.substitutions(cc.strip_comments(cc.strip_heredocs(cmd))) + shell_heredocs(cmd):
        if WORDS.search(inner):
            bad = check_text(inner, inherited, root)
            if bad:
                return bad
    return None


def main():
    try:
        cmd = (json.load(sys.stdin).get("tool_input") or {}).get("command") or ""
    except Exception:
        return 0
    if isinstance(cmd, list):  # инструмент shell у Codex присылает argv массивом
        cmd = shlex.join(str(t) for t in cmd)
    if not WORDS.search(cmd):
        return 0
    bad = check_text(cmd)
    if not bad:
        return 0
    sys.stderr.write(
        "Очистка базы заблокирована (%s).\n"
        "Правило .claude/rules/working-rules.md: рабочую БД не чистим без слова владельца; команду на ней выполняет владелец в своём терминале.\n"
        "Разрешены базы testing, testing_test_N и app_dusk, например: docker exec -e DB_DATABASE=testing <project>-horizon-1 php artisan migrate:fresh --force.\n"
        "Префикс DB_DATABASE=… перед docker exec или sail до контейнера не доходит, а artisan --env=testing бьёт по dev-базе.\n" % bad
    )
    return 2


if __name__ == "__main__":
    sys.exit(main())
