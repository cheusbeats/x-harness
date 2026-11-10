---
id: laravel-controller-thin
title: Keep Controllers Thin
category: laravel-architecture
priority: critical
tags: [controller, mvc, action, dispatch, thin]
related: [laravel-form-request, laravel-resource, solid-srp, laravel-routes]
---

# Keep Controllers Thin

A controller's job is to receive an HTTP request, validate input, dispatch the work, and return a response. Controllers must not contain business logic, data shaping, complex queries, or side effects. If a controller method exceeds ~20 lines, it is doing too much. Move logic to Action / Service / Job / Listener.

## Bad Example

```php
// ❌ Controller does everything
final class OrderController extends Controller
{
    public function store(Request $request): RedirectResponse
    {
        $validated = $request->validate([
            'product_id' => 'required|exists:products,id',
            'quantity' => 'required|integer|min:1',
        ]);

        $product = Product::findOrFail($validated['product_id']);
        $stock = $product->stock;

        if ($stock < $validated['quantity']) {
            return back()->withErrors(['quantity' => 'Not enough stock']);
        }

        $user = auth()->user();
        $total = $product->price * $validated['quantity'];

        if ($total > 1000 && !$user->hasVerifiedEmail()) {
            return back()->withErrors(['email' => 'Verify email for large orders']);
        }

        $order = new Order();
        $order->user_id = $user->id;
        $order->product_id = $product->id;
        $order->quantity = $validated['quantity'];
        $order->total = $total;
        $order->status = 'pending';
        $order->save();

        $product->decrement('stock', $validated['quantity']);

        Mail::to($user)->send(new OrderConfirmation($order));
        event(new OrderPlaced($order));
        Log::info('Order placed', ['id' => $order->id]);

        return redirect()->route('orders.show', $order);
    }
}

// Problems:
// 1. Validation, business rules, side effects all in HTTP layer
// 2. 50+ lines, multiple concerns
// 3. Cannot be reused by another entry point (CLI, API, queue)
// 4. Hard to test — needs full HTTP + DB + Mail fakes
// 5. Every change touches the controller
```

## Good Example

```php
// ✅ Thin controller dispatches the work

// 1. FormRequest — validation
final class StoreOrderRequest extends FormRequest
{
    public function rules(): array
    {
        return [
            'product_id' => ['required', 'exists:products,id'],
            'quantity' => ['required', 'integer', 'min:1'],
        ];
    }
}

// 2. Action — business logic
final class CreateOrderAction
{
    public function execute(User $user, Product $product, int $quantity): Order
    {
        $order = Order::create([
            'user_id' => $user->id,
            'product_id' => $product->id,
            'quantity' => $quantity,
            'total' => $product->price * $quantity,
            'status' => OrderStatus::Pending,
        ]);

        $product->decrement('stock', $quantity);
        OrderPlaced::dispatch($order);

        return $order;
    }
}

// 3. Policy — authorization
final class OrderPolicy
{
    public function create(User $user): bool
    {
        // large orders require verified email
        return true; // per-product rule lives in the action
    }
}

// 4. Controller — dispatch only
final class OrderController extends Controller
{
    public function store(StoreOrderRequest $request, CreateOrderAction $action): RedirectResponse
    {
        $this->authorize('create', Order::class);

        $product = Product::findOrFail($request->integer('product_id'));

        $order = $action->execute(
            $request->user(),
            $product,
            $request->integer('quantity'),
        );

        return redirect()->route('orders.show', $order);
    }
}

// Benefits:
// 1. Controller fits in 10 lines
// 2. Action is testable without HTTP
// 3. Same action can be called from CLI / queue / API
// 4. Side effects (mail, event) live in listeners
// 5. Each layer has one job
```

## When to Apply

- Controller method exceeds ~20 lines.
- Controller contains a `foreach` or complex business logic.
- Controller has direct Mail::send / Event::dispatch / Log::info.
- Controller is hard to test (requires 5+ fakes).
- The same logic needs to run from a non-HTTP entry point (CLI, queue, test).

## When NOT to Apply

Trivial controllers are fine:

```php
// ✅ Trivial read is OK to keep in the controller
public function show(Order $order): View
{
    $this->authorize('view', $order);
    return view('orders.show', compact('order'));
}

// ✅ Trivial delete is OK
public function destroy(Order $order): RedirectResponse
{
    $this->authorize('delete', $order);
    $order->delete();
    return redirect()->route('orders.index');
}
```

The line: **business logic, side effects, complex queries** go elsewhere. **Trivial HTTP plumbing** stays.

## What Goes Where

| Concern | Location |
|---------|----------|
| Validation | `FormRequest` |
| Authorization | `Policy` |
| Business logic | `Action` (invokable) or `Service` (stateful) |
| Side effects (email, event) | `Listener` (triggered by `Event`) |
| Long work | `Job` (queued) |
| Response shaping | `Resource` (API) or view (web) |
| HTTP-only concerns | `Controller` |

## Why

1. **Reusable**: action can be called from anywhere.
2. **Testable**: each layer is testable in isolation.
3. **Readable**: controller is a 1-page summary of the request.
4. **Laravel-aligned**: FormRequest, Policy, Action, Listener, Job are all framework features.
5. **Faster reviews**: reviewers know where each thing lives.
6. **Easier refactoring**: change one layer without touching others.
7. **Performance**: queueable work doesn't block the HTTP response.
