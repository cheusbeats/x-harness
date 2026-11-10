---
id: core-error-handling
title: Handle Real Errors, Fail Fast
category: core-principles
priority: critical
tags: [errors, exceptions, fail-fast, reliability]
related: [core-boring-code, core-comments, laravel-form-request]
---

# Handle Real Errors, Fail Fast

Handle errors that can realistically occur and matter to the current behavior. Do not add elaborate error-handling infrastructure for impossible or hypothetical conditions. Do not silently swallow errors. Prefer explicit failure over hidden inconsistent state.

## Bad Example

```php
// ❌ Catch-all with silent swallow
public function store(StoreOrderRequest $request): RedirectResponse
{
    try {
        $order = Order::create($request->validated());
        Mail::to($order->customer)->send(new OrderConfirmation($order));
    } catch (\Throwable $e) {
        // "just in case" — log and pretend nothing happened
        \Log::error($e->getMessage());
    }

    return redirect()->route('orders.show', $order ?? null);
}

// Problems:
// 1. Catches everything, including programming errors
// 2. Swallows the error — user sees success but email never sent
// 3. $order may be null — calling route() on null crashes next line
// 4. Customer never gets email, no retry, no alert
// 5. Logs are noisy and ignored
```

## Good Example

```php
// ✅ Let it fail fast, only catch what you handle
public function store(StoreOrderRequest $request): RedirectResponse
{
    $order = Order::create($request->validated());
    Mail::to($order->customer)->send(new OrderConfirmation($order));

    return redirect()->route('orders.show', $order);
}

// Or, if email failure should not block order creation:
public function store(StoreOrderRequest $request): RedirectResponse
{
    $order = Order::create($request->validated());

    Mail::to($order->customer)
        ->queue(new OrderConfirmation($order)); // queued, retried by Laravel

    return redirect()->route('orders.show', $order);
}

// If you really need to handle a specific error:
public function charge(Order $order): PaymentResult
{
    try {
        return $this->gateway->charge($order);
    } catch (CardDeclinedException $e) {
        // Real error with real handling
        $order->update(['status' => OrderStatus::PaymentFailed]);
        return PaymentResult::failed($e->getMessage());
    }
    // Everything else: let it bubble — Laravel's exception handler will 500
}

// Benefits:
// 1. Real errors are visible
// 2. Order creation does not depend on email success
// 3. Email retries are handled by the queue
// 4. CardDeclined is a real business case with real handling
// 5. Programming errors surface immediately
```

## The Three Rules

1. **Catch what you handle**: do not catch to log and rethrow.
2. **Let it bubble for unknown errors**: Laravel's exception handler is correct by default.
3. **Use queues for unreliable work**: email, notifications, webhooks.

## Anti-Patterns

```php
// ❌ Catching to log and rethrow (pointless)
try { ... } catch (\Throwable $e) { Log::error($e); throw $e; }

// ❌ Catching to convert to a return value (loses stack trace)
try { ... } catch (\Throwable $e) { return null; }

// ❌ Catching broad to "be safe"
try { ... } catch (\Exception $e) { /* never mind */ }

// ❌ Empty catch
try { ... } catch (\Throwable $e) { }
```

## When to Catch

```php
// ✅ Specific exception with specific handling
try {
    $this->filesystem->put($path, $contents);
} catch (FileNotFoundException $e) {
    return response()->json(['error' => 'File missing'], 404);
}

// ✅ External API with retry logic
try {
    return $this->api->call();
} catch (RequestException $e) {
    if ($e->getCode() === 429) {
        return $this->retry($e);
    }
    throw $e;
}

// ✅ Transaction with rollback
DB::transaction(function () {
    // ... operations
});
// Throws on failure, rolls back automatically
```

## Why

1. **Visible failures**: real errors should be loud, not silent.
2. **No hidden state**: silent catches leave the system in inconsistent states.
3. **Faster debugging**: stack traces point to the real problem.
4. **Laravel already handles errors**: trust the framework's exception handler.
5. **Queue for unreliable work**: don't wrap business logic in try/catch.
6. **Logs are not solutions**: a log entry is not a fix.
7. **Catch what you handle**: catching without handling is worse than not catching.

## When to Apply

- When adding a `try/catch` block.
- When wrapping business logic in a generic exception handler.
- When writing a service method that "always succeeds".
- When tempted to "be safe" with a catch-all.

## When NOT to Apply

- When you don't actually know what to do with the error — let it bubble.
- When the work is unreliable and Laravel's queue can handle it — queue it.
- When the error is impossible given the current code — no catch.
