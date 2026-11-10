---
id: core-priority-order
title: Priority Order of Principles
category: core-principles
priority: critical
tags: [priority, conflict, decision-making, principles]
related: [core-kiss, core-yagni, core-arch-decision-test]
---

# Priority Order of Principles

When engineering principles conflict, use this strict priority order. Correctness wins over elegance. Explicit requirements win over internal preferences. Existing project conventions win over abstract ideals.

## The Order

1. **Correctness** — the code must work for real, current requirements.
2. **Explicit requirements** — what the user / ticket / spec actually asks for.
3. **Existing project architecture and conventions** — match the codebase.
4. **KISS** — simplest correct solution.
5. **YAGNI** — no speculative features.
6. **Readability and maintainability** — boring, clear code.
7. **SOLID and other architectural principles** — only when they reduce complexity.

## Bad Example

```php
// ❌ SOLID purity over correctness
interface OrderProcessorInterface
{
    public function process(Order $order): void;
}

abstract class AbstractOrderProcessor implements OrderProcessorInterface
{
    public function process(Order $order): void
    {
        $this->validate($order);
        $this->calculate($order);
        $this->persist($order);
    }

    abstract protected function validate(Order $order): void;
    abstract protected function calculate(Order $order): void;
    abstract protected function persist(Order $order): void;
}

class StandardOrderProcessor extends AbstractOrderProcessor { /* ... */ }

// Problems:
// 1. Requirement was "send confirmation email after order" — only one processor
// 2. Hierarchy invented for theoretical future variants
// 3. Single concrete implementation behind 4 abstractions
```

## Good Example

```php
// ✅ Correctness + requirements + simplicity
final class OrderController extends Controller
{
    public function store(StoreOrderRequest $request): RedirectResponse
    {
        $order = Order::create($request->validated());
        Mail::to($order->customer)->send(new OrderConfirmation($order));

        return redirect()->route('orders.show', $order);
    }
}

// Benefits:
// 1. Solves the actual requirement (create order + send email)
// 2. Matches Laravel conventions (controller + FormRequest + Mail)
// 3. No premature abstraction
// 4. Easy to read, hard to misuse
```

## Why

1. **Correctness first**: shipping working code beats shipping "clean" code that doesn't run.
2. **Explicit requirements**: don't invent what was not asked.
3. **Consistency**: matching the codebase reduces cognitive load for the team.
4. **Predictable outcomes**: a fixed priority order produces consistent decisions across the team.
5. **Avoids over-engineering**: SOLID at the bottom means it never overrides simplicity.
6. **Faster reviews**: everyone knows which principle wins.
7. **Pragmatic engineering**: principles serve the code, not the other way around.

## When to Apply

- Every time two principles seem to pull in different directions.
- During design discussions ("should we add a Service class?").
- During code review when an author justifies a change with "but it's SOLID".
- When the user is undecided between two approaches.

## Quick Conflict Resolver

| Conflict | Winner |
|----------|--------|
| SOLID ideal vs simpler concrete code | Simpler concrete code (until 2nd use case) |
| New abstraction vs existing pattern in repo | Existing pattern in repo |
| Testability via interface vs direct constructor | Direct constructor (until mock needed) |
| Performance vs readability | Readability (until profile proves otherwise) |
| Future flexibility vs current simplicity | Current simplicity (YAGNI) |
