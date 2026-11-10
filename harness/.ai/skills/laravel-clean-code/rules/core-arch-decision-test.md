---
id: core-arch-decision-test
title: Architecture Decision Test
category: core-principles
priority: critical
tags: [architecture, decision, checklist, design]
related: [core-yagni, core-premature-abstraction, core-respect-existing, core-dependencies]
---

# Architecture Decision Test

Before introducing a new abstraction, interface, class, service, repository, factory, adapter, strategy, architectural layer, dependency, or configuration option, ask five questions. If the answers do not justify the new construct, do not add it.

## The 5 Questions

1. **Is it required by the current task?**
2. **Does a real current use case require it?**
3. **Does the repository already solve this problem another way?**
4. **Does this make the current implementation simpler?**
5. **Does it reduce more complexity than it introduces?**

If the answer to any of these is "no" — the construct is probably unjustified. Default to **no**.

## Bad Example

```php
// ❌ Adding a Service class to wrap one Eloquent call
final class UserService
{
    public function __construct(private readonly UserRepositoryInterface $users) {}

    public function findActive(int $id): ?User
    {
        return $this->users->findActive($id);
    }
}

// Applying the test:
// 1. Is it required? — No, controller could call User::query()->active()->find($id)
// 2. Real use case? — No, one caller
// 3. Repo already has this? — N/A; Laravel's Eloquent IS the data layer
// 4. Simpler? — No, 1 method = 3 files
// 5. Reduces complexity? — No, adds it
// → DO NOT ADD
```

## Good Example

```php
// ✅ Direct, simple, matches the codebase
final class UserController extends Controller
{
    public function show(int $id): View
    {
        $user = User::query()->active()->findOrFail($id);

        return view('users.show', compact('user'));
    }
}

// Adding a Service only when 3+ controllers need the same logic.
// Adding a Repository only when swapping the data source is a real need.
```

## Real-World Justified Additions

Sometimes the answer is "yes" to all 5:

```php
// ✅ Payment gateway abstraction — justified
interface PaymentGateway
{
    public function charge(Order $order): PaymentResult;
}
// 1. Required? Yes — multiple gateways
// 2. Real use case? Yes — Stripe + YooKassa in production
// 3. Project already has it? No
// 4. Simpler than inline? Yes — switch by config
// 5. Reduces complexity? Yes — controllers don't care about Stripe vs YooKassa
// → ADD

// ✅ Event/listener split — justified
// 1. Required? Yes — OrderPlaced event has 3+ side effects
// 2. Real use case? Yes — email, analytics, warehouse sync
// 3. Project already has it? Sometimes
// 4. Simpler than inline? Yes — each listener is testable in isolation
// 5. Reduces complexity? Yes — controller doesn't know about side effects
// → ADD
```

## Common "Justified" Excuses That Aren't

```php
// ❌ "For testability"
// Reality: User::factory()->create() is already a test double
// Reality: container swap to a Mock is also possible without interface

// ❌ "For future flexibility"
// Reality: YAGNI — future rarely looks like current

// ❌ "Best practice"
// Reality: Best practice is what the codebase does, not what blog posts say

// ❌ "SOLID"
// Reality: SOLID is the 7th priority, not the 1st

// ❌ "I've seen it in other projects"
// Reality: Their context is not your context
```

## Why

1. **Default to no**: most new constructs are unjustified.
2. **Forces justification**: a 5-question test makes you think.
3. **Prevents architecture astronaut**: every new file needs a reason.
4. **Project consistency**: respects existing patterns.
5. **Reversible**: adding is easier than removing.
6. **Saves time**: no time wasted on unused code.
7. **Honest engineering**: principles serve the project, not the ego.

## When to Apply

- Before adding any new file in `app/`.
- Before adding a new service provider binding.
- Before adding a new dependency.
- Before adding a new config key.
- Before adding a new trait, interface, or abstract class.
- Before suggesting a refactor that adds a layer.
