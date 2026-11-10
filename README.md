# x-harness

Универсальная обвязка агентной разработки: реестры планов RM/PLAN/HF, git-процесс, гейты и хуки, роли субагентов. Плюс отдельный планировочный профиль для других проектов. Репозиторий одновременно **плагин** (Claude Code, Codex, Kimi Code, ZCode, OpenCode) и **скилл** (`npx skills`). DeepSeek Harness (DSH) подключается через мост.

Политики живут только в проектных `.claude/hooks`. Claude Code исполняет их нативно. Остальные клиенты передают свои события через общий переводчик [`adapters/agent-hook.py`](adapters/agent-hook.py): он приводит имена инструментов и полей к форме Claude и пробрасывает блокировку (exit 2). В проекте без обвязки плагинные хуки ничего не делают.

## Что внутри

```
skills/x-harness/          скилл: SKILL.md, references/ (00-index — карта), scripts/install-from-source
skills/x-harness-planning/ скилл планировочного профиля
adapters/agent-hook.py     переводчик хуков для Kimi/ZCode/OpenCode/Codex-плагина/DSH
hooks/hooks.json           хуки плагина (Claude Code, ZCode, Codex)
.claude-plugin/ .codex-plugin/ .kimi-plugin/ .agents/plugins/   манифесты и маркетплейсы
.opencode/plugins/x-harness.js   плагин OpenCode (хуки + роли из .claude/agents)
harness/                   обвязка (payload install.sh), сверяется MANIFEST.sha256
profiles/planning/         профиль «только планирование»: SPEC, AGENTS.md, planning/README.md
install.sh, verify.sh      установка в проект и проверка паритета
bin/xh                     CLI: gate/drift/merge-ready/hook/doctor
CLAUDE.md, AGENTS.md       симлинки на harness/CLAUDE.md
```

## Установка

Два шага: **(1)** плагин или скилл в агентный клиент, **(2)** обвязка в проект. Плагин без обвязки в проекте ничего не делает: его хуки срабатывают только там, где установлен `install.sh`.

### Шаг 1. Плагин в клиент

Плагин даёт скиллы `x-harness` и `x-harness-planning` и хуки клиента. Ставится один раз на машину.

**Claude Code** — в чате:

```
/plugin marketplace add cheusbeats/x-harness
/plugin install x-harness@x-harness
```

Хуки проекта Claude Code исполняет и так, из `.claude/settings.json`; плагин нужен ради скиллов.

**Codex:**

```bash
codex plugin marketplace add cheusbeats/x-harness
```

```bash
codex plugin add x-harness@x-harness
```

**ZCode** — в чате:

```
/plugin marketplace add cheusbeats/x-harness
/plugin install x-harness@x-harness
```

**Kimi Code** — Plugins → установка из GitHub: `cheusbeats/x-harness`.

**OpenCode** — в `~/.config/opencode/opencode.json`:

```json
{ "plugin": ["x-harness@git+https://github.com/cheusbeats/x-harness.git"] }
```

Плагин сам регистрирует роли из `.claude/agents/*.md` проекта как субагентов OpenCode.

**DeepSeek Harness (DSH)** — x-harness ставится как бандл профиля (профиль `web` или `desktop`). Мост ставится **той же версии**, что Host (`dsh --version`):

```bash
dsh plugin --profile web add @deepseek-ai/dsh-hooks-claude-code@$(dsh --version) @deepseek-ai/dsh-hook-protocol@$(dsh --version) github:cheusbeats/x-harness
```

Перезапусти профиль. В «Настройки → Плагины → Список плагинов» появится `hooks-claude-code` с id `include:x-harness-hooks` и статусом «смонтирован». Обновление — `dsh plugin --profile web update x-harness`.

**Только скилл** (любой клиент с Agent Skills, без хуков):

```bash
npx skills add cheusbeats/x-harness --skill x-harness
```

### Шаг 2. Обвязка в проект

Проще всего — попросить агента в проекте: «Примени x-harness и установи обвязку в этот проект» (для одних реестров планов — «профиль planning»). Вручную — из каталога проекта.

Профиль `planning` — только реестры RM/PLAN/HF, owner-ok, строгий слой и git-хуки; подходит любому стеку:

```bash
git clone --depth 1 https://github.com/cheusbeats/x-harness.git /tmp/x-harness && bash /tmp/x-harness/install.sh --project . --profile planning
```

Профиль `full` — Laravel-профиль (Laravel 13, Livewire 4, Filament 5, Sail/Docker) с гейтами, ролями и навыками:

```bash
git clone --depth 1 https://github.com/cheusbeats/x-harness.git /tmp/x-harness && bash /tmp/x-harness/install.sh --project . --clients auto --skills project
```

Полезные флаги `install.sh`:

| Флаг | Что делает |
|---|---|
| `--clients LIST` | `auto` (по умолчанию — найденные на машине) или явно `claude,codex,dsh,kimi,zcode,opencode,generic` |
| `--skills project\|global\|both\|none` | куда ставить навыки проекта |
| `--dry-run` | показать план, ничего не меняя |
| `--force` | перезаписать существующие файлы (с backup в `.x-harness-backup.<время>`) |

Что `--clients` добавляет в проект: `codex` — `.codex/hooks.json` и роли `.codex/agents`; `kimi` — роли `.agents/agents/*.md`; `zcode` — `.agents/mcp.json` → `.mcp.json`; `dsh` — навыки в `.dsh/skills`.

### DSH: как это устроено

Мост `dsh-hooks-claude-code` читает свой конфиг **один раз на весь процесс DSH**, а не на проект. Поэтому x-harness подключает его глобально: `package.json` объявляет `dsh.bundle`, патч [`dsh/cordis.patch.yml`](dsh/cordis.patch.yml) монтирует мост на [`hooks/dsh-hooks.json`](hooks/dsh-hooks.json), а переводчик находит проект по `cwd` сессии. В проекте без обвязки хуки ничего не делают. Тот же шаг выполняет `install.sh --clients dsh --dsh-hooks bridge --dsh-version "$(dsh --version)"` вместе с установкой обвязки в проект.

Альтернатива — сторонний `dsh-hooks-plugin`: `--dsh-hooks community` (конфиг `.dsh/hooks.json` в проекте).

### Шаг 3. Проверка

1. Перезапусти клиент, чтобы он перечитал хуки и навыки (Codex и ZCode попросят подтвердить доверие к хукам).
2. `bash /tmp/x-harness/bin/xh doctor` в проекте — что подключено; `bash /tmp/x-harness/verify.sh --project .` — сверка установленной копии с манифестом.
3. Отрицательный сценарий: создай ветку `hotfix/test` и попроси агента записать что-нибудь в `planning/ROADMAP.md`. Запись должна быть **заблокирована** с подсказкой `registry.sh`. Если прошла — хуки клиента не подключены.

### Примеры

Во всех примерах пакет клонируется один раз в `/tmp/x-harness`, а установщик запускается **из каталога целевого проекта**, а не из самого x-harness.

```bash
git clone --depth 1 https://github.com/cheusbeats/x-harness.git /tmp/x-harness
```

Если каталог уже есть, просто обнови его:

```bash
git -C /tmp/x-harness pull --ff-only
```

#### 1. Реестры планов в проекте на любом стеке (Claude Code + Codex)

```bash
cd ~/work/projects/my-app
bash /tmp/x-harness/install.sh --project . --profile planning --clients claude,codex
```

Ожидаемый вывод (сокращён):

```
x-harness: profile=planning mode=snapshot project=/Users/you/work/projects/my-app
клиенты: claude=1 codex=1 dsh=0 kimi=0 zcode=0 opencode=0 generic=0; skills=auto
1/5 payload planning -> /Users/you/work/projects/my-app
2/5 git-хуки
ok: core.hooksPath=.githooks
init: реестры planning/
  создан: planning/ROADMAP.md
  создан: planning/ACTIVE_PLANS.md
```

Первый план:

```bash
.claude/scripts/registry.sh add PLAN auto "Название плана"
```

#### 2. Laravel-проект: Claude Code, Kimi Code и OpenCode

Сначала посмотри план без изменений, потом установи:

```bash
cd ~/work/projects/shop
bash /tmp/x-harness/install.sh --project . --clients claude,kimi,opencode --dry-run
```

```bash
bash /tmp/x-harness/install.sh --project . --clients claude,kimi,opencode
```

Проект получит `CLAUDE.md`/`AGENTS.md`, `.claude/` (хуки, скрипты, роли), `.ai/` (правила и навыки), `.githooks/`, `planning/README.md`, а для Kimi — роли `.agents/agents/*.md`. Хуки Kimi и OpenCode приходят из плагина (шаг 1), у Claude Code — из `.claude/settings.json`.

#### 3. Проект для DeepSeek Harness

Один раз на машину — бандл в профиль DSH (шаг 1), затем обвязка в каждый проект:

```bash
dsh plugin --profile web add @deepseek-ai/dsh-hooks-claude-code@$(dsh --version) @deepseek-ai/dsh-hook-protocol@$(dsh --version) github:cheusbeats/x-harness
```

```bash
cd ~/work/projects/my-app
bash /tmp/x-harness/install.sh --project . --profile planning --clients dsh
```

Перезапусти профиль `web` и открой сессию с рабочей папкой `my-app`. Если x-harness уже стоял без бандла (DSH писал `declares no dsh.bundle`), обнови его: `dsh plugin --profile web update x-harness`.

#### 4. Повторная установка поверх старой версии

```bash
git -C /tmp/x-harness pull --ff-only
```

```bash
bash /tmp/x-harness/install.sh --project . --profile planning --force
```

Старые файлы уйдут в `.x-harness-backup.<дата-время>/` в корне проекта.

#### Проверка, что хуки работают

На ветке `hotfix/test` попроси агента записать что-нибудь в `planning/ROADMAP.md`. Правильный ответ хука:

```
…/planning/ROADMAP.md — индекс реестра, прямая правка Edit/Write запрещена.
Используй .claude/scripts/registry.sh: next-id | add <RM|HF|PLAN> <id|auto> "название" | set-status <id> <статус> | show <id> | check.
```

#### Частые ошибки

| Сообщение | Причина | Что делать |
|---|---|---|
| `ERROR: в проекте уже есть: - CLAUDE.md - AGENTS.md — повтори с --force` | установщик запущен в каталоге, где уже есть свои правила (часто — в самом x-harness или в проекте с собственной обвязкой) | проверь `pwd`; `--force` заменит файлы, сохранив старые в `.x-harness-backup.*` |
| `fatal: destination path '/tmp/x-harness' already exists` | пакет уже склонирован | пропусти `git clone` или сделай `git -C /tmp/x-harness pull --ff-only` |
| `для bridge нужна точная --dsh-version` | не передана версия DSH | добавь `--dsh-version "$(dsh --version)"` |
| запись в `planning/ROADMAP.md` прошла | хуки клиента не подключены | перезапусти клиент, подтверди доверие к хукам (Codex, ZCode); для DSH проверь в списке плагинов `include:x-harness-hooks` |
| `x-harness declares no dsh.bundle` | старая версия пакета в профиле DSH | `dsh plugin --profile web update x-harness` и перезапуск профиля |

Подробно про каждый клиент, матрицу совместимости и уровни проверки — [`skills/x-harness/references/08-install-and-acceptance.md`](skills/x-harness/references/08-install-and-acceptance.md).

## Профили

Полный профиль — Laravel-профиль (Laravel 13, Livewire 4, Filament 5, Sail/Docker): команды Laravel, настройки контейнера, базы, денежные пути и проверки исторических SHA. `--mode port` не адаптирует их автоматически: перед использованием в другом проекте их нужно настроить вручную по `references/08-install-and-acceptance.md`. Для одного планирования используйте `--profile planning`.

### Планировочный профиль

Только реестры планов (RM/PLAN/HF), owner-ok, строгий слой (E2/E18/E16, защита `main`, Quality Gate по
командам проекта) и git-хуки — без Laravel-гейтов. По умолчанию строгий; переносится между агентами
(событийные хуки Claude/Codex, git-хуки везде, `bin/xh` для generic):

```bash
./install.sh --project /path/to/project --profile planning
./verify.sh --profile planning --project /path/to/project
```

`--mode` для профиля игнорируется: он всегда port-совместим. `STRICT=off` выключает строгий слой только
по слову владельца (`hooks-edit`). Подробно — `skills/x-harness/references/09-planning-profile.md`, `profiles/planning/README.md`
и `profiles/planning/SPEC.md` §9.

## Принципы

1. **Источник и адаптация.** `harness/` содержит обвязку, дополненную ролями Codex; абсолютные пути в конфигурации отсутствуют. Обновляй копию осознанно и проверяй совместимость.
2. **Один payload — адаптеры клиентов.** Конфигурация клиента подключает общее ядро там, где его события поддерживаются; отсутствие адаптера или доверия означает, что соответствующий хук не исполняется.
3. **Исполнение важнее декларации.** Наличие хука в JSON не доказывает, что клиент его вызывает. Приёмка — сценариями.
4. **Секреты и состояние не переносятся.** `.env`, `.claude/state/`, `settings.local.json`, ревью, память — вне пакета.

При установке полного профиля с навыками установщик также получает `make-interfaces-feel-better` из [jakubkrehel/make-interfaces-feel-better](https://github.com/jakubkrehel/make-interfaces-feel-better) и `impeccable` из [pbakaus/impeccable](https://github.com/pbakaus/impeccable). Их содержимое не хранится в пакете: загрузка выполняется до изменения проекта, использованный commit SHA выводится в лог. Для автономной установки есть `--no-upstream-skills`; `--dry-run` ничего не скачивает. Скрипты навыков при установке не запускаются.

## Требования

- Git, Bash, Python 3.11+ для проверки Codex-ролей, стандартные Unix-утилиты.
- Для проверок Laravel-профиля: Docker/Sail, Composer, Node (npm — на хосте).
- Для DSH-мостов хуков — `dsh` и точные версии пакетов моста (см. 08); без них работает git-слой.
- Планировочному профилю хватает Git, Bash и Python 3 (плюс `jq` для PreToolUse-хуков Claude/Codex; без него они пропускают действие).

## Безопасность

Хуки и мосты исполняют shell-команды с доступом к workspace. Ставь только из доверенного источника и проверяй diff. Пакет не заменяет песочницу, approval-политику и серверные ограничения.

## Лицензия/происхождение

Код и документация x-harness — MIT ([LICENSE](LICENSE)). 
Правила и код обвязки — `.claude/`, `.ai/`, `.githooks/`, `CLAUDE.md`. Сторонние навыки сохраняют свои лицензии (см. каталоги `.ai/skills/*` и `.claude/skills/*`).
