---
id: core-comments
title: Comments Explain Why
category: core-principles
priority: critical
tags: [comments, documentation, why]
related: [core-boring-code, core-kiss, core-final-check]
---

# Comments Explain Why

Prefer code that explains itself through clear structure and naming. Comments should explain **why**, not what. Do not write comments that merely repeat what the code already says. Reserve comments for non-obvious decisions, constraints, important invariants, and explanations of intent.

## Bad Example

```php
// ❌ Comments that restate the code
// Increment counter by 1
$counter++;

// Get user by id
$user = User::find($id);

// Check if user is admin
if ($user->is_admin) {
    // Do admin stuff
    $this->grantAccess($user);
}

// Loop through orders
foreach ($orders as $order) {
    // Process each order
    $this->process($order);
}

// Problems:
// 1. Every comment is a restatement
// 2. The code is already clear
// 3. Comments add noise, not signal
// 4. Maintenance burden — comments get stale
```

## Good Example

```php
// ✅ Comments that explain why
// Voting age is 18 by federal law; do not lower without legal review.
final const VOTING_AGE = 18;

// We use a raw query here because Eloquent's belongsToMany
// would issue 3 queries for this specific join — verified via Telescope.
$rows = DB::select('SELECT ...');

// Discounts are calculated pre-tax because accounting requires
// tax breakdown to match the invoice line items.
$discount = $this->calculateDiscountPreTax($order);

// Mocked in tests because real Mail::send would hit SES quota.
Mail::fake();

// This is intentionally synchronous: the order page must reflect
// the email send state immediately to comply with the audit trail.
Mail::send(...);

// Benefits:
// 1. Each comment adds information the code cannot express
// 2. Future maintainers know the constraint
// 3. Comments document decisions, not mechanics
// 4. No stale comments — they explain why, which doesn't drift
```

## When to Comment

- **Why** this approach, not the obvious one.
- **Constraints** that aren't visible in the code (legal, business, performance).
- **Important invariants** that must be preserved.
- **Workarounds** and why they are workarounds.
- **Surprising behavior** (mocked in tests, raw query for performance, etc.).
- **TODO with ticket** (not "fix this later" — `// TODO(ALTS-1234): ...`).

## When NOT to Comment

```php
// ❌ Self-evident
$total = $price * $qty; // multiply price by quantity

// ❌ Restating the function name
// Get all active users
public function getActiveUsers() { ... }

// ❌ Obvious from type
/** @var int */
$count = 0;

// ❌ "Magic" comments
// !!! IMPORTANT !!!
$this->doThing();

// ❌ Change log comments
// 2024-01-15: John changed this
// 2024-02-03: Mary fixed bug
// (use git, not comments)
```

## PHPDoc vs Comments

Use PHPDoc for public API surfaces only:

```php
// ✅ PHPDoc on a public method that callers will read
/**
 * Calculate order total including tax.
 *
 * Tax is applied to the discounted subtotal. Returns cents.
 */
public function total(): int

// ❌ PHPDoc on every private method
/** @var string */
private string $name = ''; // pointless
```

## Why

1. **Restated comments are noise**: they add reading time, not understanding.
2. **Stale comments are dangerous**: they lie when the code changes.
3. **Why comments age well**: the reason for a decision rarely changes.
4. **Code is the truth**: the code shows what; comments should show why.
5. **Maintenance cost**: every comment is a thing to keep in sync.
6. **Good naming replaces comments**: `$isEligibleForDiscount` > `$flag` + comment.
7. **Git replaces history**: don't put history in comments.

## When to Apply

- Every comment you write.
- During code review — flag comments that just restate the code.
- When tempted to write "this does X" — refactor to a named method instead.
