#!/usr/bin/env bash
#
# Сверка ССЫЛОК ВНУТРИ плана с реальным кодом.
#
# Зачем отдельно от plans-drift.sh: тот сверяет ИНДЕКС с гитом («план числится
# не начатым, а код влит»). Он не заглядывает внутрь документа, а гниёт как раз
# содержимое: план утверждает «сторож зовёт finalize(force: true)», а в коде
# вызывателя нет вовсе — и это выясняется только на ревью, четвёртым проходом.
#
# Причина завести: 2026-09-05, PLAN-110. Четыре прохода ревью, 17 блокирующих
# находок; примерно треть — не дыры в замысле, а расхождение плана с кодом,
# которое можно было увидеть механически.
#
# Проверяет ровно две однозначные вещи, чтобы не шуметь:
#   1. пути файлов  — `app/Foo/Bar.php` существует;
#   2. `Класс::член` — файл класса найден И имя члена в нём встречается.
# Всё остальное (голые константы, методы без класса, придуманные имена) НЕ
# трогает: план описывает и будущий код тоже, и крик на каждую будущую сущность
# сделает скрипт бесполезным через неделю.
#
# ЧЕГО СКРИПТ НЕ УМЕЕТ, и на это нельзя полагаться: он проверяет, что сущность
# СУЩЕСТВУЕТ, но не что она используется. Мёртвый `finalize(force: true)` —
# метод есть, производственного вызывателя нет — он не поймает. Такое находит
# только чтение кода.
#
# Ненайденное — НЕ ошибка сама по себе: у открытого плана это будущий код.
# Смысл появляется ПЕРЕД ЗАКРЫТИЕМ плана: там всё уже должно резолвиться.
#
# Запуск: .claude/scripts/plan-code-refs.sh planning/plans/PLAN-107-*.md

set -uo pipefail
cd "${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel)}" || exit 1

[ $# -eq 0 ] && { echo "нужен путь к плану: $0 planning/plans/PLAN-N-*.md" >&2; exit 2; }


# Признано ли расхождение в блоке поправок? Закрытый план переписывать нельзя —
# он документирует, что решали ТОГДА. Поэтому «расхождение» = ненайдено И не
# названо в разделе «Поправка по факту реализации». Так правило «перед закрытием
# пусто» становится достижимым, не требуя подделки истории.
acknowledged() {
  local plan="$1" name="$2"
  # Признание ищем и по полному имени, и по короткому: план может писать
  # `Settings\Schedules::foo`, а поправка — просто Schedules::foo.
  local short="${name##*\\}"
  awk '/^## Поправка по факту реализации/{f=1} f' "$plan" 2>/dev/null \
    | grep -qF -e "$name" -e "$short"
}

missing=0
for plan in "$@"; do
  [ -f "$plan" ] || { echo "нет файла: $plan" >&2; exit 2; }
  echo "── $plan"

  export plan

  # 1. Пути файлов в обратных кавычках.
  grep -oE '`[a-z][A-Za-z0-9_.-]*(/[A-Za-z0-9_.-]+)+\.(php|neon|json|js|css|md|sh)`' "$plan" \
    | tr -d '`' | sort -u | while read -r path; do
      # Планы часто пишут путь от корня вьюх, а не от корня репозитория.
      if [ ! -e "$path" ] && [ -z "$(find . -path "*/$path" -not -path "./node_modules/*" -not -path "./vendor/*" -print -quit 2>/dev/null)" ]; then
        acknowledged "$plan" "$path" || echo "  ✗ файла нет: $path"
      fi
    done

  # 2. Класс::член — ищем файл класса по basename, потом член внутри него.
  grep -oE '`([A-Za-z][A-Za-z0-9_]*\\)*[A-Za-z][A-Za-z0-9_]*::[A-Za-z_][A-Za-z0-9_]*(\(\))?`' "$plan" \
    | tr -d '`' | sed 's/()$//' | sort -u | while read -r ref; do
      class="${ref%%::*}"; class="${class##*\\}"
      # Фасады и классы фреймворка в app/ не лежат — молча пропускаем, иначе
      # скрипт кричит на каждый DB::transaction и его перестают читать.
      case "$class" in
        DB|Cache|Log|Queue|Schema|Http|Str|Arr|Carbon|Schedule|Artisan|Auth|Gate|Route|\
        Config|Storage|Mail|Event|Bus|Session|Validator|Hash|File|Redis|Blade|View|URL|\
        Response|Request|Livewire|Builder|Collection|Model|Command|RateLimiter|Sleep) continue ;;
      esac
      member="${ref##*::}"
      files=$(find app database tests -name "${class}.php" -type f 2>/dev/null)
      # Наследованное от Eloquent/фреймворка в самом классе не объявлено —
      # проверять там нечего, а шуметь вредно.
      case "$member" in
        factory|create|update|query|find|findOrFail|updateOrCreate|firstOrCreate|firstOrFail|\
        delete|save|where|whereIn|get|first|count|pluck|make|all|insert|upsert|increment|\
        decrement|refresh|fresh|sole|each|chunk|dispatch|fake|assertPushed|value|exists|cases|from|tryFrom) continue ;;
      esac
      if [ -z "$files" ]; then
        acknowledged "$plan" "$ref" || echo "  ✗ класса нет: ${class} (из ${ref})"
      elif ! grep -qE "(function|const|case)( +[A-Za-z_?|]+)? +${member}\b|\\\$${member}\b" $files; then
        # Колонка таблицы читается как свойство и в классе не объявлена —
        # ищем её в миграциях, прежде чем ругаться.
        if ! grep -rqE "'${member}'|\"${member}\"" database/migrations 2>/dev/null; then
          acknowledged "$plan" "$ref" || echo "  ✗ члена нет: ${ref}"
        fi
      fi
    done
done

echo
echo "Ненайденное у ОТКРЫТОГО плана — вероятно будущий код, это норма."
echo "Перед закрытием плана список обязан быть пустым."
