#!/usr/bin/env bash
# Dusk в параллельных шардах (HF-170). Запускает quality-gate.sh --merge.
#
#   dusk-shards.sh            прогон; число шардов — GATE_DUSK_SHARDS (по умолчанию 4)
#   dusk-shards.sh --plan N   напечатать разбиение классов: строка на шард (для теста полноты)
#
# У каждого шарда своя база app_dusk_N, свои базы Redis и свой `artisan serve` на порту 810N.
# Настройки идут из .env.dusk.local через окружение процесса, общий .env не подменяется, поэтому
# другие сессии и dev-приложение на время прогона ничего не теряют.
set -uo pipefail

split() {
  # Вес класса — число тестов, тяжёлые раскладываются первыми. Берём ВСЕ *Test.php: класс мимо шарда
  # не выполнился бы молча (полноту проверяет test_quality_gate.py).
  python3 - "$1" <<'PY'
import pathlib, re, sys
weights = {}
for path in pathlib.Path("tests/Browser").rglob("*Test.php"):
    weights[path.stem] = weights.get(path.stem, 0) + (len(re.findall(r"function test_|#\[Test\]", path.read_text())) or 1)
bins = [[0, []] for _ in range(int(sys.argv[1]))]
for name in sorted(weights, key=lambda n: (-weights[n], n)):
    target = min(bins, key=lambda b: b[0])
    target[0] += weights[name]
    target[1].append(name)
for _, names in bins:
    print("|".join(names))
PY
}

if [ "${1:-}" = "--plan" ]; then split "${2:?число шардов}"; exit $?; fi

# Имя compose-проекта: COMPOSE_PROJECT_NAME или имя основного чекаута (как у docker compose).
COMPOSE_PROJECT="${COMPOSE_PROJECT_NAME:-$(basename "$(dirname "$(git rev-parse --path-format=absolute --git-common-dir)")" | tr '[:upper:]' '[:lower:]' | tr -cd 'a-z0-9_-')}"
RUNNER="$COMPOSE_PROJECT-horizon-1"
SERVER="$COMPOSE_PROJECT-laravel.test-1"
SELENIUM="$COMPOSE_PROJECT-selenium-1"
PGSQL="$COMPOSE_PROJECT-pgsql-1"
BASE_PORT=8100
SHARDS="${GATE_DUSK_SHARDS:-4}"
MAIN_ROOT="$(dirname "$(git rev-parse --path-format=absolute --git-common-dir)")"
CONTAINER_DIR="/var/www/html${PWD#"$MAIN_ROOT"}"
OUT=storage/app/dusk-shards
ENV_FILE="$OUT/dusk.env"
DUSK_ENV=.env.dusk.local
[ -f "$DUSK_ENV" ] || DUSK_ENV="$MAIN_ROOT/.env.dusk.local"

is_count() { [[ "${1:-}" =~ ^[1-9][0-9]*$ ]]; }

is_count "$SHARDS" || { echo "[dusk] неверное число шардов: '$SHARDS'" >&2; exit 1; }
for c in "$RUNNER" "$SERVER" "$SELENIUM"; do
  docker ps --format '{{.Names}}' | grep -qx "$c" || { echo "[dusk] контейнер $c не запущен" >&2; exit 1; }
done

# Два прогона делят базы app_dusk_N и порты: второй дал бы ложные падения. mkdir атомарен, а каталог
# один на основной чекаут и все worktree. Зависший замок (после SIGKILL) снимает человек: самоснятие
# дало бы гонку двух владельцев.
LOCK="$MAIN_ROOT/storage/app/dusk-shards.lock"
if ! mkdir "$LOCK" 2>/dev/null; then
  echo "[dusk] уже идёт другой прогон шардов. Если это не так: rm -rf '$LOCK'" >&2; exit 1
fi

SERVE_PATTERN='port=81[0-9][0-9]|0\.0\.0\.0:81[0-9][0-9]'
PHPUNIT_PATTERN='phpunit\.dusk\.xml --no-coverage'
kill_shards() {
  docker exec "$RUNNER" pkill -f "$PHPUNIT_PATTERN" 2>/dev/null
  docker exec "$SERVER" pkill -f "$SERVE_PATTERN" 2>/dev/null
}
cleanup() {
  kill_shards
  rm -f "$ENV_FILE" storage/framework/dusk-running
  rm -rf "$LOCK"
}
trap cleanup EXIT
trap 'exit 130' INT TERM

# Замок наш, значит всё на этих портах и базах осталось от прогона, убитого через SIGKILL.
kill_shards

# Selenium без правки compose.yaml (нужен `sail up -d selenium`) держит одну сессию: лишние шарды
# встали бы в очередь и падали по таймауту.
max_sessions="$(docker exec "$SELENIUM" curl -s localhost:4444/status | python3 -c 'import json,sys; print(json.load(sys.stdin)["value"]["nodes"][0]["maxSessions"])')" || max_sessions=1
is_count "$max_sessions" || max_sessions=1
if [ "$SHARDS" -gt "$max_sessions" ]; then
  echo "[dusk] Selenium держит $max_sessions сесс., шардов столько же (нужно больше — sail up -d selenium)"
  SHARDS="$max_sessions"
fi

rm -rf "$OUT"; mkdir -p "$OUT"

# Laravel читает и .env, но окружение процесса важнее. Ключи, которых нет в .env.dusk.local, пустые:
# настоящие ключи из dev-окружения в Dusk попасть не должны (раньше их отсекала подмена .env).
python3 - "$DUSK_ENV" "$ENV_FILE" <<'PY' || { echo "[dusk] не удалось подготовить окружение" >&2; exit 1; }
import os, re, sys
def read(path):
    values = {}
    if os.path.exists(path):
        for line in open(path):
            match = re.match(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$", line.rstrip("\n"))
            if match:
                values[match[1]] = match[2].strip().strip('"')
    return values
dusk = read(sys.argv[1])
dusk = {k: re.sub(r"\$\{(\w+)\}", lambda m: dusk.get(m[1], ""), v) for k, v in dusk.items()}
for key in read(".env"):
    dusk.setdefault(key, "")
fd = os.open(sys.argv[2], os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
os.write(fd, "".join(f"{k}={v}\n" for k, v in dusk.items()).encode())
PY
touch storage/framework/dusk-running

split "$SHARDS" >"$OUT/plan.txt" || exit 1

# Сколько тестов обязаны выполнить шарды: сверка в конце ловит пустой фильтр и класс мимо шарда.
expected="$(docker exec -e XDEBUG_MODE=off -w "$CONTAINER_DIR" "$RUNNER" \
  php vendor/phpunit/phpunit/phpunit -c phpunit.dusk.xml --list-tests | grep -c '^ - ')"
is_count "$expected" || { echo "[dusk] не удалось получить список тестов" >&2; exit 1; }

run_shard() {
  local i="$1" filter="$2" port=$((BASE_PORT + $1)) db="app_dusk_$1" rc=0
  local envs=(--env-file "$ENV_FILE" -e DUSK_SHARD="$i" -e APP_URL="http://laravel.test:$port" -e DB_DATABASE="$db"
              -e REDIS_DB=$((2 + 2 * i)) -e REDIS_CACHE_DB=$((3 + 2 * i)) -e CACHE_PREFIX="app-dusk-$i-cache-" -e XDEBUG_MODE=off)
  docker exec "$PGSQL" psql -U sail -d postgres -Atc "select 1 from pg_database where datname='$db'" | grep -q 1 \
    || docker exec "$PGSQL" psql -U sail -d postgres -qc "create database $db" || return 1
  docker exec -d "${envs[@]}" -e PHP_CLI_SERVER_WORKERS=2 -w "$CONTAINER_DIR" "$SERVER" \
    php -d variables_order=EGPCS artisan serve --host=0.0.0.0 --port="$port" --no-reload
  local tries=0
  until docker exec "$SERVER" php -r "exit(@fsockopen('127.0.0.1', $port) ? 0 : 1);"; do
    tries=$((tries + 1)); [ "$tries" -lt 30 ] || { echo "[dusk] шард $i: сервер не поднялся" >&2; return 1; }
    sleep 1
  done
  docker exec "${envs[@]}" -w "$CONTAINER_DIR" "$RUNNER" \
    php -d variables_order=EGPCS vendor/phpunit/phpunit/phpunit -c phpunit.dusk.xml --no-coverage --do-not-cache-result \
    --fail-on-empty-test-suite --filter "\\\\($filter)::" >"$OUT/shard$i.log" 2>&1 || rc=$?
  echo "[dusk] шард $i, rc=$rc: $(sed 's/\x1b\[[0-9;]*m//g' "$OUT/shard$i.log" | grep -E '^(OK|Tests:)' | tail -1)"
  [ "$rc" -eq 0 ] || tail -40 "$OUT/shard$i.log"
  return "$rc"
}

pids=()
i=0
while IFS= read -r filter; do
  i=$((i + 1))
  [ -n "$filter" ] || continue
  run_shard "$i" "$filter" &
  pids+=($!)
done <"$OUT/plan.txt"

[ "${#pids[@]}" -gt 0 ] || { echo "[dusk] нет ни одного шарда" >&2; exit 1; }

status=0
for pid in "${pids[@]}"; do
  wait "$pid" || status=1
done

executed="$(sed 's/\x1b\[[0-9;]*m//g' "$OUT"/shard*.log | grep -oE '^(OK \(|Tests: )[0-9]+' | grep -oE '[0-9]+' | awk '{s+=$1} END {print s+0}')"
echo "[dusk] выполнено тестов: $executed из $expected"
if [ "$executed" != "$expected" ]; then
  echo "[dusk] выполнено не столько тестов, сколько найдено" >&2
  status=1
fi
exit "$status"
