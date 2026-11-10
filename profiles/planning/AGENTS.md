# AGENTS.md — планирование через реестры

Проект ведёт работу через реестры в `planning/` и строгий планировочный слой (по умолчанию).
Ниже — обязательный минимум для агента; полные правила реестров — `planning/README.md`.
Task-лист ассистента живёт в сессии и не переживает `git pull`: источник правды об этапе — `planning/`.

## Старт работы

1. Прочитай `planning/ACTIVE_PLANS.md` — срез активных планов.
2. Разбери вывод `.claude/hooks/plans-drift.sh` (Claude Code/Codex запускают его на SessionStart; руками тоже можно).
3. Детали нужного плана: `.claude/scripts/registry.sh show PLAN-N` и раздел `## Резюме`, а не всё тело.

## Три реестра

| Реестр | Индекс (корень `planning/`) | Тело |
|---|---|---|
| RM — идея | `ROADMAP.md` | `roadmap/RM-N-*.md` |
| PLAN — план | `ACTIVE_PLANS.md` (в работе), `PLANS.md` (закрытые) | `plans/PLAN-N-*.md`; запись о закрытии — `plans/closed/PLAN-N.md` |
| HF — хотфикс | `HOTFIXES.md` | `hotfixes/HF-N-*.md` |

- **PLAN** — есть что проектировать (несколько связанных задач, решения, дизайн): `plans/PLAN-{N}-kebab.md` + строка в `ACTIVE_PLANS.md`.
- **HF** — правка, для которой план избыточен (багфикс, мелкая правка): ветка `hotfix/*`, `hotfixes/HF-N-*.md` + строка в `HOTFIXES.md`.
- **RM** — идея «потом»: только по прямому слову владельца; сам ничего в roadmap не добавляешь.
- В корне `planning/` — только служебные файлы и каталоги `plans/ roadmap/ hotfixes/`; всё прочее — в тело записи.

## Индексы правит только registry.sh

- `.claude/scripts/registry.sh next-id <RM|PLAN|HF>` · `add <RM|HF|PLAN> <id|auto> "название"` · `set-status <id> <статус>` · `show <id>` · `check`.
- Прямой Edit/Write по индексу блокирует `.claude/hooks/registry-guard.sh`; ручная строка через Bash — тоже нарушение, её ловит `registry.sh check` по форме.
- Номер сквозной (`next-id`), не переиспользуется. Закрытые записи (`plans/closed/*`) не переписываем.
- Словарь статусов (полное совпадение, иначе `check` падает): RM — `идея`, `отложена`, `стала PLAN-N`, `отклонена`; PLAN — `черновик`, `в работе`, `на паузе`, `ждёт владельца`, `закрыт`, `аннулирован`; HF — `влит`, `откачен`.

## Формат плана

- Рекомендуемый шаблон: `# PLAN-N — название`, строка «Статус / ветка / дата», затем `## Резюме` (цель, что меняем, решения, текущий статус). Строку про ветку/дату и содержание резюме пишет автор: `registry.sh add PLAN` создаёт только `**Статус:**` и пустой `## Резюме`.
- Резюме — первым разделом: для планов начиная с `PLAN_SUMMARY_MIN_NUMBER` оно обязательно.
- Перед закрытием `.claude/scripts/plan-code-refs.sh planning/plans/PLAN-N-*.md` должен быть пуст (признанные расхождения — в разделе «Поправка по факту реализации»).

## Строгий слой (STRICT=on по умолчанию)

Профиль ставится строгим: те же барьеры дисциплины, что в полном профиле, но без Laravel. Отключается
только владельцем — `STRICT=off` в `.claude/planning.conf` (файл защищён, см. E18).

- **E2. Ветки.** Код (`CODE_ROOTS`, `CODE_FILES`) — только на `feature/PLAN-N-*` или `hotfix/*`. На `MAIN_BRANCH` правки кода и коммиты запрещены (разрешены `planning/`, `docs/`, `*.md` и прочее не-код; исключение — идущие merge/rebase/cherry-pick). На прочих ветках — только `planning/`, `docs/`, `*.md` и не-код.
- **E18. Защищённые пути.** `.claude/hooks/`, `.claude/scripts/`, `.claude/settings.json`, `.claude/planning.conf`, `.githooks/`, `AGENTS.md`, `.codex/` — только с маркером владельца `hooks-edit <ветка>`.
- **E16. Обходы хуков.** `--no-verify`, `-n`, `git config core.hooksPath …`, `-c core.hooksPath=…`, переменные `GIT_CONFIG_*` — запрещены.
- **Main.** Коммит на `MAIN_BRANCH` агенту запрещён. Мерж в `MAIN_BRANCH` — только из `feature/PLAN-N-*`/`hotfix/*`, при чистых реестрах, токенах во всех коммитах ветки и маркере владельца `merge <ветка>`; при заданном `GATE_MERGE` — после зелёного гейта. Пуш: `main-push-guard` блокирует force/delete любого refspec и push main офлайн без remote-tracking (просит `git fetch`); git `pre-push` — non-fast-forward любой ветки, удаление main, push в main из не-main, прямые коммиты впереди `<remote>/main`. Первый push main (удалённого main ещё нет) разрешён; пуши `feature/*`, `hotfix/*` и теги проходят.
- **Quality Gate.** `GATE_FAST` — перед коммитом, `GATE_MERGE` — перед мержем (команды проекта из conf; пусто — шаг пропущен). Запуск: `.claude/scripts/quality-gate.sh --fast|--merge`, для generic — `bin/xh gate --fast|--merge`. Это НЕ Laravel Quality Gate: профиль только исполняет команды проекта.

`STRICT=off` (только владелец) выключает strict guard'ы (exit 0), E2/E18 и `GATE_FAST` в
`pre-commit`, strict-часть `pre-push` и `merge-ready`. Базовый слой остаётся: реестры и `registry.sh check`,
owner-ok для `close-plan`/`rm-add`, токен в `commit-msg`, `plans-drift`.

Кто что блокирует:

- **Событийные хуки** (`branch-guard`, `commit-gate`, `merge-gate`, `main-push-guard` в Claude Code/Codex) — ранняя блокировка действия до выполнения. В DSH — только через мост; в generic их нет.
- **Git-хуки** (`pre-commit`, `commit-msg`, `pre-push`) — авторитетная проверка в терминале; работают везде, где подключён `core.hooksPath=.githooks`.
- **`bin/xh gate|hook`** — ручной запуск для generic; это не автозащита.
- Обход `--no-verify` отключает git-хуки; в Claude/Codex его ловит событийный `commit-gate`, в generic технически возможен — правило запрещает.

## Слово владельца (owner-ok)

Маркер создаёт **только владелец в своём терминале**; агент `planning-owner-ok.sh` не запускает и в
`.claude/state/planning-owner-ok/` не пишет — это блокирует `.claude/hooks/owner-ok-guard.sh`.

| Вид | Команда | Когда нужен |
|---|---|---|
| закрытие плана | `planning-owner-ok.sh close-plan PLAN-N` | `set-status PLAN-N закрыт` |
| новая идея | `planning-owner-ok.sh rm-add RM-N` | новый `RM-N` в roadmap |
| правка защищённых путей | `planning-owner-ok.sh hooks-edit <ветка>` | E18: хуки/настройки/`AGENTS.md`/`.githooks/`/`.codex/` |
| мерж в main | `planning-owner-ok.sh merge <ветка>` | `merge-gate` перед мержем |

Маркер привязан к ветке и её вершине (`sha`), живёт `OWNER_OK_TTL_HOURS` часов; новый коммит в ветку
после выдачи аннулирует маркер. Закрытие плана: явное слово → маркер `close-plan` → запись
`planning/plans/closed/PLAN-N.md` → `registry.sh set-status PLAN-N закрыт`.

## Коммиты

- Conventional commits на английском. Код — только на `feature/PLAN-N-slug` или `hotfix/*`; коммит на `MAIN_BRANCH` агенту запрещён (E2, `commit-gate` + `pre-commit`).
- Токен в сообщении: `PLAN-N` на `feature/PLAN-N-*`, `HF-N` на `hotfix/*`; на `MAIN_BRANCH` токен не требуется (мерж-коммиты).
- Токен `RM-N` допустим только в коммите по `planning/roadmap/**` или `ROADMAP.md`; права менять код он не даёт.
- `--no-verify`/`-n` и снятие `core.hooksPath` запрещены (E16). Перед коммитом проходит `GATE_FAST`, если задан.

## Дрейф

`.claude/hooks/plans-drift.sh` — информатор, всегда exit 0: код-коммит с токеном новее последнего упоминания токена в индексе; токен в коде без записи в реестре; HF-токен без строки в `HOTFIXES.md`; лишнее в корне `planning/`; неподключённые git-хуки. Найденное разбери до новой работы; проверяй код и `git log`, а не только формулировку плана.

## Конфиг

`.claude/planning.conf` (shell `KEY=VALUE`; без файла действуют те же дефолты): `MAIN_BRANCH`, `CODE_ROOTS`, `FEATURE_BRANCH_RE`, `HOTFIX_BRANCH_RE`, `TOKEN_REQUIRED`, `PLAN_SUMMARY_MIN_NUMBER`, `PLAN_WARN_BYTES`, `PLAN_HARD_BYTES`, `DRIFT_HORIZON_DAYS`, `DRIFT_MEMORY_INDEX`, `OWNER_OK_TTL_HOURS`, `PLANNING_ROOT_ALLOWED`, `STRICT`, `PROTECTED_PATHS`, `CODE_FILES`, `GATE_FAST`, `GATE_MERGE`. Менять — осознанно; это не способ обойти проверки.

## Нельзя

- Править индексы вручную; переписывать закрытые записи.
- Закрывать план, заводить RM, править защищённые пути или мержить в main без маркера владельца.
- Обходить git-хуки (`--no-verify`, `-n`, снятие `core.hooksPath`) — E16.
- Отключать `STRICT` самому: это делает владелец, `STRICT=off` в защищённом conf.
- Коммитить `.claude/state/` (маркеры owner-ok, `registry.lock`): это локальное состояние; установщик кладёт туда `.gitignore`, но правило — не коммитить.
- Выдавать «файл создан» за «правило исполняется»: проверяй сценарием — коммит без токена обязан блокироваться.
