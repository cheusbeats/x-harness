# 01. Планирование и реестры: PLAN / HF / RM

Этот файл — переносимое описание системы планирования: три реестра, команды `registry.sh`, формат плана, закрытие, хотфиксы, идеи и слово владельца. Читай его перед любой работой, которая меняет `planning/**`, заводит план или хотфикс, закрывает план; для рядовой работы достаточно `planning/ACTIVE_PLANS.md` и `registry.sh show <id>`. Все пути — от корня репозитория.

Пометка **[Claude]** — исполняется хуками Claude Code (`PreToolUse`/`SessionStart`, `.claude/settings.json`), **[Codex]** — адаптером Codex (`.codex/hooks.json`, `.codex/hooks/claude-compat.py`). Правило без пометки универсально: у другого клиента его надо воспроизвести эквивалентным механизмом.

## 1. Зачем это и что является правдой

Task-лист ассистента живёт в сессии и не переживает `git pull`; источник правды об этапе — `planning/` (`CLAUDE.md:3-5`). Реестры привязывают работу к номерам, а номера — к коммитам, поэтому чужая работа (другой агент, офлайн-сессия) видна только через git.

- Перед новой работой: прочитать `planning/ACTIVE_PLANS.md`, затем `registry.sh show PLAN-N` и `## Резюме` нужного плана; разобрать вывод `plans-drift.sh`, не доверяя одной формулировке плана.
- Реестр — не отчёт, а вход: код проверяют по `git log`, план правят по коду, а не наоборот.
- Номер сквозной и не переиспользуется (`registry.sh next-id`; `.claude/reference/planning-registries.md:16-18`).

## 2. Три реестра

| Реестр | Индекс (корень `planning/`) | Тело записи | Закрытое/архив |
|---|---|---|---|
| RM — идея | `ROADMAP.md` | `roadmap/RM-N-slug.md` | — |
| PLAN — план | `ACTIVE_PLANS.md` (в работе) | `plans/PLAN-N-slug.md` | `PLANS.md` + `plans/closed/PLAN-N.md` |
| HF — хотфикс | `HOTFIXES.md` | `hotfixes/HF-N-slug.md` | — |

Фактические индексы и шапки таблиц:

- `ACTIVE_PLANS.md`, `PLANS.md`: `| PLAN | Название | Статус | Дата | Влит-в | Автор |`;
- `HOTFIXES.md`: `| HF | Название | Статус | Дата | Влит-в | Автор |`;
- `ROADMAP.md`: `| RM | Название | Статус | Дата | Триггер / → PLAN-N |`.

Схема строки (`.claude/reference/planning-registries.md:15`): `id | название | статус | дата | влит-в | автор`; текст строки без колонки id — **≤ 160 символов** (проверяет `registry.sh check`), дата строго `YYYY-MM-DD`. В корне `planning/` допустимы только служебные файлы и каталоги `plans/ roadmap/ hotfixes/` (E9): `ACTIVE_PLANS.md HOTFIXES.md README.md ROADMAP.md PLANS.md`.

Словарь статусов (`registry.sh:38-42`, регэкспы полного совпадения):

| Реестр | Допустимые статусы |
|---|---|
| RM | `идея`, `отложена`, `стала PLAN-N` (в т. ч. `PLAN-N.M`), `отклонена` |
| PLAN | `черновик`, `в работе`, `на паузе`, `ждёт владельца`, `закрыт`, `аннулирован` |
| HF | `влит`, `откачен` |

## 3. Что куда: PLAN, HF или RM

| Ситуация | Реестр | Что заводится |
|---|---|---|
| Есть что проектировать: несколько связанных задач, дизайн, решения | **PLAN** | `plans/PLAN-{N}-kebab.md` + строка в `ACTIVE_PLANS.md` |
| Правка, для которой план избыточен: багфикс, вёрстка, конфиг, зависимость | **HF** | ветка `hotfix/*`, `hotfixes/HF-N-*.md` + строка в `HOTFIXES.md` |
| Идея «потом», которую сейчас не берём | **RM** | `roadmap/RM-N-*.md` + строка в `ROADMAP.md` |

- **PLAN.** Нумерация: `PLAN-N` — дизайн, `PLAN-N.1` — исполнение (`.claude/reference/planning-registries.md:33-34`). Новый план: `registry.sh next-id PLAN` → файл с H1 и `## Резюме` → `registry.sh add PLAN PLAN-N "название"`. `add PLAN` умеет два режима: если документ `plans/PLAN-N-*.md` уже существует — регистрирует его, не перезаписывая; иначе создаёт заготовку `# PLAN-N — название` + `**Статус:**` + пустой `## Резюме` (`registry.sh:404-412`).
- **HF.** Только когда план избыточен; обязательны ветка `hotfix/*`, файл хотфикса и новая строка индекса — иначе `merge-gate` не пропустит мерж (E3, `merge_checks.py hotfix_errors`). Запись — `registry.sh add HF auto "что и зачем" --slug <slug>` + ветка `hotfix/*` (`planning/README.md:23`).
- **RM.** Запись — **только по прямому слову владельца** («добавь в роадмап»); сам агент ничего в roadmap не переносит (`CLAUDE.md:20`). Стала планом — статус «стала PLAN-N», в плане строка «Источник: RM-N», файл идеи не удаляется (`.claude/reference/planning-registries.md:57-60`).
- **Superpowers-скиллы** по умолчанию пишут в `docs/superpowers/` — здесь НЕ так: дизайн это раздел внутри `planning/plans/PLAN-{N}-*.md`, отдельная спека не заводится (`CLAUDE.md:27`, reference:34-35).

## 3a. Мини-цикл работы

1. **Старт сессии.** Прочитать `planning/ACTIVE_PLANS.md`, разобрать вывод `.claude/hooks/plans-drift.sh`, затем `registry.sh show PLAN-N` и `## Резюме` нужного плана.
2. **Выбор реестра.** Дизайн → PLAN, малая правка → HF, идея → RM (только по слову владельца). Сомнение «план или хотфикс» решается вопросом «есть ли что проектировать»: несколько связанных задач и решения — план.
3. **Ветка.** `feature/PLAN-N-slug` или `hotfix/*` от `main`; прямые коммиты в `main` запрещены (E1/E2).
4. **Работа и код.** План правится по коду; перед каждым коммитом Larastan и `quality-gate.sh --fast` (хук `commit-gate`).
5. **Коммит.** Conventional commit на английском, в сообщении — `PLAN-N` своей ветки (или `HF-N`); токен `RM-N` права на код не даёт.
6. **Мерж.** `.claude/scripts/merge-ready.sh <ветка>` → спросить слово владельца только при READY; мерж и публикация `main` — только по слову владельца.

## 4. registry.sh: точные команды

Полный синтаксис (`registry.sh:4-13`): `next-id <RM|PLAN|HF>` · `add <RM|HF|PLAN> <id|auto> <название> [--status S] [--date D] [--trigger T] [--slug S]` · `set-status <id> <статус>` · `set-trigger <RM-N> <текст>` · `show <id>` · `check [--registry rm|plan|hf|all]` · `migrate plans|journal --sha <SHA>` (одноразовая историческая миграция). Глобально: `--root <dir>` подменяет корень.

```bash
.claude/scripts/registry.sh next-id PLAN                 # напечатает PLAN-N (max+1)
.claude/scripts/registry.sh next-id HF
.claude/scripts/registry.sh add PLAN PLAN-149 "Счета и акты" --slug invoices
.claude/scripts/registry.sh add HF auto "Парсер перенаправлений" --slug parser-redirections
.claude/scripts/registry.sh add RM auto "Идея на потом" --trigger "после PLAN-150" --slug later-idea
.claude/scripts/registry.sh set-status PLAN-149 "в работе"
.claude/scripts/registry.sh set-status HF-153 "влит"
.claude/scripts/registry.sh set-trigger RM-7 "после PLAN-150"
.claude/scripts/registry.sh show PLAN-149
.claude/scripts/registry.sh check --registry all
```

Семантика, которая важна на практике:

- `add`: `id` — либо `auto`, либо точный `<KIND>-N`; проверяется, что такого id ещё нет. Позиционных аргументов ровно три — kind, id, название; опции разбираются в любом месте. Умолчания: `--status` — `идея`/`влит`/`черновик` для RM/HF/PLAN; `--date` — сегодня; `--trigger` — `нет`. В названии и триггере запрещены `|` и переводы строк; итоговая строка обязана уложиться в 160 символов. По умолчанию slug = `[a-z0-9]+` из названия (до 40 символов), иначе `item`; для русских названий `--slug` практически обязателен. Успех печатает `PLAN-N → PLAN-N-slug.md`.
- `set-status <id> <статус>`: правит ячейку «Статус» строки индекса; для RM и HF дополнительно первую строку `- **Статус:**` в теле записи. Для PLAN тело плана не меняется (см. раздел 14). Статус обязан быть из словаря, иначе exit 2.
- `set-status <PLAN-N> закрыт|аннулирован`: строка переносится из `ACTIVE_PLANS.md` в `PLANS.md`, ссылка переписывается на `plans/closed/PLAN-N.md`; **сначала** должен существовать файл записи о закрытии, иначе `die` «сначала создай plans/closed/PLAN-N.md». В `plans/closed/_map.tsv` добавляется строка (`registry.sh:447-461`).
- `show <id>`: печатает строку(и) индекса и пути тел из `plans|roadmap|hotfixes`, найденных как `ID-*.md`. Для закрытого плана печатается строка из `PLANS.md` и дизайн-документ, но не `plans/closed/PLAN-N.md` (каталог `closed/` в `files()` не входит).
- `check`: валидирует шапку (колонки «Статус»/«Дата»), словарь, `YYYY-MM-DD`, лимит 160, дубли строк/файлов, «файл без строки»/«строка без файла», для PLAN — наличие `plans/closed/PLAN-N.md` у статуса закрыт/аннулирован и согласованность `_map.tsv`; легаси-двойники `PLAN-60`, `PLAN-105` разрешены. Вывод: `ID — сообщение`; exit 1 при находках.
- Коды: `0` чисто/успех, `1` нарушения `check`, `2` неверные аргументы или отказ записи.

## 5. Запрет ручной правки индексов (E6)

Требуется: индексы (`ROADMAP.md`, `ACTIVE_PLANS.md`, `PLANS.md`, `HOTFIXES.md`) правит только `.claude/scripts/registry.sh` (`CLAUDE.md:15`, `planning/README.md:19`).

Фактически **[Claude]** `.claude/hooks/registry-guard.sh` — `PreToolUse` на `Edit/Write/NotebookEdit` (Codex: `apply_patch`): берёт `.tool_input.file_path // .tool_input.notebook_path`, спрашивает `.claude/hooks/paths.py guarded <file>` и при совпадении возвращает `exit 2` с текстом «Индекс реестра, прямая правка Edit/Write запрещена (E6). Используй .claude/scripts/registry.sh: next-id | add | set-status <id> <статус> | show <id> | check.». Защищённые имена — в `.claude/hooks/paths.conf`: `guard ROADMAP.md`; `guard-stage4 PLANS.md`, `ACTIVE_PLANS.md`, `HOTFIXES.md`, `JOURNAL.md` (stage4 включается, когда новый формат реестра реально существует).

Граница защиты: запись через `registry.sh` идёт из Bash/python и хуком не блокируется; ручную запись через Bash отсекает только `registry.sh check` по форме (`registry-guard.sh:6-8`). То есть это защита от случайной правки инструментом, а не изоляция от намеренного обхода.

## 6. Формат плана

- Файл: `planning/plans/PLAN-{N}-kebab.md`, H1 с номером: `# PLAN-N — название`; после H1 — строка статуса («Статус / ветка / дата» по шаблону `planning/README.md:29`), затем `## Резюме`, затем остальное.
- **E7:** для планов `N ≥ 145` `## Резюме` обязано быть в первых 30 строках и содержать **≤ 15 строк** текста под заголовком до следующего `## ` (`commit_checks.py:40,409-423`, `NEW_PLAN_FROM = 145`). На практике резюме — цель, что меняем, решения, статус.
- **E8:** размер `> 40 КБ` — предупреждение для любого плана, `> 80 КБ` — блок для `N ≥ 145`; обход — комментарий `<!-- size-waiver: причина -->` в первых 30 строках (`commit_checks.py:473-477`). Обход разрешает размер, но не отменяет E7.
- **E14:** полный `Read` файла `> 40 КБ` или `> 300 строк` режет `big-read-guard.sh`; читай индекс, `## Резюме` и нужный фрагмент.
- Статусы плана — см. раздел 2. Сам статус в индексе меняется только `registry.sh set-status`.
- Самоповторное ревью плана: проход 0 без субагента (раздел «что уже есть» с путями), затем проходы `deep-reasoner` по чеклисту `plan-review-checklist` до первого прохода без БЛОКЕРов; ВАЖНО/МЕЛОЧЬ дорабатывает автор сам; денежное ревью — opus и Codex, не-денежное — Codex (`.claude/reference/planning-registries.md:39-45`).

## 7. Закрытие плана

Рабочий порядок (шаги не взаимозаменяемы); закрытие плана ≠ завершение реализации и не делается по собственной инициативе.

1. Довести работу и `.claude/scripts/plan-code-refs.sh planning/plans/PLAN-N-*.md` — список должен быть **пуст** (`CLAUDE.md:26`).
2. Получить явное слово владельца «план закрыт» (или «аннулирован»). Без него статус не меняется.
3. Владелец **в своём терминале** выдаёт маркер: `.claude/scripts/owner-ok.sh close-plan PLAN-N [ветка]` (E10).
4. Автор пишет текст записи о закрытии в `planning/plans/closed/PLAN-N.md` — это единственный путь, который `set-status` примет.
5. `.claude/scripts/registry.sh set-status PLAN-N "закрыт"` — строка уходит в `PLANS.md`, ссылка — на `plans/closed/PLAN-N.md`, `_map.tsv` дополняется.
6. Мерж. Если ветка меняет **только** `planning/**` (закрытие плана, правки реестров), полный гейт и ревью не требуются (E12, HF-152); любой файл вне `planning/`, включая удаление, возвращает строгие требования.

## 8. Неизменяемость закрытых записей

Закрытые записи НЕ переписываем: `plans/closed/*` и ранние `hotfixes/HF-*` хранят тела **побайтно** (`CLAUDE.md:24`, `planning/README.md:12-13`). Если в проекте есть скрипты `verify-*-migration.sh`, pre-push запускает их.

Старые составные заголовки (`PLAN-62`/`PLAN-63` и т. п.) сведены в один файл; остальные id — aliases в `plans/closed/_map.tsv`. Правь **план по коду**, а не наоборот; мёртвые имена закрытого плана фиксируются в разделе «Поправка по факту реализации (дата)» без обратных кавычек (`.claude/reference/planning-registries.md:19-20,35-37`).

## 9. Хотфикс (HF)

1. Ветка `hotfix/*` от `main` (короткий багфикс, вёрстка, конфиг, зависимость).
2. `.claude/scripts/registry.sh add HF auto "что и зачем" --slug <slug>` — заводит `hotfixes/HF-N-*.md` и строку `HOTFIXES.md` (статус по умолчанию `влит`, дата — сегодня). Для незамерженного хотфикса допустимо поставить статус позже через `set-status`; колонка «Влит-в» заполняется `--trigger` или позже.
3. Коммиты называют `HF-N` (на `feature/PLAN-N-*` — `PLAN-N`). Токен `RM-N` права на код не даёт.
4. `merge-gate` требует для `hotfix/*` новую запись `planning/hotfixes/HF-N-*.md` **и** новую строку `HOTFIXES.md` относительно `main` (E3, `merge_checks.py hotfix_errors`). Без этого мерж блокируется.
5. Если реестра HF ещё нет, легаси-путь требует запись в `planning/JOURNAL.md` (там же).

Запись, которую создаёт `add HF` (и которую ждут фактические тела `hotfixes/HF-N-*.md`):

```markdown
# HF-N — что и зачем

- **Статус:** влит
- **Дата:** YYYY-MM-DD
- **Влит в:** hotfix/name

- **Что:** …
- **Зачем:** …
- **Автор:** …
```

Содержательная часть («Что/Зачем») — обязательный смысл записи: именно по ней потом ищут, почему правка существует; индекс хранит только строку ≤ 160 символов.


## 10. Идея (RM)

- Добавляется **только по прямому слову владельца** («добавь в роадмап», «занеси идею»). Агент сам не переносит и не удаляет идеи.
- `registry.sh add RM auto "название" --trigger "когда/после чего" --slug <slug>`: тело `roadmap/RM-N-slug.md` содержит H1, `- **Статус:**`, `- **Записано:**`, `- **Триггер владельца:**`, `## Суть`.
- Стала планом: `set-status RM-N "стала PLAN-N"` + `set-trigger` при необходимости; файл идеи не удаляется, в плане — «Источник: RM-N».
- Коммит может называть `RM-N`; на код это прав не даёт (E2).

## 11. Слово владельца (owner-ok)

Кто: **только владелец в своём терминале**. Агент не запускает `owner-ok.sh` и не пишет в `.claude/state/owner-ok`; попытку блокирует `.claude/hooks/owner-ok-guard.sh` (`CLAUDE.md:21-23`).

```text
.claude/scripts/owner-ok.sh close-plan PLAN-N [ветка]   # закрыть/аннулировать план (E10)
.claude/scripts/owner-ok.sh rm-add     RM-N   [ветка]   # добавить идею в roadmap (E11)
.claude/scripts/owner-ok.sh hooks-edit <ветка> [ветка]  # править защищённые хуки/настройки (E18)
```

Как устроено фактически (`owner-ok.sh`, `owner_ok.py`):

- Маркер: `.claude/state/owner-ok/<вид>-<id>@<ветка>`; в имени `%`, `/`, `_`, `@` кодируются (`%25`, `%2F`, `%5F`, `%40`), чтобы ветки `feature/a/b` и `feature/a_b` не сталкивались.
- Содержимое — строки `key=value`: `kind`, `id`, `branch`, `sha` (вершина ветки на момент выдачи), `target=main`, `issued` (epoch).
- Срок — 24 ч. Маркер привязан к SHA вершины: новый коммит после выдачи отменяет разрешение для мержа; `merge-gate` забирает маркер **атомарно и один раз** (`os.rename` в `claimed/`). `SessionStart` чистит `.claimed`, просроченные и влитые (`plans-drift.sh:33-34`).
- `commit-gate` читает маркер, не расходуя (`commit_checks.py` → `owner_ok.check_commit`).
- Защищённые пути E18 (`paths.conf guard-e18`): `.claude/hooks/`, `.claude/settings.json`, `.claude/scripts/`, `.codex/`, `.agents/`, `.githooks/`, `CLAUDE.md`, `AGENTS.md`. В `CLAUDE.md:21-22` список короче («хуки/настройки/CLAUDE.md») — верить `paths.conf`.

## 12. Сверка: plans-drift.sh и plan-code-refs.sh

`.claude/hooks/plans-drift.sh` — **[Claude]** `SessionStart`, запускается и руками; **всегда exit 0**, это информатор, а не гейт; при отсутствии находок молчит (`plans-drift.sh:25,247-251`). Что проверяет:

- дрейф по планам: последний код-коммит с токеном `PLAN-N` новее последнего **добавления** строки с этим токеном в `ACTIVE_PLANS.md`/`PLANS.md` (сравнение по diff `git log -p`, `--first-parent`, горизонт 90 дней, пути `app resources routes database config tests`);
- план-документы без записи ни в одном индексе (сироты; старше полугода не ворошит);
- коммиты с кодом после последней правки `HOTFIXES.md`/`JOURNAL.md` без единого `PLAN-N`/`HF-N` — кандидаты в `registry.sh add HF`;
- банк RM: файл ↔ строка индекса в обе стороны, коммиты `RM-N` без правки индекса/идеи, наличие цели у «→ PLAN-N»;
- лишнее в корне `planning/` (E9); бюджет стартового набора (E13) и `core.hooksPath == .githooks` (E19); влитые в `main` ветки.

`.claude/scripts/plan-code-refs.sh planning/plans/PLAN-N-*.md` — сверка **ссылок внутри плана** с кодом. Проверяет ровно две вещи: пути файлов в обратных кавычках (расширения `php|neon|json|js|css|md|sh`) и `Класс::член` (файл класса в `app/database/tests`, присутствие члена; колонка таблицы ищется ещё в миграциях; фасады/фреймворковые методы пропускаются). Расхождение признаётся, если имя есть в разделе `## Поправка по факту реализации`. У открытого плана ненайденное — норма (будущий код); **перед закрытием список обязан быть пустым** (`plan-code-refs.sh:26-28,99-100`). Скрипт проверяет существование сущности, но не её использование: мёртвый метод без вызывателя он не поймает.

## 12a. Перенос на другого клиента

Правило считается перенесённым, только если у клиента есть исполнение, а не текст в инструкции. Минимальная карта:

| Универсальное правило | Claude Code | Codex | Generic |
|---|---|---|---|
| Запрет ручной правки индексов (E6) | `registry-guard.sh` в `PreToolUse` на Edit/Write | `.codex/hooks.json` + `claude-compat.py` | политика инструментов/обёртка write |
| Сверка реестров на старте | `plans-drift.sh` в `SessionStart` | тот же адаптер | обязательный шаг bootstrap-скрипта |
| Слово владельца (E10/E11/E18) | файлы `.claude/state/owner-ok` + `owner-ok-guard.sh` | тот же каталог, адаптер хуков | те же файлы + проверка в commit/merge-скрипте |
| Лимиты чтения (E14) | `big-read-guard.sh` | адаптер | лимит вывода read-тула |
| Проверки коммита/мержа (E3/E4/E12/E13/E17) | `commit-gate.sh`, `merge-gate.sh` | общие python-скрипты | pre-commit/pre-merge скрипты |

Что должно быть воспроизведено обязательно: каталог `planning/` с индексами, `registry.sh`, owner-ok-маркеры и их проверка, git-хуки `.githooks/`, пороги 40/80 КБ и 160 символов. Без этого реестры останутся декларацией.

## 13. Правила принуждения E1–E19

Таблица — из `.claude/reference/planning-registries.md:69-91`; детали исполнения уточнять в хуках.

| № | Правило | Где исполняется |
|---|---|---|
| E1 | Нет прямых коммитов в `main`; пуш `main` только с мерж-коммитами впереди `<remote>/main` (`git rev-list --first-parent --no-merges`), без force/delete | `commit-gate.sh`, `branch-guard.sh`, `main-push-guard.sh` |
| E2 | Код только на `feature/PLAN-N-*` / `hotfix/*` (классы путей — `paths.conf`) | `commit-gate.sh`, `branch-guard.sh` |
| E3 | `PLAN-N`/`HF-N` в каждом коммите с кодом; хотфикс к мержу = `hotfixes/HF-*.md` + строка `HOTFIXES.md` | `commit-gate.sh`, `merge-gate.sh` |
| E4 | План вне реестра невозможен | `registry.sh check` в commit/merge-gate, `plans-drift.sh` |
| E5 | Схема, словарь статусов, строка ≤ 160 | `registry.sh check` |
| E6 | Индексы правятся только через `registry.sh` | `registry-guard.sh` (Edit/Write/apply_patch) |
| E7/E8 | Резюме и размер плана `N ≥ 145` | `commit_checks.py` (commit-gate, pre-commit) |
| E9 | Корень `planning/` — только служебные файлы | `commit_checks.py`, `plans-drift.sh` |
| E10/E11 | Закрыть план / добавить идею — по слову владельца | `owner_ok.py` в `commit-gate.sh`, `merge-gate.sh` |
| E12 | Ревью: деньги — opus и Codex, остальное — один; ветка только с `planning/**` гейт/ревью не требует (HF-152) | `merge-gate.sh`, `mark-reviewed.sh --by` |
| E13 | Стартовый набор в бюджете (CLAUDE.md ≤ 36 КБ, набор ≤ 52 КБ) | `commit_checks.py`, `plans-drift.sh` |
| E14 | Не читать целиком файлы > 40 КБ / 300 строк | `big-read-guard.sh` |
| E15 | Те же хуки действуют на Codex | `.codex/hooks.json`, `.codex/hooks/claude-compat.py` |
| E16 | Хуки не обходятся `--no-verify` | `commit-gate.sh` |
| E17 | Номера уникальны на дереве слияния (PLAN, RM, HF) | `merge-gate.sh` → `registry.sh check` |
| E18 | Хуки/настройки/инструкции агента — только под `hooks-edit` | `branch-guard.sh`, `commit-gate.sh`, `merge-gate.sh` (`e18` в `paths.conf`) |
| E19 | Локальные git-хуки в любом терминале | `.githooks/` (`install-githooks.sh`), SessionStart-предупреждение |

## 14. Расхождения и пробелы (требуется vs фактически)

- **Статус в теле плана.** `registry.sh:7` обещает, что `set-status` «правит строку индекса и строку «Статус» файла». Фактически тело правится только для RM/HF (`registry.sh:462-467`); у PLAN меняется только индекс, строка `**Статус:**` в документе остаётся прежней.
- **Прямая правка индекса.** Требуется «индексы правит только registry.sh»; фактически `registry-guard.sh` ловит только Edit/Write/NotebookEdit/apply_patch. Правка через Bash проходит, и её отсекает лишь `registry.sh check` по форме.
- **owner-ok при закрытии.** Требуется маркер для закрытия (E10); фактически сам `registry.sh set-status` маркер не проверяет — он нужен `commit-gate`/`merge-gate` при коммите/мерже. Локально строку можно перевести в «закрыт» и без маркера.
- **Защищённые пути.** `CLAUDE.md:21-22` перечисляет «хуки/настройки/CLAUDE.md»; `paths.conf guard-e18` защищает ещё `.claude/scripts/`, `.codex/`, `.agents/`, `.githooks/`, `AGENTS.md`.
- **Состав команд.** `planning/README.md:19` перечисляет `add, set-status, next-id, show, check`; фактически есть ещё `set-trigger`, `migrate` и глобальный `--root`, а `next-id`/`show` ничего не правят.
- **`show` и закрытые планы.** `show PLAN-N` для закрытого плана печатает строку из `PLANS.md` и дизайн-документ из `plans/`, но не путь `plans/closed/PLAN-N.md` (`files()` сканирует только `plans/`).
- **Шаблон плана.** Шаблон обещает строку «Статус / ветка / дата» (`planning/README.md:29`), но `commit_checks.py` проверяет только `## Резюме` и размер; фактические планы (например PLAN-148) содержат только `**Статус:**`. Строка «ветка/дата» — требование шаблона, не проверяемое правило.
- **E13.** `commit-gate` блокирует только `CLAUDE.md > 36 КБ`; суммарный бюджет 52 КБ (`CLAUDE.md` + `.claude/rules/*` + `planning/README.md` + индекс памяти) только печатается `plans-drift.sh`, мерж не блокирует.
- **Slug по умолчанию.** Для русского названия `add ... auto` без `--slug` даёт файл `...-item.md` (`re.sub(r"[^a-z0-9]+")`); в `planning/README.md:23` пример без slug — на практике передавай `--slug`.

## Источники

- `CLAUDE.md:1-52` — стартовый срез, три реестра, git workflow, границы «слово владельца».
- `planning/README.md` — что где, как поддерживать, шаблон плана.
- `.claude/reference/planning-registries.md` — полные правила, схема, статусы, ревью, E1–E19.
- `.claude/scripts/registry.sh` — синтаксис, умолчания, `add`/`set-status`/`show`/`check`, коды 0/1/2.
- `.claude/scripts/plan-code-refs.sh` — сверка ссылок плана с кодом, «Поправка по факту реализации».
- `.claude/scripts/owner-ok.sh` — маркеры слова владельца; `.claude/hooks/owner_ok.py` — срок, SHA, атомарный захват.
- `.claude/hooks/registry-guard.sh`, `.claude/hooks/paths.conf` — запрет ручной правки индексов (E6/E18).
- `.claude/hooks/plans-drift.sh` — стартовая сверка, бюджет E13, E19.
- `.claude/hooks/commit_checks.py` — E7/E8/E13, планировочные проверки коммита.
- `.claude/hooks/merge_checks.py` — E3 для `hotfix/*`, E12, E17, owner-ok при мерже.
- `planning/ACTIVE_PLANS.md`, `planning/PLANS.md`, `planning/HOTFIXES.md`, `planning/ROADMAP.md` — фактические индексы и шапки.
- `outputs/AGENT_HARNESS.md:312-354` — конспект правил планирования и owner-ok.
