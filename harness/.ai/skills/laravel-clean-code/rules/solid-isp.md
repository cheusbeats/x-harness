---
id: solid-isp
title: Interface Segregation Principle (ISP)
category: solid-principles
priority: critical
tags: [solid, isp, interface, segregation]
related: [solid-dip, core-premature-abstraction, solid-ocp]
---

# Interface Segregation Principle (ISP)

Interfaces should expose only what consumers actually require. Do not add speculative methods. Do not create interfaces solely because abstractions are considered architecturally desirable. Many small, client-specific interfaces are better than one large, general-purpose one. Prefer composition of small interfaces over a fat one.

## Bad Example

```php
// ❌ Fat interface forces all implementers to support everything
interface Worker
{
    public function work(): void;
    public function eat(): void;
    public function sleep(): void;
    public function getSalary(): float;
    public function attendMeeting(): void;
    public function writeCode(): void;
    public function design(): void;
    public function test(): void;
}

final class HumanWorker implements Worker
{
    public function work() { /* ... */ }
    public function eat() { /* ... */ }
    public function sleep() { /* ... */ }
    public function getSalary(): float { return 5000.0; }
    public function attendMeeting() { /* ... */ }
    public function writeCode() { /* ... */ }
    public function design() { /* ... */ }
    public function test() { /* ... */ }
}

final class RobotWorker implements Worker
{
    public function work() { /* ... */ }
    public function eat() { throw new \LogicException('Robots do not eat'); }
    public function sleep() { throw new \LogicException('Robots do not sleep'); }
    public function getSalary(): float { throw new \LogicException('Robots are not paid'); }
    public function attendMeeting() { throw new \LogicException('Robots do not attend'); }
    public function writeCode() { /* ... */ }
    public function design() { throw new \LogicException('Robots do not design'); }
    public function test() { /* ... */ }
}

// Problems:
// 1. RobotWorker has 5 "impossible" methods
// 2. Every new worker type must implement all 8 methods
// 3. Fat interface, fat implementations
// 4. The interface lies about what all workers can do
```

## Good Example

```php
// ✅ Small, focused interfaces
interface Workable
{
    public function work(): void;
}

interface Codable
{
    public function writeCode(): void;
    public function test(): void;
}

interface Feedable
{
    public function eat(): void;
}

interface Payable
{
    public function getSalary(): float;
}

final class HumanWorker implements Workable, Codable, Feedable, Payable
{
    public function work() { /* ... */ }
    public function writeCode() { /* ... */ }
    public function test() { /* ... */ }
    public function eat() { /* ... */ }
    public function getSalary(): float { return 5000.0; }
}

final class RobotWorker implements Workable, Codable
{
    public function work() { /* ... */ }
    public function writeCode() { /* ... */ }
    public function test() { /* ... */ }
}

// Caller asks only for what it needs:
final class AssignTaskAction
{
    public function execute(Workable $worker): void
    {
        $worker->work();
    }
}

// Benefits:
// 1. Each implementer declares only what it actually does
// 2. No "impossible" methods
// 3. Easy to add a new worker type
// 4. Callers depend on the smallest contract they need
// 5. New capability = new interface, not a fat one
```

## When to Apply

- An interface has 5+ methods and 2+ implementers only use a subset.
- An implementer has empty methods or throws "not implemented" exceptions.
- Two clients of the same interface need different subsets.
- A new requirement forces changes to an interface used by stable code.

## When NOT to Apply (Pragmatic)

```php
// ❌ ISP gone wrong: 2-method interface for a single concrete class
interface UserFinder
{
    public function find(int $id): ?User;
}

final class EloquentUserFinder implements UserFinder { /* ... */ }

// ✅ Just use the Eloquent model directly
User::find($id);
```

ISP is for **multiple clients** with **different needs**. A single-implementation interface is just ceremony.

## Laravel Examples

```php
// ✅ Laravel's contracts are mostly ISP-friendly
// Illuminate\Contracts\Cache\Repository — only cache operations
// Illuminate\Contracts\Mail\Mailer — only mail operations
// Illuminate\Contracts\Queue\Factory — only queue operations

// ❌ Hypothetical fat contract
interface FullTextSearcher
{
    public function search(string $q): array;
    public function index(array $docs): void;
    public function reindex(): void;
    public function delete(int $id): void;
    public function suggest(string $q): array;
    public function highlight(int $id): string;
}
// → split: Searcher, Indexer, Suggester
```

## The "No-Op" Test

If an implementer has empty methods, throws "not supported", or returns null without doing anything, the interface is too fat.

```php
// ❌ Implementation signs it doesn't actually support
public function attendMeeting(): void
{
    // robots don't attend meetings
}
```

## Why

1. **Smaller contracts**: callers depend on less.
2. **No fake methods**: implementers don't lie about capabilities.
3. **Easier mocking**: tests mock only what they need.
4. **Composability**: small interfaces compose into larger behaviors.
5. **Evolution**: add a capability = new interface, no breaking change.
6. **YAGNI alignment**: don't define methods no consumer needs.
7. **Laravel-idiomatic**: most Laravel contracts follow ISP.
