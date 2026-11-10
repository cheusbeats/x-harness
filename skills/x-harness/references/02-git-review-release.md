# 02. Git-процесс, ревью, Quality Gate, мерж и релиз

**Что это.** Исполняемая обвязка git-процесса: старт сессии, ветки и коммиты, Quality Gate, тесты, ревью, готовность к мержу, публикация `main` и релизные теги.
**Когда читать.** Перед первой правкой кода в сессии, перед коммитом, перед ревью и перед вопросом владельцу о мерже. Всё ниже — shell-команды и файлы репозитория; клиент-специфичны только способы подключения хуков (§10, §11 и пометки «Claude / Codex»).

Обозначения: **«требуется»** — правило задекларировано в `CLAUDE.md` / `.claude/reference/`; **«фактически»** — что исполняет код обвязки. Где они расходятся, это сказано явно (§14). «Владелец» — человек, работающий в своём терминале.

## 1. Старт сессии

| Шаг | Действие | Зачем |
|---|---|---|
| 1 | прочитать `planning/ACTIVE_PLANS.md`, затем `.claude/scripts/registry.sh show PLAN-N` и `## Резюме` плана | срез «на сейчас»; тела планов целиком не читать (E14) |
| 2 | `git status --short` | не смешать чужие незакоммиченные изменения со своей работой |
| 3 | `git symbolic-ref --short -q HEAD` | понять ветку (не `rev-parse --abbrev-ref`: при теге `main` он даёт `heads/main`) |
| 4 | `git log --oneline -5` | сверить код с планом, а не с формулировкой плана |
| 5 | разобрать вывод SessionStart (`plans-drift.sh`), при отсутствии — запустить вручную | расхождения реестров, бюджет стартового набора, подключение git-хуков |
| 6 | `.claude/scripts/install-githooks.sh`, если `git config core.hooksPath` не `.githooks` | E19: хуки должны работать в любом терминале |
| 7 | окружение — `.claude/reference/environment.md`; после `git pull` на другой машине `vendor/bin/sail composer refresh` | stale DI-биндинги и воркеры крутят старый код |

```bash
git status --short
git symbolic-ref --short -q HEAD
.claude/hooks/plans-drift.sh          # то же, что SessionStart
.claude/scripts/install-githooks.sh   # chmod +x .githooks/* и core.hooksPath=.githooks
```

`plans-drift.sh` (SessionStart: Claude — `.claude/settings.json`, Codex — `.codex/hooks.json` → `claude-compat.py plans-drift`) сообщает: коммиты называют `PLAN-N`, а индекс не трогали; план-документ без строки; коммиты с кодом без `PLAN-N`/`HF-N`; расхождения RM; лишнее в корне `planning/`; превышение бюджета стартового набора (E13, 52 КБ); неподключённые git-хуки; ветки, влитые в `main` (снести `git branch -d`). **Выход всегда 0 — это информатор, а не гейт**: вывод не игнорируется, но ничего не блокирует.

Фактический баг-риск: `plans-drift` сравнивает `git config core.hooksPath` со строкой `.githooks`, а `install-githooks.sh` пишет относительный путь; если в конфиге оказался абсолютный путь той же папки, хуки работают, а SessionStart даёт ложное предупреждение (AGENT_HARNESS §9).

## 2. Ветки

- База — только `main`. Работа — `feature/PLAN-N-slug` или `hotfix/*` от `main`.
- **Прямые коммиты в `main` запрещены**; `develop` не заводим. Мерж в `main` и публикация `main` — только по слову владельца в чате.
- Код (любой путь вне `planning/**` и `wiki/**`; классы путей — `.claude/hooks/paths.conf`) правится только на этих ветках (E2). `RM-N` в имени ветки права на код не даёт: `feature/RM-9-x` может править только `planning/` и `wiki/`.
- Новый корневой элемент репозитория без строки в `paths.conf` — fail-closed: коммит блокируется.

```bash
git switch -c feature/PLAN-149-harness-skill
git switch -c hotfix/fix-login-loop
git push -u origin feature/PLAN-149-harness-skill
```

| Где проверяется | Механизм | Что блокирует |
|---|---|---|
| Edit / Write / NotebookEdit | `.claude/hooks/branch-guard.sh` | `main`; `feature/*` без `PLAN-N` при правке кода; любой префикс кроме `feature/*`, `hotfix/*` (detached `HEAD` пропускается) |
| `git commit` (Bash) | `.claude/hooks/commit-gate.sh` | коммит в ветку не `feature/*` / `hotfix/*` — настоящий чекпоинт |
| `git merge` (Bash) | `.claude/hooks/merge-gate.sh` | мерж в `main` без гейта, ревью, реестров и слов владельца (где нужны) |

Ветка определяется по каталогу редактируемого файла (в git worktree у файла своя ветка), а не по `CLAUDE_PROJECT_DIR`. `branch-guard` — ранняя сигнализация: правку можно провести через Bash (`sed -i`, `cat >`, `tee`), поэтому реальный заслон — `commit-gate`.

## 3. Коммиты

- Сообщения **на английском**, conventional commits (`feat`, `fix`, `docs`, `chore`, `refactor`, `perf`, `test`, `ci`, `style`, `revert`).
- Каждый коммит **с кодом** называет `PLAN-N` своей ветки, на `hotfix/*` — `HF-N` (E3). По этому токену `plans-drift` находит чужую работу. Токен `RM-N` права на код не даёт.
- `--no-verify` и `-n` агенту запрещены (E16). Обход — только владелец в своём терминале.

```text
feat(billing): add webhook idempotency (PLAN-148)
fix(queue): restart horizon workers after queue changes (HF-153)
docs(planning): record PLAN-148 merge (PLAN-148)
```

```bash
git commit -m "feat(ui): dot-style tab nav on scans page (PLAN-151)"   # пройдёт commit-gate и commit-msg
git commit --no-verify -m "..."                                        # агенту заблокировано (E16)
```

**Фактически `commit-gate.sh` (PreToolUse Bash, timeout 180 с) делает по порядку:**

1. `commit_checks.py noverify` — блокирует `commit|push --no-verify`, `git commit -n`, `-c core.hooksPath=…`, `GIT_CONFIG_KEY_n=core.hooksPath`, `git config core.hooksPath …`.
2. Разбор argv: учитывает `git -C dir`, `cd dir &&`, workdir Codex; определяет «это commit?» и режим `staged`/`dirty` (`git add && commit`, `commit -a`, `commit <пути>`).
3. Ветка: только `feature/*` / `hotfix/*`.
4. `commit_checks.py staged <branch> staged|dirty` — E2, E9 (корень `planning/`), E7 (Резюме), E8 (размер плана), fail-closed по `paths.conf`.
5. `registry.sh check --registry all`, если затронут `planning/` (по рабочему дереву; по staged-дереву — git-хук).
6. Секреты: `git diff --cached -U0 | .claude/scripts/scan-secrets.sh` (только добавленные staged-строки; самотест `--self-test`).
7. `quality-gate.sh --fast` — Larastan + Pint + eslint + симлинки скиллов; падение блокирует коммит.

**Фактически git-хук `.githooks/commit-msg`** проверяет токен `PLAN-N`/`HF-N` через `commit_checks.py msg`; `exit 2` блокирует, прочий сбой хука — fail-open (владельца не парализуем).

**Фактически `.githooks/pre-commit`** — авторитетная проверка на реальном индексе: `commit_checks.py staged … --hook` и `registry.sh check` на staged-версии `planning/`, выгруженной во временный каталог. Он **не** запускает Larastan/Pint/eslint/сканер секретов — это делает только агентский PreToolUse. Обычный терминал получает меньший набор защиты; сбой экспорта/`registry.sh` печатает предупреждение и может пропустить проверку (fail-open).

Разделение: агентский commit-gate проверяет ветку/E2, реестры, секреты и `--fast`-гейт; git `pre-commit` — только ветку/E2 и реестры (по staged-дереву).

## 4. Quality Gate

`.claude/scripts/quality-gate.sh [--fast|--merge|--dusk-plan]` — исполняемая версия правила «Larastan перед каждым тестом и коммитом; Pint перед сдачей».

| Шаг | Команда (в выбранном раннере) | `--fast` | обычный | `--merge` |
|---|---|---|---|---|
| Larastan | `php vendor/bin/phpstan analyse --no-progress` | да | да | да |
| Slug-и страниц | `php artisan site-pages:check-slugs` | да | да | да |
| Pint | `vendor/bin/pint --dirty --format agent` | да | да | да |
| PHPUnit (parallel) | `php artisan test --compact --parallel --processes=${GATE_PHPUNIT_PROCESSES:-6} --exclude-group=serial-db` | нет | да | да |
| PHPUnit (serial DB) | `php artisan test --compact --group=serial-db` | нет | да | да |
| eslint | `npm run lint --silent` на хосте (если есть `node_modules`) | да | да | да |
| Скиллы | каждый `.ai/skills/*` имеет **симлинк** `.claude/skills/<имя>` | да | да | да |
| `npm run build` | на хосте, только под Dusk | нет | нет | по условию |
| Dusk | `php artisan dusk` | нет | нет | по условию |

```bash
.claude/scripts/quality-gate.sh --fast      # ~3 с, ровно это гоняет commit-gate перед коммитом
.claude/scripts/quality-gate.sh             # + полный PHPUnit перед сдачей
.claude/scripts/quality-gate.sh --merge     # + Dusk; обязательный чеклист перед мержем
.claude/scripts/quality-gate.sh --dusk-plan # только напечатать «dusk: run|skip (причина)»
```

**Раннер PHP-шагов:** если контейнер `<project>-horizon-1` запущен — `docker exec -w <каталог> <project>-horizon-1 …`, иначе `vendor/bin/sail …`. В worktree путь пересчитывается от общего git-корня в `/var/www/html`; worktree без `vendor/` гейт блокирует и предлагает `cp -c -R "<main-root>/vendor" vendor`. **eslint и npm — на хосте macOS** (Linux-биндинги в контейнере ломают сборку).

**Условие Dusk:** Dusk (и `npm run build` под него) пропускается, только если `git diff --no-renames --name-only main...HEAD` непуст и все пути входят в `planning/`, `.claude/`, `.githooks/`, `.codex/`, `.agents/`, `wiki/` или оканчиваются `.md`. Пустой diff, ошибка diff и любой иной путь — `run` (fail closed).

**Отметка для merge-gate:** зелёный `--merge` при `git diff --quiet HEAD --` и именованной ветке пишет SHA вершины в `.claude/state/gates/<ветка с /→_>.merge-passed`. Это чистота **отслеживаемых** файлов; untracked этой проверкой не видны (но видны `merge-ready`, §7).

**Перед мержем гоняется ВСЁ** (полный PHPUnit, serial DB, Dusk, Larastan, Pint, eslint), не отфильтрованное подмножество.

Расхождения: комментарий в шапке скрипта обещает остановку на первом упавшем шаге, фактически шаги продолжаются, имена копятся в `FAILED`, exit 1 в конце. В `CLAUDE.md` порядок описан как «Larastan → Pint → PHPUnit → eslint → сверка скиллов» и не упоминает шаг `site-pages:check-slugs`; фактический порядок — в таблице выше. При отсутствии `node_modules` eslint и build **пропускаются без отказа**. Проверка скиллов смотрит существование и тип симлинка, но не фактическую цель ссылки.

## 5. Тесты: PHPUnit и Dusk

**PHPUnit** (`phpunit.xml`): наборы `tests/Unit` и `tests/Feature`; БД `testing`; sync queue; array cache/session/mail. Parallel создаёт БД `testing_test_N`; группа `serial-db` идёт отдельно и последовательно, потому что пишет реальные строки в общую `testing`. По умолчанию в гейте 6 процессов (`GATE_PHPUNIT_PROCESSES` переопределяет); два полных прогона одновременно не запускать.

```bash
docker exec <project>-horizon-1 php artisan test --compact --filter=TestName
vendor/bin/sail artisan test --compact --filter=TestName   # если laravel.test держит порт 80
docker exec <project>-horizon-1 php vendor/bin/phpstan analyse --no-progress
docker exec <project>-horizon-1 vendor/bin/pint --dirty --format agent
```

**Dusk** (`phpunit.dusk.xml`, `tests/Browser`): `tests/DuskTestCase.php` проверяет, что БД в allowlist `app_dusk`/`testing` (иначе можно стереть рабочую), исключает справочник plans из truncate, ставит `storage/framework/dusk-running`, работает с `public/build`, требует manifest и отсутствие JS/CSS новее manifest, Chrome headless 1920×1080, `DUSK_DRIVER_URL` либо `localhost:9515`. **Сборка `npm run build` — только на хосте**; из PHP она не вызывается, без свежей сборки Dusk проверяет вчерашний бандл. Поэтому Dusk не входит в обычный прогон и хук: он truncate'ит свою БД — только руками `quality-gate.sh --merge`.

Larastan: уровень 5, `baseline` (долг по типизации существует), один процесс. eslint: `eslint resources/js`, не Blade. Отдельного `pint.json` нет.

## 6. Ревью кода: ≤2 прохода

| Правило | Содержание |
|---|---|
| Проходы | не больше двух: **полный** (дифф ветки против `main` + потребители изменённого общего кода + сверка с планом) и **один дельта** по строкам, изменённым после находок |
| Что чинится | только **БЛОКЕРы**. ВАЖНО и МЕЛОЧЬ автор дорабатывает сам, **без нового прохода ревью** |
| Дельта | ревьюеру отдают список закрытого и одну задачу — подтвердить, что закрытое закрыто; новых направлений он не ищет |
| Деньги | один аудит opus и один Codex **параллельно**, затем **одна** проверка правок (не новый полный круг) |
| Повтор | новый коммит после дельты — снова дельта от той же полной базы; полное ревью повторять не нужно |
| Радиус | `.claude/scripts/blast-radius.sh <ClassName\|table.column\|methodName>` — потребители изменённого |

Отметки пишет сам ревьюер; гейт верит только им. Файлы: `.claude/state/reviews/<ветка с /→_>.full.<by>` и `.delta.<by>`.

```bash
.claude/scripts/mark-reviewed.sh --full  --by opus   feature/PLAN-149-x "итог"
.claude/scripts/mark-reviewed.sh --full  --by codex  feature/PLAN-149-x "итог"
.claude/scripts/mark-reviewed.sh --delta --by opus   feature/PLAN-149-x "правки после ревью"
.claude/scripts/mark-reviewed.sh --delta --by codex  feature/PLAN-149-x "правки после ревью"
.claude/scripts/mark-reviewed.sh --full  --by codex --at <sha> feature/PLAN-149-x "ревью шло на более раннем коммите"
```

Фактически: `.full.<by>` хранит SHA вершины (или `--at`), время UTC и итог; `--delta` требует существующей полной отметки и её предка — переписанная история (`merge-base --is-ancestor` не проходит) отменяет ревью. `merge-gate` принимает либо полное ревью ровно на вершине, либо полное на предке + дельта с `[tip, full_sha]` в первых двух строках. Для денежных путей (`.claude/hooks/money-paths.txt`) нужны **обе** отметки (`opus` и `codex`), для остального — **хотя бы одна** (E12). Скрипт только записывает отметку, сам не ревьюит — выдумывать отметку нельзя.

Расхождение: комментарий в шапке `mark-reviewed.sh` говорит «ревьюер и для `--full`, и для `--delta` — ВСЕГДА opus», но скрипт принимает `--by opus|codex`, а `merge_checks.py` для не-денежного кода довольствуется одной из отметок; действующая норма — `.claude/reference/planning-registries.md` (не-денежное ревью — Codex, денежное — opus и Codex).

## 7. merge-ready.sh: когда можно спрашивать владельца

**Правило:** перед вопросом владельцу о мерже агент запускает `.claude/scripts/merge-ready.sh <ветка>` и спрашивает слово **только при READY**. Гейты, ревью и проверки после ответа владельца не гоняются заново.

```bash
.claude/scripts/quality-gate.sh --merge
.claude/scripts/merge-ready.sh feature/PLAN-149-harness-skill
```

Фактически `merge-ready.sh` — сухой прогон `merge-gate` (`merge_checks.py --preflight <ветка>`): **ничего не мержит, owner-маркеры не расходует** (побочно может создать git-объекты `merge-tree`). Вывод:

- `READY` — всё, кроме слов владельца, пройдено; слов не требуется;
- `READY (кроме слов владельца)` — всё пройдено, ниже печатаются точные команды `.claude/scripts/owner-ok.sh …`, привязанные к вершине;
- `NOT READY` + список недостающего: нет зелёного полного гейта на вершине, нет ревью, ветка отстаёт от `main`, рабочее дерево не чистое.

Exit 0 — READY, 1 — NOT READY, 2 — ошибка (не git-репозиторий). `NOT READY` разбирается до вопроса, а не объясняется владельцу.

## 8. merge-gate.sh (Claude/Codex, агентский PreToolUse)

`merge-gate.sh` на PreToolUse Bash: дешёвый префильтр по regex, затем `python3 .claude/hooks/merge_checks.py` (exit 2 + причины в stderr = блокировка тул-колла). Для **каждой** ссылки `git merge` берётся SHA (`rev-parse --verify`; не резолвится — блок), всё считается по диффу `merge-base main..SHA`; имя ветки — только ярлык для отметок, и только если на этом SHA стоит ровно одна ветка `feature/*|hotfix/*`.

| Проверка | Что требует |
|---|---|
| T16 | правила путей `paths.conf` применяются к диффу, а не к имени ветки; неизменяемый `wiki/raw` — блок; неклассифицированный путь — fail-closed |
| однозначность | вершина не должна быть у нескольких `feature/*\|hotfix/*` веток; несколько ссылок (octopus), голый `git merge` и подвижные `FETCH_HEAD`/`ORIG_HEAD`/`MERGE_HEAD`/`CHERRY_PICK_HEAD` в `main` запрещены |
| гейт | `.claude/state/gates/<ветка>.merge-passed` с SHA ровно на вершине |
| E12 | ревью на вершине: полное на tip либо полное-предок + дельта до tip; деньги — обе отметки |
| E3 | `hotfix/*` добавляет `planning/hotfixes/HF-N-*.md` и новую строку в `HOTFIXES.md`; `feature/PLAN-N-*` — план N есть в реестре |
| E17 | `registry.sh check --registry all` на **дереве результата слияния** `main + tip` (`git merge-tree --write-tree`, распакованное `planning/`) |
| E10/E11/E18 | слово владельца: маркер `.claude/state/owner-ok/…` сверяется по SHA вершины и забирается атомарно (один раз) |
| отставание | ветка обязана содержать актуальный `main`: иначе merge применит правки к переименованным файлам (rename detection) |

**Освобождение E12:** ветка, где менялся **только** `planning/**` и которая содержит актуальный `main`, не требует полного гейта и ревью (HF-152); любой путь вне `planning/`, даже удаление `.md`, возвращает строгие штампы. Все прочие проверки (имя ветки, реестры, E3, слова) не снимаются.

**Дополнительно защищены:** `cherry-pick`/`rebase` на `main`; `reset --hard`/`--merge`/`--keep` на `main`; `update-ref` (`--stdin`, `main`, `HEAD` на main); `branch -f main`, `checkout/switch -B/-C --force-create main`; `git fetch`/`git push .` с обновлением `main`; смена `HEAD` символической ссылкой; мерж после изменения ссылок в той же shell-команде. `git pull` в `main` разрешён только как `git pull --ff-only` при upstream `<remote>/main` либо `git pull [--ff-only] <именованный remote> main`. Внутренняя ошибка `merge_checks.py` блокирует мерж (fail-closed).

**Фактически:** для мержа **не в `main`** проверяются правила путей и штампы, но маркеры владельца не нужны. Обычный мерж ветки в `main` словом владельца в чате **машиной не проверяется** — гейт проверяет owner-маркеры только там, где их требует `owner_ok.needed` (закрытие плана, добавление RM, правка защищённых путей). «Только по слову владельца» — поведенческое правило `CLAUDE.md` для агента.

## 9. main-push-guard.sh: публикация main

Отдельный агентский PreToolUse-хук (Claude — `.claude/settings.json`, Codex — `.codex/hooks.json`, логика общая). Решение владельца 2026-10-17: **публикация влитых веток в `main` разрешена, прямые правки `main` и перезапись истории — нет.**

Пуш в `main` (`git push [origin] main`, `main:main`, `refs/heads/main`, `HEAD`/`HEAD:main` при текущей ветке `main`, голый `git push`/`git push origin` из `main`) разрешён **только если** на основной линии нет прямых коммитов впереди серверного `main`: `git rev-list --first-parent --no-merges <server>..main` пуст. Серверный SHA берётся реальным `git ls-remote <remote> refs/heads/main` (а не локальным tracking-ref), remote — только именованный из `git remote`.

Блокируются: `+main`, `--force`/`-f`/`--force-with-lease`, `--delete`/`:main`, `--all`/`--mirror`, refspec с источником не `main` (`feature:main`, `HEAD:main` не из `main`), wildcard/matching refspec, подстановки `$(..)`/обратные кавычки на `main`, `git subtree push … main`, `--repo`, неименованный remote, недоступный `ls-remote`, отсутствие SHA локально, расхождение истории, отсутствие локального `main`.

```bash
# разрешено (после мержа ветки и слова владельца пушить)
git push origin main
git push -u origin feature/PLAN-149-x     # ветки и теги проходят
# заблокировано
git push --force origin main
git push origin feature/PLAN-149-x:main
git push --all origin
```

Осознанный компромисс: команду от данных хук отличает только по regex, поэтому текст `git push origin main` внутри `echo`, `grep`, heredoc или сообщения коммита тоже проверяется как команда. Это защита от случайности агента, а не от умысла.

**Фактически** git-хук `.githooks/pre-push` **не** проверяет структуру `main` (в `commit_checks.py push-range` нет логики first-parent/`main`): он проверяет структуру диапазона, реестры и замороженные тела. Требование E1 «нет прямых коммитов в `main`» исполняется только агентским `main-push-guard.sh` (и `branch-guard`/`commit-gate` против прямых правок). В обычном терминале публикация `main` структурно не проверяется.

## 10. Git-хуки любого терминала (.githooks)

```bash
.claude/scripts/install-githooks.sh
# chmod +x .githooks/*; git config core.hooksPath .githooks
```

| Хук | Фактическая работа |
|---|---|
| `pre-commit` | E19: `commit_checks.py staged … --hook` + `registry.sh check --registry all` на staged-дереве `planning/`; fail-open при внутренней ошибке хука, нарушение реестра блокирует |
| `commit-msg` | E3: `commit_checks.py msg <branch> <file> <PPID>` — токен `PLAN-N`/`HF-N` |
| `pre-push` | структура диапазона (`push-range`), реестры на пушимом дереве (`git archive`), при изменениях `closed/*`, `hotfixes/*` или `verify-*` — `verify-plans-migration.sh` и `verify-journal-migration.sh` на detached worktree; если диапазон трогает `.claude/hooks/`, `.claude/scripts/`, `.githooks/`, `.codex/` — девять тестов хуков на worktree пушимого SHA, параллельно |
| `post-merge` | `exec .claude/scripts/release-tag.sh` |

Тесты хуков (их же гоняет `pre-push`):

```bash
python3 .claude/hooks/test_planning_gates.py
python3 .claude/hooks/test_main_push_guard.py
python3 .claude/hooks/test_owner_ok.py
python3 .claude/hooks/test_merge_gate.py
python3 .claude/hooks/test_e18.py
python3 .claude/scripts/test_registry.py
python3 .claude/hooks/test_githooks.py
python3 .claude/hooks/test_quality_gate.py
cd .codex/hooks && python3 -m unittest test_claude_compat
```

Теги и удаление веток `pre-push` пропускает. Наборы идут с вычищенным окружением (`GIT_*`, `CLAUDE_PROJECT_DIR`), чтобы фикстуры не ходили в настоящий репозиторий. Нет `python3`, не удался export/checkout/worktree или сам `registry.sh` — предупреждение и **fail-open**; блокируют только фактическое нарушение структуры/реестров/замороженных тел и упавшие тесты. Блокировка печатает «Обход — только владелец: `git push --no-verify`».

## 11. release-tag.sh

`post-merge` запускает `.claude/scripts/release-tag.sh`: локальный annotated-тег стабильной версии `vX.Y.Z` на `main`, без pre-release, **никогда не пушит**.

| Коммиты с прошлого стабильного тега | Бамп |
|---|---|
| `BREAKING CHANGE` / `type!:` | major (пока `0.x` — minor) |
| `feat` | minor |
| `fix` / `perf` / `refactor` / `revert` | patch |
| `docs` / `test` / `chore` / `ci` / `style` | версия не меняется |

Скрипт выходит молча, если ветка не `main` или на `HEAD` уже стоит точный `vX.Y.Z`; идемпотентен. Публикация тегов не автоматизирована: скрипт только создаёт тег, `git push origin --tags` — отдельная ручная команда.

## 12. CI не заменяет локальный гейт

CI-пайплайн проекта может не содержать PHPUnit, Dusk, Larastan, Pint, eslint, а его включение настраивается вне репозитория, поэтому чтение файла не доказывает, что pipeline включён. Утверждение «всё проверит CI» неверно: единственный полный прогон — локальный `quality-gate.sh --merge`.

## 13. Что делает только владелец

| Действие | Как оформляется | Источник |
|---|---|---|
| мерж в `main` и публикация `main` | слово владельца в чате; структурно `main-push-guard` требует лишь отсутствия прямых коммитов | `CLAUDE.md` 36-39, `main-push-guard.sh` |
| маркер `owner-ok` (закрытие плана, новая RM, правка хуков/настроек/`CLAUDE.md`/`.githooks/`) | `.claude/scripts/owner-ok.sh close-plan PLAN-N \| rm-add RM-N \| hooks-edit <ветка>` **только в своём терминале**; агент скрипт не запускает и в `.claude/state/owner-ok` не пишет | `planning-registries.md` 62-67, `owner-ok-guard.sh` |
| закрытие плана | явное «план закрыт», затем `.claude/scripts/registry.sh set-status PLAN-N закрыт` (и `plans/closed/PLAN-N.md`) | `CLAUDE.md` 17-18 |
| обход хуков | `git commit --no-verify` / `git push --no-verify` в своём терминале | `commit-gate.sh`, `commit_checks.py` |
| публикация релизных тегов | `git push origin --tags` вручную (скрипт теги не пушит; хук слова владельца для тегов не требует) | `release-tag.sh` |
| правка защищённых путей | только под маркером `hooks-edit` (E18: `.claude/hooks/`, `.claude/scripts/`, `.claude/settings.json`, `.githooks/`, `.codex/`, `.agents/`, `CLAUDE.md`, `AGENTS.md`) | `paths.conf` 81-89 |

## 14. Расхождения «требуется» / «фактически» и пробелы

| Пункт | Требуется | Фактически |
|---|---|---|
| порядок гейта | `CLAUDE.md`: Larastan → Pint → PHPUnit → eslint → сверка скиллов | `quality-gate.sh`: Larastan → `site-pages:check-slugs` → Pint → PHPUnit (parallel + serial) → eslint → симлинки → Dusk |
| остановка гейта | комментарий: «падает на первом шаге с ненулевым кодом» | `set -uo pipefail` без `-e`: шаги продолжаются, `FAILED` копится, exit 1 в конце |
| покрытие коммита гейтом | «гейт запускается перед `git commit`» | только агентский PreToolUse; обычный терминал запускает лишь `.githooks/pre-commit` без Larastan/Pint/eslint/секретов |
| слово владельца при мерже | «только по слову владельца» | обычный мерж машиной не проверяется; owner-маркеры нужны лишь для E10/E11/E18; пуш `main` не спрашивает маркер, только структуру |
| E1 на пуше | E1 приписан `commit-gate`, `branch-guard`, `main-push-guard` | в обычном терминале `pre-push` структуру `main` не проверяет |
| ревьюер | `mark-reviewed.sh` (шапка): «ВСЕГДА opus» | скрипт принимает `opus\|codex`; не-деньги — одна отметка; деньги — обе |
| чистота дерева для штампа | «полный гейт на вершине» | штамп пишется при `git diff --quiet HEAD --` (tracked), `merge-ready` смотрит `git status --porcelain` (видит untracked) |
| Dusk «перед мержем всё» | перед мержем гонять Dusk | Dusk пропускается, если diff — только документы/служебные пути |
| E16 | хуки не обходятся `--no-verify` | блокирует только агентский хук; человек в терминале обходит штатно |
| ядро хуков | проверки «зелёные» | `pre-push`/`pre-commit` fail-open при сбоях инфраструктуры; пропущенная проверка ≠ зелёная |
| `core.hooksPath` | `.githooks` | если в конфиге абсолютный путь, SessionStart даёт ложное предупреждение при рабочих хуках |

## 15. Минимальный порядок перед мержем

1. Ветка актуальна: `git merge main` (в ветку), конфликтные правки — обычный цикл.
2. Полное ревью: `.claude/scripts/mark-reviewed.sh --full --by opus|codex <ветка> "итог"` (деньги — обе отметки).
3. Правки по БЛОКЕРАм, затем один дельта-проход: `.claude/scripts/mark-reviewed.sh --delta --by … <ветка> "правки"`.
4. На **чистой** вершине: `.claude/scripts/quality-gate.sh --merge` (пишет штамп гейта на SHA).
5. `.claude/scripts/merge-ready.sh <ветка>` → `READY` (или `READY (кроме слов владельца)` + команды `owner-ok`).
6. Только теперь спросить владельца о мерже. После его «да» гейты и ревью не перегонять.
7. Мерж и публикацию выполняет владелец (или агент по его прямому слову в чате); `post-merge` создаст локальный тег.

## Источники

| Файл | Что взято |
|---|---|
| `CLAUDE.md` 4-5, 14-28, 30-46 | старт сессии, три реестра, слово владельца, Git workflow |
| `.claude/reference/planning-registries.md` 39-53, 69-101 | ревью ≤2 прохода, E1–E19, merge-ready, сверка при старте |
| `.claude/scripts/quality-gate.sh` | шаги, флаги, раннер, Dusk-условие, штамп |
| `.claude/scripts/merge-ready.sh`, `.claude/hooks/merge_checks.py` 383-413 | preflight, READY/NOT READY |
| `.claude/scripts/mark-reviewed.sh` | режимы, `--by`, `--at`, формат и ancestry отметок |
| `.claude/scripts/release-tag.sh` | semver-бампы, идемпотентность, локальность |
| `.claude/scripts/install-githooks.sh` | `core.hooksPath=.githooks` |
| `.githooks/pre-commit`, `commit-msg`, `pre-push`, `post-merge` | хуки любого терминала, список тестов, fail-open |
| `.claude/hooks/commit-gate.sh`, `commit_checks.py` | порядок агентского коммит-гейта, E16, E2/E7/E8/E9 |
| `.claude/hooks/branch-guard.sh`, `merge-gate.sh`, `main-push-guard.sh`, `merge_checks.py` | ветки, мерж, публикация `main` |
| `.claude/hooks/plans-drift.sh` 218-308 | SessionStart: дрейф, бюджет, git-хуки |
| `.claude/hooks/paths.conf`, `.claude/hooks/money-paths.txt` | классы путей, E18, денежные пути |
| `.claude/settings.json`, `.codex/hooks.json` | подключение хуков Claude / Codex |
| `outputs/AGENT_HARNESS.md` 132-370, 527-558 | снимок обвязки, сценарии приёмки, известный дрейф |
