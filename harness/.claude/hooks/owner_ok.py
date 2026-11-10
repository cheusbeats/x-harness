#!/usr/bin/env python3
"""Маркеры слова владельца (PLAN-145, E10/E11): `.claude/state/owner-ok/<вид>-<id>@<ветка с / → _>`.

Маркер создаёт ТОЛЬКО владелец в своём терминале: `.claude/scripts/owner-ok.sh <вид> <id> [ветка]`.
Формат — строки key=value: kind, id, branch, sha (вершина ветки на момент выдачи), target=main, issued (epoch).

Правила приёма:
  commit-gate / pre-commit  читают маркер: есть, ветка, срок (24 ч), вид/id; SHA НЕ сверяют (вершина
                            меняется с каждым коммитом) и маркер НЕ расходуют;
  merge-gate                сверяет SHA вершины мержимой ветки и цель main, затем атомарно забирает
                            маркер (`os.rename` в `.claimed`; кто не смог — «разрешение уже использовано»).
  SessionStart              `cleanup`: удаляет `.claimed`, просроченные и влитые.

CLI (для bash-хуков):
  owner_ok.py merge-claim 1|0 REF…   merge-gate после зелёных проверок (1 = цель мержа main); exit 2 + причина.
                                     Любой сбой = отказ (fail-closed)
  owner_ok.py cleanup                plans-drift (SessionStart); exit 0 всегда
  owner_ok.py edit-guard FILE BRANCH branch-guard: Edit/Write защищённого пути (E18) без маркера - exit 2
  owner_ok.py guard                  команда агента на stdin; exit 2, если она выдаёт/подделывает маркер (I7)
"""
import os
import re
import subprocess
import sys
import time
from pathlib import Path

TTL = 24 * 3600
KINDS = ("close-plan", "rm-add", "hooks-edit")
INDEX_FILES = ("planning/PLANS.md", "planning/ACTIVE_PLANS.md")
PLAN_ID = r"PLAN-(\d+(?:\.\d+)*)"
CLOSED_STATUS = re.compile(r"(закрыт|аннулирован)\b")


def git(*args, cwd=None):
    """stdout git как текст; при ошибке (нет ревизии/файла) — пустая строка."""
    res = subprocess.run(["git", *args], capture_output=True, cwd=cwd)
    return res.stdout.decode("utf-8", "surrogateescape") if res.returncode == 0 else ""


def root_dir():
    return git("rev-parse", "--show-toplevel").strip() or os.getcwd()


def enc(text):
    """Однозначное имя для файла: % / _ @ кодируются, поэтому feature/a/b и feature/a_b не сталкиваются."""
    for ch, code in (("%", "%25"), ("/", "%2F"), ("_", "%5F"), ("@", "%40")):
        text = text.replace(ch, code)
    return text


def marker_path(root, kind, ident, branch):
    return Path(root) / ".claude/state/owner-ok" / ("%s-%s@%s" % (kind, enc(ident), enc(branch)))


def claimed_path(path):
    """Забранные маркеры лежат отдельно и живой маркер с тем же именем не затирают."""
    return Path(path).parent / "claimed" / Path(path).name


def read_marker(path):
    try:
        text = Path(path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    return dict(line.split("=", 1) for line in text.splitlines() if "=" in line)


def expired(path, data, now=None):
    now = now or time.time()
    try:
        issued = int(data.get("issued", "0"))
        return now - issued > TTL or now - Path(path).stat().st_mtime > TTL
    except (ValueError, OSError):
        return True


def how_to(kind, ident):
    return "попроси владельца выполнить `.claude/scripts/owner-ok.sh %s %s`" % (kind, ident)


def problem(root, kind, ident, branch, tip=None):
    """None, если маркер принимается; иначе причина. tip задан только у merge-gate (сверка SHA и цели)."""
    path = marker_path(root, kind, ident, branch)
    what = {"rm-add": "запись в roadmap", "close-plan": "закрытие плана",
            "hooks-edit": "правка защищённых путей (хуки, настройки, инструкции агента; E18)"}.get(kind, "правка")
    data = read_marker(path)
    if data is None:
        if claimed_path(path).exists():
            return "%s %s: разрешение уже использовано; %s" % (what, ident, how_to(kind, ident))
        return "%s %s — только по слову владельца: %s" % (what, ident, how_to(kind, ident))
    if data.get("kind") != kind or data.get("id") != ident or data.get("branch") != branch:
        return "%s %s: маркер не относится к этой операции/ветке; %s" % (what, ident, how_to(kind, ident))
    if expired(path, data):
        return "%s %s: разрешение владельца старше 24 ч; %s" % (what, ident, how_to(kind, ident))
    if tip is not None and (data.get("sha") != tip or data.get("target") != "main"):
        return "%s %s: после выдачи разрешения ветка изменилась (SHA вершины не совпал); %s" % (what, ident, how_to(kind, ident))
    return None


def claim(path):
    """Атомарный захват: rename на одной ФС; проигравший параллельный гейт получает False."""
    try:
        claimed_path(path).parent.mkdir(parents=True, exist_ok=True)
        os.rename(path, claimed_path(path))
        return True
    except OSError:
        return False


def release(path):
    """Откат захвата (мерж не состоялся из-за другого маркера набора)."""
    try:
        os.rename(claimed_path(path), path)
    except OSError:
        pass


# ---------------------------------------------------------------- детекторы E10/E11

def rm_rows(text):
    """RM-N из строк таблицы ROADMAP.md (`| [RM-1](…) |` или `| RM-1 |`), регистр не важен."""
    return set(re.findall(r"^\|\s*\[?RM-(\d+)\b", text, re.M | re.I))


def plan_ids(text):
    return set(re.findall(PLAN_ID, text, re.I))


def split_row(line):
    """Куски строки по неэкранированному «|» (копия из registry.sh: `\\|` в названии не разделитель, `\\\\|` — слеш и разделитель)."""
    parts, cur, run = [], [], 0
    for ch in line:
        if ch == "|" and run % 2 == 0:
            parts.append("".join(cur))
            cur, run = [], 0
            continue
        run = run + 1 if ch == "\\" else 0
        cur.append(ch)
    parts.append("".join(cur))
    return parts


def closed_rows(text):
    """Все PLAN-ID первой ячейки строк реестра, у которых КОЛОНКА «Статус» — закрыт/аннулирован."""
    found, col = set(), None
    for line in text.splitlines():
        if not line.startswith("|"):
            col = None
            continue
        cells = [c.strip().lower() for c in split_row(line)]
        if col is None:
            col = next((i for i, c in enumerate(cells) if c.startswith("статус")), None)
        elif col < len(cells) and CLOSED_STATUS.match(cells[col]):
            found |= plan_ids(cells[1])
    return found


def closed_sections(text):
    """Текущий формат ACTIVE_PLANS.md: секции `## PLAN-N …` со строкой `**Статус:** …`; ID — все из заголовка."""
    found = set()
    for block in re.split(r"(?m)^(?=## )", text):
        head = block.split("\n", 1)[0]
        status = re.search(r"\*\*Статус:\*\*\s*(.*)", block)
        if head.startswith("## ") and status and CLOSED_STATUS.match(status.group(1).strip().lower()):
            found |= plan_ids(head)
    return found


def heading_ids(text):
    """Старый формат PLANS.md (до миграции): все PLAN-ID заголовков `## PLAN-N / PLAN-M — …`."""
    return plan_ids("\n".join(l for l in text.splitlines() if l.startswith("## ")))


def e18_needed(entries, branch, old):
    """E18: изменение защищённого пути (любой статус, и удаление) -> {("hooks-edit", ветка)}. Правило и список путей
    берутся из paths.conf версии `old` (HEAD / merge-base): выключить E18 той же правкой, что он должен остановить, нельзя."""
    import paths
    # Объединение: правило включено, если оно включено в `old` ИЛИ в main (ветка, созданная до `e18 on`, его не обходит).
    texts = [t for t in (git("show", "%s:.claude/hooks/paths.conf" % old), git("show", "main:.claude/hooks/paths.conf")) if t]
    confs = [paths.parse(t) for t in texts] if texts else [paths.load()]
    if branch and any(paths.e18_on(c) and paths.e18_protected(p, c) for c in confs for _, p in entries):
        return {("hooks-edit", branch)}
    return set()


def e18_file_problem(file, branch):
    """branch-guard (PreToolUse Edit/Write): правка защищённого пути при `e18 on` требует действующий маркер
    hooks-edit текущей ветки - только чтение, без сверки SHA. -> текст отказа или None.
    ПРИНЯТЫЙ РИСК: исполняемый код, который commit-gate импортирует (owner_ok.py, commit_checks.py, paths.py), можно
    изменить правкой ДО того, как маркер потребуется (хук в этот момент работает на старом коде или на уже изменённом);
    авторитетная проверка - merge-gate: он выполняется на коде main и смотрит на дифф ветки целиком."""
    import paths
    top = root_dir()
    text = git("show", "HEAD:.claude/hooks/paths.conf")
    conf = paths.parse(text) if text else paths.load()
    rel = os.path.relpath(os.path.realpath(file), os.path.realpath(top))
    if not (paths.e18_on(conf) and paths.e18_protected(rel, conf)):
        return None
    return problem(top, "hooks-edit", branch, branch)


def needed(entries, read_new, old="HEAD", branch=None):
    """[(статус, путь)] изменений -> {(вид, id)}, для которых нужно слово владельца.
    read_new(path) -> новая версия файла; old — ревизия «до» (HEAD / merge-base); branch — ветка операции (для E18)."""
    status = {p: s for s, p in entries}
    old_files = git("ls-tree", "-r", "--name-only", old, "--", "planning/roadmap").splitlines()

    def old_text(path):
        return git("show", "%s:%s" % (old, path))

    # E11: новый RM — новый файл или новая строка ROADMAP.md с id, которого не было в old
    rm_file = r"planning/roadmap/RM-(\d+)-[^/]+\.md"
    rm = {m.group(1) for s, p in entries for m in [re.fullmatch(rm_file, p, re.I)] if m and s != "D"}
    if status.get("planning/ROADMAP.md", "D") != "D":
        rm |= rm_rows(read_new("planning/ROADMAP.md"))
    old_rm = rm_rows(old_text("planning/ROADMAP.md")) | {m.group(1) for f in old_files for m in [re.fullmatch(rm_file, f, re.I)] if m}

    # E10: закрытие — новая архивная запись closed/PLAN-N*.md, либо переход статуса в закрыт/аннулирован
    # (строка реестра или секция ACTIVE_PLANS.md), либо (PLANS.md до миграции) новый PLAN-ID в заголовке.
    # Переход считается независимо от архива: уже существующий closed/PLAN-9.md новое закрытие не подавляет.
    closed = {m.group(1) for s, p in entries for m in [re.fullmatch(r"planning/plans/closed/" + PLAN_ID + r"[^/]*\.md", p, re.I)] if m and s == "A"}
    for path in INDEX_FILES:
        if status.get(path, "D") == "D":
            continue
        new_text, was = read_new(path), old_text(path)
        if path == "planning/PLANS.md" and not was:
            was = old_text("planning/plans.md")  # переименование plans.md -> PLANS.md: это не новые закрытия
        closed |= (closed_rows(new_text) | closed_sections(new_text)) - (closed_rows(was) | closed_sections(was))
        if path == "planning/PLANS.md":
            closed |= heading_ids(new_text) - heading_ids(was)
    # Миграция PLANS.md в реестр (этап 4a): записи с заголовками старого PLANS.md уже закрыты, их перенос в
    # closed/ и в строки индекса новым закрытием не считается.
    closed -= heading_ids(old_text("planning/PLANS.md")) | heading_ids(old_text("planning/plans.md"))  # и имя до переименования
    return ({("rm-add", "RM-" + n) for n in rm - old_rm} | {("close-plan", "PLAN-" + n) for n in closed}
            | e18_needed(entries, branch, old))


def check_commit(root, branch, entries, read_new):
    """Для commit-gate / pre-commit: список причин отказа (пусто = можно)."""
    found = (problem(root, k, i, branch) for k, i in sorted(needed(entries, read_new, branch=branch)))
    return [e for e in found if e]


# ---------------------------------------------------------------- merge-gate и SessionStart

def merge_claim(target_main, refs):
    """CLI-обёртка: ссылки -> (SHA, имя ветки без origin/) и общий захват."""
    if target_main != "1":
        return 0  # цель мержа не main: маркеры не нужны и не расходуются
    items, errors = [], []
    for ref in refs:
        tip = git("rev-parse", "--verify", "--quiet", ref + "^{commit}").strip()
        if tip:
            items.append((tip, re.sub(r"^origin/", "", ref)))
        else:
            errors.append("ссылка '%s' не найдена" % ref)
    return claim_items(items, errors)


def word_checks(items):
    """Слова владельца, нужные для мержа (SHA вершины, имя ветки) в main, БЕЗ захвата маркеров:
    [(вид, id, ветка, ошибка|None, путь маркера)]. Общая часть claim_items и merge-ready (--preflight)."""
    root, out_list = root_dir(), []
    for tip, name in items:
        base = git("merge-base", "main", tip).strip() or "HEAD"
        out = git("diff", "--name-status", "-z", "--no-renames", base, tip).split("\0")
        entries = [(out[i], out[i + 1]) for i in range(0, len(out) - 1, 2)]
        for k, i in sorted(needed(entries, lambda p, t=tip: git("show", "%s:%s" % (t, p)), old=base, branch=name)):
            out_list.append((k, i, name, problem(root, k, i, name, tip), marker_path(root, k, i, name)))
    return out_list


def claim_items(items, errors=()):
    """Весь набор маркеров всех мержимых (SHA вершины, имя ветки) проверяется и забирается разом:
    при любом отказе откат. Вызывается, только когда цель мержа — main."""
    errors, plan = list(errors), {}
    for k, i, name, err, path in word_checks(items):
        if err:
            errors.append(err)
        else:
            plan[path] = (k, i)
    claimed = []
    if not errors:
        for path, (k, i) in plan.items():
            if claim(path):
                claimed.append(path)
            else:
                errors.append("%s: разрешение уже использовано (параллельный мерж); %s" % (i, how_to(k, i)))
                break
    if errors:
        for path in claimed:  # не оставляем половину маркеров сожжённой
            release(path)
        for e in errors:
            print("Мерж заблокирован (E10/E11): %s" % e, file=sys.stderr)
        return 2
    return 0


def cleanup():
    root = Path(root_dir())
    directory = root / ".claude/state/owner-ok"
    if not directory.is_dir():
        return 0
    merged = set(git("branch", "--merged", "main", "--format=%(refname:short)").split())
    for path in [p for p in directory.iterdir() if p.is_file()] + list((directory / "claimed").glob("*")):
        data = read_marker(path) or {}
        branch = data.get("branch", "")
        done = branch in merged
        if path.parent.name != "claimed":
            # живой маркер уходит с влитой веткой, только если поверх точки выдачи есть коммиты; иначе — по сроку
            done = done and git("rev-parse", "--verify", "--quiet", "refs/heads/" + branch).strip() != data.get("sha")
        if expired(path, data) or done:
            path.unlink(missing_ok=True)
    return 0


# ---------------------------------------------------------------- запрет агенту выдавать слово владельца (I7)

OWNER_RE = re.compile(r"(?<![A-Za-z0-9_])owner-ok\.sh|(?<![A-Za-z0-9_])owner_ok\.py|\.claude/state/owner-ok")
READ_ONLY = {"grep", "rg", "cat", "ls", "head", "tail", "wc", "git", "stat", "diff"}


SHELL_KEYS = ("core.pager", "core.editor", "core.sshcommand", "core.fsmonitor", "core.askpass", "sequence.editor",
              "diff.external", "credential.helper", "gpg.program", "uploadpack.packobjectshook")


def shell_via_git(cmd):
    """-> причина, если git запускает произвольный shell: `-c alias.x=!…`, `-c` со значением на `!`, core.pager/editor/…,
    `git config alias.…`, `--exec-path`. Нужен, чтобы агент не собрал обход хуков через алиасы."""
    import commit_checks
    try:
        calls = commit_checks.parse(cmd, os.getcwd())
    except ValueError:
        return None
    for call in calls:
        for item in call["cfg"]:
            key, _, value = item.partition("=")
            if key.lower().startswith("alias.") or key.lower() in SHELL_KEYS or "!" in value or value.startswith("!"):
                return "git -c %s запускает произвольный shell" % key
        if any(o.startswith("--exec-path") for o in call["opts"]):
            return "git --exec-path подменяет git-команды"
        if call["sub"] == "config":
            words = [a.lower() for a in call["args"]]
            if any(w.startswith("alias.") or w in SHELL_KEYS for w in words) and not any(w in ("--get", "--get-all", "--list", "-l") for w in words):
                return "git config alias.*/pager/editor запускает произвольный shell"
    return None


def guard(cmd):
    """exit 2, если команда агента выдаёт/подделывает маркер или гонит shell через git. Чтение (grep, cat, git …) без перенаправления — можно."""
    import commit_checks  # strip_heredocs: тело heredoc — данные
    why = shell_via_git(cmd)
    if why:
        print("Заблокировано: %s (I4)." % why, file=sys.stderr)
        return 2
    for segment in re.split(r"[;&|\n]+", commit_checks.strip_heredocs(cmd)):
        words = segment.split()
        if OWNER_RE.search(segment) and (not words or words[0] not in READ_ONLY or ">" in segment):
            print("Слово владельца (E10/E11) выдаёт только владелец в своём терминале: .claude/scripts/owner-ok.sh. "
                  "Агенту запрещено запускать его и писать в .claude/state/owner-ok.", file=sys.stderr)
            return 2
    return 0


if __name__ == "__main__":
    action = sys.argv[1] if len(sys.argv) > 1 else ""
    try:
        if action == "merge-claim":
            sys.exit(merge_claim(sys.argv[2], sys.argv[3:]))
        if action == "edit-guard":  # FILE BRANCH
            why = e18_file_problem(sys.argv[2], sys.argv[3])
            if why:
                print("Заблокировано (E18): %s" % why, file=sys.stderr)
            sys.exit(2 if why else 0)
        if action == "guard":
            sys.exit(guard(sys.stdin.read()))
        sys.exit(cleanup())
    except Exception as exc:  # noqa: BLE001
        print("owner_ok internal error: %s: %s" % (type(exc).__name__, exc), file=sys.stderr)
        # merge-claim — fail-closed (слово владельца — условие мержа); остальное fail-open, как остальные хуки
        sys.exit(2 if action == "merge-claim" else 0)
