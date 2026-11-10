---
id: core-respect-existing
title: Respect Existing Architecture
category: core-principles
priority: critical
tags: [convention, consistency, project-patterns]
related: [core-minimize-change, core-arch-decision-test, core-refactoring]
---

# Respect Existing Architecture

Before introducing a new pattern, inspect how the repository already solves the same problem. Prefer consistency with the existing codebase. Do not introduce a second architectural approach for the same problem without a concrete reason. Reuse existing conventions, structure, naming, patterns, infrastructure, and utilities.

## Bad Example

```php
// ❌ Project uses Eloquent directly in controllers, no Service layer
// New developer adds Service + Interface + Repository for ONE endpoint

namespace App\Services\Orders;

use App\Repositories\Contracts\OrderRepositoryInterface;

final class OrderCreationService
{
    public function __construct(private readonly OrderRepositoryInterface $orders) {}

    public function create(array $data): Order
    {
        return $this->orders->create($data);
    }
}

// Problems:
// 1. Every other endpoint in the project calls Model::create directly
// 2. New pattern: now reviewers must learn two ways to do the same thing
// 3. The 5 existing controllers didn't need this
// 4. The author justified it with "best practice", not project need
```

## Good Example

```php
// ✅ Match the project's existing style
final class OrderController extends Controller
{
    public function store(StoreOrderRequest $request): RedirectResponse
    {
        $order = Order::create($request->validated());
        // ... same pattern as every other controller in the project

        return redirect()->route('orders.show', $order);
    }
}

// Benefits:
// 1. Reads like every other controller
// 2. No new files
// 3. Reviewer sees a familiar pattern
// 4. Easy to delete, easy to refactor later as a group

// If later 3+ controllers need shared logic, extract once — for all of them.
```

## How to Check

Before adding a new pattern, ask:

1. Does the project use Eloquent directly in controllers, or through repositories?
2. Does the project use Service classes, Actions, or plain controller methods?
3. Does the project use FormRequest or inline `$request->validate()`?
4. Does the project use API Resources or return models/arrays?
5. Does the project bind interfaces in service providers?

Use `Grep` or `Read` on the project before introducing a new convention.

## Why

1. **Cognitive load**: developers should not have to know two ways to do the same thing.
2. **Onboarding speed**: familiar code is faster to read.
3. **Review speed**: reviewers don't have to evaluate "is this pattern OK in this project".
4. **Refactor consistency**: when something changes, the change applies everywhere.
5. **Less discussion**: "match the codebase" is a fast, uncontroversial decision rule.
6. **Prevents architecture astronaut**: every new pattern needs justification, not just adoption.
7. **Reversible later**: if the project later adopts the new pattern, you can migrate systematically.

## When to Apply

- Before creating a new file structure (Service, Action, Repository, etc.).
- Before introducing a config file or service provider binding.
- Before adding middleware, events, listeners, observers.
- Before choosing a validation strategy.
- Before choosing a test style (Pest vs PHPUnit, datasets, etc.).

## When NOT to Apply

When the existing pattern is genuinely wrong:

```php
// Existing: every controller queries DB directly + has no validation
// New: introduces FormRequest for ONE new endpoint
// Decision: introduce FormRequest for THIS endpoint, file a follow-up to migrate others
```

Respect existing, but also fix the obviously broken. Justify the deviation.
