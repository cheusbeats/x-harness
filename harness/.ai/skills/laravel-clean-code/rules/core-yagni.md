---
id: core-yagni
title: You Aren't Gonna Need It (YAGNI)
category: core-principles
priority: critical
tags: [yagni, speculative, future-features]
related: [core-kiss, core-premature-abstraction, core-arch-decision-test]
---

# You Aren't Gonna Need It (YAGNI)

Implement only what is required now. Do not build features, extension points, configurations, or abstractions for hypothetical future use. Future requirements should be implemented when they become actual requirements.

## Bad Example

```php
// ❌ Speculative multi-channel notification system
interface NotificationChannelInterface
{
    public function send(User $user, string $message): void;
}

final class EmailChannel implements NotificationChannelInterface { /* ... */ }
final class SmsChannel implements NotificationChannelInterface { /* ... */ }
final class PushChannel implements NotificationChannelInterface { /* ... */ }
final class SlackChannel implements NotificationChannelInterface { /* ... */ }
final class DiscordChannel implements NotificationChannelInterface { /* ... */ }

final class NotificationManager
{
    public function __construct(
        private readonly iterable $channels,
        private readonly UserPreferencesRepository $preferences,
    ) {}

    public function notify(User $user, string $message): void
    {
        foreach ($this->channels as $channel) {
            if ($this->preferences->isEnabled($user, $channel)) {
                $channel->send($user, $message);
            }
        }
    }
}

// Problems:
// 1. Only email is used today
// 2. User preferences repository doesn't exist
// 3. 5 channel classes for 1 use case
// 4. Container binding for unused abstractions
```

## Good Example

```php
// ✅ Just send an email
final class OrderController extends Controller
{
    public function store(StoreOrderRequest $request): RedirectResponse
    {
        $order = Order::create($request->validated());
        Mail::to($order->customer)->send(new OrderConfirmation($order));

        return redirect()->route('orders.show', $order);
    }
}

// When SMS becomes a real requirement (3 months from now):
// - Add a second Mail::send or a queued job
// - Extract NotificationManager only if you now have 2+ channels

// Benefits:
// 1. One line of code instead of 5 classes
// 2. Easy to delete if requirements change
// 3. Real requirements drive the design
```

## Why

1. **Most "future" needs never materialize** — the code is wasted.
2. **Speculative code is harder to change** — it pretends to be ready for change.
3. **Wrong abstractions are expensive** — the future often needs a different shape.
4. **YAGNI keeps the surface small** — fewer places for bugs.
5. **Easier reviews** — reviewers don't have to validate hypothetical scenarios.
6. **Better focus** — current requirements get full attention.
7. **Faster delivery** — no time wasted on unused features.

## When to Apply

- Before adding a feature flag for a feature that has no user yet.
- Before creating an interface for a single implementation.
- Before adding a config value with no consumer.
- Before writing a generic helper for one use case.
- Before adding "optional" parameters no caller passes.
- Before writing fallback paths for impossible error states.

## When NOT to Apply

YAGNI does not mean "no planning":

```php
// ❌ Not YAGNI — it's "no planning"
class OrderController {
    public function store(Request $request) {
        Order::create($request->all()); // no validation, no type, no auth
    }
}
// ✅ Still simple, but applies basic Laravel hygiene
class OrderController {
    public function store(StoreOrderRequest $request) {
        $this->authorize('create', Order::class);
        Order::create($request->validated());
    }
}
```

YAGNI is about not building for hypothetical futures, not about skipping current essentials.
