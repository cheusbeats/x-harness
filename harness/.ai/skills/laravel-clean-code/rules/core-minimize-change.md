---
id: core-minimize-change
title: Minimize Change Surface
category: core-principles
priority: critical
tags: [diff, focus, scope, minimal-change]
related: [core-stay-in-scope, core-respect-existing, core-refactoring]
---

# Minimize Change Surface

Make the smallest coherent change that fully solves the requested problem. Do not modify unrelated code. Do not perform opportunistic refactoring unless it is required for the requested change. Keep diffs focused. A bug fix should look like a bug fix. A small feature should produce a small focused change.

## Bad Example

```php
// ❌ Task: "fix the typo in the email template"
// PR changes: 47 files, renames a model, swaps service container bindings

// Original (broken subject line)
'subject' => 'Welcom to our platform',

// Changed subject (correct) ✅
// But also changed:
// - User model: renamed $name to $fullName (140 call sites)
// - OrderController: extracted to OrderService (no other controller changed)
// - composer.json: added league/csv "for future use"
// - routes/web.php: reordered 12 routes
// - 3 unrelated tests updated to match renames

// Problems:
// 1. Diff is un-reviewable
// 2. Reverts are hard
// 3. Hidden changes (composer) can break prod
// 4. Reviewer must verify unrelated changes
// 5. Conflicts with main guaranteed
```

## Good Example

```php
// ✅ Same task: 1-line fix, 1 file

// resources/views/emails/welcome.blade.php
- 'Welcom to our platform',
+ 'Welcome to our platform',

// Benefits:
// 1. Trivially reviewable
// 2. Trivially revertable
// 3. No risk to unrelated code
// 4. Clearly scoped
// 5. Mergeable in seconds
```

## Why

1. **Reviewability**: small diffs get reviewed; big diffs get rubber-stamped.
2. **Revertability**: one-line fix is easy to revert, 47-file change is not.
3. **Blame**: small diffs keep `git blame` clean.
4. **Conflict avoidance**: less code touched = fewer merges.
5. **Risk**: small diffs have less chance of breaking something unrelated.
6. **Signal**: focused diff communicates "I only did the task."
7. **Velocity**: small changes ship faster.

## When to Apply

- Every code change.
- Every PR.
- Every commit.
- Every "while I'm in here" thought.

## When NOT to Apply

When the unrelated change is required for the current task:

```php
// Task: "add new column to users table"
// Required: migration (additive) + model fillable + FormRequest rule + test
// This is NOT scope creep — these are all part of the same feature
```

The line is: "is this change **required** for the task?" If yes, include it. If no, separate it.
