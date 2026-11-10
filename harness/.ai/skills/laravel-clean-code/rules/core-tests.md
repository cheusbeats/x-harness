---
id: core-tests
title: Tests Protect Changed Behavior
category: core-principles
priority: critical
tags: [testing, pest, phpunit, coverage]
related: [core-minimize-change, core-final-check, laravel-testing]
---

# Tests Protect Changed Behavior

Add or modify tests when they protect the behavior changed by the task. Focus tests on observable behavior and important edge cases. Do not create large speculative test frameworks for simple changes. Do not rewrite unrelated tests. A test must catch a real regression risk.

## Bad Example

```php
// ❌ Test for code that doesn't exist "for completeness"
test('order service handles 47 different edge cases', function () {
    // 200 lines of speculative tests for a feature that hasn't been built yet
});

// ❌ Test that tests the framework, not the code
test('laravel can find a user by id', function () {
    $user = User::factory()->create();
    $found = User::find($user->id);
    expect($found->id)->toBe($user->id);
    // This tests Eloquent, not your code
});

// ❌ Brittle test tied to implementation details
test('order controller calls Mail::send with exact class name', function () {
    Mail::shouldReceive('send')
        ->once()
        ->with(OrderConfirmation::class, Mockery::any());
    // Brittle: refactoring the Mailable breaks the test
});

// Problems:
// 1. Speculative tests for non-existent code
// 2. Tests the framework, not behavior
// 3. Brittle to refactoring
// 4. 200 lines of test for 5 lines of behavior
```

## Good Example

```php
// ✅ Pest test for the changed behavior
use App\Models\Order;
use App\Models\User;
use Illuminate\Support\Facades\Mail;
use App\Mail\OrderConfirmation;

it('sends a confirmation email when an order is created', function () {
    Mail::fake();

    $user = User::factory()->create();
    $this->actingAs($user)->post('/orders', [
        'product_id' => 1,
        'quantity' => 2,
    ])->assertRedirect();

    Mail::assertSent(OrderConfirmation::class, fn ($mail) =>
        $mail->hasTo($user->email)
    );
});

it('rejects an order with invalid quantity', function () {
    $this->actingAs(User::factory()->create())
        ->post('/orders', ['product_id' => 1, 'quantity' => 0])
        ->assertSessionHasErrors('quantity');
});

it('prevents guests from creating orders', function () {
    $this->post('/orders', ['product_id' => 1, 'quantity' => 1])
        ->assertRedirect('/login');
});

// Benefits:
// 1. Each test verifies one behavior
// 2. Tests the contract, not the implementation
// 3. Will catch the bug if OrderController::store breaks
// 4. Will not break if you refactor the Mailable
// 5. Pest reads like prose
```

## The Test Budget

Ask before writing each test:

1. What behavior am I protecting?
2. Is there a real regression risk if this test is missing?
3. Is this test testing my code or the framework?
4. Will this test still pass if I refactor the implementation?

If 1 or 2 is "none" — skip the test. If 3 is "the framework" — skip the test. If 4 is "no" — make the test more behavioral.

## When to Add Tests

- **Always**: when fixing a bug (regression test).
- **Always**: when adding a new public API (endpoint, job, listener).
- **Always**: when changing a business rule (price calc, eligibility).
- **Sometimes**: when adding a complex method with branches.
- **Rarely**: for trivial getters / data objects.
- **Never**: to "improve coverage" without a behavior to protect.

## When NOT to Add Tests

```php
// ❌ Don't test:
- Framework behavior (Eloquent, validation rules, routing)
- Trivial accessors ($user->name returns $user->name)
- Static analysis (PHPStan covers this)
- The test itself (tautological tests)

// ✅ Do test:
- Business rules
- Edge cases that matter
- Authorization
- Integration points (mail sent, event fired, job dispatched)
- The "thing that broke last time" (regression)
```

## Why

1. **Tests are code**: they need maintenance, refactoring, review.
2. **Brittle tests are worse than no tests**: they block refactoring.
3. **Test the contract, not the implementation**: behavior over mechanics.
4. **Real regression risk > theoretical coverage**: focus where bugs happen.
5. **Pest makes tests cheap**: use it.
6. **Test pyramid**: many unit tests for pure logic, fewer feature tests for wiring.
7. **TDD is a tool, not a religion**: write tests when they protect behavior, not for ceremony.

## When to Apply

- Every bug fix → regression test.
- Every new endpoint → feature test.
- Every new business rule → unit + feature test.
- Every refactor → existing tests should still pass.
