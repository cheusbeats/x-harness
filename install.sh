#!/usr/bin/env bash
# install.sh — установка обвязки x-harness в проект.
#   --profile full     (по умолчанию) Laravel-профиль: правила, хуки, реестры, гейты.
#   --profile planning планировочный слой в любой проект: RM/PLAN/HF, роадмап, планы, хотфиксы,
#                      owner-ok, drift, git-хуки — без Laravel-гейтов.
# Идемпотентен; при --force делает backup; не копирует state, settings.local.json, секреты и память.
set -euo pipefail

ROOT="$(cd -- "$(dirname -- "$0")" && pwd -P)"
HARNESS="$ROOT/harness"
PROFILES="$ROOT/profiles"
PROJECT="$PWD"
PROFILE="full"
MODE="snapshot"
CLIENTS="auto"
SKILLS="auto"
FORCE=0
DRY=0
VERIFY=1
FIX_PATHS=0
DSH_HOOKS="none"
DSH_PROFILE="web"
DSH_VERSION=""
NO_GIT=0
UPSTREAM_SKILLS=1
UPSTREAM_PROJECT=0
UPSTREAM_GLOBAL=0
UPSTREAM_TMP=""
UPSTREAM_NAMES="make-interfaces-feel-better impeccable"
TS="$(date +%Y%m%d-%H%M%S)"

usage() {
  cat <<'EOF'
Usage: ./install.sh [options]

  --project DIR        целевой проект (по умолчанию текущий каталог)
  --profile NAME       full (по умолчанию) = Laravel-профиль; planning = только управление планами
  --mode snapshot|port snapshot = payload как есть (по умолчанию); port = подстроить параметры под проект (только full)
  --clients LIST       auto | all | claude,codex,dsh,kimi,zcode,opencode,generic | none
  --skills LIST        auto | project | global | both | none
  --no-upstream-skills не скачивать make-interfaces-feel-better и impeccable (offline)
  --dsh-hooks MODE     none | bridge | community  (по умолчанию none; см. skills/x-harness/references/08)
  --dsh-profile NAME   профиль DSH для моста хуков (по умолчанию web)
  --dsh-version VER    точная версия моста, напр. 0.1.0-rc.8 (обязательна для bridge)
  --force              перезаписать существующие файлы (с backup)
  --fix-paths          переписать абсолютный cwd в .codex/config.toml на целевой проект (full)
  --dry-run            только показать план
  --no-verify          не запускать verify.sh в конце
  --no-git             проект может быть без git (git-хуки не подключаются)
  -h, --help

Что ставит --profile full:
  1) harness/* -> проект (CLAUDE.md, AGENTS.md, .claude/, .ai/, .codex/, .githooks/, .mcp.json, boost.json, planning/README.md)
  2) git-хуки: git config core.hooksPath .githooks (если это git-репозиторий)
  3) навыки: project = .agents/skills + .dsh/skills (симлинки на .ai/skills/.claude/skills);
              global = копии в ~/.claude/skills, ~/.codex/skills, ~/.dsh/skills, ~/.agents/skills + сам x-harness
  4) по желанию: мост хуков для DSH (bridge/community) через adapters/agent-hook.py
     kimi: роли .agents/agents/*.md -> .claude/agents; zcode: .agents/mcp.json -> .mcp.json
     хуки Kimi/ZCode/OpenCode/Codex — плагин x-harness (команды печатаются в конце)
  5) verify.sh: сверка установленной копии с MANIFEST.sha256

Что ставит --profile planning:
  1) AGENTS.md, planning/ (реестры RM/PLAN/HF), .claude/{settings.json,planning.conf,scripts,hooks}, .githooks/
  2) registry.sh из harness/ + planning-init.sh (создаёт индексы и plans/closed/)
  3) skill x-harness-planning (--skills), Codex-адаптер при --clients codex, DSH-мост по флагу
  4) verify.sh --profile planning: сверка установленного планировочного слоя
EOF
}

log()  { printf '%s\n' "$*"; }
warn() { printf 'WARN: %s\n' "$*" >&2; }
fail() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }
run()  { if [ "$DRY" = 1 ]; then printf '  [dry]'; printf ' %q' "$@"; printf '\n'; else "$@"; fi; }

# Copy only Git-tracked package files or files verified by a sealed bundle manifest.
managed_copy() { # source destination | --check
  if [ "$DRY" = 1 ] && [ "${1:-}" != --check ]; then
    printf '  [dry] managed-copy'; printf ' %q' "$@"; printf '\n'; return 0
  fi
  python3 - "$ROOT" "$@" <<'PY_MANAGED'
from pathlib import Path
import hashlib
import json
import os
import shutil
import subprocess
import sys

root = Path(sys.argv[1]).resolve()
args = sys.argv[2:]
allowed = {'skills', 'AGENTS.md', 'CLAUDE.md', 'README.md', 'MANIFEST.sha256',
           'install.sh', 'verify.sh', 'references', 'harness', 'profiles', 'bin', 'tests', 'adapters'}
blocked = {'.git', '.env', 'auth.json', 'settings.local.json', 'state', '__pycache__'}
manifest = root / '.x-harness-package.json'

def safe(rel):
    return (not rel.is_absolute() and rel.parts and rel.parts[0] in allowed
            and all(p not in ('.', '..') and p not in blocked and not p.startswith('.env.')
                    and not p.endswith(('.key', '.pem')) for p in rel.parts))

def describe(path):
    try:
        relative = path.relative_to(root)
        for parent in relative.parents:
            if parent != Path('.') and (root / parent).is_symlink():
                raise ValueError('Симлинк среди родительских каталогов источника: ' + str(parent))
        if not path.resolve(strict=False).is_relative_to(root):
            raise ValueError('Источник за пределами пакета: ' + str(path))
    except (OSError, RuntimeError) as exc:
        raise ValueError('Невозможно разрешить источник: ' + str(path)) from exc
    if path.is_symlink():
        target = os.readlink(path)
        if Path(target).is_absolute() or not path.resolve().is_relative_to(root):
            raise ValueError('Внешний симлинк: ' + str(path))
        return {'type': 'link', 'target': target}
    if not path.is_file():
        raise ValueError('Файл отсутствует: ' + str(path))
    return {'type': 'file', 'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
            'mode': path.stat().st_mode & 0o777}

proc = subprocess.run(['git', '-C', str(root), 'rev-parse', '--show-toplevel'],
                      capture_output=True, text=True)
if proc.returncode == 0 and Path(proc.stdout.strip()).resolve() == root:
    raw = subprocess.check_output(['git', '-C', str(root), 'ls-files', '-z'])
    records = {os.fsdecode(item): describe(root / os.fsdecode(item))
               for item in raw.split(b'\0') if item and safe(Path(os.fsdecode(item)))}
elif manifest.is_file() and not manifest.is_symlink():
    data = json.loads(manifest.read_text(encoding='utf-8'))
    if data.get('version') != 1 or not isinstance(data.get('files'), dict):
        raise ValueError('Некорректный манифест пакета')
    records = data['files']
    for name, expected in records.items():
        rel = Path(name)
        if not safe(rel) or describe(root / rel) != expected:
            raise ValueError('Изменён или недопустим файл пакета: ' + name)
else:
    raise ValueError('Нужен Git checkout x-harness или пакет с проверяемым манифестом')
if 'skills/x-harness/SKILL.md' not in records:
    raise ValueError('skills/x-harness/SKILL.md отсутствует в манифесте')
if 'MANIFEST.sha256' in records:
    expected_paths = {}
    for line in (root / 'MANIFEST.sha256').read_text(encoding='utf-8').splitlines():
        parts = line.split(' ', 3)
        if parts[0] == 'H' and len(parts) == 4:
            expected_paths['harness/' + parts[3]] = {'type': 'file', 'mode': int(parts[1], 8), 'sha256': parts[2]}
        elif parts[0] == 'L' and len(parts) == 3:
            expected_paths['harness/' + parts[2]] = {'type': 'link', 'target': parts[1]}
        else:
            raise ValueError('Некорректная строка MANIFEST.sha256')
    missing = sorted(set(expected_paths) - set(records))
    extra = sorted(name for name in records if name.startswith('harness/') and name not in expected_paths)
    changed = sorted(name for name, expected in expected_paths.items() if name in records and records[name] != expected)
    if missing or extra or changed:
        raise ValueError('MANIFEST.sha256 не совпадает с управляемыми файлами harness; '
                         + 'не учтены=' + repr(missing) + '; лишние=' + repr(extra) + '; изменены=' + repr(changed))
if args == ['--check']:
    raise SystemExit(0)
source, destination = map(Path, args)
source = Path(os.path.abspath(source))
rel_source = source.relative_to(root)
if '..' in rel_source.parts:
    raise ValueError('Источник вне пакета')
source_name = rel_source.as_posix()
is_root = rel_source == Path('.')
is_leaf = source_name in records
prefix = '' if is_root else source_name.rstrip('/') + '/'
selected = {name: value for name, value in records.items()
            if is_root or name == source_name or name.startswith(prefix)}
if not selected:
    raise ValueError('Нет управляемых файлов: ' + source_name)
for name, value in sorted(selected.items()):
    suffix = name if is_root else ('' if name == source_name else name[len(prefix):])
    out = destination / suffix if suffix else destination
    out.parent.mkdir(parents=True, exist_ok=True)
    if value['type'] == 'link':
        out.symlink_to(value['target'])
    else:
        shutil.copy2(root / name, out)
if is_root:
    (destination / '.x-harness-package.json').write_text(
        json.dumps({'version': 1, 'files': selected}, ensure_ascii=False, sort_keys=True, indent=2) + '\n',
        encoding='utf-8')
PY_MANAGED
}


# Refuse path escapes before touching project or global skill directories.
check_destination_parents() { # root relative-path ...
  python3 - "$@" <<'PY_DEST'
from pathlib import Path
import sys

root = Path(sys.argv[1]).resolve()
for name in sys.argv[2:]:
    rel = Path(name)
    if rel.is_absolute() or '..' in rel.parts:
        raise SystemExit('Недопустимый путь назначения: ' + name)
    current = root
    for part in rel.parts:
        current = current / part
        if current.is_symlink():
            try:
                resolved = current.resolve(strict=False)
            except (OSError, RuntimeError) as exc:
                raise SystemExit('Невозможно разрешить ссылку: ' + str(current)) from exc
            if not resolved.is_relative_to(root):
                raise SystemExit('Ссылка ведёт за пределы назначения: ' + str(current))
PY_DEST
}

# Codex-адаптер: hooks.json из .claude/settings.json (matcher-ы Codex + claude-compat.py),
# чтобы strict-набор хуков не дублировался руками и совпадал с Claude-настройкой.
gen_codex_hooks() { # outfile
  python3 - "$PROJECT/.claude/settings.json" "$1" <<'PY'
import json, re, sys
src, dst = sys.argv[1], sys.argv[2]
data = json.load(open(src, encoding="utf-8"))
matcher_map = {
    "Bash": "Bash|exec_command|shell_command|shell|functions.exec_command",
    "Edit|Write|NotebookEdit": "apply_patch|Edit|Write|NotebookEdit",
}
hook_re = re.compile(r"\.claude/hooks/([A-Za-z0-9_-]+)\.sh")
out = {}
for event, groups in data.get("hooks", {}).items():
    out_groups = []
    for group in groups:
        g = dict(group)
        if g.get("matcher"):
            g["matcher"] = matcher_map.get(g["matcher"], g["matcher"])
        hooks = []
        for h in group.get("hooks", []):
            h = dict(h)
            m = hook_re.search(h.get("command", ""))
            if h.get("type") == "command" and m:
                command = 'python3 "$(git rev-parse --show-toplevel)/.codex/hooks/claude-compat.py" ' + m.group(1)
                if event == "SessionStart":
                    command += " 2>/dev/null || true"
                h["command"] = command
            hooks.append(h)
        g["hooks"] = hooks
        out_groups.append(g)
    out[event] = out_groups
json.dump({"description": "Проверки планировочного профиля x-harness для Codex; логика остаётся в .claude/hooks.",
           "hooks": out}, open(dst, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
print("  создан", dst)
PY
}

while [ $# -gt 0 ]; do
  case "$1" in
    --project) PROJECT="$2"; shift 2 ;;
    --profile) PROFILE="$2"; shift 2 ;;
    --mode) MODE="$2"; shift 2 ;;
    --clients) CLIENTS="$2"; shift 2 ;;
    --skills) SKILLS="$2"; shift 2 ;;
    --dsh-hooks) DSH_HOOKS="$2"; shift 2 ;;
    --dsh-profile) DSH_PROFILE="$2"; shift 2 ;;
    --dsh-version) DSH_VERSION="$2"; shift 2 ;;
    --force) FORCE=1; shift ;;
    --fix-paths) FIX_PATHS=1; shift ;;
    --dry-run) DRY=1; shift ;;
    --no-verify) VERIFY=0; shift ;;
    --no-git) NO_GIT=1; shift ;;
    --no-upstream-skills) UPSTREAM_SKILLS=0; shift ;;
    -h|--help) usage; exit 0 ;;
    *) fail "неизвестный аргумент: $1 (см. --help)" ;;
  esac
done

[ -d "$HARNESS" ] || fail "нет каталога harness/ рядом с install.sh"
[ -d "$PROJECT" ] || fail "нет целевого проекта: $PROJECT"
PROJECT="$(cd "$PROJECT" && pwd -P)"
case "$PROFILE" in full|planning) ;; *) fail "--profile: full|planning" ;; esac
case "$MODE" in snapshot|port) ;; *) fail "--mode: snapshot|port" ;; esac
case "$SKILLS" in auto|project|global|both|none) ;; *) fail "--skills: auto|project|global|both|none" ;; esac
case "$DSH_HOOKS" in none|bridge|community) ;; *) fail "--dsh-hooks: none|bridge|community" ;; esac
if [ "$PROFILE" = planning ]; then
  [ -d "$PROFILES/planning" ] || fail "нет каталога profiles/planning/ рядом с install.sh"
fi

command -v python3 >/dev/null 2>&1 || fail "нужен python3 (на нём хуки и verify)"
python3 -c 'import sys; sys.exit(sys.version_info < (3, 9))' || fail "нужен Python 3.9 или новее"

# --- проект и git -----------------------------------------------------------
IS_GIT=0
if git -C "$PROJECT" rev-parse --show-toplevel >/dev/null 2>&1; then IS_GIT=1; fi
if [ "$IS_GIT" = 0 ] && [ "$NO_GIT" = 0 ]; then
  fail "$PROJECT не git-репозиторий (для нового проекта: git init; или --no-git)"
fi
if [ "$IS_GIT" = 1 ]; then
  GIT_ROOT="$(git -C "$PROJECT" rev-parse --show-toplevel)"
  case "$PROJECT" in
    "$GIT_ROOT"|"$GIT_ROOT"/*) ;;
    *) warn "проект вне корня git $GIT_ROOT — хуки/реестры рассчитаны на корень репозитория" ;;
  esac
fi
if [ "$PROFILE" = planning ] && [ "$IS_GIT" = 0 ]; then
  warn "planning-профиль без git: drift и git-хуки работать не будут"
fi

# Не заменять существующий пользовательский набор Git-хуков.
if [ "$IS_GIT" = 1 ]; then
  [ "$PROJECT" = "$GIT_ROOT" ] || fail "--project должен указывать на корень git: $GIT_ROOT"
  existing_hooks="$(git -C "$PROJECT" config --get core.hooksPath || true)"
  if [ -n "$existing_hooks" ] && ! python3 - "$GIT_ROOT" "$existing_hooks" <<'PY_HOOKS'
from pathlib import Path
import sys
root = Path(sys.argv[1]).resolve()
path = Path(sys.argv[2]).expanduser()
if not path.is_absolute():
    path = root / path
raise SystemExit(0 if path.resolve() == (root / '.githooks').resolve() else 1)
PY_HOOKS
  then
    fail "core.hooksPath уже использует другой путь: $existing_hooks; сначала согласуйте совместное подключение"
  fi
fi

# --- клиенты ----------------------------------------------------------------
CLIENT_CLAUDE=0; CLIENT_CODEX=0; CLIENT_DSH=0; CLIENT_KIMI=0; CLIENT_ZCODE=0; CLIENT_OPENCODE=0; CLIENT_GENERIC=0
detect_client() {
  case "$1" in
    claude) command -v claude >/dev/null 2>&1 || [ -d "$HOME/.claude" ] ;;
    codex)  command -v codex  >/dev/null 2>&1 || [ -d "$HOME/.codex" ] ;;
    dsh)    command -v dsh    >/dev/null 2>&1 || [ -d "$HOME/.dsh" ] ;;
    kimi)   command -v kimi   >/dev/null 2>&1 || [ -d "$HOME/.kimi-code" ] ;;
    zcode)  [ -d "$HOME/.zcode" ] || [ -d /Applications/ZCode.app ] ;;
    opencode) command -v opencode >/dev/null 2>&1 || [ -d "$HOME/.config/opencode" ] ;;
    generic) return 0 ;;
    *) return 1 ;;
  esac
}
case "$CLIENTS" in
  auto)
    detect_client claude && CLIENT_CLAUDE=1
    detect_client codex && CLIENT_CODEX=1
    detect_client dsh && CLIENT_DSH=1
    detect_client kimi && CLIENT_KIMI=1
    detect_client zcode && CLIENT_ZCODE=1
    detect_client opencode && CLIENT_OPENCODE=1
    CLIENT_GENERIC=1 ;;
  all) CLIENT_CLAUDE=1; CLIENT_CODEX=1; CLIENT_DSH=1; CLIENT_KIMI=1; CLIENT_ZCODE=1; CLIENT_OPENCODE=1; CLIENT_GENERIC=1 ;;
  none) ;;
  *)
    old_ifs="$IFS"; IFS=','
    for c in $CLIENTS; do
      IFS="$old_ifs"
      case "$c" in
        claude) CLIENT_CLAUDE=1 ;; codex) CLIENT_CODEX=1 ;; dsh) CLIENT_DSH=1 ;;
        kimi) CLIENT_KIMI=1 ;; zcode) CLIENT_ZCODE=1 ;; opencode) CLIENT_OPENCODE=1 ;;
        generic) CLIENT_GENERIC=1 ;; *) fail "неизвестный клиент: $c" ;;
      esac
    done
    IFS="$old_ifs" ;;
esac

log "x-harness: profile=$PROFILE mode=$MODE project=$PROJECT"
log "клиенты: claude=$CLIENT_CLAUDE codex=$CLIENT_CODEX dsh=$CLIENT_DSH kimi=$CLIENT_KIMI zcode=$CLIENT_ZCODE opencode=$CLIENT_OPENCODE generic=$CLIENT_GENERIC; skills=$SKILLS"

# Проверить каталог источника или sealed bundle до любых изменений проекта.
managed_copy --check

# Upstream skills are fetched and validated in isolation before any target writes.
prepare_upstream_skill() { # name url skill-path
  local name="$1" url="$2" skill_path="$3"
  if [ "$DRY" = 1 ]; then
    log "  [dry] upstream $name: $url ($skill_path)"
    return 0
  fi
  git -c core.hooksPath=/dev/null clone --depth 1 --filter=blob:none --sparse -- "$url" "$UPSTREAM_TMP/repos/$name" || fail "не удалось получить upstream $name"
  git -C "$UPSTREAM_TMP/repos/$name" sparse-checkout set -- "$skill_path" || fail "не удалось получить каталог upstream $name"
  python3 - "$UPSTREAM_TMP/repos/$name" "$skill_path" "$UPSTREAM_TMP/skills/$name" <<'PY_UPSTREAM'
from pathlib import Path
import os
import shutil
import subprocess
import sys

repo = Path(sys.argv[1]).resolve()
relative = Path(sys.argv[2])
source = repo / relative
destination = Path(sys.argv[3])
blocked = {'.git', '.env', 'auth.json', 'settings.local.json', 'state', '__pycache__'}
for path in (source, *source.parents):
    if path == repo:
        break
    if path.is_symlink():
        raise SystemExit('Симлинк в пути upstream skill: ' + str(path))
source = source.resolve()
if not source.is_relative_to(repo) or not source.is_dir():
    raise SystemExit('Upstream skill отсутствует или вне репозитория')
raw = subprocess.check_output(['git', '-C', str(repo), 'ls-files', '-z', '--', str(relative)])
files = []
for item in raw.split(b'\0'):
    if not item:
        continue
    path = repo / os.fsdecode(item)
    rel = path.relative_to(source)
    if any(part in blocked or part.startswith('.env.') or part.endswith(('.pem', '.key', '.pyc'))
           for part in rel.parts):
        continue
    for parent in path.parents:
        if parent == source:
            break
        if parent.is_symlink():
            raise SystemExit('Симлинк среди каталогов upstream: ' + str(parent))
    if not path.resolve(strict=False).is_relative_to(source):
        raise SystemExit('Upstream симлинк ведёт за пределы skill: ' + str(rel))
    if path.is_symlink():
        if Path(os.readlink(path)).is_absolute() or not path.exists():
            raise SystemExit('Недопустимый upstream симлинк: ' + str(rel))
    elif not path.is_file():
        raise SystemExit('Upstream содержит не обычный файл: ' + str(rel))
    files.append((path, rel))
if Path('SKILL.md') not in {rel for _, rel in files}:
    raise SystemExit('В upstream нет отслеживаемого SKILL.md')
for path, rel in files:
    out = destination / rel
    out.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink():
        out.symlink_to(os.readlink(path))
    else:
        shutil.copy2(path, out)
PY_UPSTREAM
  log "  upstream $name: $url @ $(git -C "$UPSTREAM_TMP/repos/$name" rev-parse HEAD)"
}
if [ "$PROFILE" = full ] && [ "$UPSTREAM_SKILLS" = 1 ]; then
  case "$SKILLS" in project|both|auto) UPSTREAM_PROJECT=1 ;; esac
  case "$SKILLS" in
    global|both|auto)
      if [ "$CLIENT_CLAUDE$CLIENT_CODEX$CLIENT_DSH$CLIENT_GENERIC" != 0000 ]; then UPSTREAM_GLOBAL=1; fi ;;
  esac
fi

# --- backup / conflict ------------------------------------------------------
BACKUP="$PROJECT/.x-harness-backup.$TS"
# Verify all destination parents and planning-init's implicit writes before first mutation.
check_destination_parents "$PROJECT" \
  planning planning/roadmap planning/plans planning/plans/closed planning/hotfixes \
  planning/roadmap/.gitkeep planning/plans/.gitkeep planning/plans/closed/.gitkeep planning/hotfixes/.gitkeep \
  planning/README.md planning/ROADMAP.md planning/ACTIVE_PLANS.md planning/PLANS.md planning/HOTFIXES.md \
  ".x-harness-backup.$TS" ".x-harness-backup.$TS/planning" ".x-harness-backup.$TS/.codex/hooks" \
  .claude .githooks
if [ "$PROFILE" = full ]; then
  check_destination_parents "$PROJECT" .ai .codex
elif [ "$CLIENT_CODEX" = 1 ]; then
  check_destination_parents "$PROJECT" .codex .codex/hooks .codex/hooks.json
fi
if [ "$FIX_PATHS" = 1 ]; then
  check_destination_parents "$PROJECT" .codex/config.toml
fi
case "$SKILLS" in
  project|both|auto)
    check_destination_parents "$PROJECT" .agents/skills .claude/skills
    if [ "$PROFILE" = full ] || [ "$CLIENT_DSH" = 1 ]; then
      check_destination_parents "$PROJECT" .dsh/skills
    fi ;;
esac
if [ "$DSH_HOOKS" != none ]; then
  check_destination_parents "$PROJECT" .dsh .dsh/hooks.json .dsh/hooks-bridge.json .dsh/hooks-bridge.yml .dsh/agent-hook.py
fi
[ "$CLIENT_KIMI" != 1 ] || check_destination_parents "$PROJECT" .agents .agents/agents
[ "$CLIENT_ZCODE" != 1 ] || check_destination_parents "$PROJECT" .agents .agents/mcp.json
case "$SKILLS" in
  global|both|auto)
    [ "$CLIENT_CLAUDE" != 1 ] || check_destination_parents "$HOME" .claude/skills
    [ "$CLIENT_CODEX" != 1 ] || check_destination_parents "$HOME" .codex/skills
    [ "$CLIENT_DSH" != 1 ] || check_destination_parents "$HOME" .dsh/skills
    [ "$CLIENT_ZCODE" != 1 ] || check_destination_parents "$HOME" .zcode/skills
    if [ "$CLIENT_CODEX" = 1 ] || [ "$CLIENT_DSH" = 1 ] || [ "$CLIENT_KIMI" = 1 ] || [ "$CLIENT_OPENCODE" = 1 ] || [ "$CLIENT_GENERIC" = 1 ]; then
      check_destination_parents "$HOME" .agents/skills
    fi ;;
esac
if [ "$UPSTREAM_PROJECT" = 1 ]; then
  for name in $UPSTREAM_NAMES; do
    check_destination_parents "$PROJECT" ".ai/skills/$name" ".claude/skills/$name" ".agents/skills/$name" ".dsh/skills/$name"
  done
fi
if [ "$UPSTREAM_GLOBAL" = 1 ]; then
  for name in $UPSTREAM_NAMES; do
    [ "$CLIENT_CLAUDE" != 1 ] || check_destination_parents "$HOME" ".claude/skills/$name"
    [ "$CLIENT_CODEX" != 1 ] || check_destination_parents "$HOME" ".codex/skills/$name"
    [ "$CLIENT_DSH" != 1 ] || check_destination_parents "$HOME" ".dsh/skills/$name"
    [ "$CLIENT_ZCODE" != 1 ] || check_destination_parents "$HOME" ".zcode/skills/$name"
    if [ "$CLIENT_CODEX" = 1 ] || [ "$CLIENT_DSH" = 1 ] || [ "$CLIENT_KIMI" = 1 ] || [ "$CLIENT_OPENCODE" = 1 ] || [ "$CLIENT_GENERIC" = 1 ]; then
      check_destination_parents "$HOME" ".agents/skills/$name"
    fi
  done
fi
backup_path() {
  rel="$1"
  if [ "$DRY" = 1 ]; then log "  [dry] backup: $rel"; return 0; fi
  mkdir -p "$BACKUP/$(dirname "$rel")"
  mv "$PROJECT/$rel" "$BACKUP/$rel"
  log "  backup: $rel -> .x-harness-backup.$TS/$rel"
}
conflicts=""
add_conflict() { conflicts="$conflicts $1"; }

if [ "$PROFILE" = full ]; then
  TOP_ENTRIES=".claude .ai .codex .githooks CLAUDE.md AGENTS.md .mcp.json boost.json"
  preflight_conflicts() {
    for rel in $TOP_ENTRIES; do
      if [ -e "$PROJECT/$rel" ] || [ -L "$PROJECT/$rel" ]; then add_conflict "$rel"; fi
    done
    if [ -e "$PROJECT/planning/README.md" ] || [ -L "$PROJECT/planning/README.md" ]; then add_conflict "planning/README.md"; fi
  }
else
  # planning-профиль не забирает чужой planning/ — только README и свои файлы.
  PLANNING_CONFLICTS=".claude .githooks AGENTS.md planning/README.md"
  if [ "$CLIENT_CODEX" = 1 ]; then
    PLANNING_CONFLICTS="$PLANNING_CONFLICTS .codex/hooks.json .codex/hooks/claude-compat.py"
  fi
  preflight_conflicts() {
    for rel in $PLANNING_CONFLICTS; do
      if [ -e "$PROJECT/$rel" ] || [ -L "$PROJECT/$rel" ]; then add_conflict "$rel"; fi
    done
  }
fi
preflight_conflicts
if [ -n "$conflicts" ] && [ "$FORCE" = 0 ]; then
  fail "в проекте уже есть:$(printf '%s\n' "$conflicts" | tr ' ' '\n' | sed '/^$/d;s/^/- /')  — повтори с --force (будет backup: .x-harness-backup.$TS)"
fi

if [ "$UPSTREAM_PROJECT" = 1 ] || [ "$UPSTREAM_GLOBAL" = 1 ]; then
  if [ "$DRY" != 1 ]; then
    UPSTREAM_TMP="$(mktemp -d)"
    trap 'rm -rf "$UPSTREAM_TMP"' EXIT
  fi
  prepare_upstream_skill make-interfaces-feel-better https://github.com/jakubkrehel/make-interfaces-feel-better.git skills/make-interfaces-feel-better
  prepare_upstream_skill impeccable https://github.com/pbakaus/impeccable.git .agents/skills/impeccable
fi

# --- payload ----------------------------------------------------------------
if [ "$PROFILE" = full ]; then
  log "1/5 payload full -> $PROJECT"
  run mkdir -p "$PROJECT/planning"
  for rel in $TOP_ENTRIES; do
    if [ -e "$PROJECT/$rel" ] || [ -L "$PROJECT/$rel" ]; then backup_path "$rel"; fi
    managed_copy "$HARNESS/$rel" "$PROJECT/$rel"
  done
  if [ -e "$PROJECT/planning/README.md" ] || [ -L "$PROJECT/planning/README.md" ]; then
    backup_path "planning/README.md"
  fi
  managed_copy "$HARNESS/planning/README.md" "$PROJECT/planning/README.md"
else
  log "1/5 payload planning -> $PROJECT"
  run mkdir -p "$PROJECT/planning"
  for rel in $PLANNING_CONFLICTS; do
    if [ -e "$PROJECT/$rel" ] || [ -L "$PROJECT/$rel" ]; then backup_path "$rel"; fi
  done
  managed_copy "$PROFILES/planning/.claude" "$PROJECT/.claude"
  managed_copy "$PROFILES/planning/.githooks" "$PROJECT/.githooks"
  managed_copy "$PROFILES/planning/AGENTS.md" "$PROJECT/AGENTS.md"
  managed_copy "$PROFILES/planning/planning/README.md" "$PROJECT/planning/README.md"
  # registry.sh — единственный источник истины из harness/ (не дублируем в профиле)
  managed_copy "$HARNESS/.claude/scripts/registry.sh" "$PROJECT/.claude/scripts/registry.sh"
  managed_copy "$HARNESS/.claude/scripts/install-githooks.sh" "$PROJECT/.claude/scripts/install-githooks.sh"
  # state (маркеры owner-ok, registry.lock) не должен попадать в коммит проекта
  if [ "$DRY" = 1 ]; then
    log "  [dry] .claude/state/.gitignore"
  else
    mkdir -p "$PROJECT/.claude/state/planning-owner-ok"
    printf '*\n!.gitignore\n' > "$PROJECT/.claude/state/.gitignore"
  fi
  if [ "$CLIENT_CODEX" = 1 ]; then
    run mkdir -p "$PROJECT/.codex/hooks"
    managed_copy "$HARNESS/.codex/hooks/claude-compat.py" "$PROJECT/.codex/hooks/claude-compat.py"
    if [ "$DRY" = 1 ]; then
      log "  [dry] .codex/hooks.json (из .claude/settings.json)"
    else
      gen_codex_hooks "$PROJECT/.codex/hooks.json"
    fi
  fi
  if [ "$DRY" = 1 ]; then
    log "  [dry] .claude/planning.conf (MAIN_BRANCH/CODE_ROOTS автодетект)"
  else
    python3 - "$PROJECT" <<'PY'
import subprocess, sys
from pathlib import Path

project = Path(sys.argv[1])
tmpl = project / ".claude" / "planning.conf.template"
conf = project / ".claude" / "planning.conf"
text = tmpl.read_text(encoding="utf-8")

def git(*args):
    r = subprocess.run(["git", "-C", str(project), *args], capture_output=True, text=True)
    return r.stdout.strip() if r.returncode == 0 else ""

main = ""
origin_head = git("symbolic-ref", "--short", "-q", "refs/remotes/origin/HEAD")
if origin_head.startswith("origin/"):
    main = origin_head[len("origin/"):]
if not main:
    for cand in ("main", "master"):
        if git("rev-parse", "--verify", "--quiet", "refs/heads/" + cand):
            main = cand
            break
if not main:
    main = git("symbolic-ref", "--short", "-q", "HEAD") or "main"

PREFERRED = ("app", "src", "lib", "packages", "modules", "components", "services",
             "internal", "cmd", "pkg", "server", "client", "database", "config",
             "resources", "routes", "tests")
SKIP = {"planning", "node_modules", "vendor", "dist", "build", "coverage", "public", "storage"}
roots = []
names = sorted(p.name for p in project.iterdir()
               if p.is_dir() and not p.name.startswith(".") and p.name not in SKIP)
roots = [n for n in PREFERRED if n in names]
if not roots:
    roots = names or ["src"]

def put(key, value):
    global text
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if line.startswith(key + "="):
            lines[i] = key + "=" + value
            break
    else:
        lines.append(key + "=" + value)
    text = "\n".join(lines) + "\n"

def shell_value(value):
    # planning.conf is sourced by Bash: filesystem names must remain data.
    return '"' + ''.join('\\' + ch if ch in '\\"$`' else ch for ch in value) + '"'

put("MAIN_BRANCH", shell_value(main))
put("CODE_ROOTS", shell_value(" ".join(roots)))
conf.write_text(text, encoding="utf-8")
print("  planning.conf: MAIN_BRANCH=%s CODE_ROOTS=%s" % (main, " ".join(roots)))
PY
  fi
fi

# --- fix paths (opt-in, full) -----------------------------------------------
if [ "$FIX_PATHS" = 1 ] && [ -f "$PROJECT/.codex/config.toml" ]; then
  if [ "$DRY" = 1 ]; then log "  [dry] fix .codex/config.toml cwd -> $PROJECT"; else
    python3 - "$PROJECT/.codex/config.toml" "$PROJECT" <<'PY'
import json, re, sys
p, root = sys.argv[1], sys.argv[2]
s = open(p, encoding="utf-8").read()
s2 = re.sub(r'(?m)^cwd\s*=.*$', lambda _: "cwd = " + json.dumps(root, ensure_ascii=False), s)
open(p, "w", encoding="utf-8").write(s2)
PY
    log "  fix: .codex/config.toml cwd -> $PROJECT"
  fi
fi

# --- git hooks --------------------------------------------------------------
log "2/5 git-хуки"
if [ "$IS_GIT" = 1 ]; then
  if [ "$DRY" = 1 ]; then log "  [dry] bash .claude/scripts/install-githooks.sh"; else
    ( cd "$PROJECT" && bash .claude/scripts/install-githooks.sh )
  fi
else
  warn "не git-репозиторий: core.hooksPath не подключён"
fi

# --- skills -----------------------------------------------------------------
install_skill_copy() { # src name destdir
  local src="$1" name="$2" destdir="$3" skill_backup
  [ -d "$destdir" ] || run mkdir -p "$destdir"
  if [ -e "$destdir/$name" ] || [ -L "$destdir/$name" ]; then
    [ "$FORCE" = 1 ] || { warn "навык $name уже есть в $destdir (--force для замены)"; return 0; }
    if [ "$DRY" = 1 ]; then
      log "  [dry] backup skill: $destdir/$name"
    else
      skill_backup="$(mktemp -d "$destdir/.x-harness-backup.$TS.XXXXXX")"
      mv "$destdir/$name" "$skill_backup/$name"
      log "  backup skill: $destdir/$name -> $skill_backup/$name"
    fi
  fi
  run cp -a "$src" "$destdir/$name"
}
install_skill_link() { # target name destdir
  local target="$1" name="$2" destdir="$3" skill_backup
  [ -d "$destdir" ] || run mkdir -p "$destdir"
  # Relative targets must still resolve correctly when skills/ is an in-project symlink.
  target="$(python3 - "$destdir" "$target" <<'PY_REL'
import os
import sys
base, target = sys.argv[1:]
intended = os.path.normpath(os.path.join(base, target))
print(os.path.relpath(intended, os.path.realpath(base)))
PY_REL
)"
  if [ -e "$destdir/$name" ] && [ ! -L "$destdir/$name" ]; then
    [ "$FORCE" = 1 ] || { warn "навык $name в $destdir не симлинк (--force)"; return 0; }
    if [ "$DRY" = 1 ]; then
      log "  [dry] backup skill: $destdir/$name"
    else
      skill_backup="$(mktemp -d "$destdir/.x-harness-backup.$TS.XXXXXX")"
      mv "$destdir/$name" "$skill_backup/$name"
      log "  backup skill: $destdir/$name -> $skill_backup/$name"
    fi
  fi
  run ln -snf "$target" "$destdir/$name"
}

install_tracked_skill() ( # src name destdir
  src="$1"; name="$2"; destdir="$3"
  if [ "$DRY" = 1 ]; then
    log "  [dry] глобальный skill $name: управляемые файлы -> $destdir"
    return 0
  fi
  tmpdir="$(mktemp -d)"
  trap 'rm -rf "$tmpdir"' EXIT
  managed_copy "$src" "$tmpdir/$name"
  install_skill_copy "$tmpdir/$name" "$name" "$destdir"
)

if [ "$PROFILE" = full ]; then
  install_project_skills() {
    log "3/5 навыки проекта: .agents/skills + .dsh/skills"
    if [ "$UPSTREAM_PROJECT" = 1 ]; then
      for n in $UPSTREAM_NAMES; do
        install_skill_copy "$UPSTREAM_TMP/skills/$n" "$n" "$PROJECT/.ai/skills"
        install_skill_link "../../.ai/skills/$n" "$n" "$PROJECT/.claude/skills"
        install_skill_link "../../.ai/skills/$n" "$n" "$PROJECT/.agents/skills"
        install_skill_link "../../.ai/skills/$n" "$n" "$PROJECT/.dsh/skills"
      done
    fi
    for d in "$HARNESS/.ai/skills"/*; do
      [ -d "$d" ] || continue
      n="$(basename "$d")"
      [ "$DRY" = 1 ] || [ -d "$PROJECT/.ai/skills/$n" ] || continue
      install_skill_link "../../.ai/skills/$n" "$n" "$PROJECT/.agents/skills"
      install_skill_link "../../.ai/skills/$n" "$n" "$PROJECT/.dsh/skills"
    done
    for d in "$HARNESS/.claude/skills"/*; do
      [ -d "$d" ] && [ ! -L "$d" ] || continue
      n="$(basename "$d")"
      [ "$DRY" = 1 ] || [ -d "$PROJECT/.claude/skills/$n" ] || continue
      install_skill_link "../../.claude/skills/$n" "$n" "$PROJECT/.agents/skills"
      install_skill_link "../../.claude/skills/$n" "$n" "$PROJECT/.dsh/skills"
    done
  }
  install_global_skills() {
    log "3/5 навыки глобально (копии + сам x-harness)"
    dirs=""
    [ "$CLIENT_CLAUDE" = 1 ] && dirs="$dirs $HOME/.claude/skills"
    [ "$CLIENT_CODEX" = 1 ] && dirs="$dirs $HOME/.codex/skills"
    [ "$CLIENT_DSH" = 1 ] && dirs="$dirs $HOME/.dsh/skills"
    [ "$CLIENT_ZCODE" = 1 ] && dirs="$dirs $HOME/.zcode/skills"
    if [ "$CLIENT_CODEX" = 1 ] || [ "$CLIENT_DSH" = 1 ] || [ "$CLIENT_KIMI" = 1 ] || [ "$CLIENT_OPENCODE" = 1 ] || [ "$CLIENT_GENERIC" = 1 ]; then
      dirs="$dirs $HOME/.agents/skills"
    fi
    [ -z "$dirs" ] && { warn "нет клиентов для глобальной установки навыков"; return 0; }
    for dest in $dirs; do
      if [ "$UPSTREAM_GLOBAL" = 1 ]; then
        for n in $UPSTREAM_NAMES; do install_skill_copy "$UPSTREAM_TMP/skills/$n" "$n" "$dest"; done
      fi
      for d in "$HARNESS/.ai/skills"/*; do [ -d "$d" ] && install_tracked_skill "$d" "$(basename "$d")" "$dest"; done
      for d in "$HARNESS/.claude/skills"/*; do
        [ -d "$d" ] && [ ! -L "$d" ] && install_tracked_skill "$d" "$(basename "$d")" "$dest"
      done
      install_tracked_skill "$ROOT/skills/x-harness" "x-harness" "$dest"
    done
  }
  case "$SKILLS" in
    none) : ;;
    project) install_project_skills ;;
    global) install_global_skills ;;
    both) install_project_skills; install_global_skills ;;
    auto) install_project_skills; install_global_skills ;;
  esac
else
  install_planning_skill() {
    src="$ROOT/skills/x-harness-planning"
    name="x-harness-planning"
    [ -f "$src/SKILL.md" ] || { warn "нет $src/SKILL.md — навык x-harness-planning не установлен"; return 0; }
    case "$SKILLS" in
      none) return 0 ;;
      project|both|auto)
        log "3/5 навык проекта: x-harness-planning"
        install_tracked_skill "$src" "$name" "$PROJECT/.claude/skills"
        [ "$CLIENT_DSH" = 1 ] && install_tracked_skill "$src" "$name" "$PROJECT/.dsh/skills"
        install_tracked_skill "$src" "$name" "$PROJECT/.agents/skills"
        ;;
    esac
    case "$SKILLS" in
      global|both|auto)
        dirs=""
        [ "$CLIENT_CLAUDE" = 1 ] && dirs="$dirs $HOME/.claude/skills"
        [ "$CLIENT_CODEX" = 1 ] && dirs="$dirs $HOME/.codex/skills"
        [ "$CLIENT_DSH" = 1 ] && dirs="$dirs $HOME/.dsh/skills"
        [ "$CLIENT_ZCODE" = 1 ] && dirs="$dirs $HOME/.zcode/skills"
        if [ "$CLIENT_CODEX" = 1 ] || [ "$CLIENT_DSH" = 1 ] || [ "$CLIENT_KIMI" = 1 ] || [ "$CLIENT_OPENCODE" = 1 ] || [ "$CLIENT_GENERIC" = 1 ]; then
          dirs="$dirs $HOME/.agents/skills"
        fi
        [ -z "$dirs" ] && { warn "нет клиентов для глобальной установки навыка"; return 0; }
        log "3/5 навык глобально: x-harness-planning"
        for dest in $dirs; do install_tracked_skill "$src" "$name" "$dest"; done
        ;;
    esac
  }
  install_planning_skill
fi

# --- DSH hooks (optional) ---------------------------------------------------
gen_dsh_hooks() { # outfile — DSH tool names/keys differ (bash, edit, path...): agent-hook.py normalizes them
  run cp "$ROOT/adapters/agent-hook.py" "$PROJECT/.dsh/agent-hook.py"
  python3 - "$1" "$PROJECT" <<'PY'
import json, shlex, sys
dst, project = sys.argv[1], sys.argv[2]
hook = lambda event: "cd %s && python3 .dsh/agent-hook.py dsh %s" % (shlex.quote(project), event)
json.dump({"description": "x-harness hooks for DSH: .dsh/agent-hook.py runs the project's .claude/hooks",
           "hooks": {"SessionStart": [{"hooks": [{"type": "command", "command": hook("SessionStart"), "timeout": 30}]}],
                     "PreToolUse": [{"matcher": "bash|edit|write|read|apply_patch|Bash|Edit|Write|Read",
                                     "hooks": [{"type": "command", "command": hook("PreToolUse"), "timeout": 300}]}]}},
          open(dst, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
print("  создан", dst)
PY
}

# --- Kimi / ZCode project files ----------------------------------------------
if [ "$CLIENT_KIMI" = 1 ] && [ -d "$PROJECT/.claude/agents" ]; then
  log "4/5 Kimi: роли .agents/agents/*.md -> .claude/agents (один источник)"
  run mkdir -p "$PROJECT/.agents/agents"
  for f in "$PROJECT/.claude/agents"/*.md; do
    [ -f "$f" ] || continue
    n="$(basename "$f" .md)"; out="$PROJECT/.agents/agents/$n.md"
    if [ -e "$out" ] && [ "$FORCE" != 1 ]; then warn "есть $out — пропущен (нужен --force)"; continue; fi
    [ "$DRY" = 1 ] && { log "  [dry] $out"; continue; }
    desc="$(sed -n '2,/^---$/{s/^description: *//p;}' "$f" | head -1)"
    printf -- '---\nname: %s\ndescription: %s\n---\n\nРоль проекта. Прочитай `.claude/agents/%s.md` и выполняй его целиком: это единственный источник инструкции роли. Имена моделей Claude там (sonnet/opus/haiku) — не модели Kimi, игнорируй их.\n' \
      "$n" "$desc" "$n" > "$out"
  done
fi
if [ "$CLIENT_ZCODE" = 1 ] && [ -f "$PROJECT/.mcp.json" ]; then
  log "4/5 ZCode: .agents/mcp.json -> .mcp.json"
  if [ -e "$PROJECT/.agents/mcp.json" ] && [ "$FORCE" != 1 ]; then warn "есть .agents/mcp.json — пропущен (нужен --force)"
  else run mkdir -p "$PROJECT/.agents"; run ln -sfn ../.mcp.json "$PROJECT/.agents/mcp.json"; fi
fi

log "4/5 DSH-мост хуков: $DSH_HOOKS"
case "$DSH_HOOKS" in
  none) ;;
  bridge)
    # Мост читает конфиг один раз на весь процесс DSH, поэтому хуки — глобальный бандл x-harness
    # (package.json → dsh.bundle), а не файл в проекте. Проект переводчик находит по cwd сессии.
    command -v dsh >/dev/null 2>&1 || fail "для --dsh-hooks bridge нужен dsh в PATH"
    [ -n "$DSH_VERSION" ] || fail "для bridge нужна точная --dsh-version, равная версии Host"
    DSH_SOURCE="${XH_DSH_SOURCE:-github:cheusbeats/x-harness}"
    if [ "$DRY" = 1 ]; then
      log "  [dry] dsh plugin --profile $DSH_PROFILE add @deepseek-ai/dsh-hooks-claude-code@$DSH_VERSION @deepseek-ai/dsh-hook-protocol@$DSH_VERSION $DSH_SOURCE"
    else
      dsh plugin --profile "$DSH_PROFILE" add \
        "@deepseek-ai/dsh-hooks-claude-code@$DSH_VERSION" \
        "@deepseek-ai/dsh-hook-protocol@$DSH_VERSION" \
        "$DSH_SOURCE"
      log "  бандл x-harness добавлен в профиль $DSH_PROFILE; перезапусти профиль DSH"
    fi ;;
  community)
    command -v dsh >/dev/null 2>&1 || fail "для --dsh-hooks community нужен dsh в PATH"
    if [ "$DRY" = 1 ]; then
      log "  [dry] dsh plugin add dsh-hooks-plugin; .dsh/hooks.json"
    else
      dsh plugin --profile "$DSH_PROFILE" add dsh-hooks-plugin
      mkdir -p "$PROJECT/.dsh"
      gen_dsh_hooks "$PROJECT/.dsh/hooks.json"
      warn "community-плагин — сторонний код: проверь доверие, набор событий и семантику (skills/x-harness/references/08)"
    fi ;;
esac

# --- init planning (planning profile) ---------------------------------------
if [ "$PROFILE" = planning ]; then
  log "init: реестры planning/"
  if [ "$DRY" = 1 ]; then
    log "  [dry] bash .claude/scripts/planning-init.sh"
  else
    ( cd "$PROJECT" && bash .claude/scripts/planning-init.sh ) || fail "planning-init.sh завершился с ошибкой"
  fi
fi

# --- verify -----------------------------------------------------------------
log "5/5 проверка"
if [ "$VERIFY" = 1 ] && [ "$DRY" = 0 ]; then
  bash "$ROOT/verify.sh" --project "$PROJECT" --profile "$PROFILE" || warn "verify.sh нашёл расхождения (см. выше)"
fi


plugin_hint() {
  [ "$CLIENT_CODEX$CLIENT_KIMI$CLIENT_ZCODE$CLIENT_OPENCODE" = 0000 ] && return 0
  cat <<'HINT'

Плагин x-harness (хуки Kimi/ZCode/OpenCode; скилл в любом клиенте). Хуки срабатывают только в проектах с обвязкой:
  Codex:    codex plugin marketplace add cheusbeats/x-harness && codex plugin add x-harness@x-harness
  Kimi:     в Kimi Code — Plugins → Add from GitHub: cheusbeats/x-harness
  ZCode:    Settings → Plugins → marketplace cheusbeats/x-harness (формат .claude-plugin)
  OpenCode: ~/.config/opencode/opencode.json → "plugin": ["x-harness@git+https://github.com/cheusbeats/x-harness.git"]
HINT
}
if [ "$PROFILE" = planning ]; then
  cat <<EOF

Готово (planning). Дальше:
  - перезапусти клиента, чтобы он перечитал settings.json/навыки;
  - проверь: $ROOT/verify.sh --project "$PROJECT" --profile planning
  - заведи первую запись: .claude/scripts/registry.sh next-id PLAN
    и .claude/scripts/registry.sh add PLAN auto "Название плана";
  - правила — AGENTS.md и planning/README.md; параметры — .claude/planning.conf.
  - установка != исполнение: прогони $ROOT/tests/acceptance-planning.sh.
EOF
else
  cat <<EOF

Готово. Дальше:
  - перезапусти клиента (Claude Code / Codex / DSH-профиль), чтобы он перечитал хуки и навыки;
  - подтверди доверие к хукам в клиенте (Codex: /hooks; Claude: подтверждение при первом запуске);
  - проверь: $ROOT/verify.sh --project "$PROJECT" + $ROOT/bin/xh doctor;
  - установка != исполнение: прогони позитивный и негативный сценарий хука (skills/x-harness/references/03, 08).
EOF
fi
plugin_hint
