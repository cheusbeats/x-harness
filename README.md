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

## Установка плагина

Плагин даёт скиллы и событийные хуки клиента. Саму обвязку в проект ставит `install.sh` (см. ниже) — без неё хуки плагина ничего не делают.

| Клиент | Команда |
|---|---|
| Claude Code | `/plugin marketplace add cheusbeats/x-harness`, затем `/plugin install x-harness@x-harness` (хуки проекта и так нативные; плагин даёт скиллы) |
| Codex | `codex plugin marketplace add cheusbeats/x-harness && codex plugin add x-harness@x-harness` |
| ZCode | `/plugin marketplace add cheusbeats/x-harness`, затем `/plugin install x-harness@x-harness` |
| Kimi Code | Plugins → установка из GitHub: `cheusbeats/x-harness` |
| OpenCode | `~/.config/opencode/opencode.json`: `{"plugin": ["x-harness@git+https://github.com/cheusbeats/x-harness.git"]}` |
| DSH | `install.sh --clients dsh --dsh-hooks bridge --dsh-version <версия Host>` — мост вызывает `.dsh/agent-hook.py` |

Двойного прогона нет. Под Claude Code плагинный хук пропускается: проектный `.claude/settings.json` уже работает нативно. Под Codex он пропускается, если в проекте есть `.codex/hooks.json`.

## Установка скилла

```bash
npx skills add cheusbeats/x-harness --skill x-harness
```

После этого скажи агенту: «Примени x-harness и установи обвязку в текущий проект». Копия скилла без `.git` разворачивает обвязку так:

```bash
bash <каталог-скилла>/scripts/install-from-source --project /path/to/project --clients auto --skills project
```

Скрипт получает Git checkout `main` во временный каталог и запускает штатный `install.sh`. Для одного планирования добавь `--profile planning`.

## Быстрый старт

```bash
# 1) поставить обвязку в проект (snapshot = payload как поставляется)
./install.sh --project /path/to/project --clients auto --skills auto

# 2) проверить, что установленная копия совпадает с манифестом
./verify.sh --project /path/to/project --tests

# 3) что подключено в текущем репозитории
bin/xh doctor
```

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
