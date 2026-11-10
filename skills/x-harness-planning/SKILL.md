---
name: x-harness-planning
description: Правила планирования проекта через реестры RM/PLAN/HF — когда заводить план, хотфикс или идею, как устроены индексы planning/, команды registry.sh, закрытие плана и слово владельца (owner-ok), токены PLAN-N/HF-N в коммитах, сверка plans-drift. Использовать при работе с планами, реестром, хотфиксом, роадмапом, индексами planning/, и всегда, когда в задаче есть PLAN-N, HF-N или RM-N.
---

# x-harness-planning — планы и реестры проекта

Навык для любого проекта, где стоит планировочный профиль x-harness: `planning/` с реестрами
RM/PLAN/HF, правила в `AGENTS.md`, строгий слой (E2/E18/E16, защита main, gate) и проверки в
`.githooks/`. Все пути — от корня репозитория.

## Когда читать

- Перед работой, которая меняет `planning/**`: новый план, хотфикс, идея, закрытие, правка индекса; выбор PLAN/HF/RM.
- Перед коммитом: нужен ли токен `PLAN-N`/`HF-N` и какой.
- Когда хук заблокировал коммит/правку индекса или `plans-drift` сообщил о расхождении.

Для рядовой работы достаточно `planning/ACTIVE_PLANS.md` — читать весь навык каждый раз не нужно.

## Что является правдой

`planning/` — источник правды об этапе работы. Task-лист ассистента живёт в сессии и не переживает
`git pull`. План — не отчёт: код проверяй по `git log`, план правь по коду, а не наоборот.

## Три реестра

| Реестр | Индекс (корень `planning/`) | Тело |
|---|---|---|
| RM — идея | `ROADMAP.md` | `roadmap/RM-N-*.md` |
| PLAN — план | `ACTIVE_PLANS.md` (в работе), `PLANS.md` (закрытые) | `plans/PLAN-N-*.md`; запись о закрытии — `plans/closed/PLAN-N.md` |
| HF — хотфикс | `HOTFIXES.md` | `hotfixes/HF-N-*.md` |

В корне `planning/` — только служебные файлы и каталоги `plans/ roadmap/ hotfixes/`.

## PLAN, HF или RM

| Ситуация | Реестр |
|---|---|
| Есть что проектировать: несколько связанных задач, дизайн, решения | **PLAN** |
| Правка, для которой план избыточен: багфикс, мелкая правка, конфиг, зависимость | **HF** |
| Идея «потом», которую сейчас не берут в работу | **RM** (только по слову владельца) |

## Обязательный цикл

1. **Старт.** Прочитай `planning/ACTIVE_PLANS.md`; разбери вывод `.claude/hooks/plans-drift.sh`;
   `registry.sh show PLAN-N` + `## Резюме` нужного плана.
2. **Реестр.** Новый план → `plans/PLAN-{N}-kebab.md` + `registry.sh add PLAN`. Хотфикс → `hotfix/*` +
   `registry.sh add HF`. Идея → RM только с маркером владельца.
3. **Ветка.** `feature/PLAN-N-slug` или `hotfix/*` от `MAIN_BRANCH`; код на `MAIN_BRANCH` и на
   не-плановых ветках запрещён (E2). Защищённые пути — только с маркером `hooks-edit` (E18).
4. **Работа.** Минимальная правка; план правится по факту кода. Перед закрытием
   `.claude/scripts/plan-code-refs.sh planning/plans/PLAN-N-*.md` должен быть пуст.
5. **Коммит.** Conventional commit на английском + токен `PLAN-N`/`HF-N` (см. ниже). Без `--no-verify`/
   `-n` (E16). При `STRICT=on` команда `GATE_FAST` обязательна и должна пройти.
6. **Мерж.** Только по слову владельца: маркер `merge <ветка>`, чистые реестры, токены во всех коммитах,
   `GATE_MERGE` обязателен. Перед вопросом — `.claude/scripts/merge-ready.sh <ветка>`.
7. **Закрытие.** Только по слову владельца и маркеру `close-plan`.

## Строгий слой (по умолчанию)

Профиль ставится со `STRICT=on`; отключает только владелец — `STRICT=off` в `.claude/planning.conf`
(защищённый путь, нужен маркер `hooks-edit`).

- **E2.** Код (`CODE_ROOTS`, `CODE_FILES`) — только на `feature/PLAN-N-*`/`hotfix/*`; на `MAIN_BRANCH`
  правки кода и коммиты запрещены (`planning/`, `docs/`, `*.md` можно; merge/rebase/cherry-pick —
  исключение); на прочих ветках — только planning/docs/*.md/не-код.
- **E18.** `PROTECTED_PATHS` (хуки, скрипты, `settings.json`, `planning.conf`, `.githooks/`, `AGENTS.md`,
  `.codex/`) — только с маркером `hooks-edit <ветка>`.
- **E16.** `--no-verify`, `-n`, `git config core.hooksPath …`, `GIT_CONFIG_*` — запрещены.
- **Main.** Коммит на main агенту запрещён; мерж — только из `feature/PLAN-N-*`/`hotfix/*` с маркером
  `merge`; пуш: `main-push-guard` — force/delete любого refspec и push main офлайн без remote-tracking
  (просит `git fetch`); `pre-push` — non-fast-forward любой ветки, удаление main, push в main из не-main,
  прямые коммиты впереди `<remote>/main`. Первый push main разрешён; `feature/*`/`hotfix/*` и теги проходят.
- **Gate.** `GATE_FAST`/`GATE_MERGE` — команды проекта из conf; при STRICT=on пустые GATE_FAST и GATE_MERGE блокируют операцию. Это не Laravel
  Quality Gate. Запуск: `.claude/scripts/quality-gate.sh --fast|--merge`, `merge-ready.sh <ветка>`;
  generic — `bin/xh gate`.
- **`STRICT=off`** (только владелец) выключает strict guard'ы, E2/E18/`GATE_FAST` в pre-commit,
  strict-часть pre-push и merge-ready; реестры, owner-ok `close-plan`/`rm-add`, токен и drift остаются.

Кто блокирует: в Claude Code/Codex — событийные хуки (`branch-guard`, `commit-gate`, `merge-gate`,
`main-push-guard`) до действия; git-хуки (`pre-commit`, `commit-msg`, `pre-push`) — авторитетно и без
клиента; generic — git-хуки + ручной `bin/xh gate`.

## registry.sh — единственный способ правки индексов

Индексы (`ROADMAP.md`, `ACTIVE_PLANS.md`, `PLANS.md`, `HOTFIXES.md`) правит только
`.claude/scripts/registry.sh`. Прямой Edit/Write по ним блокирует `.claude/hooks/registry-guard.sh`
(exit 2); ручная строка через Bash — тоже нарушение, её ловит `registry.sh check`.

```bash
registry.sh next-id <RM|PLAN|HF>                 # следующий номер, max+1
registry.sh add <RM|HF|PLAN> <id|auto> "название" [--status S] [--date D] [--trigger T] [--slug S]
registry.sh set-status <id> <статус>
registry.sh show <id>
registry.sh check [--registry rm|plan|hf|all]    # exit 1 при нарушениях
```

Практика: для русских названий передавай `--slug` (иначе файл будет `...-item.md`); для PLAN `add`
регистрирует готовый документ или создаёт заготовку; `set-status PLAN-N закрыт` требует `plans/closed/PLAN-N.md`.

## Статусы (словарь, полное совпадение)

- RM: `идея`, `отложена`, `стала PLAN-N`, `отклонена`
- PLAN: `черновик`, `в работе`, `на паузе`, `ждёт владельца`, `закрыт`, `аннулирован`
- HF: `влит`, `откачен`

Другой статус — ошибка `check`. Дата — `YYYY-MM-DD`; текст строки индекса (без колонки id) ≤ 160 символов.

## Формат плана

```markdown
# PLAN-N — название

**Статус:** черновик · **Ветка:** feature/PLAN-N-slug · **Дата:** YYYY-MM-DD

## Резюме

Цель, что меняем, принятые решения, текущий статус.
```

Шаблон — рекомендация: `registry.sh add PLAN` создаёт только `**Статус:**` и пустой `## Резюме`; строку
про ветку/дату и содержание пишет автор.

- `## Резюме` — первым разделом; обязательно для планов начиная с `PLAN_SUMMARY_MIN_NUMBER`.
- Размер: `PLAN_WARN_BYTES` — предупреждение, `PLAN_HARD_BYTES` — блок; осознанный обход —
  `<!-- size-waiver: причина -->` в начале плана.
- Не дублируй дизайн отдельной «спекой»: решения — раздел плана.

## Закрытие плана

1. Явное слово владельца «план закрыт».
2. Владелец **в своём терминале** выдаёт маркер: `.claude/scripts/planning-owner-ok.sh close-plan PLAN-N [ветка]`.
3. Запись о закрытии — `planning/plans/closed/PLAN-N.md`.
4. `.claude/scripts/registry.sh set-status PLAN-N закрыт` — строка уходит в `PLANS.md`.

Маркер owner-ok (kind, id, branch, sha, ttl_until, target) живёт `.claude/state/planning-owner-ok/`,
привязан к ветке и её вершине, срок — `OWNER_OK_TTL_HOURS`. Агент маркер не создаёт: запуск
`planning-owner-ok.sh` и запись в state блокирует `.claude/hooks/owner-ok-guard.sh`.

Другие виды: `rm-add RM-N` (новая идея), `hooks-edit <ветка>` (E18: хуки/настройки/`AGENTS.md`),
`merge <ветка>` (мерж в main). `merge`-маркер привязан к вершине исходной ветки; новый коммит в неё
аннулирует разрешение.

## Токены коммитов

- Ветка `feature/PLAN-N-*` → в сообщении `PLAN-N`; ветка `hotfix/*` → `HF-N`.
- На основной ветке (`MAIN_BRANCH`) токен не требуется — там мерж-коммиты.
- Коммит, который трогает только `planning/roadmap/**` или `ROADMAP.md`, может нести `RM-N`; права
  менять код `RM-N` не даёт.
- `commit-msg` проверяет токен (`planning-checks.py msg`); `pre-commit` — E2/E18, резюме/размер
  плана, лишнее в корне `planning/`, маркер owner-ok, затем `registry.sh check` по staged-дереву и
  `GATE_FAST`; `pre-push` — форма реестров и защита main (non-fast-forward любой ветки, удаление main,
  push в main не из main, прямые коммиты впереди `<remote>/main`; первый push main разрешён, теги
  пропускаются).
- На `MAIN_BRANCH` коммит агенту запрещён; `--no-verify`/`-n` и снятие `core.hooksPath` запрещены (E16).

## Дрейф

`.claude/hooks/plans-drift.sh` — информатор, всегда exit 0. Сообщает: код-коммиты по `CODE_ROOTS` с
токеном новее последнего упоминания в индексе; токен в коде без записи в реестре; HF без строки
в `HOTFIXES.md`; коммиты с кодом без токена; лишнее в корне `planning/`; неподключённые git-хуки.

## Конфиг

`.claude/planning.conf`: `MAIN_BRANCH`, `CODE_ROOTS`, `FEATURE_BRANCH_RE`, `HOTFIX_BRANCH_RE`,
`TOKEN_REQUIRED`, `PLAN_SUMMARY_MIN_NUMBER`, `PLAN_WARN_BYTES`, `PLAN_HARD_BYTES`,
`DRIFT_HORIZON_DAYS`, `DRIFT_MEMORY_INDEX`, `OWNER_OK_TTL_HOURS`, `PLANNING_ROOT_ALLOWED`, `STRICT`,
`PROTECTED_PATHS`, `CODE_FILES`, `GATE_FAST`, `GATE_MERGE`. Без файла действуют дефолты. Правка
конфига — настройка проекта, а не обход проверок (защищённые ключи — только с маркером `hooks-edit`).

## Чего нельзя

- Править индексы руками (даже «одну строчку»), переписывать закрытые записи `plans/closed/*`.
- Закрывать план, заводить RM, править защищённые пути или мержить в main без маркера владельца.
- Обходить git-хуки (`--no-verify`, `-n`, снятие `core.hooksPath`) — E16; коммитить `.claude/state/`.
- Отключать `STRICT` самому (`STRICT=off`) — это слово владельца.
- Коммитить код на `MAIN_BRANCH` или не-плановой ветке — E2.
- Выдавать «файл создан» за «правило исполняется» — проверяй сценарием: коммит без токена блокируется.

## Шпаргалка

```bash
# новый план / хотфикс
.claude/scripts/registry.sh next-id PLAN   # PLAN-N
.claude/scripts/registry.sh add PLAN PLAN-N "Название" --slug kebab
.claude/scripts/registry.sh add HF auto "Что и зачем" --slug fix   # ветка hotfix/*

# строгий слой
.claude/scripts/quality-gate.sh --fast      # перед коммитом (GATE_FAST)
.claude/scripts/quality-gate.sh --merge     # перед мержем (GATE_MERGE)
.claude/scripts/merge-ready.sh <ветка>      # сухой прогон требований мержа
bin/xh gate --fast|--merge                  # generic-клиент

# сверка
.claude/scripts/registry.sh check --registry all && .claude/hooks/plans-drift.sh
```

**Граница Git-хуков:** в клиентах без PreToolUse нативные Git-хуки не гарантируют проверку owner-ok и гейта при `git merge`, в том числе fast-forward. Перед мержем запускайте `merge-ready` и вручную проверяйте условия; для принуждения используйте серверную защиту.
