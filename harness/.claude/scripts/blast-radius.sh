#!/usr/bin/env bash
# Радиус поражения: кто в коде читает названные символы, таблицы и колонки.
#
# Заведён 2026-09-07 после PLAN-108: пять проходов ревью, и находки трёх из них
# были не дырами замысла, а невыявленным списком потребителей — пять читателей
# истории позиций, шесть мест ветвления по источнику прогона, девять мест, где
# зашито «восемь задач». Всё это перечисляется механически за секунды; платить
# за это deep-reasoner'у по 200k токенов незачем.
#
#   .claude/scripts/blast-radius.sh CaptureRunSource capture_runs.region_id in_free_serp
#
# Аргумент — что угодно, что ищется по коду: класс, метод, таблица, колонка.
# Форму `таблица.колонка` разбирает сам: ищет и полное имя, и голую колонку.
set -uo pipefail

cd "$(git rev-parse --show-toplevel)" || exit 1

if [ $# -eq 0 ]; then
    echo "Usage: $0 <символ|таблица|колонка>… (пример: CaptureRunSource capture_runs.region_id)" >&2
    exit 1
fi

# Каталоги кода. Тесты отдельной секцией: сломанный тест — тоже потребитель,
# но в план он идёт другой строкой, чем прод-код.
CODE_DIRS=(app config routes database resources)
TEST_DIRS=(tests)

section() {
    local needle=$1 label=$2
    shift 2
    local hits
    hits=$(grep -rn --binary-files=without-match -- "$needle" "$@" 2>/dev/null \
        | grep -v '/vendor/' | grep -v '/node_modules/')
    if [ -z "$hits" ]; then
        echo "    $label: —"
        return
    fi
    echo "    $label: $(printf '%s\n' "$hits" | wc -l | tr -d ' ') строк в $(printf '%s\n' "$hits" | cut -d: -f1 | sort -u | wc -l | tr -d ' ') файлах"
    printf '%s\n' "$hits" | sed 's/^/      /'
}

for arg in "$@"; do
    echo "── $arg"
    section "$arg" "код" "${CODE_DIRS[@]}"
    section "$arg" "тесты" "${TEST_DIRS[@]}"

    # `таблица.колонка` — колонка живёт и без имени таблицы (Eloquent-модели,
    # миграции, фабрики), поэтому ищем её ещё и отдельно.
    if [[ "$arg" == *.* ]]; then
        column=${arg##*.}
        echo "    голая колонка \`$column\`:"
        section "$column" "код" "${CODE_DIRS[@]}"
        section "$column" "тесты" "${TEST_DIRS[@]}"
    fi
    echo
done
