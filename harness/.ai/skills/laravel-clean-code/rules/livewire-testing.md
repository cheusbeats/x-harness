---
id: livewire-testing
title: Test Livewire Components with Pest
category: livewire-architecture
priority: critical
tags: [livewire, testing, pest, browser, smoke]
related: [laravel-testing, livewire-form-objects, livewire-state-minimal]
---

# Test Livewire Components with Pest

Use `pestphp/pest-plugin-livewire` for component unit tests and `livewire()` helper for feature tests. Test the component in isolation — boot it, set state, call methods, assert render output. Use a real DB via `RefreshDatabase` for queries; use `Livewire::test()` for fast unit tests.

## Bad Example

```php
// ❌ Testing the rendered HTML for a behavior
test('order list shows orders', function () {
    $order = Order::factory()->create();

    $response = $this->get('/orders');
    $response->assertSee($order->reference);
    // Problem: this is a feature test, not a Livewire test
    // It tests the route, not the component
});

// ❌ Testing the underlying model, not the component
test('order list filters by status', function () {
    Order::factory()->create(['status' => 'active']);
    Order::factory()->create(['status' => 'cancelled']);

    $active = Order::where('status', 'active')->get();
    expect($active)->toHaveCount(1);
    // Problem: this tests Eloquent, not the component
});

// ❌ Test that boots the full HTTP stack
test('order form validates', function () {
    $response = $this->post('/orders', ['reference' => '']);
    $response->assertSessionHasErrors('reference');
    // Problem: doesn't test the Livewire component
});
```

## Good Example

```php
// ✅ Pest + Livewire plugin for component unit tests
use App\Models\Order;
use Livewire\Livewire;

it('renders orders on the page', function () {
    $orders = Order::factory()->count(3)->create();

    // SFC components are booted by name; class-based — by ::class
    Livewire::test('order-list')
        ->assertSee($orders->first()->reference)
        ->assertSee($orders->last()->reference);
});

it('filters by search', function () {
    $match = Order::factory()->create(['reference' => 'ORDER-001']);
    $other = Order::factory()->create(['reference' => 'OTHER-002']);

    Livewire::test('order-list')
        ->set('search', 'ORDER')
        ->assertSee($match->reference)
        ->assertDontSee($other->reference);
});

it('filters by status', function () {
    $active = Order::factory()->create(['status' => 'active']);
    $cancelled = Order::factory()->create(['status' => 'cancelled']);

    Livewire::test('order-list')
        ->set('status', 'active')
        ->assertSee($active->reference)
        ->assertDontSee($cancelled->reference);
});

it('paginates 20 per page', function () {
    $orders = Order::factory()->count(25)->create();

    Livewire::test('order-list')
        ->assertSee($orders->last()->reference)        // newest on page 1
        ->assertDontSee($orders->first()->reference);  // oldest fell onto page 2
});
```

```php
// ✅ Test a Livewire form object
use App\Models\Product;

it('validates required fields', function () {
    Livewire::test('order-form-page')
        ->set('form.reference', '')
        ->set('form.customer_email', 'not-an-email')
        ->call('save')
        ->assertHasErrors(['form.reference', 'form.customer_email']);
});

it('creates an order when valid', function () {
    $product = Product::factory()->create();

    Livewire::test('order-form-page')
        ->set('form.reference', 'ORDER-001')
        ->set('form.customer_email', 'customer@example.com')
        ->set('form.quantity', 2)
        ->set('form.product_id', $product->id)
        ->call('save')
        ->assertHasNoErrors()
        ->assertDispatched('order-saved');

    $this->assertDatabaseHas('orders', [
        'reference' => 'ORDER-001',
        'customer_email' => 'customer@example.com',
    ]);
});
```

```php
// ✅ Test component-to-component events
it('refreshes the list when an order is saved', function () {
    $order = Order::factory()->create();

    Livewire::test('order-list')
        ->dispatch('order-saved', orderId: $order->id)
        ->assertSee($order->reference);
});
```

## Pest Livewire API

```php
Livewire::test('order-list', ['param' => 'value'])  // SFC by name, class-based by ::class
    ->set('property', 'value')        // set public property
    ->set('form.field', 'value')      // set nested form property
    ->call('methodName', 'arg')       // call public method
    ->call('save')                    // call without args
    ->dispatch('event', 'param')      // dispatch an event
    ->assertSee('text')
    ->assertDontSee('text')
    ->assertHasErrors(['field'])
    ->assertHasNoErrors()
    ->assertDispatched('event-name')
    ->assertNotDispatched('event-name')
    ->assertRedirect('/somewhere')
    ->assertOk();
```

## Browser Tests for Smoke

```php
// ✅ Browser test (pestphp/pest-plugin-browser) for a critical flow
use Pest\Browser\Playwright;

it('lets a user create an order end-to-end', function () {
    $this->browse(function (Browser $browser) {
        $browser->visit('/orders/new')
            ->type('reference', 'ORDER-001')
            ->type('customer_email', 'customer@example.com')
            ->click('@save-button')
            ->waitForText('Order created')
            ->assertSee('ORDER-001');
    });
});
```

## When to Apply

- Every Livewire component.
- Every Form object.
- Every cross-component event.
- Every new wire:click action.

## Why

1. **Fast**: `Livewire::test()` is faster than HTTP feature tests.
2. **Targeted**: tests the component, not the route.
3. **Pest-native**: `livewire()` helper reads like prose.
4. **Real DB**: `RefreshDatabase` gives real behavior.
5. **Component-level assertions**: `set`, `call`, `assertSee` map to Livewire methods.
6. **Form testing**: nested `form.field` works out of the box.
7. **Browser fallback**: smoke-test critical flows in a real browser.
