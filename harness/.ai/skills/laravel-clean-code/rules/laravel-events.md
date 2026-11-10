---
id: laravel-events
title: Decouple Side Effects with Events
category: laravel-architecture
priority: critical
tags: [events, listeners, decoupling, side-effects]
related: [laravel-jobs-queue, solid-ocp, laravel-controller-thin]
---

# Decouple Side Effects with Events

When multiple side effects must happen as a result of an action (email, analytics, notifications, webhooks), use Laravel's event/listener system. Listeners can be queued, can be added/removed independently, and can be tested in isolation. The action class does not need to know what happens next.

## Bad Example

```php
// ❌ Direct coupling — OrderService knows every side effect
final class OrderService
{
    public function place(Order $order): void
    {
        // 1. Main work
        $order->update(['status' => 'placed']);

        // 2. Side effect 1
        Mail::to($order->customer)->send(new OrderConfirmation($order));

        // 3. Side effect 2
        $this->analytics->track('order_placed', $order);

        // 4. Side effect 3
        $this->warehouse->reserve($order);

        // 5. Side effect 4
        Http::post(config('services.crm.url'), $order->toArray());

        // 6. Side effect 5
        event(new NotifySlack('New order!'));
    }
}

// Problems:
// 1. OrderService knows about 5 different concerns
// 2. Cannot disable one side effect without editing the class
// 3. Cannot add a 6th side effect without editing
// 4. All 5 must be tested together
// 5. Cannot run side effects in parallel / on a queue independently
// 6. Failures in #4 break #1, #2, #3
```

## Good Example

```php
// ✅ Event-driven — OrderService only fires one event

final class OrderPlaced
{
    use Dispatchable, SerializesModels;

    public function __construct(public readonly Order $order) {}
}

final class OrderService
{
    public function place(Order $order): void
    {
        $order->update(['status' => 'placed']);
        OrderPlaced::dispatch($order);
    }
}

// Each side effect is its own listener
final class SendOrderConfirmation
{
    public function handle(OrderPlaced $event): void
    {
        Mail::to($event->order->customer)
            ->send(new OrderConfirmation($event->order));
    }
}

final class TrackOrderAnalytics
{
    public function handle(OrderPlaced $event): void
    {
        Analytics::track('order_placed', $event->order->toArray());
    }
}

final class ReserveWarehouseStock
{
    public function handle(OrderPlaced $event): void
    {
        $this->warehouse->reserve($event->order);
    }
}

final class PushToCrm
{
    public function handle(OrderPlaced $event): void
    {
        Http::post(config('services.crm.url'), $event->order->toArray());
    }
}

// In EventServiceProvider (or auto-discovered):
protected $listen = [
    OrderPlaced::class => [
        SendOrderConfirmation::class,
        TrackOrderAnalytics::class,
        ReserveWarehouseStock::class,
        PushToCrm::class,
    ],
];

// Benefits:
// 1. OrderService knows only about the event
// 2. Add a side effect = add a listener
// 3. Remove a side effect = remove a listener
// 4. Each listener is testable in isolation
// 5. Listeners can implement ShouldQueue
// 6. Failure in one listener does not affect others
// 7. Order can be controlled via $listen priority
```

## Queueable Listeners

```php
// ✅ Side effects that may be slow should be queued
final class SendOrderConfirmation implements ShouldQueue
{
    public int $tries = 3;

    public function handle(OrderPlaced $event): void
    {
        Mail::to($event->order->customer)
            ->send(new OrderConfirmation($event->order));
    }

    public function failed(Throwable $e): void
    {
        Log::error('Order confirmation failed', [
            'order_id' => $event->order->id,
        ]);
    }
}
```

## When to Use Events

- 2+ side effects happen after one action.
- Side effects are added or removed independently.
- A side effect may need to be queued.
- Different teams own different side effects.

## When NOT to Use Events

- One side effect after one action — call it directly.
- Side effect is critical to the action (must complete for the action to be considered successful) — call directly.
- Simple synchronous logic — no need to add a layer.

## Event Naming

```php
// ✅ Past tense — describes what happened
OrderPlaced, OrderShipped, OrderCancelled, PaymentReceived, UserRegistered

// ❌ Imperative — describes what to do
SendOrderEmail, NotifyWarehouse, TrackAnalytics
```

## Why

1. **Decoupled**: producer doesn't know consumers.
2. **Pluggable**: add listeners without editing the producer.
3. **Testable**: each listener is a unit.
4. **Queued**: each listener can have its own retry policy.
5. **Discoverable**: `EventServiceProvider` lists all flows.
6. **Laravel-idiomatic**: framework feature.
7. **Open/Closed**: add behavior without modifying existing code.
