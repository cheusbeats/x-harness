#!/usr/bin/env bash
# registry.sh — реестры RM / PLAN / HF (PLAN-145, T2).
#
#   registry.sh next-id <RM|PLAN|HF>
#   registry.sh add <RM|HF|PLAN> <id|auto> <название> [--status S] [--date D] [--trigger T] [--slug S]
#   registry.sh migrate plans|journal --sha <SHA>   # одноразово: PLANS.md -> plans/closed/, JOURNAL.md -> hotfixes/ (этап 4)
#   registry.sh set-status <id> <статус>      # правит строку индекса и строку «Статус» файла
#   registry.sh set-trigger <RM-N> <текст>    # правит только колонку «Триггер / → PLAN-N» индекса (файл RM не трогает);
#                                             # нужно, чтобы сократить длинный триггер под лимит строки перед `→ PLAN-N`
#   registry.sh show <id>
#   registry.sh check [--registry rm|plan|hf|all]
# Глобально: --root <dir> подменяет корень репозитория (тесты).
# Коды: 0 чисто, 1 нарушения, 2 неверные аргументы.
#
# Индексы: RM planning/ROADMAP.md, HF planning/HOTFIXES.md, PLAN planning/ACTIVE_PLANS.md + PLANS.md.
# Строка: | [ID](путь) | Название | статус | дата | ... |. Лимит 160 символов — без первой колонки.
# PLAN: активные планы — ACTIVE_PLANS.md, закрытые — PLANS.md (тела в plans/closed/, aliases/registry_row в closed/_map.tsv).
# set-status <PLAN-N> закрыт|аннулирован переносит строку ACTIVE_PLANS.md -> PLANS.md (нужен plans/closed/PLAN-N.md).
set -euo pipefail

ROOT=""
ARGS=()
while [ $# -gt 0 ]; do
  case "$1" in
    --root) ROOT="${2:-}"; shift 2 ;;
    *) ARGS+=("$1"); shift ;;
  esac
done
[ -n "$ROOT" ] || ROOT="$(git rev-parse --show-toplevel)"
export REGISTRY_ROOT="$ROOT"
exec python3 - "${ARGS[@]+"${ARGS[@]}"}" <<'PY'
import contextlib, fcntl, os, re, subprocess, sys
from pathlib import Path

ROOT = Path(os.environ["REGISTRY_ROOT"])
PL = ROOT / "planning"
MAXLEN = 160
STATUSES = {
    "RM": [r"идея", r"отложена", r"стала PLAN-\d+(\.\d+)*", r"отклонена"],
    "PLAN": [r"черновик", r"в работе", r"на паузе", r"ждёт владельца", r"закрыт", r"аннулирован"],
    "HF": [r"влит", r"откачен"],
}
INDEX = {"RM": [PL / "ROADMAP.md"], "HF": [PL / "HOTFIXES.md"],
         "PLAN": [PL / "ACTIVE_PLANS.md", PL / "PLANS.md"]}
DIR = {"RM": PL / "roadmap", "HF": PL / "hotfixes", "PLAN": PL / "plans"}
# PLAN-реестр считается созданным, когда есть plans/closed/ (этап 4)
EXISTS = {"RM": lambda: INDEX["RM"][0].exists() and DIR["RM"].is_dir(),
          "HF": lambda: INDEX["HF"][0].exists() and DIR["HF"].is_dir(),
          "PLAN": lambda: (DIR["PLAN"] / "closed").is_dir()}
# старые планы, у которых исторически два документа (до E17); новые дубли — нарушение
LEGACY_MULTI_DOC = {"PLAN-60", "PLAN-105"}
NUM = r"\d+(?:\.\d+)*"
ROW = re.compile(r"^(?:\|\s*\[?|\[)((RM|PLAN|HF)-(" + NUM + r"))\]?")


def die(msg, code=2):
    print(msg, file=sys.stderr)
    sys.exit(code)


def status_ok(kind, s):
    return any(re.fullmatch(p, s) for p in STATUSES[kind])


def read(path):
    """Читает без нормализации окончаний строк; не-UTF8 → rc=2."""
    try:
        with open(path, encoding="utf-8", newline="") as f:
            return f.read()
    except UnicodeDecodeError:
        die(f"{path}: не UTF-8")


def _replace(src, dst):
    # тестовый крючок: REGISTRY_FAIL_REPLACE_N=n роняет n-ю замену (только в тестах)
    n = os.environ.get("REGISTRY_FAIL_REPLACE_N")
    if n:
        _replace.count += 1
        if _replace.count == int(n):
            raise OSError("simulated replace failure")
    os.replace(src, dst)


_replace.count = 0


def commit(writes):
    """Атомарно-подобная запись нескольких файлов [(path, text)]: .tmp рядом, замены по порядку,
    при сбое — возврат уже заменённых из сохранённых байтов (или удаление созданных), rc=2."""
    orig = {p: (p.read_bytes() if p.exists() else None) for p, _ in writes}
    tmps = []
    try:
        for p, text in writes:
            tmp = Path(str(p) + ".tmp")
            tmps.append(tmp)
            with open(tmp, "w", encoding="utf-8", newline="") as f:
                f.write(text)
        done = []
        try:
            for p, _ in writes:
                _replace(Path(str(p) + ".tmp"), p)
                done.append(p)
        except OSError as e:
            for p in done:
                if orig[p] is None:
                    p.unlink()
                else:
                    p.write_bytes(orig[p])
            die(f"запись не удалась, изменения откачены: {e}")
    finally:
        for tmp in tmps:
            if tmp.exists():
                tmp.unlink()


def write(path, text):
    commit([(path, text)])


@contextlib.contextmanager
def locked():
    """Эксклюзивная блокировка на время записи (add/set-status)."""
    d = ROOT / ".claude" / "state"
    d.mkdir(parents=True, exist_ok=True)
    with open(d / "registry.lock", "w") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        yield


def split_row(line):
    """Куски строки по неэкранированному «|»: «|» экранирован, только если перед ним нечётное число «\\»
    подряд (`\\|` — экранированный слеш и настоящий разделитель). parts[0] — до первого «|»."""
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


def row_text(line):
    """Текст строки без колонки id/ссылки (для лимита длины)."""
    parts = split_row(line.rstrip("\r\n"))
    return "|".join(parts[2:])


def cells(line):
    return [c.strip() for c in split_row(line.strip())[1:-1]]


def well_formed(line):
    """Строгая форма строки таблицы: ведущий и замыкающий «|» (неэкранированные)."""
    parts = split_row(line.rstrip())
    return len(parts) >= 3 and parts[0].strip() == "" and parts[-1].strip() == ""


def scan(kind):
    """([(path, lineno, line, id, cells, hdr)], [(метка, проблема)]) — строки вида kind и нарушения формы таблиц.

    hdr — {имя колонки в нижнем регистре: индекс} шапки своей таблицы. Строгая форма: ведущий и
    замыкающий «|», число ячеек строки и разделителя равно числу ячеек шапки."""
    out, bad = [], []
    for p in INDEX[kind]:
        if not p.exists():
            continue
        lines = read(p).split("\n")
        hdr, n, state = {}, 0, None  # state: None вне таблицы | "sep" ждём разделитель | "body"
        for i, line in enumerate(lines):
            at = f"{p.name}:{i + 1}"
            m = ROW.match(line)
            if not line.startswith("|") and not m:
                hdr, n, state = {}, 0, None  # конец таблицы
                continue
            if state is None and m:  # строка данных без шапки: колонок нет, править нельзя
                bad.append((m.group(1), f"{at}: строка таблицы без шапки"))
                n, state = -1, "body"
            elif state is None:
                hdr = {c.lower(): k for k, c in enumerate(cells(line))}
                n, state = len(cells(line)), "sep"
                if not well_formed(line):
                    bad.append((at, "шапка без ведущего/замыкающего «|»"))
                continue
            if state == "sep":
                state = "body"
                if not re.match(r"^\|[\s:|-]+\|\s*$", line) or len(cells(line)) != n:
                    bad.append((at, "разделитель шапки не `|---|` или число ячеек ≠ шапке"))
                continue
            label = m.group(1) if m else at
            if not well_formed(line):
                bad.append((label, f"{at}: нет ведущего/замыкающего «|»"))
            elif n >= 0 and len(cells(line)) != n:
                bad.append((label, f"{at}: ячеек {len(cells(line))}, в шапке {n}"))
            if m and m.group(2) == kind:
                out.append((p, i, line, m.group(1), cells(line), hdr))
    return out, bad


def rows(kind):
    return scan(kind)[0]


def col(hdr, c, name):
    """Значение колонки по имени шапки (None, если колонки нет)."""
    k = hdr.get(name)
    return c[k] if k is not None and k < len(c) else None


def files(kind):
    """{id: [имена файлов]}; PLAN: документы PLAN-N-*.md (closed/ отдельно)."""
    d = {}
    for f in sorted(DIR[kind].glob(f"{kind}-*.md")):
        m = re.match(rf"{kind}-({NUM})-.+\.md$", f.name)
        if m:
            d.setdefault(f"{kind}-{m.group(1)}", []).append(f.name)
    return d


def closed_files():
    d = {}
    for f in sorted((DIR["PLAN"] / "closed").glob("PLAN-*.md")):
        m = re.fullmatch(rf"PLAN-({NUM})\.md", f.name)
        if m:
            d.setdefault(f"PLAN-{m.group(1)}", []).append(f.name)
    return d


def load_map():
    """closed/_map.tsv -> [{heading, file, ids, row, flags}]; шапка (1-я строка) пропускается."""
    p = DIR["PLAN"] / "closed" / "_map.tsv"
    if not p.exists():
        return []
    out = []
    for n, line in enumerate(read(p).split("\n")):
        if n and line:
            h, f, ids, reg, flags = line.split("\t")
            out.append({"heading": h, "file": f, "ids": ids.split(), "row": reg == "yes", "flags": flags})
    return out


def map_problems():
    """Согласованность _map.tsv, plans/closed/ и PLANS.md (E4/E17). Новые закрытия (PLAN-N.md) в карте не обязаны быть."""
    closed, out = DIR["PLAN"] / "closed", []
    mp = load_map()
    names = {m["file"] for m in mp}
    canon = re.compile(rf"PLAN-{NUM}\.md")
    idx = INDEX["PLAN"][1]
    linked = set(re.findall(r"\]\(plans/closed/([^)]+)\)", read(idx))) if idx.exists() else set()
    for m in mp:
        if not (closed / m["file"]).is_file():
            out.append((m["file"], "файл из _map.tsv отсутствует"))
        if m["row"] and m["file"] not in linked:
            out.append((m["file"], "registry_row=yes, но строки в PLANS.md нет"))
        if not m["row"] and m["file"] in linked:
            out.append((m["file"], "registry_row=no, но строка в PLANS.md есть"))
    for f in sorted(linked - names):
        if not canon.fullmatch(f):
            out.append((f, "строка PLANS.md ведёт на файл вне _map.tsv"))
        elif not (closed / f).is_file():
            out.append((f, "строка PLANS.md ведёт на несуществующий файл"))
    for f in sorted(x.name for x in closed.glob("*.md")):
        if f not in names and f != "_preamble.md" and not canon.fullmatch(f):
            out.append((f, "файл в closed/ вне _map.tsv"))
    return out


def major(i):
    return int(re.search(r"\d+", i).group())


def next_id(kind):
    ids = [major(r[3]) for r in rows(kind)] + [major(i) for i in files(kind)]
    if kind == "PLAN" and (DIR["PLAN"] / "closed").is_dir():
        ids += [major(i) for i in closed_files()]
        ids += [major(i) for m in load_map() for i in m["ids"]]
    return f"{kind}-{max(ids, default=0) + 1}"


def check(kind):
    if not EXISTS[kind]():
        print(f"{kind}: реестр ещё не создан (этап 4) — пропуск")
        return []
    rs, bad = scan(kind)
    seen = {}
    for p, i, line, id_, c, hdr in rs:
        seen.setdefault(id_, []).append(p.name)
        text = row_text(line)
        if len(text) > MAXLEN:
            bad.append((id_, f"текст строки {len(text)} > {MAXLEN} символов"))
        st, dt = col(hdr, c, "статус"), col(hdr, c, "дата")
        if st is None or dt is None:
            bad.append((id_, "в шапке таблицы нет колонок «Статус»/«Дата»"))
            continue
        if not status_ok(kind, st):
            bad.append((id_, f"статус «{st}» вне словаря"))
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", dt):
            bad.append((id_, f"дата «{dt}» не YYYY-MM-DD"))
    for id_, where in seen.items():
        if len(where) > 1:
            bad.append((id_, f"{len(where)} строк индекса ({', '.join(where)})"))
    fs = files(kind)
    for id_, names in fs.items():
        if len(names) > 1 and id_ not in LEGACY_MULTI_DOC:
            bad.append((id_, f"{len(names)} файлов: {', '.join(names)}"))
    cl = closed_files() if kind == "PLAN" else {}
    for id_, names in cl.items():
        if len(names) > 1:
            bad.append((id_, f"{len(names)} архивных записей"))
    if kind != "PLAN":
        for id_ in fs:
            if id_ not in seen:
                bad.append((id_, "файл без строки индекса"))
        for id_ in seen:
            if id_ not in fs:
                bad.append((id_, "строка индекса без файла"))
    else:
        mp = load_map()
        alias = {i: m["ids"][0] for m in mp for i in m["ids"][1:]}
        no_row = {m["ids"][0] for m in mp if m["ids"] and not m["row"]}
        for id_ in fs:
            if id_ not in seen and alias.get(id_) not in seen and id_ not in no_row:
                bad.append((id_, "документ плана без строки индекса"))
        for id_ in cl:
            if id_ not in seen and id_ not in no_row:
                bad.append((id_, "архивная запись без строки индекса"))
        bad += map_problems()
        for p, i, line, id_, c, hdr in rs:
            st = col(hdr, c, "статус")
            if st in ("закрыт", "аннулирован") and id_ not in cl:
                bad.append((id_, f"{st}, но нет plans/closed/{id_}.md"))
    return bad


def guard(kind):
    """Fail-closed: в индексе есть нарушения формы — ничего не пишем (rc=2)."""
    bad = scan(kind)[1]
    if bad:
        die("индекс повреждён, запись отменена: " + "; ".join(f"{a} — {b}" for a, b in bad[:3]))


def find_row(id_):
    kind = id_.split("-")[0]
    hit = [r for r in rows(kind) if r[3] == id_]
    return kind, hit


def set_cell(text, lineno, idx, value):
    """Новый текст индекса с одной изменённой ячейкой (idx — индекс среди ячеек строки)."""
    lines = text.split("\n")
    parts = split_row(lines[lineno])
    parts[idx + 1] = f" {value} "
    lines[lineno] = "|".join(parts)
    return "\n".join(lines)


def insert_row(text, kind, row, id_):
    """Вставляет строку в индекс по возрастанию номера (после последней строки вида, иначе в конец)."""
    cr = "\r" if "\r\n" in text else ""
    lines = text.split("\n")
    pos = None
    last = None
    for i, line in enumerate(lines):
        m = ROW.match(line)
        if m and m.group(2) == kind:
            last = i
            if pos is None and major(m.group(1)) > major(id_):
                pos = i
    if pos is None:
        pos = last + 1 if last is not None else (len(lines) - 1 if lines[-1] == "" else len(lines))
    lines.insert(pos, row + cr)
    return "\n".join(lines)


def cmd_add(kind, id_, title, opt):
    if kind not in ("RM", "HF", "PLAN"):
        die("kind: RM|HF|PLAN")
    status = opt.get("--status", {"RM": "идея", "HF": "влит", "PLAN": "черновик"}[kind])
    if not status_ok(kind, status):
        die(f"статус «{status}» вне словаря {kind}")
    date = opt.get("--date") or __import__("datetime").date.today().isoformat()
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date):
        die(f"дата «{date}» не YYYY-MM-DD")
    trigger = opt.get("--trigger", "нет")
    for name, v in (("название", title), ("триггер", trigger)):
        if "|" in v or "\n" in v or "\r" in v:
            die(f"{name}: нельзя «|» и переводы строк")
    if not title.strip():
        die("пустое название")
    with locked():
        guard(kind)
        if id_ == "auto":
            id_ = next_id(kind)
        if not re.fullmatch(rf"{kind}-{NUM}", id_):
            die(f"id должен быть вида {kind}-N или auto")
        if any(r[3] == id_ for r in rows(kind)):
            die(f"{id_} уже существует")
        if id_ in files(kind) and kind != "PLAN":
            die(f"{id_} уже существует")
        slug = opt.get("--slug") or re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:40].strip("-") or "item"
        fname = f"{id_}-{slug}.md"
        existing = files(kind).get(id_) if kind == "PLAN" else None  # документ уже есть: регистрируем его, не пишем заново
        if existing:
            fname = existing[0]
        label = "Записано" if kind == "RM" else "Дата"
        body = f"# {id_} — {title}\n\n- **Статус:** {status}\n- **{label}:** {date}\n"
        if kind == "PLAN":
            body = f"# {id_} — {title}\n\n**Статус:** {status}\n\n## Резюме\n\n\n"
            row = f"| [{id_}](plans/{fname}) | {title} | {status} | {date} | — | Claude |"
            head = "| PLAN | Название | Статус | Дата | Влит-в | Автор |\n|---|---|---|---|---|---|"
        elif kind == "RM":
            body += f"- **Триггер владельца:** {trigger}\n\n## Суть\n\n\n"
            row = f"| [{id_}](roadmap/{fname}) | {title} | {status} | {date} | {trigger} |"
            head = "| RM | Название | Статус | Дата | Триггер / → PLAN-N |\n|---|---|---|---|---|"
        else:
            body += f"- **Влит в:** {trigger}\n\n"
            row = f"| [{id_}](hotfixes/{fname}) | {title} | {status} | {date} | {trigger} | Claude |"
            head = "| HF | Название | Статус | Дата | Влит-в | Автор |\n|---|---|---|---|---|---|"
        if len(row_text(row)) > MAXLEN:
            die(f"текст строки {len(row_text(row))} > {MAXLEN} символов")
        DIR[kind].mkdir(parents=True, exist_ok=True)
        idx = INDEX[kind][0]
        # сначала читаем и проверяем индекс, потом пишем оба файла
        text = read(idx) if idx.exists() else f"# {kind} — реестр\n\n{head}\n"
        new_text = insert_row(text, kind, row, id_)
        commit([(idx, new_text)] if existing else [(DIR[kind] / fname, body), (idx, new_text)])
    print(f"{id_} → {fname}")


def cmd_set_status(id_, status):
    with locked():
        guard(id_.split("-")[0] if re.match(r"^(RM|PLAN|HF)-", id_) else "RM")
        kind, hit = find_row(id_)
        if len(hit) != 1:
            die(f"{id_}: строк индекса {len(hit)}")
        if not status_ok(kind, status):
            die(f"статус «{status}» вне словаря {kind}")
        p, i, line, _, c, hdr = hit[0]
        k = hdr.get("статус")
        if k is None:
            die(f"{p.name}: в шапке таблицы нет колонки «Статус»")
        new_idx = set_cell(read(p), i, k, status)
        writes = [(p, new_idx)]
        done_idx = INDEX["PLAN"][1]
        if kind == "PLAN" and status in ("закрыт", "аннулирован") and p != done_idx:
            # закрытие: строка уходит из ACTIVE_PLANS.md в PLANS.md; тело записи пишет автор заранее
            if not (DIR["PLAN"] / "closed" / f"{id_}.md").is_file():
                die(f"{id_}: сначала создай plans/closed/{id_}.md (текст записи о закрытии)")
            lines = new_idx.split("\n")
            moved = re.sub(r"\]\([^)]*\)", f"](plans/closed/{id_}.md)", lines.pop(i).rstrip("\r"), count=1)
            writes = [(p, "\n".join(lines)), (done_idx, insert_row(read(done_idx), "PLAN", moved, id_))]
            # карта закрытых (_map.tsv): новая запись тоже получает строку (heading из заголовка записи, registry_row=yes)
            mp = DIR["PLAN"] / "closed" / "_map.tsv"
            if f"{id_}.md" not in {m["file"] for m in load_map()}:
                head = read(DIR["PLAN"] / "closed" / f"{id_}.md").split("\n", 1)[0].lstrip("#").strip() or id_
                head = re.sub(r"\s+", " ", head).strip()  # TAB/CR/LF в заголовке порвали бы колонки _map.tsv
                text = read(mp) if mp.exists() else "heading\tfile\tids\tregistry_row\tflags\n"
                text += ("" if text.endswith("\n") else "\n") + f"{head}\t{id_}.md\t{id_}\tyes\t\n"
                writes.append((mp, text))
        if kind in ("RM", "HF"):
            fs = files(kind).get(id_, [])
            if len(fs) == 1:
                f = DIR[kind] / fs[0]
                writes.append((f, re.sub(r"^(- \*\*Статус:\*\*)[^\r\n]*",
                                         lambda m: f"{m.group(1)} {status}", read(f), count=1, flags=re.M)))
        commit(writes)  # все чтения (UTF-8) уже позади
    print(f"{id_} → {status}")


def cmd_set_trigger(id_, text):
    """Меняет ячейку «Триггер…» строки RM в индексе. Итоговая строка обязана уложиться в MAXLEN."""
    if not id_.startswith("RM-"):
        die("set-trigger: только RM-N")
    if not text.strip() or "|" in text or "\n" in text or "\r" in text:
        die("триггер: непустой, без «|» и переводов строк")
    with locked():
        guard("RM")
        kind, hit = find_row(id_)
        if len(hit) != 1:
            die(f"{id_}: строк индекса {len(hit)}")
        p, i, line, _, c, hdr = hit[0]
        k = next((v for n, v in hdr.items() if n.startswith("триггер")), None)
        if k is None:
            die(f"{p.name}: в шапке таблицы нет колонки «Триггер»")
        new_text = set_cell(read(p), i, k, text.strip())
        new_line = new_text.split("\n")[i]
        if len(row_text(new_line)) > MAXLEN:
            die(f"текст строки {len(row_text(new_line))} > {MAXLEN} символов")
        commit([(p, new_text)])
    print(f"{id_} триггер → {text.strip()}")


def cmd_show(id_):
    kind, hit = find_row(id_)
    if not hit:
        die(f"{id_}: нет в индексе")
    for p, i, line, _, _, _ in hit:
        print(line)
    for n in files(kind).get(id_, []):
        print(DIR[kind].relative_to(ROOT) / n)


def _clean_title(t):
    """Заголовок -> текст ячейки: без пометок «(закрыт …)», `|` экранирован, не длиннее 72 символов."""
    t = re.sub(r"\s*[—-]?\s*\((?:закрыт|аннулирован|готов)[^)]*\)?", "", t)
    t = re.sub(r"\s+—\s+закрыт\s+\d{4}-\d{2}-\d{2}.*$", "", t).strip().replace("|", "\\|")
    return t if len(t) <= 72 else t[:71].rstrip() + "…"


def _intro_date(heading, sha):
    """Дата первого появления заголовка в PLANS.md (для записей, где дата закрытия в заголовке не указана)."""
    out = subprocess.run(["git", "-C", str(ROOT), "log", "--reverse", "--format=%as", "-S" + heading, sha, "--",
                          "planning/plans.md"], capture_output=True, text=True).stdout.split()
    return out[0] if out else subprocess.run(["git", "-C", str(ROOT), "log", "-1", "--format=%as", sha],
                                             capture_output=True, text=True).stdout.strip()


# impl-документы и номера, которых нет в заголовках PLANS.md, но закрытые записью родителя (документ PLAN-X.1-*.md -> строка X)
EXTRA_ALIASES = {"PLAN-62": ["PLAN-62.1"], "PLAN-65": ["PLAN-65.1"], "PLAN-67": ["PLAN-67.1"], "PLAN-69": ["PLAN-69.1"],
                 "PLAN-73": ["PLAN-72"], "PLAN-78": ["PLAN-78.1"], "PLAN-79": ["PLAN-79.1"], "PLAN-84": ["PLAN-84.1", "PLAN-85.1"],
                 "PLAN-97": ["PLAN-97.1"], "PLAN-106": ["PLAN-106.1"]}


def cmd_migrate_journal(sha):
    """JOURNAL.md из SHA -> hotfixes/HF-1…N-<хеш>.md (запись = байты от `- 20…` до следующей записи или `## `, без изменений),
    seam-файлы для заголовков месяцев, _preamble.md, _order.txt, _map.tsv и индекс HOTFIXES.md. Проверка: verify-journal-migration.sh."""
    out = DIR["HF"]
    if (out / "_map.tsv").exists() or INDEX["HF"][0].exists():
        die("уже мигрировано: HOTFIXES.md или hotfixes/_map.tsv существует")
    res = subprocess.run(["git", "-C", str(ROOT), "show", f"{sha}:planning/JOURNAL.md"], capture_output=True)
    if res.returncode:
        die(f"git show {sha}:planning/JOURNAL.md не удался")
    data = res.stdout
    if b"\r" in data:
        die("исходник с CRLF — миграция отказана")
    starts = [m.start() for m in re.finditer(rb"(?m)^(?:- 20|## )", data)] + [len(data)]
    preamble, order, maprows, idx_rows, bodies, n, seams = data[:starts[0]], [], [], [], {}, 0, 0
    head = re.compile(r"- (\d{4}-\d{2}-\d{2}) · (.+?) · (.+?) — ", re.S)
    for a, b in zip(starts, starts[1:]):
        body = data[a:b]
        line = body.split(b"\n", 1)[0].decode("utf-8")
        flags = [] if body.endswith(b"\n") else ["no_final_lf"]
        if line.startswith("## "):
            seams += 1
            fname, ids, row = f"_seam-{seams}.md", "", "no"
            flags.append("seam")
        else:
            m = head.match(line)
            assert m, line
            n += 1
            h = re.search(r"`([0-9a-f]{7,40})`", m.group(2))
            fname, ids, row = f"HF-{n}-{h.group(1) if h else 'journal'}.md", f"HF-{n}", "yes"
            title = line[m.end():].replace("|", "\\|")
            title = title if len(title) <= 60 else title[:59].rstrip() + "…"
            merged = (h.group(1) if h else m.group(2).strip("`")).replace("|", "\\|")
            merged = merged if len(merged) <= 40 else merged[:39] + "…"
            author = m.group(3).replace("|", "\\|")[:30]
            idx_rows.append(f"| [HF-{n}](hotfixes/{fname}) | {title} | влит | {m.group(1)} | {merged} | {author} |")
        bodies[fname] = body
        order.append(fname)
        maprows.append("\t".join([line[:60].replace("\t", " "), fname, ids, row, ",".join(flags)]))
    out.mkdir(parents=True, exist_ok=True)
    for fname, body in bodies.items():
        (out / fname).write_bytes(body)
    (out / "_preamble.md").write_bytes(preamble)
    write(out / "_order.txt", "\n".join(order) + "\n")
    write(out / "_map.tsv", "\n".join(["heading\tfile\tids\tregistry_row\tflags"] + maprows) + "\n")
    write(INDEX["HF"][0], (
        "# Хотфиксы — реестр\n\n"
        "Тела — `hotfixes/HF-N-*.md` (мигрированные из журнала — дословно). Правка — только `registry.sh add HF`.\n\n"
        "| HF | Название | Статус | Дата | Влит-в | Автор |\n|---|---|---|---|---|---|\n" + "\n".join(idx_rows) + "\n"))
    print(f"{n} записей -> hotfixes/, seam-файлов {seams}, строк индекса {len(idx_rows)}")


def cmd_migrate(what, sha):
    """PLANS.md из SHA -> closed/<файлы> (тела побайтно), _preamble.md, _order.txt, _map.tsv и новый PLANS.md-индекс.
    Единица — заголовок `## `. Проверка: .claude/scripts/verify-plans-migration.sh."""
    if what == "journal":
        return cmd_migrate_journal(sha)
    if what != "plans":
        die("migrate plans|journal --sha <SHA>")
    closed = DIR["PLAN"] / "closed"
    if (closed / "_map.tsv").exists():
        die("уже мигрировано: closed/_map.tsv существует")
    res = subprocess.run(["git", "-C", str(ROOT), "show", f"{sha}:planning/plans.md"], capture_output=True)
    if res.returncode:
        die(f"git show {sha}:planning/plans.md не удался")
    data = res.stdout
    if b"\r" in data:
        die("исходник с CRLF — миграция отказана")
    starts = [m.start() for m in re.finditer(rb"(?m)^## ", data)] + [len(data)]
    used, order, maprows, idx_rows, bodies = set(), [], [], [], {}
    for a, b in zip(starts, starts[1:]):
        body = data[a:b]
        h = body.split(b"\n", 1)[0].decode("utf-8")[3:]
        assert "\t" not in h, h
        pm = re.match(rf"PLAN-({NUM})(?:\s*/\s*(?:PLAN-)?{NUM})*", h)
        flags = [] if body.endswith(b"\n") else ["no_final_lf"]
        ids, in_index, idcell = [], True, None
        if h.startswith("Записи без номера"):
            fname, in_index = "_seam-unnumbered.md", False
            flags.append("seam")
        elif pm and f"PLAN-{pm.group(1)}" not in used:
            ids = [f"PLAN-{x}" for x in re.findall(NUM, pm.group(0))]
            fname = f"{ids[0]}.md"
            used.add(ids[0])
            in_index = ids[0] != "PLAN-27"
        elif pm:  # повторный заголовок того же id
            n = sum(1 for f in order if f.startswith(f"_dup-PLAN-{pm.group(1)}-")) + 2
            fname, idcell = f"_dup-PLAN-{pm.group(1)}-{n}.md", f"_dup-PLAN-{pm.group(1)}-{n}"
            flags.append("dup")
        else:
            slug = re.sub(r"[^a-z0-9]+", "-", h.split(" — ")[0].lower()).strip("-")
            fname, in_index = f"_unnumbered-{slug}.md", slug != "pending"
            idcell = fname[:-3]
            flags.append("unnumbered")
        assert fname not in bodies, fname
        bodies[fname] = body
        order.append(fname)
        single = len(ids) == 1
        if ids and ids[0] in EXTRA_ALIASES:
            ids += EXTRA_ALIASES[ids[0]]
            flags.append("extra_aliases")
        maprows.append("\t".join([h, fname, " ".join(ids), "yes" if in_index else "no", ",".join(flags)]))
        if in_index:
            title = _clean_title(h.split(" — ", 1)[1] if single and " — " in h else h)
            date = (re.search(r"\d{4}-\d{2}-\d{2}", h) or [None])[0] or _intro_date("## " + h, sha)
            merged = re.search(r"(?:merge|мерж)\W+`?([0-9a-f]{7,40})", h)
            st = "аннулирован" if "аннулирован" in h else "закрыт"
            idx_rows.append(f"| [{idcell or ids[0]}](plans/closed/{fname}) | {title} | {st} | {date} | "
                            f"{merged.group(1) if merged else '—'} | Claude |")
    closed.mkdir(parents=True, exist_ok=True)
    for fname, body in bodies.items():
        (closed / fname).write_bytes(body)
    (closed / "_preamble.md").write_bytes(data[:starts[0]])
    write(closed / "_order.txt", "\n".join(order) + "\n")
    write(closed / "_map.tsv", "\n".join(["heading\tfile\tids\tregistry_row\tflags"] + maprows) + "\n")
    write(INDEX["PLAN"][1], (
        "# Закрытые планы — реестр\n\n"
        "Тела записей — `plans/closed/` (дословно). Активные — [ACTIVE_PLANS.md](ACTIVE_PLANS.md). "
        "Правка — только `registry.sh`; псевдонимы — `closed/_map.tsv`.\n\n"
        "| PLAN | Название | Статус | Дата | Влит-в | Автор |\n|---|---|---|---|---|---|\n" + "\n".join(idx_rows) + "\n"))
    print(f"{len(order)} секций -> closed/, строк индекса {len(idx_rows)}")


def main(a):
    if not a:
        die("usage: registry.sh next-id|add|set-status|show|check|migrate")
    c, rest = a[0], a[1:]
    if c == "next-id" and len(rest) == 1 and rest[0] in STATUSES:
        print(next_id(rest[0]))
    elif c == "add" and len(rest) >= 3:
        opt, pos, k = {}, [], 0
        while k < len(rest):
            if rest[k] in ("--status", "--date", "--trigger", "--slug") and k + 1 < len(rest):
                opt[rest[k]] = rest[k + 1]; k += 2
            else:
                pos.append(rest[k]); k += 1
        if len(pos) != 3:
            die("add <RM|HF|PLAN> <id|auto> <название> [--status S] [--date D] [--trigger T] [--slug S]")
        cmd_add(pos[0], pos[1], pos[2], opt)
    elif c == "migrate" and len(rest) == 3 and rest[1] == "--sha":
        cmd_migrate(rest[0], rest[2])
    elif c == "set-status" and len(rest) == 2:
        cmd_set_status(*rest)
    elif c == "set-trigger" and len(rest) == 2:
        cmd_set_trigger(*rest)
    elif c == "show" and len(rest) == 1:
        cmd_show(rest[0])
    elif c == "check":
        reg = "all"
        if rest:
            if len(rest) != 2 or rest[0] != "--registry" or rest[1] not in ("rm", "plan", "hf", "all"):
                die("check [--registry rm|plan|hf|all]")
            reg = rest[1]
        kinds = ["RM", "PLAN", "HF"] if reg == "all" else [reg.upper()]
        bad = [b for k in kinds for b in check(k)]
        for id_, msg in bad:
            print(f"{id_} — {msg}")
        sys.exit(1 if bad else 0)
    else:
        die("неверные аргументы")


main(sys.argv[1:])
PY
