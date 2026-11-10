# planning/ — реестры планирования

Читать, когда меняешь сами правила планирования; на старте сессии достаточно `ACTIVE_PLANS.md`.
Реестры привязывают работу к номерам, а номера — к коммитам: чужая работа (другой агент, офлайн-сессия)
видна только через git, поэтому коммит обязан называть `PLAN-N` или `HF-N`.

## Что где

| Путь | Что |
|---|---|
| `ROADMAP.md` + `roadmap/` | реестр RM — идеи «потом» (запись только по слову владельца) |
| `ACTIVE_PLANS.md` + `plans/PLAN-N-*.md` | реестр PLAN — планы в работе |
| `PLANS.md` + `plans/closed/` | реестр PLAN — закрытые: тело записи `plans/closed/PLAN-N.md` |
| `HOTFIXES.md` + `hotfixes/` | реестр HF — правки вне планов |

В корне `planning/` — только эти файлы и каталоги `plans/ roadmap/ hotfixes/`. Всё прочее — в тело
плана, идеи или хотфикса.

## Статусы (словарь)

- **RM:** `идея`, `отложена`, `стала PLAN-N`, `отклонена`
- **PLAN:** `черновик`, `в работе`, `на паузе`, `ждёт владельца`, `закрыт`, `аннулирован`
- **HF:** `влит`, `откачен`

Статус вне словаря — ошибка `registry.sh check`. Дата строки — `YYYY-MM-DD`; текст строки индекса
(без колонки id) — не длиннее 160 символов.

## Индексы правит только registry.sh

Индексы (`ROADMAP.md`, `ACTIVE_PLANS.md`, `PLANS.md`, `HOTFIXES.md`) правятся только
`.claude/scripts/registry.sh`; Edit/Write по ним блокирует `.claude/hooks/registry-guard.sh`.

| Команда | Что делает |
|---|---|
| `registry.sh next-id <RM|PLAN|HF>` | следующий свободный номер (max+1), номер не переиспользуется |
| `registry.sh add <RM|HF|PLAN> <id|auto> "название" [--status S] [--date D] [--trigger T] [--slug S]` | заводит тело записи и строку индекса; для PLAN с уже существующим документом только регистрирует его |
| `registry.sh set-status <id> <статус>` | меняет статус в индексе; для PLAN `закрыт`/`аннулирован` переносит строку в `PLANS.md` |
| `registry.sh show <id>` | строка индекса и путь тела |
| `registry.sh check [--registry rm|plan|hf|all]` | схема таблиц, словарь, даты, лимиты, «файл ↔ строка»; exit 1 при находках |

Для русских названий передавай `--slug`: иначе имя файла получится `...-item.md`.

## Строгий слой (STRICT=on по умолчанию)

Профиль ставится строгим. Отключается только владельцем — `STRICT=off` в `.claude/planning.conf`
(файл в защищённых путях, агенту нужен маркер `hooks-edit`).

- **E2. Ветки.** Код (`CODE_ROOTS`, `CODE_FILES`) — только на `feature/PLAN-N-*` или `hotfix/*`. На
  `MAIN_BRANCH` правки кода и коммиты запрещены (`planning/`, `docs/`, `*.md` и прочее не-код можно;
  идущие merge/rebase/cherry-pick — исключение). На прочих ветках — только `planning/`, `docs/`, `*.md`
  и не-код.
- **E18. Защищённые пути.** `.claude/hooks/`, `.claude/scripts/`, `.claude/settings.json`,
  `.claude/planning.conf`, `.githooks/`, `AGENTS.md`, `.codex/` — только с маркером владельца
  `hooks-edit <ветка>`.
- **E16. Обходы.** `--no-verify`, `-n`, `git config core.hooksPath …`, `-c core.hooksPath=…`,
  `GIT_CONFIG_*` — запрещены.
- **Main.** Коммит на `MAIN_BRANCH` агенту запрещён; мерж в main — только из `feature/PLAN-N-*`/`hotfix/*`,
  с чистыми реестрами, токенами и маркером владельца `merge <ветка>`; пуш: событийный `main-push-guard`
  блокирует force/delete любого refspec и push main офлайн без remote-tracking (просит `git fetch`), git
  `pre-push` — non-fast-forward любой ветки, удаление main, push в main из не-main, прямые коммиты впереди
  `<remote>/main`; первый push main разрешён, `feature/*`/`hotfix/*` и теги проходят; обходные движения main (`cherry-pick`, `rebase`,
  `reset --hard`, `branch -f main`) блокирует `merge-gate`.
- **Quality Gate.** `GATE_FAST` — перед коммитом, `GATE_MERGE` — перед мержем (команды проекта из conf;
  при STRICT=on пустой GATE_FAST или GATE_MERGE блокирует операцию). Запуск: `.claude/scripts/quality-gate.sh --fast|--merge`, generic —
  `bin/xh gate --fast|--merge`. Это не Laravel-гейт: исполняются команды проекта.

Что блокирует что: событийные хуки Claude/Codex (`branch-guard`, `commit-gate`, `merge-gate`,
`main-push-guard`) блокируют действие до запуска; git-хуки (`pre-commit`, `commit-msg`, `pre-push`) —
авторитетная проверка без клиента; generic — git-хуки плюс ручной `bin/xh gate`.

`STRICT=off` (только владелец) выключает строгие guard'ы, E2/E18 и `GATE_FAST` в `pre-commit`,
strict-часть `pre-push` и `merge-ready`; базовый слой (реестры, `registry.sh check`, owner-ok
`close-plan`/`rm-add`, токен, drift) продолжает работать.

## Как завести запись

- **План.** `registry.sh next-id PLAN` → файл `plans/PLAN-{N}-kebab.md` → `registry.sh add PLAN PLAN-N "название"`
  (если файла нет, `add` создаст заготовку с `## Резюме`).
- **Хотфикс.** `registry.sh add HF auto "что и зачем" --slug <slug>` + ветка `hotfix/*`.
- **Идея.** `registry.sh add RM auto "название" --trigger "когда" --slug <slug>` — только по прямому слову
  владельца («добавь в роадмап»).

## Шаблон плана

```markdown
# PLAN-N — название

**Статус:** черновик · **Ветка:** feature/PLAN-N-slug · **Дата:** YYYY-MM-DD

## Резюме

Цель, что меняем, принятые решения, текущий статус — коротко.
```

`registry.sh add PLAN` создаёт только `# PLAN-N — название`, `**Статус:**` и пустой `## Резюме`; строку
про ветку/дату и содержание резюме пишет автор — шаблон выше рекомендация, а не автогенерация.

- `## Резюме` — первым разделом; для планов начиная с `PLAN_SUMMARY_MIN_NUMBER` оно обязательно,
  иначе коммит не пройдёт `.githooks/pre-commit`.
- Размер: `PLAN_WARN_BYTES` — предупреждение, `PLAN_HARD_BYTES` — блок. Осознанный обход —
  комментарий `<!-- size-waiver: причина -->` в начале плана.
- Перед закрытием `.claude/scripts/plan-code-refs.sh planning/plans/PLAN-N-*.md` должен быть пуст
  (признанные расхождения — в разделе «Поправка по факту реализации»). Скрипт информационный:
  проверяет существование файлов/членов, но не их использование.

## Инициализация и починка

`.claude/scripts/planning-init.sh` идемпотентно создаёт недостающие индексы с шапками таблиц, каталоги
`roadmap/ plans/ plans/closed/ hotfixes/` и `.gitkeep`, существующее не перезаписывает; в конце
выполняет `registry.sh check --registry all`. Нужен, если `planning/` пуст или индекс потерян.

## Закрытие плана

1. Явное слово владельца: «план закрыт» (или «аннулирован»).
2. Владелец **в своём терминале** выдаёт маркер: `.claude/scripts/planning-owner-ok.sh close-plan PLAN-N`.
3. Запись о закрытии: `plans/closed/PLAN-N.md` — другой файл `set-status` не примет.
4. `.claude/scripts/registry.sh set-status PLAN-N закрыт` — строка уходит из `ACTIVE_PLANS.md` в `PLANS.md`.

Маркер создаёт только владелец; агент скрипт не запускает (`.claude/hooks/owner-ok-guard.sh`). Закрытые
записи не переписываем: они фиксируют, что решили тогда.

Виды owner-ok: `close-plan PLAN-N`, `rm-add RM-N`, `hooks-edit <ветка>` (E18), `merge <ветка>` (мерж в
main). Маркер привязан к ветке и вершине, живёт `OWNER_OK_TTL_HOURS` часов.

## Сверка и коммиты

- `.claude/hooks/plans-drift.sh` — информатор (всегда exit 0): код-коммиты по `CODE_ROOTS` с токеном
  `PLAN-N`/`HF-N` новее последнего упоминания токена в индексе; токен в коде без записи в реестре;
  HF без строки в `HOTFIXES.md`; код-коммиты без токена (кандидаты в реестр HF); лишнее в корне
  `planning/`; неподключённые git-хуки; `DRIFT_MEMORY_INDEX` задан, но файла нет.
- Коммит называет `PLAN-N` (ветка `feature/PLAN-N-*`) или `HF-N` (`hotfix/*`); на основной ветке токен
  не требуется (мерж-коммиты). Коммит только по `planning/roadmap/**`/`ROADMAP.md` может нести `RM-N`.
- Коммит на `MAIN_BRANCH` агенту запрещён; код — только на `feature/PLAN-N-*`/`hotfix/*` (E2).
- `pre-commit`: E2 и E18, затем `registry.sh check` по staged-дереву `planning/`, затем `GATE_FAST`
  (если задан). `pre-push`: при `STRICT=on` блокируются non-fast-forward (force) любой ветки, удаление
  main, push в main из не-main и прямые коммиты впереди `<remote>/main`; первый push main (удалённого main
  ещё нет) разрешён; теги пропускаются.
- `.claude/state/` (маркеры owner-ok, `registry.lock`) — локальное состояние: не коммить (установщик кладёт `.claude/state/.gitignore`).
- Параметры — `.claude/planning.conf`: `MAIN_BRANCH`, `CODE_ROOTS`, шаблоны веток, `TOKEN_REQUIRED`,
  пороги плана, `DRIFT_HORIZON_DAYS`, `OWNER_OK_TTL_HOURS`, `PLANNING_ROOT_ALLOWED`, `STRICT`,
  `PROTECTED_PATHS`, `CODE_FILES`, `GATE_FAST`, `GATE_MERGE`.

**Граница Git-хуков:** в клиентах без PreToolUse нативные Git-хуки не гарантируют проверку owner-ok и гейта при `git merge`, в том числе fast-forward. Перед мержем запускайте `merge-ready` и вручную проверяйте условия; для принуждения используйте серверную защиту.
