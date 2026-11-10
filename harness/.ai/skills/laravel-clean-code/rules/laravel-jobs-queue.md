---
id: laravel-jobs-queue
title: Long Work Goes to Jobs on a Queue
category: laravel-architecture
priority: critical
tags: [jobs, queue, async, performance, side-effects]
related: [laravel-events, laravel-controller-thin, core-error-handling]
---

# Long Work Goes to Jobs on a Queue

Any work that takes more than ~100ms — or that may fail and should be retried — must run as a queued job, not synchronously in the controller. Mail, notifications, webhooks, image processing, exports, and any third-party API call are candidates for queueing.

## Bad Example

```php
// ❌ Synchronous work in the controller
final class OrderController extends Controller
{
    public function store(StoreOrderRequest $request): RedirectResponse
    {
        $order = Order::create($request->validated());

        // 1. Send email (SMTP = 500-2000ms)
        Mail::to($order->customer)->send(new OrderConfirmation($order));

        // 2. Call payment gateway (HTTP = 200-1000ms)
        $this->gateway->charge($order);

        // 3. Call shipping API (HTTP = 200-1000ms)
        $this->shipping->createLabel($order);

        // 4. Generate PDF invoice (CPU + disk = 100-2000ms)
        $this->pdf->generate($order);

        // 5. Push to analytics (HTTP = 100-500ms)
        $this->analytics->track('order_placed', $order);

        return redirect()->route('orders.show', $order);
    }
}

// Problems:
// 1. Total latency: 1100-6500ms before redirect
// 2. If step 3 fails, steps 4 and 5 are skipped silently
// 3. Customer waits for 5 third parties to respond
// 4. If user closes the page, all work is lost
// 5. Each third-party outage breaks the order endpoint
```

## Good Example

```php
// ✅ Controller dispatches; jobs do the work

final class OrderController extends Controller
{
    public function store(StoreOrderRequest $request): RedirectResponse
    {
        $order = Order::create($request->validated());
        ProcessOrder::dispatch($order);

        return redirect()->route('orders.show', $order);
    }
}

final class ProcessOrder implements ShouldQueue
{
    use Dispatchable, InteractsWithQueue, Queueable, SerializesModels;

    public int $tries = 3;
    public int $backoff = 10;

    public function handle(PaymentGateway $gateway, ShippingGateway $shipping): void
    {
        $gateway->charge($this->order);
        $shipping->createLabel($this->order);
        $this->order->update(['status' => OrderStatus::Paid]);
    }

    public function failed(Throwable $e): void
    {
        $this->order->update(['status' => OrderStatus::Failed]);
    }
}

// Side effects via listeners
final class SendOrderConfirmation
{
    public function handle(OrderPlaced $event): void
    {
        Mail::to($event->order->customer)
            ->queue(new OrderConfirmation($event->order));
    }
}

// Benefits:
// 1. Controller returns in < 100ms
// 2. Each side effect is retried independently
// 3. A failed payment does not lose the email
// 4. Customer sees instant success
// 5. Laravel's queue handles backoff, retries, failure
// 6. Worker scales horizontally
```

## When to Queue

- Sending email (use `Mail::queue()` / `->queue()` Mailable).
- Sending notifications.
- Calling third-party APIs (payment, shipping, analytics).
- Image processing, PDF generation, exports.
- Webhooks.
- Any work that may take more than 100ms or that may fail transiently.

## When NOT to Queue

- Validation.
- Authorization checks.
- Reading from the database.
- Trivial writes (a single insert with no side effects).
- Work that the user must wait for (e.g. real-time search results).

## Job Conventions

```php
// ✅ Job is invokable, queueable, has a contract
final class GenerateInvoicePdf implements ShouldQueue
{
    use Queueable;

    public int $tries = 3;
    public int $timeout = 120;
    public string $queue = 'invoices';

    public function __construct(public readonly Order $order) {}

    public function handle(PdfGenerator $pdf): void
    {
        $path = $pdf->generate($this->order);
        $this->order->update(['invoice_path' => $path]);
    }
}

// Dispatch
GenerateInvoicePdf::dispatch($order);
GenerateInvoicePdf::dispatch($order)->onQueue('high');
GenerateInvoicePdf::dispatch($order)->delay(now()->addMinutes(5));
```

## Why

1. **Latency**: user-facing endpoints stay fast.
2. **Reliability**: failed steps are retried.
3. **Decoupling**: third-party outages don't break your app.
4. **Scalability**: workers scale independently of web servers.
5. **Observability**: queue dashboard shows what's pending / failed.
6. **Laravel-idiomatic**: framework feature, expected by the team.
7. **Failure handling**: `failed()` method gives you a clean recovery point.
