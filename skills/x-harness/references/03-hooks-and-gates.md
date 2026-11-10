# 03 — Хуки, гейты и адаптеры

Этот файл — карта фактического принуждения: что запускается до правки, коммита, мержа и пуша, какие файлы и конфиги читаются, когда действие блокируется и где обвязка не срабатывает. Читать, когда хук заблокировал вызов, при установке обвязки у нового клиента (Claude Code, Codex, DSH, GLM, generic), при проверке паритета и при споре «правило декларируется, но не проверяется». Срез — 30.10.2026, сверено с кодом, а не с комментариями. Пути даны от корня проекта; в переносимом пакете те же файлы лежат под `harness/`.

## 1. Контракт интеграции

Обвязка состоит из двух независимых слоёв, и ни один не включается самим фактом чтения инструкций:

1. **Агентский слой** — события рантайма: `SessionStart` и `PreToolUse` (`.claude/settings.json`, для Codex — `.codex/hooks.json`). Выполняется до инструмента и может запретить вызов.
2. **Нативные git-хуки** — `.githooks/` (подключаются `core.hooksPath`). Работают в любом терминале и не зависят от агента.

Claude передаёт каждому хуку JSON через stdin. Минимум для shell-вызова:

```json
{"tool_name":"Bash","tool_input":{"command":"git status --short"},"cwd":"/abs/project"}
```

Минимум для файлового вызова:

```json
{"tool_name":"Write","tool_input":{"file_path":"/abs/project/app/Foo.php"},"cwd":"/abs/project"}
```

| Поле | Кто читает |
|---|---|
| `.tool_input.command` | `commit-gate.sh`, `merge-gate.sh`, `main-push-guard.sh`, `owner-ok-guard.sh` |
| `.tool_input.file_path` / `.notebook_path` | `branch-guard.sh` (только `file_path`), `registry-guard.sh` (`file_path` или `notebook_path`) |
| `.tool_input.file_path`, `.offset`, `.limit` | `big-read-guard.sh` (Read) |
| `.tool_name` | `big-read-guard.sh` (Read или Bash) |
| env `CLAUDE_PROJECT_DIR` | `branch-guard`, `commit-gate`, `merge-gate`, `main-push-guard`, `owner-ok-guard` делают `cd "${CLAUDE_PROJECT_DIR:-.}"`; `plans-drift.sh` ищет корень через git; `big-read-guard.sh` работает с путём как есть |

Правила контракта:

- **exit 0** — допуск; **exit 2** — блокировка, причина из stderr уходит агенту как сообщение. Все восемь проектных хуков используют только 0 и 2; прочие коды означают сбой самого хука, а не вердикт.
- У нативных git-хуков семантика обратная по знаку: **ненулевой** код блокирует операцию (в проекте — exit 1).
- Таймауты (секунды): SessionStart — 20; файловые guard'ы — по 10; `commit-gate` — 180; остальные — 10. Полный гейт в 180 с не входит — см. §7.
- Path должен быть абсолютным. Ветку файловые guard'ы определяют по **каталогу файла**, а не по `CLAUDE_PROJECT_DIR`: в git worktree у файла своя ветка. Адаптер обязан запускать хук в правильном каталоге и выставлять `CLAUDE_PROJECT_DIR` в корень нужного checkout.
- Для patch-инструмента адаптер перечисляет **все** Add/Update/Delete/Move пути и вызывает файловые проверки для каждого. Для shell — нормализует имя инструмента в `Bash`, `cmd` в `command`, учитывает `workdir`. Строки JavaScript-оркестратора за shell-команды не выдаются.
- Зависимости: `jq` (разбор payload в shell-хуках) и `python3` (модули). Если `jq` отсутствует, shell-хуки получают пустой payload и, как правило, молча пропускают вызов — это fail-open, а не защита.
- Внутренний сбой: `merge-gate`/`merge_checks.py` и захват owner-маркера — **fail-closed**; `commit-gate`/`commit_checks.py`, ранние файловые guard'ы, cleanup и git `pre-commit`/`pre-push` при собственных ошибках чаще **fail-open** (печатают предупреждение и пропускают). Не считать «хук ничего не сказал» доказательством проверки.

## 2. Матрица событий `.claude/settings.json`

| Событие | matcher | Хуки в порядке перечисления | timeout | statusMessage |
|---|---|---|---|---|
| `SessionStart` | — | `plans-drift.sh` | 20 | «Сверяю планы с git» |
| `PreToolUse` | `Edit\|Write\|NotebookEdit` | `branch-guard.sh`, `registry-guard.sh` | 10 / 10 | — |
| `PreToolUse` | `Bash` | `commit-gate.sh`, `merge-gate.sh`, `main-push-guard.sh`, `owner-ok-guard.sh`, `big-read-guard.sh` | 180 / 10 / 10 / 10 / 10 | «Quality Gate перед коммитом» у commit-gate |
| `PreToolUse` | `Read` | `big-read-guard.sh` | 10 | — |

Факты и ограничения матрицы:

- `SessionStart` запускается командой `"$CLAUDE_PROJECT_DIR/.claude/hooks/plans-drift.sh" 2>/dev/null || true`: stderr скрыт, ошибка подавлена, поэтому это только контекст, не гейт.
- Все пять Bash-хуков запускаются на **каждый** Bash-вызов; дорогой только `commit-gate` (и то в основном `quality-gate --fast`).
- В настройках **нет** `PostToolUse`, `Stop`, `SubagentStop` и автоматического полного тестирования в конце ответа. Ревью/тесты после работы запускает агент по правилам, а не хук.
- `permissions.allow` в том же файле — отдельный слой разрешений; он не заменяет хуки, но и хуки не ослабляет.
- `settings.local.json` — пользовательский файл (здесь 31 КБ, игнорируется глобальным gitignore пользователя: `**/.claude/settings.local.json`). В нём широкие `Bash(git commit *)`, `Bash(git push *)`, `Bash(git merge *)` и др. В переносимый пакет он не входит; канон — `.claude/settings.json`.

## 3. Хуки по одному

Коды E1–E19 расшифрованы в `references/01-planning-registries.md`; ниже упоминаются только те, которые проверяет соответствующий хук.

### 3.1 `plans-drift.sh` — сверка планов (SessionStart)

- **Триггер:** SessionStart, timeout 20. Выход **всегда 0** — информатор, не гейт. Молчит, если расхождений нет; при находках печатает в stdout, который Claude добавляет в контекст сессии.
- **Проверяет:**
  - дрейф per-PLAN: последний код-коммит с токеном `PLAN-N` (заголовок важнее тела) новее последнего добавления этого токена в `planning/ACTIVE_PLANS.md`/`planning/PLANS.md` (по добавленным строкам `git log -p`, горизонт 90 дней, `--first-parent`);
  - планы-документы `planning/plans/PLAN-*.md` без строки ни в одном индексе (кроме старых > 180 дней);
  - код-коммиты после последней правки `planning/HOTFIXES.md`/`planning/JOURNAL.md` без единого `PLAN-N`/`HF-N`;
  - RM: файл `planning/roadmap/RM-N-*.md` без строки в `planning/ROADMAP.md`, строка без файла, коммит с `RM-N` без последующей правки индекса/файла, «→ PLAN-N» без документа;
  - лишние элементы в корне `planning/` (разрешены только `ACTIVE_PLANS.md`, `HOTFIXES.md`, `README.md`, `ROADMAP.md`, `PLANS.md`, `plans`, `roadmap`, `hotfixes`), по `git ls-files -co --exclude-standard`;
  - бюджет стартового набора: сумма `CLAUDE.md` + `.claude/rules/*` + `planning/README.md` + индекс памяти > `HARNESS_START_BUDGET_BYTES` (53248 = 52 КБ);
  - `git config core.hooksPath` ≠ `.githooks` (предупреждение E19);
  - ветки, влитые в `main` (к удалению).
- **Читает:** индексы и каталоги выше; git-историю по `app resources routes database config tests`; индекс памяти `$HOME/.claude/projects/<путь проекта, не-алфанумерики заменены на ->/memory/MEMORY.md` (переопределяется `HARNESS_MEMORY_INDEX`). Попутно вызывает `owner_ok.py cleanup` (удаляет `.claimed`, просроченные и влитые маркеры).
- **Тесты:** `test_planning_gates.py` → `PlansDriftTest` (чистота/тишина, бюджет, память в бюджете, «хуки не подключены»); `test_claude_compat.py`.
- **Расхождения:** проверка сравнивает `core.hooksPath` только с `.githooks`, а абсолютный путь к той же папке хуки подключает — в этом случае предупреждение ложное.

### 3.2 `branch-guard.sh` — ветка при правке файла

- **Триггер:** PreToolUse `Edit|Write|NotebookEdit`; читает `tool_input.file_path` (для `NotebookEdit` поле не читается — каталогом становится `CLAUDE_PROJECT_DIR`). Каталог файла (или `CLAUDE_PROJECT_DIR`) становится cwd; ветка — `git symbolic-ref -q HEAD` (не `rev-parse --abbrev-ref`: одноимённый тег `refs/tags/main` даёт ложное `heads/main`).
- **Проверки:**

| Ветка | Вердикт |
|---|---|
| `feature/*` или `hotfix/*` | сначала E18: `owner_ok.py edit-guard FILE BRANCH` — правка защищённого пути без маркера `hooks-edit` → exit 2 |
| `feature/PLAN-<N>-*`, `hotfix/*`, detached `HEAD` | допуск |
| прочие `feature/*` (без PLAN-токена) | `paths.py classify` по `paths.conf`; `code` → exit 2, `planning/wiki/...` → допуск; `unknown` пропускается (fail-closed сработает на коммите) |
| `main` | exit 2: «Нетривиальные правки запрещены напрямую в main…» + команда создания ветки |
| любой другой префикс | exit 2: «Ветка '…' не по конвенции. Допустимы только feature/* и hotfix/*.» |

- **Сообщения:** для кода на ветке без PLAN — «Ветка '…' без PLAN-токена: код правится только на feature/PLAN-<N>-* или hotfix/* (E2)»; для main — «Создай ветку: git checkout -b feature/PLAN-N-slug… или hotfix/slug.»
- **Тесты:** `test_planning_gates.py` → `BranchGuardTest`; `test_e18.py` → `EditGuardTest`; `test_claude_compat.py` (apply_patch, каждый путь, move в другой worktree).
- **Ограничение:** это ранняя сигнализация, не sandbox. Запись через Bash (`sed -i`, `cat >`, `tee`) идёт мимо; настоящий чекпоинт — `commit-gate`. При отсутствии git/каталога — fail-open (exit 0). Detached HEAD ранний guard пропускает, но `commit-gate` такой коммит заблокирует.

### 3.3 `registry-guard.sh` — индексы реестров

- **Триггер:** PreToolUse `Edit|Write|NotebookEdit`; читает `file_path`/`notebook_path`; `python3 paths.py guarded FILE`.
- **Что защищено (paths.conf):** `guard ROADMAP.md` — всегда; `guard-stage4 PLANS.md, ACTIVE_PLANS.md, HOTFIXES.md, JOURNAL.md` — включаются автоматически, только когда существует новая структура: `planning/plans/closed/` для PLANS/ACTIVE, `planning/hotfixes/` для HOTFIXES/JOURNAL (`paths.py STAGE4_READY`). Сейчас оба каталога есть, поэтому защищены `ROADMAP.md`, `PLANS.md`, `ACTIVE_PLANS.md`, `HOTFIXES.md`; `JOURNAL.md` отсутствует. Имя сверяется без учёта регистра (macOS), корень каталога тоже считается защищённым.
- **Сообщение:** «<файл> — индекс реестра, прямая правка Edit/Write запрещена (E6). Используй .claude/scripts/registry.sh: next-id | add | set-status <id> <статус> | show <id> | check.»
- **Тесты:** `test_planning_gates.py` → `RegistryGuardTest`; `test_claude_compat.py`.
- **Ограничение:** запись через `registry.sh` идёт из Bash/python и не блокируется (это и есть разрешённый путь). Вручную записанную через Bash строку отсекает только `registry.sh check` по форме.

### 3.4 `commit-gate.sh` — чекпоинт коммита

- **Триггер:** PreToolUse `Bash`, timeout 180. Читает `tool_input.command`; `GUARD_ORIG_PWD` сохраняется для разбора `git -C d …`, `cd d && git …` и workdir Codex.
- **Порядок проверок:**
  1. `commit_checks.py noverify` (E16): `--no-verify` у `commit/push/merge/am/rebase`, `git commit -n`, `-c core.hooksPath=…` (кроме `.githooks`), `GIT_CONFIG_KEY_n=core.hooksPath`, запись `git config core.hooksPath`. Проверка идёт **до** определения «это коммит», потому что касается и push.
  2. `commit_checks.py inspect`: корень репозитория, где пойдёт коммит, режим `staged`|`dirty`, признак вызова `git commit`. Нет коммита → exit 0. `dirty` — если в команде `git add/rm/mv/apply/restore/stash/checkout` или коммит с путями/`-a`/`-i`/`-o`/`--all`/`--include`/`--only`: индекс ещё не финальный, проверяется супермножество грязного дерева.
  3. Ветка (в каталоге коммита): только `feature/*` или `hotfix/*`, иначе exit 2 — «Коммит в ветку '…' заблокирован (CLAUDE.md → Git workflow)…».
  4. `commit_checks.py staged BRANCH MODE` по `paths.conf`: E2 (код только на `feature/PLAN-<N>-*`/`hotfix/*`), fail-closed на неклассифицированный корневой путь, `frozen` (`wiki/raw/`), E9 (корень `planning/`), E7 (`## Резюме` ≤ 15 строк у планов N ≥ 145), E8 (план > 80 КБ блок, > 40 КБ предупреждение, `<!-- size-waiver: … -->` в первых 30 строках), E13 (`CLAUDE.md` ≤ 36 КБ), E10/E11/E18 (`owner_ok.check_commit` читает маркеры владельца, не расходуя их).
  5. Если в индексе или `git status --porcelain` есть `planning/`: `registry.sh check --registry all` по рабочему дереву (E4/E5); нарушения → exit 2. По staged-дереву это же делает git-хук `pre-commit`.
  6. `scan-secrets.sh` по `git diff --cached -U0`; находка → exit 2; нет исполняемого сканера — шаг пропускается.
  7. `quality-gate.sh --fast`; падение → exit 2 («Quality Gate упал — коммит заблокирован…»).
- **Тесты:** `test_planning_gates.py` → `CommitGateTest` (E2/E4/E5/E7/E8/E9/E13/E16, data-строки, `-C`, hooksPath, heredoc, non-UTF8); `test_owner_ok.py` (E10/E11/E18 через оба хука); `test_e18.py`; `test_claude_compat.py`.
- **Ограничения:** сообщение коммита здесь не проверяется (E3 — `commit-msg`); секреты ищутся только в staged-диффе; полный PHPUnit/Dusk не запускаются; при отсутствии `quality-gate.sh` шаг молча пропускается (exit 0).

### 3.5 `merge-gate.sh` — мерж и обходные движения `main`

- **Триггер:** PreToolUse `Bash`; сначала дешёвый префильтр по regex `merge|pull|cherry-pick|rebase|reset|update-ref|symbolic-ref|branch|push|fetch|checkout|switch|tag` — иначе exit 0. Затем `merge_checks.py` (JSON на stdin). Разбор — argv, не regex; тела heredoc — данные.
- **Проверки:**
  - fail-closed: неразобранная git-команда из «опасного» набора блокируется; не удалось определить репозиторий — отказ;
  - запрет двигать `main` в обход мержа: `cherry-pick/rebase` на `main`, `reset --hard/--merge/--keep` на `main`, `update-ref` (`--stdin`, `main`, `HEAD` на main), `branch -f main`, `push . … main`, `fetch`, обновляющий локальный `main`, `symbolic-ref`, `checkout -B/-C main`;
  - мерж **в main**: ровно одна ссылка, статическая (не `FETCH_HEAD`/`ORIG_HEAD`/`MERGE_HEAD`/`CHERRY_PICK_HEAD`), без octopus, без изменения ссылок раньше в той же цепочке, без «upstream/--ff-only без ссылки»;
  - по каждой ссылке (T16): `rev-parse --verify` в SHA (не резолвится — блок), общая база с `refs/heads/main`, правила путей по **диффу** `merge-base main..SHA` (код — только если ссылка однозначно `feature/PLAN-N-*`/`hotfix/*`; иначе вне `planning/` блок), имя ветки должно быть единственным на вершине;
  - E12: полный гейт на вершине (`.claude/state/gates/<ветка>.merge-passed` = SHA) и ревью (`.claude/state/reviews/<ветка>.full|delta.<by>`); деньги (`money-paths.txt`) — обе отметки opus и codex, иначе хотя бы одна. Ветка, где дифф только `planning/` **и** содержит актуальный main, гейт/ревью не требует (HF-152);
  - E3: `hotfix/*` — файл `planning/hotfixes/HF-N-*.md` + новая строка `HOTFIXES.md` (или запись `JOURNAL.md` до миграции); `feature/PLAN-N-*` — план N есть в реестре;
  - E17: `git merge-tree --write-tree main SHA` → `registry.sh check --registry all` на дереве результата;
  - E10/E11/E18: `owner_ok.claim_items` — маркеры сверяются по SHA вершины и `target=main`, забираются атомарно (`os.rename` в `claimed/`), при любом отказе — откат всех; после мержа повторно не принимаются.
- **`git pull` в main:** разрешён только `--ff-only` с upstream `<remote>/main` или `git pull [--ff-only] <именованный remote> main`; `--rebase`, URL/путь, прочие ссылки — блок.
- **Сообщения:** «Мерж '<ref>' заблокирован: …», «деньги (money-paths.txt): нужны отметки ревью opus И codex — …», «нет зелёного полного гейта на вершине …».
- **Сухой прогон:** `.claude/scripts/merge-ready.sh <ветка>` → `merge_checks.py --preflight`: печатает READY/NOT READY и не расходует маркеры; владельца о мерже спрашивают только при READY.
- **Тесты:** `test_merge_gate.py` (preflight, резолв ссылок, ревью, деньги, E17, hotfix/план, обходы, парсинг, полнота money-путей); `test_owner_ok.py`; `test_e18.py`.
- **Ограничение:** внутренняя ошибка `merge_checks.py` = отказ (fail-closed), но `merge-gate.sh` без `merge_checks.py` (файла нет) ничего не проверит.

### 3.6 `main-push-guard.sh` — публикация `main`

- **Триггер:** PreToolUse `Bash`; если в команде нет подстроки `push` — exit 0. Перенаправления вырезаются через `commit_checks.strip_redirections`.
- **Разрешает** пуш `main` только когда на первой родительской линии `main` впереди реального серверного `<remote>/main` нет немерж-коммитов: `git ls-remote <remote> refs/heads/main`, серверный SHA должен существовать локально, быть предком локального `main`, а `git rev-list --first-parent --no-merges <server>..refs/heads/main` — пуст. Remote обязан быть именованным из `git remote`.
- **Блокирует:** `+main`, `--force`/`-f`/`--force-with-lease`/`--force-if-includes`, `--delete`/`:main`, `--all`/`--mirror`, wildcard/matching refspec, источник не `main` (`feature:main`, `HEAD:main` не из main), подстановки `$(…)`/обратные кавычки на `main`, `git subtree push … main`, неразрешимый/URL-remote, `--repo`, отсутствие локального `main`. Голый `git push` из `main` проверяется как публикация.
- **Понимает:** цепочки (`a && git push …`, `;`, `|`), вложенные оболочки, `cd <dir> && git push` (ветка из того каталога), `git -C <dir>`, флаги со значениями (`--repo`, `--receive-pack`, `-o`, …), `checkout/switch` до пуша в той же команде.
- **Сообщение:** «Пуш в main заблокирован (<причина>). Правило проекта: прямых правок main нет; в main публикуются только влитые ветки (мерж-коммиты) и только по слову владельца…».
- **Тесты:** `test_main_push_guard.py` (прямые пуши, тег `main`, голый push, цепочки/вложенные shell, подстановки, `cd`, опции, реальный серверный SHA против устаревшего tracking-ref, force/delete/all, wildcard, переключение ветки внутри команды).
- **Известный компромисс:** команду от данных хук отличает только regex, поэтому текст «git push origin main» внутри `echo`/grep/heredoc/сообщения коммита тоже проверяется как команда. Это защита от случайности агента, не от злого умысла.

### 3.7 `owner-ok-guard.sh` — слово владельца не подделать

- **Триггер:** PreToolUse `Bash`; `jq -r '.tool_input.command'` → `owner_ok.py guard`.
- **Блокирует (exit 2):**
  - запуск `.claude/scripts/owner-ok.sh` / `owner_ok.py` и любую запись в `.claude/state/owner-ok`, кроме чтения разрешёнными командами (`grep`, `rg`, `cat`, `ls`, `head`, `tail`, `wc`, `git`, `stat`, `diff`) и без `>` в сегменте;
  - shell через git: `-c alias.x=!…`/`core.pager`/`core.editor`/`core.sshCommand`/`credential.helper` и др., `--exec-path`, `git config alias.*` — чтобы нельзя было собрать обход хуков алиасом.
- **E18 (edit-guard):** список защищённых путей и переключатель `e18 on/off` читаются из `paths.conf` версии HEAD; без маркера `hooks-edit` правка блокируется.
- **Механика маркера (owner_ok.py):** файл `.claude/state/owner-ok/<вид>-<enc(id)>@<enc(ветка)>`, строки `kind/id/branch/sha/target=main/issued`; виды `close-plan`, `rm-add`, `hooks-edit`; TTL 24 ч; `commit-gate`/`pre-commit` читают маркер (ветка, вид/id, срок, SHA не сверяют) и не расходуют; `merge-gate` сверяет SHA вершины и цель `main`, затем атомарно забирает; SessionStart (`plans-drift`) чистит `.claimed`, просроченные и влитые.
- **Сообщения:** «Слово владельца (E10/E11) выдаёт только владелец в своём терминале…»; «Заблокировано: … (I4)».
- **Тесты:** `test_owner_ok.py` → `GuardTest`, `MergeGateHardeningTest`, `MarkerNameTest`; `test_e18.py` (E18 через edit-guard/commit/merge).
- **Ограничение:** хук видит только Bash агента. Владелец в своём терминале выдаёт маркеры скриптом `owner-ok.sh`; агент этого не видит и не должен.

### 3.8 `big-read-guard.sh` — чтение целиком

- **Триггер:** PreToolUse `Read` и `Bash` (один скрипт на оба matcher'а).
- **Пороги:** > 300 строк **или** > 40960 байт; переопределяются `BIG_READ_MIN_LINES`, `BIG_READ_MAX_BYTES`. Сравнение строгое (`-gt`).
- **Read:** пропуск, если задан `offset` или `limit`, файла нет или путь не файл. Иначе блок (exit 2): «Файл N строк, M байт (порог: …)» + подсказка: реестры — `registry.sh show <id>`; иначе по порядку `mcp__local-workers__run_worker` (`deepseek-worker`) → `Agent(model:"haiku")` → `Read` с `offset/limit`.
- **Bash:** только команда, **начинающаяся** с `cat|head|tail|less|more` и без `|` или `>`; берётся первый не-флаговый аргумент. Прочие способы чтения не покрыты.
- **Исключения:** `composer.lock`, `package-lock.json`, `vendor/`, `node_modules/`, `*.min.js/css`, бинарные (`png/jpg/jpeg/gif/webp/ico/woff/woff2/pdf/zip`).
- **Тесты:** `test_planning_gates.py` → `BigReadGuardTest` (40 КБ, 300 строк, ranged read, исключения, cat).
- **Ограничение:** это экономия контекста, а не безопасность; `cat file | sed`, чтение другими инструментами и curl проходят. В Codex адаптер дописывает своё сообщение про `rg/sed` и worker.

## 4. Python-модули и конфиги

| Файл | Роль | CLI/входы |
|---|---|---|
| `paths.py` | классификация путей по `paths.conf` | `classify [--root DIR] ПУТЬ…` → `вид<TAB>путь`; `guarded ПУТЬ` (exit 0/1); `planning-root-ok ПУТЬ`; `unclassified` |
| `paths.conf` | единый список классов: `code`, `planning`, `wiki`, `exempt`, `frozen` (префикс, блок любой правки), `planning-root`, `guard`, `guard-stage4`, `e18 on/off`, `guard-e18` | маски fnmatch по первому сегменту; новый корневой элемент без строки = fail-closed |
| `commit_checks.py` | дешёвые проверки коммита | `inspect`, `staged BRANCH [staged или dirty]`, `noverify`, `msg BRANCH FILE [PPID]`, `push-range BASE HEAD` |
| `merge_checks.py` | проверки мержа/pull | JSON на stdin; `--preflight REF` для `merge-ready.sh` |
| `owner_ok.py` | маркеры владельца | `guard`, `edit-guard FILE BRANCH`, `merge-claim 1/0 REF…`, `cleanup` |
| `money-paths.txt` | «денежные» пути для E12 | маски fnmatch/префиксы; полноту держит `test_merge_gate.py::test_every_money_keyword_file_is_money` |

- `commit_checks.py` разбирает команду как argv (не regex): строки-данные (`echo`, `python3 -c`, значения `-m/-t`) командами не считаются, вложенные `bash|sh|zsh -c` разбираются рекурсивно. Непредвиденное исключение → exit 0 (fail-open), потому что авторитетная проверка — git `pre-commit`.
- `merge_checks.py` использует тот же парсер; при неразобранной команде с опасной git-подкомандой — отказ; любое исключение — exit 2 (fail-closed).
- `owner_ok.py` — единственный модуль, который пишет маркеры; `merge-claim` при сбое всегда exit 2, остальные действия fail-open.
- E18 берёт политику из `paths.conf` версии HEAD/merge-base (и union с `main`), поэтому выключить правило той же правкой, которую оно должно остановить, нельзя.

## 5. Нативные git-хуки `.githooks/`

Подключение: `.claude/scripts/install-githooks.sh` → `chmod +x .githooks/*` и `git config core.hooksPath .githooks` (если уже ровно `.githooks` — сообщает «уже подключено»). Скрипт идемпотентен для относительного значения; фактическое значение сейчас абсолютное, поэтому повторный запуск нормализует его в `.githooks`. Без этих хуков проверки не работают в обычном терминале — `plans-drift` предупреждает об этом на SessionStart.

| Хук | Что делает | Выход |
|---|---|---|
| `pre-commit` | `commit_checks.py staged BRANCH staged --hook` (E2 не применяется при merge/cherry-pick/revert/rebase — по состоянию git, но структура проверяется); экспорт **staged**-дерева `planning/` во временный каталог и `registry.sh check --registry all --root <tmp>`; неполный экспорт/внутренняя ошибка registry — предупреждение, проверка пропускается (fail-open) | 0/1 |
| `commit-msg` | `commit_checks.py msg BRANCH FILE PPID` (E3): для `feature/PLAN-N-*` обязателен `PLAN-N` (граница идентификатора), для `hotfix/*` — `HF-<число>`; `RM-N` допустим только если staged состоит из `planning/ROADMAP.md`/`planning/roadmap/**`; исключения — «Merge branch / remote-tracking branch / pull request / tag», `Revert`, `fixup!`, `squash!` или идущий merge/rebase/cherry-pick; при `--amend` учитываются файлы прежнего коммита | 0/1 (через exit 2 → 1) |
| `pre-push` | теги и удаления (sha из нулей) пропускаются; для диапазона `BASE..SHA` — `commit_checks.py push-range` (структура, без E2); реестры на архиве `planning/` пушимого дерева; верификаторы миграций `verify-plans-migration.sh`, `verify-journal-migration.sh` на detached-worktree, если тронуты `closed/`, `hotfixes/` или верификаторы; если диапазон трогает `.claude/hooks/`, `.claude/scripts/`, `.githooks/`, `.codex/` (или диапазон неизвестен) — тесты хуков на чекауте пушимого коммита, параллельно, в вычищенном окружении (`GIT_*`, `CLAUDE_PROJECT_DIR` удалены) | 0/1 |
| `post-merge` | `exec .claude/scripts/release-tag.sh`: локальный semver-тег на `main` по conventional commits (`BREAKING`/major, на 0.x — minor; `feat`/minor; `fix/perf/refactor/revert`/patch, docs/test/chore — без тега), не пушит | — |

- `pre-push` fail-open на отсутствии python3, невычислимом диапазоне, сбое экспорта/чекаута — но известное нарушение блокирует.
- Обход только у владельца: `git commit --no-verify`, `git push --no-verify`; агенту они запрещены `commit-gate` (E16).
- Тесты: `test_githooks.py` (commit-msg, pre-commit, pre-push, install), `test_registry.py` (формы реестров).

### 5.1 Состояние обвязки (не переносится)

Всё лежит под `.claude/state/` и **gitignored**; при переносе каталог создаётся заново, старые отметки не копируются.

| Путь | Пишет | Читает | Смысл |
|---|---|---|---|
| `state/gates/<ветка с /→_>.merge-passed` | `quality-gate.sh --merge` | `merge_checks.py` | SHA вершины, на которой полный гейт зелёный |
| `state/reviews/<ветка>.<full или delta>.<opus или codex>` | `mark-reviewed.sh --by` | `merge_checks.py` | SHA полного ревью; для дельты — tip и база полного |
| `state/owner-ok/<kind>-<enc(id)>@<enc(ветка)>` (+ `claimed/`) | `owner-ok.sh` (владелец) | commit-gate, pre-commit, merge-gate | разрешение владельца, TTL 24 ч |
| `state/registry.lock` | `registry.sh` (`flock`) | `registry.sh` | сериализация записи индексов |

## 6. Адаптер Codex

`.codex/hooks.json` повторяет матрицу событий, а `.codex/hooks/claude-compat.py` переводит payload Codex в payload Claude и вызывает те же `.claude/hooks/*.sh` — логика не копируется.

| Claude | Codex (по `.codex/hooks.json`) | Команда |
|---|---|---|
| SessionStart | SessionStart | `claude-compat.py plans-drift` |
| PreToolUse Edit/Write/NotebookEdit | `apply_patch / Edit / Write / NotebookEdit` | `branch-guard`, `registry-guard` |
| PreToolUse Bash | `Bash / exec_command / shell_command / shell / functions.exec_command` | `commit-gate`, `merge-gate`, `main-push-guard`, `owner-ok-guard`, `big-read-guard` |
| PreToolUse Read | `Read` | `big-read-guard` |

Что делает адаптер: берёт `cwd`, `tool_name`, `tool_input`; `cmd` → `command`; `workdir` приклеивает к cwd; ищет корень через `git rev-parse --show-toplevel` и, если там есть `.claude/hooks`, выставляет `CLAUDE_PROJECT_DIR`; shell-имена (`exec_command`, `shell_command`, `shell`, `functions.exec_command`) → `Bash`; для `apply_patch` вытаскивает пути из строк `*** Add File:`, `*** Update File:`, `*** Delete File:`, `*** Move to:` и вызывает файловый хук на каждый (registry-guard — реальный путь, branch-guard — существующий родительский каталог); при нулевом коде возвращает его; для big-read-guard добавляет сообщение про `rg/sed`/worker. Нет путей — синтетический `.codex-hook-target`.

Ограничения: сам `.codex/config.toml` (в нём `[features] hooks = true` и MCP laravel-boost) **gitignored** (`/.codex/*`, кроме `hooks.json` и `hooks/*.py`) — при переносе его нужно создать заново. Активация событий зависит от билда Codex и не проверяется из репозитория: наличие `hooks.json` — декларация, а не доказательство. Адаптер покрыт `.codex/hooks/test_claude_compat.py` (проверяет и symlink-инварианты `AGENTS.md → CLAUDE.md`, `.agents/skills → .claude/skills`, apply_patch, no-verify, main, секреты); тест гоняется `pre-push` при изменении хуков.

## 7. Quality Gate `.claude/scripts/quality-gate.sh`

Режимы: без флагов — полный; `--fast` — без полного прогона тестов (его зовёт `commit-gate`); `--merge` — добавляет Dusk и пишет отметку гейта; `--dusk-plan` — только печатает `dusk: run|skip (причина)` и выходит.

| Шаг | Команда | --fast | обычный | --merge |
|---|---|---|---|---|
| Larastan | `php vendor/bin/phpstan analyse --no-progress` | да | да | да |
| Slugs | `php artisan site-pages:check-slugs` | да | да | да |
| Pint | `vendor/bin/pint --dirty --format agent` | да | да | да |
| PHPUnit parallel | `php artisan test --compact --parallel --processes=${GATE_PHPUNIT_PROCESSES:-6} --exclude-group=serial-db` | нет | да | да |
| PHPUnit serial | `php artisan test --compact --group=serial-db` | нет | да | да |
| eslint | `npm run lint --silent` (только если есть `node_modules`) | да | да | да |
| Skills | каждый `.ai/skills/*` имеет `.claude/skills/<name>` как symlink (если оба каталога есть) | да | да | да |
| Build | `npm run build --silent` на хосте | нет | нет | если нужен Dusk и есть node_modules |
| Dusk | `php artisan dusk` | нет | нет | по diff-условию |

- PHP-шаги: `docker exec -w <container-dir> <project>-horizon-1 …`, если контейнер запущен; иначе `vendor/bin/sail`. `container-dir` = `/var/www/html` + путь worktree относительно общего git-root. Worktree без `vendor/` — exit 1 с подсказкой `cp -c -R <main-root>/vendor vendor`.
- Dusk пропускается, только если `git diff --no-renames --name-only main...HEAD` непуст и все пути в `planning/ .claude/ .githooks/ .codex/ .agents/ wiki/` или `*.md`; пустой diff/ошибка/любой иной путь → run.
- **Где вызывается:** `commit-gate` → `--fast`; `--merge` — вручную (или через `merge-ready`-цикл) перед мержем; нативный `pre-commit` гейт **не** запускает. Зелёный `--merge` пишет `.claude/state/gates/<ветка с /→_>.merge-passed` с SHA, только если ветка именованная и `git diff --quiet HEAD --` (отслеживаемые файлы; untracked не учитываются). Эту отметку читает `merge-gate`.
- **Расхождения:** комментарий обещает остановку на первом сбое, но `set -uo pipefail` без `-e` продолжает шаги, собирает `FAILED` и возвращает 1. eslint без `node_modules` пропускается. Проверка skills смотрит существование и тип symlink, но не цель. Dusk без пересборки может проверять устаревший `public/build`.

## 8. Наборы тестов обвязки

| Файл | Что проверяет |
|---|---|
| `.claude/hooks/test_planning_gates.py` | `commit-gate` (E2/E4/E5/E7/E8/E9/E13/E16, data-строки, `-C`, hooksPath, heredoc, non-UTF8), `branch-guard`, `registry-guard`, `big-read-guard`, `plans-drift`, `paths.conf` (полнота классификации корня), парсинг перенаправлений |
| `.claude/hooks/test_owner_ok.py` | `owner-ok.sh` (формат маркера, id/ветка/срок), E10/E11 в commit/pre-commit/merge, атомарный захват и параллельные гейты, guard, cleanup, имя маркера |
| `.claude/hooks/test_merge_gate.py` | preflight `merge-ready`, резолв ссылок в SHA, T16, E12 (деньги/одна отметка/привязка к вершине), E17, E3 hotfix/план, обходы main, pull, парсер, полнота `money-paths.txt` |
| `.claude/hooks/test_e18.py` | E18: `paths.conf` `e18 on`, каждый защищённый путь в commit/pre-commit/merge/edit-guard, срок/ветка, union с main, «выключение в том же диффе не помогает» |
| `.claude/hooks/test_githooks.py` | `.githooks/commit-msg`, `pre-commit` (staged-дерево, merge-конфликт, fail-open), `pre-push` (теги/удаления, диапазон, тесты на пушимом коммите, герметичность env, верификаторы, неизвестный диапазон), `install-githooks.sh` |
| `.claude/hooks/test_main_push_guard.py` | `main-push-guard`: прямые/голые пуши, тег main, цепочки, подстановки, `cd`, force/delete/all, реальный серверный SHA, переключение ветки |
| `.claude/hooks/test_quality_gate.py` | только решение `--dusk-plan` (run/skip и причина), полный гейт не запускается |
| `.claude/scripts/test_registry.py` | формы и коды `registry.sh` (0 чисто, 1 нарушения, 2 аргументы) |
| `.codex/hooks/test_claude_compat.py` | адаптер Codex: правила/скиллы как symlink, apply_patch по каждому пути, no-verify, main, секреты, big-read |

Запуск вручную: `python3 .claude/hooks/test_planning_gates.py` и т.п.; `.codex/hooks/test_claude_compat.py` — `cd .codex/hooks && python3 -m unittest test_claude_compat`. Все наборы работают на временных git-репозиториях и вычищают `GIT_*`/`CLAUDE_PROJECT_DIR`, чтобы фикстуры не ушли в настоящий репозиторий. `pre-push` запускает **все** наборы из таблицы на чекауте пушимого коммита, когда диапазон трогает хуки/скрипты (или диапазон неизвестен). SessionStart их не запускает, CI-конфига для них в обвязке нет.

## 9. Ограничения и расхождения

1. **Декларация ≠ исполнение.** Файл `.claude/settings.json` или `.codex/hooks.json` описывает подключение; работает ли событие в конкретной версии рантайма, из репозитория не видно. Проверять сценарием (блокируемый вызов), а не наличием файла.
2. **Нативные git-хуки покрывают меньше, чем агентские.** Требуется (`CLAUDE.md` → «Git workflow»): Larastan перед каждым коммитом; фактически (`.githooks/pre-commit`): Larastan/Pint/eslint/сканер секретов не запускаются — это делает `commit-gate` (PreToolUse). В обычном терминале `git commit` получает только дешёвые проверки и реестры; полный гейт — только через агент или вручную.
3. **`settings.local.json`** (31 КБ) не входит в пакет и игнорируется глобально; его `permissions.allow` (включая `Bash(git commit *)`, `Bash(git push *)`, `Bash(git merge *)`) — локальная настройка машины, а не обвязка. Переносить нужно `.claude/settings.json`.
4. **`core.hooksPath` сейчас абсолютный**, а `plans-drift` ждёт ровно `.githooks` — SessionStart печатает ложное предупреждение E19. `install-githooks.sh` нормализует значение.
5. **Fail-open точки:** `commit_checks.py` при исключении → 0; `pre-commit` при сбое экспорта/registry → предупреждение; `pre-push` без python3/диапазона/чекаута → предупреждение; `branch-guard` без git → 0; `big-read-guard` без файла → 0; отсутствие `jq` → пустой payload. Fail-closed: `merge_checks.py` (любая внутренняя ошибка), `owner_ok merge-claim`, неразобранная опасная git-команда в merge-gate.
6. **Ранние файловые guard'ы — не sandbox.** Правка через Bash (`sed -i`, `cat >`, `tee`) проходит мимо `branch-guard`/`registry-guard`; ловит коммит/мерж.
7. **Устаревшие адаптеры.** `.cline/hooks/PreToolUse.sh` — один диспетчер, портирует только 4 проверки: commit-gate (ветка → секреты → `quality-gate --fast`), branch-guard, big-read-guard, plans-drift; `merge-gate`, `main-push-guard`, `registry-guard`, `owner-ok-guard` отсутствуют, тестов нет, файл датирован 26.09.2026 (до PLAN-145). `.trae/` содержит только `rules/wiki.md`, `skills/` и `mcp.json` — хуков нет вообще. Оба каталога помечены `code` в `paths.conf`, но как слой принуждения не считаются.
8. **Устаревшие комментарии.** В `test_e18.py` докстринг говорит «в боевом paths.conf правило выключено (`e18 off`)», фактически `paths.conf` содержит `e18 on` и тест `ConfTest.test_real_conf_is_on` это проверяет. В `mark-reviewed.sh` комментарий «ревьюер всегда opus» расходится с `--by opus|codex` и логикой merge (обычный код — одна отметка, деньги — обе).
9. **Ревью-маркер — заявление, не криптография.** `mark-reviewed.sh --by` пишет файл; кем выполнен аудит, технически не доказуется.
10. **Маркер владельца привязан к SHA вершины только на мерже.** После нового коммита в ветку разрешение на мерж нужно выдавать заново; commit-маркеры SHA не сверяют и живут 24 ч.
11. **`main-push-guard` не различает команду и текст** (echo/heredoc), `big-read-guard` покрывает только Read и простой cat-подобный Bash. Это защита от случайности, а не от намеренного обхода.
12. **`.claude/state/`, `.codex/config.toml`, `outputs/`** — gitignored. При переносе пакета их нужно создать/настроить отдельно: state-каталоги для гейтов/ревью/маркеров, `config.toml` для Codex, `core.hooksPath` для git-хуков.

## 10. Быстрая диагностика

| Сообщение / симптом | Кто блокирует | Что делать |
|---|---|---|
| «СВЕРКА ПЛАНОВ…» в начале сессии | `plans-drift` | разобрать до новой работы: обновить индексы, закрыть/завести план |
| «Ветка '…' не по конвенции» | `branch-guard` | `git branch -m feature/PLAN-N-slug` или `hotfix/slug` |
| «… — индекс реестра, прямая правка … запрещена (E6)» | `registry-guard` | править через `.claude/scripts/registry.sh` |
| «Обход хуков запрещён (E16)» | `commit-gate` | убрать `--no-verify`/`-n`/`core.hooksPath`; обход — только владелец |
| «Коммит в ветку '…' заблокирован» | `commit-gate` | создать `feature/*`/`hotfix/*`; правки сохранятся |
| «registry.sh check нашёл нарушения реестров» | `commit-gate` | `.claude/scripts/registry.sh check --registry all` |
| «В staged-диффе похоже на секрет» | `commit-gate` | убрать фрагмент из диффа; ложное — владелец коммитит сам |
| «Quality Gate упал — коммит заблокирован» | `commit-gate` | `.claude/scripts/quality-gate.sh --fast` и починить шаг |
| «нет зелёного полного гейта на вершине» | `merge-gate` | `.claude/scripts/quality-gate.sh --merge` на чистом дереве |
| «деньги … нужны отметки ревью opus И codex» | `merge-gate` | `.claude/scripts/mark-reviewed.sh --full --by …` |
| «… — только по слову владельца» | `owner_ok` в commit/merge | владелец выдаёт маркер: `owner-ok.sh <вид> <id> [ветка]` |
| «Пуш в main заблокирован (…)» | `main-push-guard` | пушить ветку `git push -u origin <ветка>`; main — только мерж владельца |
| «Файл N строк, M байт (порог…)» | `big-read-guard` | `registry.sh show`, worker/субагент или `Read` с `offset/limit` |
| Хук не сработал в worktree | `CLAUDE_PROJECT_DIR`/каталог | запускать хук из нужного checkout; файловые guard'ы смотрят каталог файла |
| `git commit` в терминале прошёл без гейта | нативные хуки | `git config core.hooksPath`; `.claude/scripts/install-githooks.sh` |

## 11. Источники

- `.claude/settings.json`, `.claude/settings.local.json` (локальный, не переносится)
- `.claude/hooks/plans-drift.sh`, `branch-guard.sh`, `registry-guard.sh`, `commit-gate.sh`, `merge-gate.sh`, `main-push-guard.sh`, `owner-ok-guard.sh`, `big-read-guard.sh`
- `.claude/hooks/paths.py`, `paths.conf`, `commit_checks.py`, `merge_checks.py`, `owner_ok.py`, `money-paths.txt`
- `.claude/hooks/test_planning_gates.py`, `test_owner_ok.py`, `test_merge_gate.py`, `test_e18.py`, `test_githooks.py`, `test_main_push_guard.py`, `test_quality_gate.py`
- `.githooks/pre-commit`, `commit-msg`, `pre-push`, `post-merge`; `.claude/scripts/install-githooks.sh`
- `.claude/scripts/quality-gate.sh`, `merge-ready.sh`, `mark-reviewed.sh`, `release-tag.sh`, `owner-ok.sh`, `scan-secrets.sh`, `registry.sh`, `test_registry.py`
- `.codex/hooks.json`, `.codex/config.toml`, `.codex/hooks/claude-compat.py`, `.codex/hooks/test_claude_compat.py`
- `.claude/reference/planning-registries.md` (E1–E19), `CLAUDE.md` → «Планирование», «Git workflow»
- `outputs/AGENT_HARNESS.md`, строки 62–131 и 180–241 (черновик; сверен с кодом и исправлен)
