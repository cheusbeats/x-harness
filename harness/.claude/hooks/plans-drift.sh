#!/usr/bin/env bash
#
# Детектор расхождений между планами и реальностью репозитория.
#
# Зачем: планы в planning/ пишутся руками, а код коммитят разные сессии и разные
# агенты — в том числе когда никто не смотрит. Раз индекс не привязан к git,
# он молча устаревает: 2026-08-02 нашлось, что PLAN-90 числился «код не начат»
# через месяц после мержа Фаз 1–2, а PLAN-90.4 не был заведён в индексе вовсе.
#
# Дизайн (v2, тот же день — v1 не пережил собственную первую проверку):
#   - per-PLAN сравнение «последний код-коммит по токену» vs «последнее упоминание
#     токена в СОДЕРЖИМОМ индекса», а не единая точка «когда индекс правили в
#     последний раз». Единая точка — ловушка: любая косметическая правка
#     ACTIVE_PLANS.md сдвигает окно вперёд и молча прячет старый непокрытый план.
#   - индекс проверяется по добавленным строкам диффа (`git log -p`), не по
#     тексту коммита — план может попасть в индекс без переиздания номера в
#     commit message (например, как строка таблицы-указателя).
#   - код-коммиты идут с `--first-parent`: без него merge-коммиты дают 0 файлов
#     в diff и весь мёрж истории попросту не существует для скрипта (проверено
#     на merge 1550852 — PLAN-87/88/89/90.1/90.2).
#
# Запуск: автоматически на SessionStart (.claude/settings.json), либо руками:
#   .claude/hooks/plans-drift.sh
#
# Выход всегда 0 — это информатор, а не гейт.

set -uo pipefail

repo="$(git rev-parse --show-toplevel 2>/dev/null)" || exit 0
cd "$repo" || exit 0
command -v python3 >/dev/null 2>&1 || exit 0

# Чистка маркеров слова владельца (E10/E11): .claimed, просроченные (24 ч), влитые. Молча.
python3 "$(dirname "$0")/owner_ok.py" cleanup >/dev/null 2>&1 || true

index_files=(planning/ACTIVE_PLANS.md planning/PLANS.md)
[ -f planning/ACTIVE_PLANS.md ] || exit 0

# Горизонт для «код-коммитов»: 90 дней. Не совпадение — PLANS.md как дисциплина
# завёлся 2026-06-04, всё до этого числится историческим долгом и не относится
# к «текущая работа отражена». Пере-нагонять полугодовые дыры на каждой сессии —
# шум, не сигнал; для разового аудита есть `git log --since=... --first-parent`
# вручную.
horizon_days=90

# «Кандидаты в журнал» — это ПОСЛЕДОВАТЕЛЬНАЯ выметка: разобрал коммит один раз,
# трогать его снова не нужно. Единая точка отсчёта здесь корректна (в отличие от
# per-plan сравнения выше) — потому что метка ставится в тот же файл, который эта
# проверка контролирует: правка JOURNAL.md И ЕСТЬ факт «на этот коммит посмотрели».
# 90-дневное окно для НЕГО не годится — до создания JOURNAL.md коммиты по
# определению не могли быть в нём упомянуты, окно тонуло бы в старом бэклоге.
journal_sync="$(git log -1 --format=%H -- planning/HOTFIXES.md planning/JOURNAL.md 2>/dev/null)"
journal_range="HEAD"
[ -n "$journal_sync" ] && journal_range="${journal_sync}..HEAD"

tmp_code="$(mktemp)"
tmp_idx="$(mktemp)"
tmp_journal="$(mktemp)"

git log --first-parent --since="${horizon_days}.days.ago" \
  --format='%H%x01%ct%x01%s%x01%b%x02' \
  -- app resources routes database config tests \
  > "$tmp_code" 2>/dev/null

git log -p --format='COMMIT%x01%H%x01%ct%x02%n' \
  -- "${index_files[@]}" \
  > "$tmp_idx" 2>/dev/null

if [ -n "$journal_sync" ]; then
  git log --first-parent --format='%H%x01%ct%x01%s%x01%b%x02' "$journal_range" \
    -- app resources routes database config tests \
    > "$tmp_journal" 2>/dev/null
fi

tmp_drift_out="$(mktemp)"
tmp_unlogged_out="$(mktemp)"
trap 'rm -f "$tmp_code" "$tmp_idx" "$tmp_journal" "$tmp_drift_out" "$tmp_unlogged_out"' EXIT

python3 - "$tmp_code" "$tmp_idx" "$tmp_journal" "$tmp_drift_out" "$tmp_unlogged_out" <<'PY'
import re, sys

code_path, idx_path, journal_path, drift_out, unlogged_out = sys.argv[1:6]
token_re = re.compile(r'PLAN-\d+(?:\.\d+)?')
logged_re = re.compile(r'PLAN-\d+(?:\.\d+)?|HF-\d+')  # коммит назвал план или хотфикс

# --- код: токен ищем в тексте коммита (заголовок+тело — задача формулируется словами) ---
code_map = {}      # token -> (ts, short_sha, subject)
raw = open(code_path, encoding='utf-8', errors='replace').read()
for rec in raw.split('\x02'):
    rec = rec.strip('\n')
    if not rec.strip():
        continue
    parts = rec.split('\x01', 3)
    if len(parts) < 4:
        continue
    sha, ts, subj, body = parts
    ts_i = int(ts)
    # Заголовок важнее тела. Если коммит назвал план в заголовке — это и есть его
    # план, а номера в теле там обычно контекст, а не работа. Пример из истории:
    # `13362fd docs(planning): PLAN-86 закрыт` трогает тест, а в теле упоминает
    # PLAN-84 и PLAN-87 как позицию вставки записи в PLANS.md — хук годами
    # показывал по ним ложный дрейф. Тело остаётся резервом для коммитов с
    # безымянным заголовком (серия PLAN-87/88/89/97, где номер только в теле).
    tokens = set(token_re.findall(subj)) or set(token_re.findall(body))
    for p in tokens:
        if p not in code_map or ts_i > code_map[p][0]:
            code_map[p] = (ts_i, sha[:7], subj.strip())

# --- журнал: коммиты после последней правки JOURNAL.md, без ни одного PLAN-N.
# Ищем в заголовке+теле, как и в code_map — иначе теряется та же серия
# PLAN-87/88/89/97, где номер только в теле, а не в заголовке.
unlogged = []
jraw = open(journal_path, encoding='utf-8', errors='replace').read()
for rec in jraw.split('\x02'):
    rec = rec.strip('\n')
    if not rec.strip():
        continue
    parts = rec.split('\x01', 3)
    if len(parts) < 4:
        continue
    sha, _ts, subj, body = parts
    if not logged_re.search(subj + '\n' + body):
        unlogged.append((sha[:7], subj.strip()))

# --- индекс: токен ищем в ДОБАВЛЕННЫХ строках диффа — план может попасть в
# индекс без переиздания номера в самом commit message (например, свёрнутая
# строка таблицы-указателя), текстовый поиск по коммиту такое бы не поймал.
idx_map = {}        # token -> (ts, short_sha)
cur_ts = cur_sha = None
for line in open(idx_path, encoding='utf-8', errors='replace'):
    if line.startswith('COMMIT\x01'):
        parts = line.rstrip('\n').split('\x01')
        cur_sha = parts[1][:7]
        cur_ts = int(parts[2].split('\x02')[0])
        continue
    if line.startswith('+++') or line.startswith('---'):
        continue
    if line.startswith('+'):
        for p in set(token_re.findall(line)):
            if cur_ts is not None and (p not in idx_map or cur_ts > idx_map[p][0]):
                idx_map[p] = (cur_ts, cur_sha)

drift = []
for p, (ts, sha, subj) in code_map.items():
    if p not in idx_map or idx_map[p][0] < ts:
        drift.append((p, sha, subj))
drift.sort()

with open(drift_out, 'w') as f:
    for p, sha, subj in drift:
        f.write(f"{p}\t{sha}\t{subj[:70]}\n")

with open(unlogged_out, 'w') as f:
    for sha, subj in unlogged[:5]:
        f.write(f"{sha}\t{subj[:70]}\n")
    if len(unlogged) > 5:
        f.write(f"...ещё {len(unlogged) - 5}\n")
PY

# --- план-документы без записи ни в одном индексе (PLAN-90.4 был именно таким) ---
orphans=""
for doc in planning/plans/PLAN-*.md; do
  [ -e "$doc" ] || continue
  token="$(basename "$doc" | grep -oE '^PLAN-[0-9]+(\.[0-9]+)?')"
  [ -n "$token" ] || continue
  last="$(git log -1 --format=%ct -- "$doc" 2>/dev/null)"
  [ -n "$last" ] || continue
  # Старьё (>полгода) не ворошим — тот же принцип, что и горизонт кода.
  [ "$last" -lt "$(( $(date +%s) - 15552000 ))" ] && continue
  if ! grep -qF "$token" planning/ACTIVE_PLANS.md planning/PLANS.md planning/plans/closed/_map.tsv 2>/dev/null; then
    orphans="${orphans} ${token}"
  fi
done

# --- банк идей RM-N (PLAN-144): файлы planning/roadmap/RM-*.md <-> таблица planning/ROADMAP.md ---
roadmap_lines=""
if [ -f planning/ROADMAP.md ] && [ -d planning/roadmap ]; then
  index_ids="$(grep -oE '^\| *\[?RM-[0-9]+' planning/ROADMAP.md | grep -oE 'RM-[0-9]+' | sort -u)"
  file_ids="$(ls planning/roadmap 2>/dev/null | grep -oE '^RM-[0-9]+' | sort -u)"
  # (1) файл без строки в индексе
  for id in $file_ids; do
    printf '%s\n' "$index_ids" | grep -qx "$id" || roadmap_lines="${roadmap_lines}    $id — файл planning/roadmap/$id-*.md без строки в ROADMAP.md
"
  done
  # (2) строка индекса без файла
  for id in $index_ids; do
    printf '%s\n' "$file_ids" | grep -qx "$id" || roadmap_lines="${roadmap_lines}    $id — строка в ROADMAP.md без файла planning/roadmap/$id-*.md
"
  done
  # (3) коммиты, называющие RM-N, после которых ни индекс, ни файл идеи не правились
  while read -r csha cts; do
    [ -n "$csha" ] || continue
    for id in $(git log -1 --format=%B "$csha" | grep -oE '(^|[^A-Z])RM-[0-9]+' | grep -oE 'RM-[0-9]+' | sort -u); do
      last="$(git log -1 --format=%ct -- planning/ROADMAP.md "planning/roadmap/$id-*.md" 2>/dev/null)"
      if [ -z "$last" ] || [ "$last" -lt "$cts" ]; then
        roadmap_lines="${roadmap_lines}    $id — коммит $(git log -1 --format='%h %s' "$csha" | cut -c1-70): индекс и файл идеи с тех пор не правились
"
      fi
    done
  done < <(git log --since="${horizon_days}.days.ago" -E --grep='(^|[^A-Z])RM-[0-9]' --format='%H %ct' 2>/dev/null)
  # (4) «→ PLAN-N» в индексе должен вести на существующий план
  for t in $(grep -oE '→ *PLAN-[0-9]+(\.[0-9]+)?' planning/ROADMAP.md | grep -oE 'PLAN-[0-9]+(\.[0-9]+)?' | sort -u); do
    ls planning/plans/"$t"-*.md >/dev/null 2>&1 || grep -qE "${t//./\\.}([^0-9.]|\$)" planning/PLANS.md planning/plans/closed/_map.tsv 2>/dev/null \
      || roadmap_lines="${roadmap_lines}    $t — в ROADMAP.md стоит «→ $t», но документа planning/plans/$t-*.md нет
"
  done
elif [ -f planning/ROADMAP.md ] && grep -qE '^\| *\[?RM-[0-9]+' planning/ROADMAP.md; then
  roadmap_lines="    в ROADMAP.md есть строки RM-N, но каталога planning/roadmap/ нет
"
fi

# --- корень planning/ — только служебные файлы (PLAN-144): всё прочее — план в plans/ или идея в roadmap/ ---
root_extra=""
# Перебор по тому, что видит git (tracked + untracked без игнорируемого): .DS_Store и прочий мусор из .gitignore не шумят.
for name in $(git ls-files -co --exclude-standard -- planning | awk -F/ 'NF>1{print $2}' | sort -u); do
  case "$name" in
    ACTIVE_PLANS.md|HOTFIXES.md|README.md|ROADMAP.md|PLANS.md|plans|roadmap|hotfixes) ;;
    *) root_extra="${root_extra} ${name}" ;;
  esac
done
[ -n "$root_extra" ] && roadmap_lines="${roadmap_lines}    лишнее в корне planning/:${root_extra} (допустимы только служебные файлы, планы — в plans/, идеи — в roadmap/)
"

# --- окружение (PLAN-145, E13/E19): бюджет стартового набора и git-хуки ---
# Стартовый набор = то, что агент читает в начале каждой сессии. Печатаем ТОЛЬКО при превышении.
# Файлы-слагаемые: CLAUDE.md, .claude/rules/*, индекс памяти, planning/README.md.
# Переменные HARNESS_START_BUDGET_BYTES / HARNESS_MEMORY_INDEX нужны тестам.
env_lines=""
budget="${HARNESS_START_BUDGET_BYTES:-53248}"   # 52 КБ
# Каталог памяти Claude Code: путь проекта, где каждый не-алфанумерический символ заменён на «-».
memory_index="${HARNESS_MEMORY_INDEX:-$HOME/.claude/projects/$(pwd -P | sed 's#[^A-Za-z0-9]#-#g')/memory/MEMORY.md}"
start_bytes=0
for f in CLAUDE.md .claude/rules/* planning/README.md "$memory_index"; do
  [ -f "$f" ] && start_bytes=$((start_bytes + $(wc -c < "$f")))
done
if [ "$start_bytes" -gt "$budget" ]; then
  env_lines="${env_lines}    стартовый набор (CLAUDE.md + rules + MEMORY.md + README) $((start_bytes / 1024)) КБ > бюджета $((budget / 1024)) КБ (E13)
"
fi
if [ "$(git config core.hooksPath 2>/dev/null)" != ".githooks" ]; then
  env_lines="${env_lines}    git-хуки не подключены: .claude/scripts/install-githooks.sh (E19) — без них проверки не работают в обычном терминале
"
fi

drift_lines="$(cat "$tmp_drift_out" 2>/dev/null)"
unlogged_lines="$(cat "$tmp_unlogged_out" 2>/dev/null)"

# Молчим, когда расхождений нет: строка «всё синхронно» уходила в контекст
# каждой сессии впустую. Хук говорит только когда нашёл.
if [ -z "$drift_lines" ] && [ -z "$orphans" ] && [ -z "$unlogged_lines" ] && [ -z "$roadmap_lines" ] && [ -z "$env_lines" ]; then
  exit 0
fi

echo "СВЕРКА ПЛАНОВ (окно ${horizon_days}д по коду, per-plan сравнение с содержимым индекса):"

if [ -n "$drift_lines" ]; then
  echo
  echo "  Код по плану новее, чем последнее упоминание в индексе (или там его нет):"
  printf '%s\n' "$drift_lines" | while IFS=$'\t' read -r token sha subj; do
    [ -n "$token" ] || continue
    echo "    $token — $sha $subj"
  done
  echo "  Проверь planning/ACTIVE_PLANS.md и planning/PLANS.md: план мог закрыться"
  echo "  или просто ждать своей строки. Не факт что это баг — проверь код и git log,"
  echo "  не только формулировку плана."
fi

if [ -n "$orphans" ]; then
  echo
  echo "  План-документы без записи в ACTIVE_PLANS.md и PLANS.md (план невидим):"
  for o in $orphans; do echo "    $o"; done
fi

if [ -n "$unlogged_lines" ]; then
  echo
  echo "  Коммиты с кодом после последней правки HOTFIXES.md, без единого PLAN-N/HF-N (кандидаты в реестр хотфиксов: registry.sh add HF):"
  printf '%s\n' "$unlogged_lines" | while IFS=$'\t' read -r sha subj; do
    [ -n "$sha" ] || continue
    echo "    $sha $subj"
  done
fi

if [ -n "$roadmap_lines" ]; then
  echo
  echo "  Банк идей RM-N и корень planning/ (ROADMAP.md <-> roadmap/):"
  printf '%s' "$roadmap_lines"
fi

if [ -n "$env_lines" ]; then
  echo
  echo "  Окружение и бюджет контекста:"
  printf '%s' "$env_lines"
fi

# Отработанные ветки. Ветка, целиком влитая в main, больше ничего не держит:
# её история уже в main, а живой список веток должен показывать только то, над
# чем идёт работа. Правило — CLAUDE.md → «Git workflow».
merged_branches=$(git branch --merged main --format='%(refname:short)' 2>/dev/null | grep -vx 'main' || true)
if [ -n "$merged_branches" ]; then
  echo
  echo "  Ветки, влитые в main — снести (git branch -d <ветка>):"
  printf '%s\n' "$merged_branches" | while read -r b; do
    [ -n "$b" ] || continue
    echo "    $b"
  done
fi

echo
echo "Актуализируй planning/ прежде чем браться за новое. Правило — CLAUDE.md → «Планирование — три реестра»."
exit 0
