#!/usr/bin/env bash
# verify.sh — parity-проверка обвязки.
#   full:     MANIFEST.sha256 <=> harness/ <=> установленная копия
#   planning: harness-источники + profiles/planning/ <=> установленный планировочный слой
#             (+ реестры planning/ и git core.hooksPath)
# Коды: 0 — совпадает, 1 — расхождения, 2 — ошибка аргументов/окружения.
set -euo pipefail

ROOT="$(cd -- "$(dirname -- "$0")" && pwd)"
HARNESS="$ROOT/harness"
PROFILES="$ROOT/profiles"
MANIFEST="$ROOT/MANIFEST.sha256"
PROJECT=""
PROFILE="auto"
TESTS=0
WRITE=0
QUIET=0

usage() {
  cat <<'EOF'
Usage: ./verify.sh [options]
  --project DIR   проверить установленную копию в проекте
  --profile NAME  auto (по умолчанию: planning при .claude/planning.conf, иначе full) | full | planning
  --tests         дополнительно прогнать тесты (full — .claude/hooks/test_*.py; planning — tests/acceptance-planning.sh)
  --manifest      пересчитать MANIFEST.sha256 по harness/ и выйти (после обновления копии)
  --quiet         печатать только итог
  -h, --help
EOF
}

while [ $# -gt 0 ]; do
  case "$1" in
    --project) PROJECT="$2"; shift 2 ;;
    --profile) PROFILE="$2"; shift 2 ;;
    --tests) TESTS=1; shift ;;
    --manifest) WRITE=1; shift ;;
    --quiet) QUIET=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "verify.sh: неизвестный аргумент $1" >&2; exit 2 ;;
  esac
done

[ -d "$HARNESS" ] || { echo "verify.sh: нет harness/" >&2; exit 2; }
command -v python3 >/dev/null || { echo "verify.sh: нужен python3" >&2; exit 2; }
command -v git >/dev/null || { echo "verify.sh: нужен git" >&2; exit 2; }

case "$PROFILE" in auto|full|planning) ;; *) echo "verify.sh: --profile auto|full|planning" >&2; exit 2 ;; esac
if [ "$PROFILE" = auto ]; then
  if [ -n "$PROJECT" ] && [ -f "$PROJECT/.claude/planning.conf" ]; then
    PROFILE="planning"
  else
    PROFILE="full"
  fi
fi
if [ "$PROFILE" = planning ] && [ -z "$PROJECT" ] && [ "$WRITE" = 0 ]; then
  echo "verify.sh: для planning нужен --project DIR" >&2; exit 2
fi

# --- harness <=> MANIFEST ---------------------------------------------------
python3 - "$HARNESS" "$MANIFEST" "$WRITE" "$QUIET" <<'PY'
import hashlib, os, sys

harness, manifest, write, quiet = sys.argv[1], sys.argv[2], sys.argv[3] == "1", sys.argv[4] == "1"

def collect(root):
    out = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames.sort()
        for d in list(dirnames):
            p = os.path.join(dirpath, d)
            if os.path.islink(p):
                out.append(("L", os.readlink(p), os.path.relpath(p, root)))
                dirnames.remove(d)
        for f in sorted(filenames):
            p = os.path.join(dirpath, f)
            rel = os.path.relpath(p, root)
            if os.path.islink(p):
                out.append(("L", os.readlink(p), rel))
            else:
                st = os.stat(p)
                h = hashlib.sha256(open(p, "rb").read()).hexdigest()
                out.append(("H", "%o" % (st.st_mode & 0o777), h, rel))
    out.sort(key=lambda x: x[-1])
    return out

def render(entries):
    lines = []
    for e in entries:
        if e[0] == "H":
            lines.append("H %s %s %s" % (e[1], e[2], e[3]))
        else:
            lines.append("L %s %s" % (e[1], e[2]))
    return "\n".join(lines) + "\n"

def parse(text):
    d = {}
    for line in text.splitlines():
        if not line.strip():
            continue
        parts = line.split(" ", 3)
        if parts[0] == "H":
            d[parts[3]] = ("H", parts[1], parts[2])
        elif parts[0] == "L":
            d[parts[2]] = ("L", parts[1])
    return d

entries = collect(harness)
if write:
    with open(manifest, "w", encoding="utf-8") as fh:
        fh.write(render(entries))
    print("manifest: записано %d записей в %s" % (len(entries), manifest))
    sys.exit(0)

if not os.path.exists(manifest):
    print("verify: нет MANIFEST.sha256 (создай: ./verify.sh --manifest)", file=sys.stderr)
    sys.exit(1)

expected = parse(open(manifest, encoding="utf-8").read())
actual = {}
for e in entries:
    if e[0] == "H":
        actual[e[3]] = ("H", e[1], e[2])
    else:
        actual[e[2]] = ("L", e[1])

problems = []
for path, val in sorted(expected.items()):
    if path not in actual:
        problems.append("missing: %s" % path)
    elif actual[path] != val:
        problems.append("changed: %s" % path)
for path in sorted(set(actual) - set(expected)):
    problems.append("extra:   %s" % path)

if problems:
    print("verify: harness drift (%d)" % len(problems), file=sys.stderr)
    for p in problems:
        print("  " + p, file=sys.stderr)
    sys.exit(1)
if not quiet:
    print("verify: harness OK (%d файлов/симлинков) <=> MANIFEST.sha256" % len(expected))
PY

# --- установленная копия ----------------------------------------------------
hooks_check() {
  if ! git -C "$PROJECT" rev-parse --show-toplevel >/dev/null 2>&1; then
    echo "verify: WARN проект без git — git-хуки не активны" >&2
    return 0
  fi
  hooks="$(git -C "$PROJECT" config --get core.hooksPath || true)"
  if [ "$hooks" = ".githooks" ]; then
    echo "verify: git core.hooksPath=.githooks OK"
  else
    echo "verify: git core.hooksPath='$hooks' (ожидалось .githooks) — подключи .claude/scripts/install-githooks.sh" >&2
    return 1
  fi
}

if [ -n "$PROJECT" ]; then
  [ -d "$PROJECT" ] || { echo "verify.sh: нет проекта $PROJECT" >&2; exit 2; }
  PROJECT="$(cd "$PROJECT" && pwd -P)"

  if [ "$PROFILE" = full ]; then
    python3 - "$HARNESS" "$MANIFEST" "$PROJECT" <<'PY'
import hashlib, os, sys

harness, manifest, project = sys.argv[1], sys.argv[2], sys.argv[3]
expected = {}
for line in open(manifest, encoding="utf-8"):
    line = line.rstrip("\n")
    if not line:
        continue
    parts = line.split(" ", 3)
    if parts[0] == "H":
        expected[parts[3]] = ("H", parts[1], parts[2])
    elif parts[0] == "L":
        expected[parts[2]] = ("L", parts[1])

problems = []
for rel, val in sorted(expected.items()):
    p = os.path.join(project, rel)
    if not os.path.lexists(p):
        problems.append("missing: %s" % rel)
        continue
    if val[0] == "L":
        if not os.path.islink(p) or os.readlink(p) != val[1]:
            problems.append("link:    %s" % rel)
        continue
    if os.path.islink(p):
        problems.append("not file: %s" % rel)
        continue
    st = os.stat(p)
    mode = "%o" % (st.st_mode & 0o777)
    h = hashlib.sha256(open(p, "rb").read()).hexdigest()
    if h != val[2]:
        problems.append("content: %s" % rel)
    if mode != val[1]:
        problems.append("mode:    %s (%s != %s)" % (rel, mode, val[1]))

if problems:
    print("verify: проект НЕ идентичен обвязке (%d)" % len(problems), file=sys.stderr)
    for p in problems:
        print("  " + p, file=sys.stderr)
    sys.exit(1)
print("verify: проект идентичен обвязке по %d файлам/симлинкам" % len(expected))
PY
  else
    python3 - "$ROOT" "$HARNESS" "$PROJECT" <<'PY'
import hashlib, os, sys
from pathlib import Path

root, harness, project = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
profiles = root / "profiles" / "planning"

installed = {
    Path("AGENTS.md"): profiles / "AGENTS.md",
    Path("planning/README.md"): profiles / "planning" / "README.md",
    Path(".claude/settings.json"): profiles / ".claude" / "settings.json",
    Path(".claude/planning.conf.template"): profiles / ".claude" / "planning.conf.template",
}
for d in (".claude/scripts", ".claude/hooks", ".githooks"):
    base = profiles / d
    if not base.is_dir():
        print("verify: нет каталога профиля %s" % base, file=sys.stderr)
        sys.exit(1)
    for p in sorted(base.glob("*")):
        if p.is_file():
            installed[p.relative_to(profiles)] = p

harness_src = [Path(".claude/scripts/registry.sh"), Path(".claude/scripts/install-githooks.sh")]
problems = []

def compare(rel, src):
    dst = project / rel
    if not dst.is_file():
        problems.append("missing: %s" % rel)
        return
    if dst.read_bytes() != src.read_bytes():
        problems.append("content: %s" % rel)
    if (os.stat(src).st_mode & 0o777) != (os.stat(dst).st_mode & 0o777):
        problems.append("mode:    %s" % rel)

for rel, src in installed.items():
    compare(rel, src)
for rel in harness_src:
    compare(rel, harness / rel)

conf = project / ".claude" / "planning.conf"
if not conf.is_file():
    problems.append("missing: .claude/planning.conf")
else:
    text = conf.read_text(encoding="utf-8")
    for key in ("MAIN_BRANCH=", "CODE_ROOTS=", "DRIFT_HORIZON_DAYS=", "STRICT="):
        if not any(line.startswith(key) for line in text.splitlines()):
            problems.append("conf:    нет строки %s" % key)

state_ignore = project / ".claude" / "state" / ".gitignore"
if not state_ignore.is_file():
    problems.append("missing: .claude/state/.gitignore (маркеры owner-ok не должны попадать в коммит)")

codex = project / ".codex" / "hooks.json"
if codex.is_file():
    text = codex.read_text(encoding="utf-8", errors="replace")
    for needle in ("plans-drift", "branch-guard", "registry-guard", "commit-gate", "merge-gate", "main-push-guard", "owner-ok-guard"):
        if needle not in text:
            problems.append("codex:   hooks.json без %s" % needle)
    compat = project / ".codex" / "hooks" / "claude-compat.py"
    src = harness / ".codex" / "hooks" / "claude-compat.py"
    if not compat.is_file():
        problems.append("missing: .codex/hooks/claude-compat.py")
    elif compat.read_bytes() != src.read_bytes():
        problems.append("content: .codex/hooks/claude-compat.py")

if problems:
    print("verify: planning-профиль НЕ идентичен (%d)" % len(problems), file=sys.stderr)
    for p in problems:
        print("  " + p, file=sys.stderr)
    sys.exit(1)
print("verify: planning-профиль идентичен по %d файлам" % (len(installed) + len(harness_src)))
PY

    # реестры planning/
    if git -C "$PROJECT" rev-parse --show-toplevel >/dev/null 2>&1; then
      missing_idx=""
      for f in ROADMAP.md ACTIVE_PLANS.md PLANS.md HOTFIXES.md; do
        [ -f "$PROJECT/planning/$f" ] || missing_idx="$missing_idx $f"
      done
      if [ -n "$missing_idx" ]; then
        printf 'verify: нет индексов реестров:%s (запусти .claude/scripts/planning-init.sh)\n' "$missing_idx" >&2
        exit 1
      fi
      if ! reg_out="$(cd "$PROJECT" && .claude/scripts/registry.sh check --registry all 2>&1)"; then
        echo "verify: registry.sh check нашёл нарушения:" >&2
        printf '%s\n' "$reg_out" | head -15 >&2
        exit 1
      fi
      if [ "$QUIET" = 0 ]; then echo "verify: реестры planning/ чисты"; fi
    fi
  fi

  hooks_check || exit 1

  if [ "$TESTS" = 1 ]; then
    if [ "$PROFILE" = planning ]; then
      if [ -f "$ROOT/tests/acceptance-planning.sh" ]; then
        echo "verify: прогон tests/acceptance-planning.sh (может занять время)"
        bash "$ROOT/tests/acceptance-planning.sh"
      else
        echo "verify: tests/acceptance-planning.sh ещё нет — пропуск" >&2
      fi
    else
      echo "verify: прогон тестов хуков (может занять время)"
      ( cd "$PROJECT" && python3 -m unittest discover -s .claude/hooks -p 'test_*.py' )
    fi
  fi
fi

if [ "$QUIET" = 1 ]; then
  exit 0
fi

cat <<'EOF'

Помни: «настроено» не значит «исполняется». Проверь сценарии в клиенте:
  - позитивный: разрешённая команда проходит; сессия стартует с drift-сводкой;
  - негативный: правка индекса реестра через Edit блокируется, коммит без токена/владельца блокируется.
  - событийные хуки работают нативно только у Claude Code и Codex; DSH — через мост (subset); generic — git-хуки + bin/xh.
EOF
