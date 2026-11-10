# Local MCP workers (вынесено из CLAUDE.md, PLAN-145)

Читать, когда в сессии доступен MCP-сервер `local-workers`.

### Local MCP workers — cheaper than a subagent spawn, narrower capability

The `local-workers` MCP server (`mcp__local-workers__*`) runs small local models as junior
implementers. They are not a replacement for the `.claude/agents/` roster above — they're a
cheaper rung below it for work small enough that spinning up a full subagent is overkill.

**Names of the individual workers are deliberately NOT pinned here.** The line-up changes; a
doc that hardcodes tool names goes stale silently and then tells you to call something that
does not exist. Read whatever the server currently exposes and route by ROLE, not by name.
No `local-workers` tools available (server down, not configured)? Then this rung simply does
not exist for that session — use the agent roster above, and do not mention the workers.

**Claude does the thinking, always:** understands the request, reads the architecture, decides
the approach, draws the change boundary, decomposes, verifies the diff. The worker never receives
the user's original request — only a prepared, self-contained subtask.

**Eligible for a worker:** one goal, 1–3 files, existing architecture already decided, a concrete
expected result, a targeted verification command, completable in a single independent run.
Concrete: local bug fix; a method/class against an already-defined contract; editing one
service/repository/action/job; a validation rule; adding an enum/mapping/DTO/value object; wiring
an existing mechanism into one call site; writing unit/feature/regression tests; fixing a test
plus its direct cause; a small CRUD/API/UI change with the architecture already settled; a
mechanical edit across explicitly-listed places; migrating code onto an already-chosen API.

**Never eligible:** architecture design or choosing between approaches, whole-project
understanding, repo-wide or large cross-cutting refactors, product-behavior decisions, unclear
requirements, backward-compatibility calls, infra/deployment changes without an exact plan, mass
schema changes, unattended work across dozens of files, "study the project and implement X",
"figure out why it's broken" without prior localization. Oversized asks get decomposed by Claude
first — never handed to a worker whole.

**Worker context is minimal, prepared, fresh every call:** the concrete goal, facts it must not
guess, explicit relevant paths, expected behavior, scope limits, a verification command. Never:
the full conversation, project history, `CLAUDE.md`/`AGENTS.md` or "the whole repo for context",
neighboring files it doesn't need. Don't tell it to read `CLAUDE.md`/`AGENTS.md` — Claude extracts
the relevant constraints and puts only those in the task text.

**Worker-side exploration stays local:** target file, immediate callers/dependencies, an existing
analog or test, a small directly-related set. Needing broad system exploration or many unknown
dependencies means the task exceeded the worker's envelope — it stops, and Claude either clarifies
the architecture or decomposes further.

**Task shape, one bounded step per call, never several independent asks in one call:** exact
change, expected behavior, allowed/assumed files, what must not change, existing behavior to
preserve, targeted test, an explicit STOP condition for architectural ambiguity.

**On a failing test:** exact actual/expected → immediate producer → at most one level of
helper/dependency → one minimal fix → rerun the targeted test. Max two diagnose/fix cycles per
failing test, then STOP with a concrete blocker. Forbidden: weakening exact tests/fixtures without
proof, speculative refactors, reading large neighboring parts of the project "to understand",
guessing neighboring-module behavior that could be checked directly instead.

**`STATUS: success` from a worker proves nothing.** After every call Claude independently checks
`git status`, the actual diff, absence of stray changes, acceptance criteria, targeted tests, and
static checks if warranted — this is the same "verify before accepting" discipline as any other
subagent, run through `quality-gate.sh` where applicable. Workers never commit/push/merge unless a
separate project policy explicitly says so.

**Routing by role, not by name.** Default to the LIGHTEST worker the server exposes for any
eligible bounded task. Reach for a heavier one only when the task is still bounded but needs
noticeably more local reasoning — reconciling several dependencies, carefully deriving behavior
from existing code, several related edge cases. A heavier worker is not a fallback for routine
mechanical work just because it is available; if a task is too much for the light one, shrink
and sharpen it first rather than trading up.

**Sequential only.** Never run two local workers in parallel; never start the second before the
first call fully completes.

If a short, unambiguous subtask can't be written without dragging in large project context, the
task goes to Claude directly or gets decomposed further — not to a local worker.

