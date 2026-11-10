---
id: core-refactoring
title: Refactor Only When Required
category: core-principles
priority: critical
tags: [refactoring, scope, minimal-change]
related: [core-minimize-change, core-respect-existing, core-stay-in-scope]
---

# Refactor Only When Required

Refactor when necessary to safely implement the current requirement. Do not refactor merely because another design appears cleaner. Prefer the current working architecture + small necessary modification over a new architecture + rewritten implementation — unless the existing architecture genuinely prevents a correct solution.

## Bad Example

```php
// ❌ Task: "Fix a bug in OrderController::store"
// Author's plan: rewrite to OrderService + Repository + DTO + Event

// Existing (working) controller:
final class OrderController extends Controller
{
    public function store(StoreOrderRequest $request): RedirectResponse
    {
        $order = Order::create($request->validated());
        Mail::to($order->customer)->send(new OrderConfirmation($order));

        return redirect()->route('orders.show', $order);
    }
}

// Author's "fix":
// - Created OrderService
// - Created OrderRepositoryInterface + EloquentOrderRepository
// - Created CreateOrderAction
// - Created OrderCreated event + SendOrderEmail listener
// - Refactored controller to dispatch the action
// - Bug fix is now buried in 600 lines of new architecture

// Problems:
// 1. Bug fix = 1 line, but PR = 12 files
// 2. Existing pattern works for every other controller
// 3. "Cleaner" architecture is opinion, not requirement
// 4. Reviewer must evaluate the architecture, not the fix
// 5. Risk of breaking working code
```

## Good Example

```php
// ✅ Same task: fix the bug, keep the architecture
final class OrderController extends Controller
{
    public function store(StoreOrderRequest $request): RedirectResponse
    {
        $order = Order::create($request->validated());
        Mail::to($order->customer)->send(new OrderConfirmation($order)); // ← bug fix here

        return redirect()->route('orders.show', $order);
    }
}

// Benefits:
// 1. Bug fix = 1-2 lines
// 2. Same pattern as every other controller
// 3. Trivially reviewable
// 4. No risk of breaking working code
// 5. If the controller later needs a Service, do it for ALL controllers together
```

## When Refactoring IS Required

Refactor when the existing code **prevents a correct solution**:

```php
// ✅ Refactor: required to add the feature
// Task: "send a Slack notification when a high-value order is placed"
// Problem: OrderController::store is 200 lines, adding 10 more is too much
// Solution: extract the side effects to a listener (event-based)
// Result: refactor IS the feature work, not a side quest
```

## The Test

Before refactoring, ask:

1. Can I add the new feature with a small change to the existing code?
2. If not, is the existing code genuinely preventing the new feature?
3. Is the refactor limited to what the new feature requires?
4. Is the refactor shared by at least 3 places, not just one?

If 1 is "yes" — do not refactor. If 2 is "no" — do not refactor.

## Why

1. **Risk**: rewriting working code introduces bugs.
2. **Cost**: refactors are expensive and time-consuming.
3. **Review burden**: reviewers must verify the refactor, not just the task.
4. **Style wars**: "cleaner" is subjective and endless.
5. **YAGNI alignment**: don't redesign for hypothetical futures.
6. **Project consistency**: respect what the codebase already does.
7. **Velocity**: ship the fix, schedule the refactor.

## When to Apply

- When a bug fix PR grows to 20+ files.
- When "while I'm here" thoughts appear.
- When the author justifies changes with "this is cleaner".
- When the existing pattern works for every other controller/class in the project.

## When NOT to Apply

- When the task **requires** a structural change.
- When the existing code is genuinely wrong (security, correctness).
- When the refactor is small and obviously required.
- When a scheduled refactor is in the current sprint.
