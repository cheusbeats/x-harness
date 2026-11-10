# planning/ — реестры планирования

Читать только когда меняешь правила планирования; на старте сессии достаточно `ACTIVE_PLANS.md`. Полные правила, схема статусов и таблица
правил принуждения E1–E19 — `.claude/reference/planning-registries.md`.

## Что где

| Путь | Что |
|---|---|
| `ROADMAP.md` + `roadmap/` | реестр RM — идеи на потом (запись только по слову владельца) |
| `ACTIVE_PLANS.md` + `plans/PLAN-N-*.md` | реестр PLAN — планы в работе; документы планов и справочники (`audit-rules.md`, `PRODUCTION_SCALING.md`…) |
| `PLANS.md` + `plans/closed/` | реестр PLAN — закрытые планы (тела дословно, служебные `_map.tsv`, `_order.txt`, `_preamble.md`) |
| `HOTFIXES.md` + `hotfixes/` | реестр HF — правки вне планов |

В корне `planning/` — только эти файлы и каталоги `plans/ roadmap/ hotfixes/` (E9).

## Как поддерживать

- Индексы (`ROADMAP.md`, `ACTIVE_PLANS.md`, `PLANS.md`, `HOTFIXES.md`) правит только `.claude/scripts/registry.sh` (`add`, `set-status`, `next-id`, `show`, `check`).
- **Новый план** → `PLAN-{N}-kebab.md` в `plans/` (N — `registry.sh next-id PLAN`), H1 с номером, затем `registry.sh add PLAN PLAN-N "название"`.
  Для N ≥ 145 первым идёт `## Резюме` ≤ 15 строк (цель, что меняем, решения, статус); размер плана 40 КБ — предупреждение, 80 КБ — блок
  (обход `<!-- size-waiver: причина -->` в первых 30 строках).
- **Правка без плана** (багфикс, вёрстка, конфиг, зависимость) → хотфикс: `registry.sh add HF auto "что и зачем"` + ветка `hotfix/*`.
- **Закрытие плана** — только после явного «план закрыт» и маркера `owner-ok close-plan`: текст записи → `plans/closed/PLAN-N.md`, затем
  `registry.sh set-status PLAN-N закрыт`.
- **Идея** → `RM-N` только по прямому слову владельца («добавь в роадмап»).
- Коммиты называют `PLAN-N` (или `HF-N`); закрытые записи не переписываем. Сверка — `.claude/hooks/plans-drift.sh`.

План-шаблон: `# PLAN-N — название` · строка «Статус / ветка / дата» · `## Резюме` · остальное.
