---
id: core-final-check
title: Final Engineering Check
category: core-principles
priority: critical
tags: [checklist, review, done, ship]
related: [core-minimize-change, core-stay-in-scope, core-tests]
---

# Final Engineering Check

Before considering a coding task complete, verify a fixed checklist. If any item fails, fix it before declaring done. The goal is **defensible completion** — the change is correct, focused, simple, and reversible.

## The Checklist

Run this before marking the task as done:

- [ ] The requested behavior is implemented.
- [ ] The implementation is correct (it works for the real requirement, not just happy path).
- [ ] Existing behavior outside the task was not intentionally changed.
- [ ] The solution is no more complex than necessary.
- [ ] No speculative functionality was added.
- [ ] No unnecessary abstraction was introduced.
- [ ] Existing project conventions were followed.
- [ ] The change surface is focused.
- [ ] New dependencies are justified.
- [ ] Relevant tests pass / new tests were added.
- [ ] `vendor/bin/pint --dirty` reports no issues (when PHP files were changed).
- [ ] Any remaining uncertainty is reported explicitly.

If **a simpler solution satisfies all requirements equally well, prefer the simpler solution**.

## Bad Example

```php
// ❌ "Done" without the check
// - Implemented feature: yes
// - Existing tests: still pass
// - But: also refactored 5 unrelated controllers "while I was here"
// - But: added a new package for "future use"
// - But: introduced a Service class no other controller uses
// - But: skipped pint
// - Author: "done, ready for review"
// Reviewer: spends 2 hours figuring out what's actually new
```

## Good Example

```php
// ✅ "Done" with the check
// - Implemented feature: order confirmation email ✅
// - Tests: feature test added, all tests pass ✅
// - Existing controllers: untouched ✅
// - New abstraction: none (uses Mail::send like other controllers) ✅
// - New package: none ✅
// - Pint: clean ✅
// - Composer audit: clean ✅
// - Unrelated discoveries: filed 2 follow-up issues, did not fix ✅
// Reviewer: 5-minute review, clean merge
```

## How to Apply

1. **Self-review before "ready for review"**: run the checklist on your own diff.
2. **Be honest about uncertainty**: "I'm not sure if this breaks X" is acceptable; "I'm sure" without checking is not.
3. **List known limitations**: "this doesn't handle timezone DST yet" is fine, just say it.
4. **Verify, don't assume**: "tests pass" means you ran them, not "I think they would".

## Why

1. **Self-review catches 80% of review comments**: cheaper to fix before review.
2. **Checklist prevents the same mistakes**: repeatable process beats memory.
3. **Reviewer trust**: a clean self-review earns faster approvals.
4. **Ship with confidence**: the checklist is the minimum bar.
5. **Defensible completion**: anyone can read the checklist and see "yes, this is done".
6. **Prevents scope creep**: explicitly calls out "did I change unrelated things?".
7. **Tests + Pint + Audit**: the boring but real safety net.

## When to Apply

- Before saying "done" or "ready for review".
- Before opening a PR.
- Before merging your own PR.
- Before considering a task complete in any tracker.

## The Simplest-Solution Test

If two implementations both meet requirements:

- [ ] Choose the one with fewer files.
- [ ] Choose the one with fewer lines.
- [ ] Choose the one with fewer abstractions.
- [ ] Choose the one that matches the rest of the codebase.

If still tied: ship the simpler one. You can always add complexity later.
