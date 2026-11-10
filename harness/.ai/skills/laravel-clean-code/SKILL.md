---
name: laravel-clean-code
description: Practical clean-code rules for Laravel 13 and Livewire 4. Use when implementing, refactoring, reviewing, or debugging Laravel, PHP, Livewire, or Blade code. Covers KISS, YAGNI, DRY, pragmatic SOLID, minimal changes, Laravel conventions, Livewire component rules, and no @php in Blade.
license: MIT
metadata:
  author: cheusbeats
  version: 1.3.0
  framework: Laravel 13 / Livewire 4
  language: PHP 8.4
  tags:
    - laravel
    - livewire
    - php
    - clean-code
    - best-practices
  compatible_agents:
    - Claude Code
    - Cursor
    - Codex
    - Windsurf
    - GitHub Copilot
    - Trae
---

# Laravel Clean Code (Laravel 13 + Livewire 4)

Mandatory engineering principles for all Laravel and Livewire work: implementation, refactoring, debugging, code review, architecture, maintenance.

Goals: correctness, simplicity, minimal change surface, consistency with the existing codebase, mandatory no-`@php` in Blade.

## When to Apply

Activate when:

- writing or modifying any PHP / Laravel / Livewire code;
- reviewing a pull request;
- refactoring an existing class, controller, job, migration, or Livewire component;
- designing a new feature, endpoint, component, or job;
- choosing between architecture alternatives (Service vs Action, Repository vs query, etc.);
- debugging behavior that became complex;
- writing or modifying a Blade view.

## Priority Order (When Principles Conflict)

1. Correctness
2. Explicit requirements
3. Existing project architecture and conventions
4. KISS
5. YAGNI
6. Readability and maintainability
7. SOLID and other architectural principles

Never trade correctness for theoretical purity. Never trade simplicity for architectural elegance that the codebase does not need.

## Rule Categories

| # | Category | Priority | Prefix | Count |
|---|----------|----------|--------|-------|
| 1 | Core Principles | CRITICAL | `core-` | 17 |
| 2 | SOLID Principles (Pragmatic) | CRITICAL | `solid-` | 5 |
| 3 | Laravel Architecture | CRITICAL | `laravel-` | 14 |
| 4 | Livewire Architecture | CRITICAL | `livewire-` | 8 |

**Total: 44 rules across 4 categories.**

## How to Use Rule Files

Load only the rule files relevant to the current task from `rules/<rule-id>.md`:

1. Identify the smallest set of applicable rule IDs.
2. For Blade files, check `laravel-blade-no-php` first.
3. For Eloquent or Livewire data access, check the N+1 and query rules.
4. Match the installed Laravel, Livewire, and package versions before applying version-specific examples.
5. Keep findings in the output format below and avoid unrelated refactoring.

## Core Principles (CRITICAL)

| Rule | Summary |
|------|---------|
| `core-priority-order` | Priority order when principles conflict |
| `core-kiss` | Keep it simple — simplest correct solution |
| `core-yagni` | You aren't gonna need it — no speculative features |
| `core-boring-code` | Prefer boring, predictable code over clever code |
| `core-premature-abstraction` | Wait for evidence before abstracting |
| `core-dry` | Single source of knowledge, but do not over-DRY |
| `core-respect-existing` | Follow existing project conventions |
| `core-minimize-change` | Smallest coherent change that fixes the issue |
| `core-no-speculative-compat` | No compatibility shims without consumers |
| `core-stay-in-scope` | Do not solve unrelated problems |
| `core-dependencies` | Avoid new dependencies when stdlib is enough |
| `core-arch-decision-test` | 5 questions before adding a new construct |
| `core-refactoring` | Refactor only when required by current task |
| `core-error-handling` | Handle real errors, fail fast, no silent swallow |
| `core-comments` | Comments explain why, not what |
| `core-tests` | Tests protect behavior changed by the task |
| `core-final-check` | Final checklist before considering task complete |

## SOLID Principles (CRITICAL, Pragmatic)

| Rule | Summary |
|------|---------|
| `solid-srp` | Single responsibility — one reason to change |
| `solid-ocp` | Open for extension, closed for modification |
| `solid-lsp` | Subtypes must honor base type contract |
| `solid-isp` | Small, client-specific interfaces |
| `solid-dip` | Depend on abstractions, not concretions |

## Laravel Architecture (CRITICAL)

| Rule | Summary |
|------|---------|
| `laravel-controller-thin` | Controllers dispatch, do not contain logic |
| `laravel-form-request` | Validation lives in FormRequest, not controller |
| `laravel-resource` | API output goes through API Resources |
| `laravel-eloquent-n-plus-one` | Avoid N+1 with eager loading |
| `laravel-eloquent-scopes` | Reuse query logic via local scopes |
| `laravel-jobs-queue` | Long work goes to jobs on a queue |
| `laravel-events` | Decouple side effects with events/listeners |
| `laravel-routes` | Routes are thin, named, and grouped by middleware |
| `laravel-service-container` | Bind only what you actually swap |
| `laravel-policies` | Authorization in Policy classes, not controllers |
| `laravel-testing` | Feature tests for behavior, unit for pure logic |
| `laravel-config-env` | Use config(), never env() outside config/ |
| `laravel-migrations` | Migrations are additive, never destructive on existing data |
| `laravel-blade-no-php` | **MANDATORY: no `@php` directives in Blade** |

## Livewire Architecture (CRITICAL)

| Rule | Summary |
|------|---------|
| `livewire-component-single-purpose` | One component, one concern (no "And" components) |
| `livewire-state-minimal` | Minimal public state, no derived data — use `#[Computed]` |
| `livewire-form-objects` | Use Livewire v4 Form objects for forms |
| `livewire-queries-with-eloquent` | Use Eloquent with eager loading, no N+1 |
| `livewire-events-communication` | Components communicate via `dispatch` / `#[On]` |
| `livewire-testing` | Test components with `Livewire::test()` and Pest |
| `livewire-no-direct-queries` | No DB queries in Blade views |
| `livewire-lifecycle-hooks` | Use mount/updated/render/#[Computed] correctly |

## Output Format

When auditing or reviewing code, output findings in this format:

```
file:line - [rule-id] Description of issue
```

Examples:

```
app/Http/Controllers/OrderController.php:34 - [laravel-controller-thin] Business logic in controller — extract to OrderService or Action
app/Http/Controllers/OrderController.php:58 - [laravel-eloquent-n-plus-one] `$orders` loaded without `->with('items')`, N+1 on line 60
app/Jobs/ProcessOrder.php:12 - [core-yagni] Interface for single concrete job class
app/Http/Controllers/Api/UserController.php:22 - [laravel-form-request] Inline validation — move to StoreUserRequest
resources/views/orders/show.blade.php:14 - [laravel-blade-no-php] @php directive in Blade — move logic to model accessor
app/Livewire/OrderManager.php:8 - [livewire-component-single-purpose] Component has 13 properties for 3 concerns — split
app/Livewire/OrderList.php:23 - [livewire-state-minimal] $totalRevenue stored as public property — use #[Computed]
app/Livewire/CartPage.php:34 - [livewire-queries-with-eloquent] N+1: missing ->with('items') on $orders
resources/views/livewire/cart.blade.php:12 - [livewire-no-direct-queries] Model::query() in Blade — use #[Computed]
```

## References

- **Clean Code** by Robert C. Martin
- **Refactoring** by Martin Fowler
- **The Pragmatic Programmer** by Hunt & Thomas
- **Laravel 13 docs** — https://laravel.com/docs/13.x
- **Livewire 4 docs** — https://livewire.laravel.com/docs
- **Domain-Driven Design** by Eric Evans (use selectively)
- AsyrafHussin/agent-skills — base file structure inspiration
