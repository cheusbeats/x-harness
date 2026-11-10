#!/usr/bin/env python3
"""Читатель paths.conf (PLAN-145, T15). Формат файла описан в самом paths.conf.

  paths.py classify [--root DIR] ПУТЬ...   -> «вид<TAB>путь» на строку:
                                              code|planning|exempt|unknown
  paths.py guarded ПУТЬ                    -> exit 0, если planning/<имя> под E6 (registry-guard)
  paths.py planning-root-ok ПУТЬ           -> exit 0, если путь planning/... допустим в корне planning/ (E9)
  paths.py unclassified [--root DIR]       -> корневые элементы `git ls-files` без класса
"""
import fnmatch
import subprocess
import sys
from pathlib import Path

CONF = Path(__file__).resolve().parent / "paths.conf"


def load(conf=CONF):
    """{вид: [значения]} — комментарии после `#` и пустые строки отбрасываются."""
    return parse(conf.read_text(encoding="utf-8"))


def parse(text):
    out = {}
    for line in text.splitlines():
        line = line.split("#", 1)[0].strip()
        if line:
            kind, _, value = line.partition(" ")
            out.setdefault(kind, []).append(value.strip())
    return out


def rel(path, root):
    p = Path(path)
    if p.is_absolute() and root:
        try:
            return p.resolve().relative_to(Path(root).resolve()).as_posix()
        except ValueError:
            return p.as_posix()
    s = p.as_posix()
    return s[2:] if s.startswith("./") else s


def classify(path, conf):
    first = path.split("/", 1)[0]
    for kind in ("planning", "exempt", "code"):
        if any(fnmatch.fnmatch(first, mask) for mask in conf.get(kind, [])):
            return kind
    return "unknown"


def e18_on(conf):
    """E18 включён строкой `e18 on` (по умолчанию и при `e18 off` — молчит)."""
    return conf.get("e18", ["off"])[-1] == "on"


def e18_protected(path, conf):
    """Путь под защитой E18: префикс каталога (`x/`) или точное имя; сам вид guard-e18 в paths.conf."""
    # корень каталога тоже защищён: gitlink/symlink на .githooks, .claude/hooks и т.п. подменяет всё содержимое
    return any(path.startswith(p) or path == p.rstrip("/") if p.endswith("/") else path == p for p in conf.get("guard-e18", []))


def planning_root_ok(path, conf):
    parts = path.split("/")
    return len(parts) >= 2 and parts[0] == "planning" and parts[1] in conf.get("planning-root", [])


# guard-stage4 включается САМ, когда существует новая структура реестра (иначе registry.sh не умеет
# менять этот файл, и защита парализовала бы работу): имя файла -> каталог внутри planning/.
STAGE4_READY = {"PLANS.md": "plans/closed", "ACTIVE_PLANS.md": "plans/closed",
                "HOTFIXES.md": "hotfixes", "JOURNAL.md": "hotfixes"}


def is_guarded(path, conf, planning_dir=None):
    parts = path.split("/")
    if len(parts) < 2 or parts[-2] != "planning":
        return False
    # имя сверяем без учёта регистра: на регистронезависимой ФС (macOS) plans.md и PLANS.md — один файл
    name = next((n for n in {**{g: g for g in conf.get("guard", [])}, **{k: k for k in STAGE4_READY}} if n.lower() == parts[-1].lower()), parts[-1])
    if name in conf.get("guard", []):
        return True
    ready = STAGE4_READY.get(name)
    return bool(ready and name in conf.get("guard-stage4", []) and planning_dir and (Path(planning_dir) / ready).is_dir())


def main(argv):
    conf = load()
    root = None
    if "--root" in argv:
        i = argv.index("--root")
        root = argv[i + 1]
        del argv[i:i + 2]
    cmd, args = argv[0], argv[1:]
    if cmd == "classify":
        for a in args:
            p = rel(a, root)
            print("%s\t%s" % (classify(p, conf), p))
    elif cmd == "guarded":
        return 0 if is_guarded(rel(args[0], root), conf, Path(args[0]).resolve().parent) else 1
    elif cmd == "planning-root-ok":
        return 0 if planning_root_ok(rel(args[0], root), conf) else 1
    elif cmd == "unclassified":
        files = subprocess.run(["git", "-C", root or ".", "ls-files"], capture_output=True, text=True, check=True).stdout.split("\n")
        roots = sorted({f.split("/", 1)[0] for f in files if f})
        for r in roots:
            if classify(r + "/x", conf) == "unknown" and classify(r, conf) == "unknown":
                print(r)
    else:
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
