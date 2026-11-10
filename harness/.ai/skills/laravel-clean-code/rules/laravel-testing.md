---
id: laravel-testing
title: Feature Tests for Behavior, Unit for Pure Logic
category: laravel-architecture
priority: critical
tags: [pest, phpunit, testing, feature, unit]
related: [core-tests, laravel-controller-thin, laravel-policies]
---

# Feature Tests for Behavior, Unit for Pure Logic

Use Pest feature tests for HTTP-level behavior (endpoints, validation, auth, redirects, JSON shape). Use Pest unit tests for pure logic (calculations, transformations, scopes). Do not test the framework. Do not over-mock. Real DB is fine via `RefreshDatabase`. Use factories, not manual model creation.

## Bad Example

```php
// ❌ Unit test that requires Laravel booted
test('order total is sum of item prices', function () {
    $user = new User(['name' => 'John']);
    $order = new Order(['user_id' => $user->id]);
    $item = new OrderItem(['price' => 10, 'quantity' => 2]);
    // ... manual wiring, no factory, no DB, but trying to use Eloquent
    expect($order->total())->toBe(20);
});

// ❌ Feature test that tests the framework
test('post endpoint exists', function () {
    $response = $this->post('/orders', []);
    $response->assertStatus(302); // testing Laravel's redirect, not your code
});

// ❌ Too many mocks
test('order service charges payment', function () {
    $gateway = Mockery::mock(PaymentGateway::class);
    $mailer = Mockery::mock(Mailer::class);
    $repo = Mockery::mock(OrderRepository::class);
    $analytics = Mockery::mock(Analytics::class);
    // 7 mocks, 50 lines of setup, 1 assertion
});

// Problems:
// 1. Unit test that needs Laravel is not a unit test
// 2. Feature test that asserts framework behavior is wasted
// 3. Over-mocking makes tests brittle
// 4. No factories — manual model construction is fragile
```

## Good Example

```php
// ✅ Unit test for pure logic (no Laravel)
use App\Support\Pricing;

it('calculates total as sum of item price * quantity', function () {
    $items = collect([
        (object) ['price' => 100, 'quantity' => 2],
        (object) ['price' => 50,  'quantity' => 1],
    ]);

    expect(Pricing::total($items))->toBe(250);
});

it('applies a 10% discount above 1000', function () {
    $items = collect([
        (object) ['price' => 600, 'quantity' => 2], // 1200
    ]);

    expect(Pricing::total($items))->toBe(1080.0); // 1200 * 0.9
});

// ✅ Feature test for HTTP behavior
use App\Models\User;
use App\Models\Product;
use Illuminate\Support\Facades\Mail;
use App\Mail\OrderConfirmation;

it('lets an authenticated user create an order', function () {
    Mail::fake();
    $user = User::factory()->create();
    $product = Product::factory()->create(['stock' => 10, 'price' => 100]);

    $this->actingAs($user)
        ->post(route('orders.store'), [
            'product_id' => $product->id,
            'quantity' => 2,
        ])
        ->assertRedirect(route('orders.show', 1));

    Mail::assertSent(OrderConfirmation::class, fn ($mail) =>
        $mail->hasTo($user->email)
    );

    $this->assertDatabaseHas('orders', [
        'user_id' => $user->id,
        'product_id' => $product->id,
        'quantity' => 2,
        'total' => 200,
    ]);
});

it('rejects an unauthenticated user', function () {
    $this->post(route('orders.store'), [])
        ->assertRedirect(route('login'));
});

it('rejects an invalid quantity', function () {
    $user = User::factory()->create();

    $this->actingAs($user)
        ->post(route('orders.store'), ['product_id' => 1, 'quantity' => 0])
        ->assertSessionHasErrors('quantity');
});

// Benefits:
// 1. Each test is readable
// 2. Real DB (RefreshDatabase) for realism, factories for speed
// 3. Mail::fake() instead of Mail::mock() (Laravel-native)
// 4. One behavior per test
// 5. assertDatabaseHas catches regressions
```

## The Test Pyramid (Laravel Edition)

| Layer | Type | Tool | When |
|-------|------|------|------|
| Top | Feature (HTTP) | Pest + `RefreshDatabase` | New endpoint, new auth rule, new flow |
| Middle | Integration | Pest + `RefreshDatabase` | New job, new listener, new command |
| Bottom | Unit | Pest (no Laravel) | Pricing, validation logic, scopes, calculations |

## When to Use Each

- **Feature test**: new endpoint, changed auth, new redirect, new JSON shape.
- **Integration test**: new job, new listener, new command — anything that touches the framework.
- **Unit test**: pure function, no Laravel, no DB.

## Use `RefreshDatabase`

```php
// tests/Pest.php
uses(Tests\TestCase::class, Illuminate\Foundation\Testing\RefreshDatabase::class)->in('Feature');
```

## Use Factories

```php
// ✅ Factories are the test data source
$user = User::factory()->create();
$user = User::factory()->admin()->create(); // use states
$users = User::factory()->count(10)->create();

// ❌ Manual construction
$user = new User(['name' => 'John', 'email' => 'john@example.com']);
$user->save();
```

## When to Apply

- Every bug fix → regression test.
- Every new endpoint → feature test.
- Every new business rule → unit + feature test.
- Every new job/listener → integration test.

## Why

1. **Confidence**: feature tests prove the wiring works.
2. **Speed**: unit tests are fast, no DB.
3. **Readability**: Pest reads like prose.
4. **Pest 4 features**: datasets, higher-order tests, profiles.
5. **Laravel-idiomatic**: framework testing tools.
6. **Regression safety**: a test for "what broke last time".
7. **Documentation**: tests show how the code is supposed to be used.
