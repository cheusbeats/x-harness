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

**DeepSeek Harness (DSH)** — плагинов из GitHub у DSH нет, хуки подключаются мостом на шаге 2.

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

### DSH: мост хуков

1. Узнай версию Host: `dsh --version`. Мост ставится **той же** версией.
2. Установи обвязку с мостом (профиль DSH — `web` или `desktop`, по умолчанию `web`):

```bash
bash /tmp/x-harness/install.sh --project . --clients dsh --dsh-hooks bridge --dsh-version "$(dsh --version)" --dsh-profile web
```

   Установщик выполнит `dsh plugin add @deepseek-ai/dsh-hooks-claude-code@<версия>` и создаст `.dsh/agent-hook.py`, `.dsh/hooks-bridge.json` и `.dsh/hooks-bridge.yml`.
3. Скопируй блок из `.dsh/hooks-bridge.yml` в `~/.dsh/profiles/<профиль>/cordis.patch.yml` и перезапусти профиль DSH. Без этого шага мост не загрузится.
4. Проверь (шаг 3 ниже). Мост DSH поддерживает часть событий (SessionStart, PreToolUse и др.); живой прогон в Host зависит от версии — проверяй отрицательный сценарий.

Альтернатива — сторонний `dsh-hooks-plugin`: `--dsh-hooks community` (тот же `.dsh/agent-hook.py`, конфиг `.dsh/hooks.json`).

### Шаг 3. Проверка

1. Перезапусти клиент, чтобы он перечитал хуки и навыки (Codex и ZCode попросят подтвердить доверие к хукам).
2. `bash /tmp/x-harness/bin/xh doctor` в проекте — что подключено; `bash /tmp/x-harness/verify.sh --project .` — сверка установленной копии с манифестом.
3. Отрицательный сценарий: создай ветку `hotfix/test` и попроси агента записать что-нибудь в `planning/ROADMAP.md`. Запись должна быть **заблокирована** с подсказкой `registry.sh`. Если прошла — хуки клиента не подключены.

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
