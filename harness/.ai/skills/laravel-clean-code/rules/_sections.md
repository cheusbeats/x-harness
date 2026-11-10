# Laravel Clean Code (Laravel + Livewire) — Rule Categories

Defines the organizational structure for core engineering rules, ordered by priority and impact. Laravel 13 + Livewire 4 specific.

## Category Overview

| Priority | Category | Impact | Rule Count | Prefix |
|----------|----------|--------|------------|--------|
| 1 | Core Principles | CRITICAL | 17 | `core-` |
| 2 | SOLID Principles | CRITICAL | 5 | `solid-` |
| 3 | Laravel Architecture | CRITICAL | 14 | `laravel-` |
| 4 | Livewire Architecture | CRITICAL | 8 | `livewire-` |

**Total: 44 rules.**

---

## 1. Core Principles (CRITICAL)

**Priority:** CRITICAL
**Impact:** Engineering fundamentals, applied to every change
**Prefix:** `core-`

Universal engineering principles adapted for Laravel 13 / Livewire 4 / PHP 8.4.

### Rules

#### Decision & Priority

- `core-priority-order` — Priority order when principles conflict
- `core-arch-decision-test` — 5 questions before adding a new construct

#### Simplicity & Scope

- `core-kiss` — Keep it simple, stupid
- `core-yagni` — You aren't gonna need it
- `core-boring-code` — Prefer boring, predictable code
- `core-premature-abstraction` — Wait for evidence before abstracting
- `core-dry` — Single source of knowledge, but not dogma
- `core-minimize-change` — Smallest coherent change
- `core-stay-in-scope` — Do not solve unrelated problems
- `core-refactoring` — Refactor only when required
- `core-no-speculative-compat` — No compatibility shims without consumers

#### Code Quality

- `core-error-handling` — Handle real errors, fail fast
- `core-comments` — Comments explain why, not what
- `core-tests` — Tests protect behavior changed by the task
- `core-dependencies` — Avoid new dependencies when possible
- `core-respect-existing` — Follow project conventions
- `core-final-check` — Final checklist before considering task complete

**Key Concepts:**

- Correctness first
- Simplicity over cleverness
- Minimal change surface
- Project consistency
- Boring code wins

**When to Apply:**

- Every code change
- Every review
- Every refactor
- Every new feature design

---

## 2. SOLID Principles (CRITICAL — Pragmatic)

**Priority:** CRITICAL
**Impact:** Reduces real coupling, not theoretical purity
**Prefix:** `solid-`

SOLID applied only when it actually reduces complexity in the Laravel context.

### Rules

- `solid-srp` — Single Responsibility Principle
- `solid-ocp` — Open/Closed Principle
- `solid-lsp` — Liskov Substitution Principle
- `solid-isp` — Interface Segregation Principle
- `solid-dip` — Dependency Inversion Principle

**When to Apply:**

- Designing a new class that has multiple obvious responsibilities
- Adding an extension point that already has 2+ implementations
- Refactoring a controller that does 5 things

**When NOT to Apply:**

- Adding an interface for a single implementation (YAGNI)
- Forcing DI when constructor injection of a concrete is fine
- Splitting a 30-line class into 5 SRP classes for the sake of SRP

---

## 3. Laravel Architecture (CRITICAL)

**Priority:** CRITICAL
**Impact:** Laravel-idiomatic code, performance, security, maintainability
**Prefix:** `laravel-`

Concrete Laravel 13 patterns. Every rule has a PHP 8.4 / Laravel 13 example. **Includes the mandatory `laravel-blade-no-php` rule.**

### Rules

#### Request Lifecycle

- `laravel-routes` — Thin, named, grouped routes
- `laravel-form-request` — Validation in FormRequest
- `laravel-policies` — Authorization in Policy classes
- `laravel-controller-thin` — Controllers dispatch, do not contain logic
- `laravel-resource` — API output via API Resources

#### Data Layer

- `laravel-eloquent-n-plus-one` — Avoid N+1 with eager loading
- `laravel-eloquent-scopes` — Reuse query logic via scopes
- `laravel-migrations` — Additive, safe migrations

#### Async & Side Effects

- `laravel-jobs-queue` — Long work on a queue
- `laravel-events` — Decouple side effects with events/listeners

#### Infrastructure

- `laravel-service-container` — Bind only what you swap
- `laravel-config-env` — config() in app code, env() only in config/
- `laravel-testing` — Feature tests for behavior, unit for pure logic

#### Views

- `laravel-blade-no-php` — **MANDATORY: no `@php` directives in Blade templates**

**When to Apply:**

- Every new controller / endpoint
- Every new Eloquent query
- Every new migration
- Every new background job
- Every config value
- Every Blade view

**Mandatory check:** For every Blade view, run `laravel-blade-no-php` first.

---

## 4. Livewire Architecture (CRITICAL)

**Priority:** CRITICAL
**Impact:** Livewire-idiomatic components, performance, maintainability
**Prefix:** `livewire-`

Concrete Livewire 4 patterns. Every rule has a Livewire 4 / PHP 8.4 example.

### Rules

- `livewire-component-single-purpose` — One component, one concern (no "And" components)
- `livewire-state-minimal` — Minimal public state, use `#[Computed]` for derived data
- `livewire-form-objects` — Use Livewire v4 Form objects for forms
- `livewire-queries-with-eloquent` — Use Eloquent with eager loading, no N+1
- `livewire-events-communication` — Components communicate via `dispatch` / `#[On]`
- `livewire-testing` — Test components with `Livewire::test()` and Pest
- `livewire-no-direct-queries` — No DB queries in Blade views
- `livewire-lifecycle-hooks` — Use mount / updated / render / `#[Computed]` correctly

**When to Apply:**

- Every new Livewire component
- Every modification of an existing component
- Every Blade view rendered by a Livewire component

---

## Rule Naming Convention

All rules follow:

```
{prefix}-{concept}
```

Examples:

- `core-kiss` — Core principle, KISS concept
- `solid-srp` — SOLID, Single Responsibility
- `laravel-form-request` — Laravel, FormRequest pattern
- `livewire-state-minimal` — Livewire, state minimal concept

## Priority Levels

- **CRITICAL** — Core engineering + Laravel + Livewire architecture. Violations significantly impact maintainability, security, performance, and team velocity.

## Impact Assessment

- **CRITICAL Impact** — Affects entire feature, security, performance, multiple developers.

## Usage Guidelines

1. **For Blade files**: run `laravel-blade-no-php` first (mandatory).
2. **For Livewire components**: run `livewire-component-single-purpose`, `livewire-state-minimal`, `livewire-form-objects`.
3. **For controllers**: run `laravel-controller-thin`, `laravel-form-request`, `laravel-policies`.
4. **For Eloquent**: run `laravel-eloquent-n-plus-one`, `laravel-eloquent-scopes`.
5. **For all changes**: run `core-final-check`.

## Cross-References

Rules often relate. The `related` field in frontmatter indicates rules commonly applied together.

## Evolution

This skill evolves as:

- New Laravel patterns emerge
- New Livewire features are added
- Team feedback is incorporated
- Laravel / Livewire versions change (currently Laravel 13 / Livewire 4)
