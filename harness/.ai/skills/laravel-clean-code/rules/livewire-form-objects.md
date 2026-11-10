---
id: livewire-form-objects
title: Use Livewire Form Objects (Livewire v4)
category: livewire-architecture
priority: critical
tags: [livewire, forms, validation, form-objects, v4]
related: [livewire-state-minimal, livewire-component-single-purpose, laravel-form-request]
---

# Use Livewire Form Objects (Livewire v4)

Use Livewire's `Form` objects for any non-trivial form validation and submission. Do not cram validation, rules, and submission logic into the component. Form objects separate the form's state, validation, and submission from the component's UI concerns.

## Bad Example

```php
// ❌ Validation, submission, and state all in the component
final class OrderForm extends Component
{
    public string $reference = '';
    public string $customer_email = '';
    public int $quantity = 1;
    public ?int $product_id = null;
    public string $notes = '';
    public array $items = [];
    public float $subtotal = 0;
    public float $tax = 0;
    public float $total = 0;
    public bool $submitting = false;

    protected function rules(): array
    {
        return [
            'reference' => ['required', 'string', 'max:32', Rule::unique('orders', 'reference')->ignore($this->order?->id)],
            'customer_email' => ['required', 'email'],
            'quantity' => ['required', 'integer', 'min:1'],
            'product_id' => ['required', 'exists:products,id'],
            'notes' => ['nullable', 'string', 'max:1000'],
            'items' => ['required', 'array', 'min:1'],
        ];
    }

    public function updatedItems(): void
    {
        $this->recalculate();
    }

    public function updatedQuantity(): void
    {
        $this->recalculate();
    }

    public function save(): void
    {
        $this->validate();

        $order = Order::create($this->only(['reference', 'customer_email', 'quantity', 'product_id', 'notes']));
        $order->items()->createMany($this->items);

        $this->reset();
        $this->dispatch('order-saved');
    }

    public function recalculate(): void
    {
        // 20 lines of math
    }
}

// Problems:
// 1. 13 public properties for the form
// 2. Validation logic lives in the component
// 3. Submission logic lives in the component
// 4. Hard to test the form without booting Livewire
// 5. Form state cannot be reused across components (e.g. quick-create modal)
// 6. "submitting" flag is manual state
// 7. recalculate() is recomputed on every keystroke
```

## Good Example

```php
// ✅ Form object — validation + state + submission
namespace App\Livewire\Forms;

use App\Models\Order;
use Livewire\Form;
use Livewire\Attributes\Validate;

final class OrderForm extends Form
{
    #[Validate('required|string|max:32')]
    #[Validate('unique:orders,reference', message: 'Reference already exists.')]
    public string $reference = '';

    #[Validate('required|email')]
    public string $customer_email = '';

    #[Validate('required|integer|min:1')]
    public int $quantity = 1;

    #[Validate('required|exists:products,id')]
    public ?int $product_id = null;

    #[Validate('nullable|string|max:1000')]
    public string $notes = '';

    public ?Order $order = null;

    public function setOrder(?Order $order): void
    {
        $this->order = $order;
        if ($order) {
            $this->fill($order->only(['reference', 'customer_email', 'quantity', 'product_id', 'notes']));
        }
    }

    public function store(): Order
    {
        $this->validate();
        return Order::create($this->all());
    }

    public function update(): Order
    {
        $this->validate();
        $this->order->update($this->all());
        return $this->order;
    }
}
```

```blade
{{-- ✅ resources/views/livewire/order-form-page.blade.php — component just wires the form to the UI --}}
<?php
use App\Livewire\Forms\OrderForm;
use App\Models\Order;
use Livewire\Component;

new class extends Component {
    public OrderForm $form;

    public function mount(?Order $order = null): void
    {
        $this->form->setOrder($order);
    }

    public function save(): void
    {
        $order = $this->form->order
            ? $this->form->update()
            : $this->form->store();

        $this->dispatch('order-saved', orderId: $order->id);
        $this->form->reset();
    }
}
?>

<form wire:submit="save">
    <input type="text" wire:model="form.reference" />
    @error('form.reference') <span>{{ $message }}</span> @enderror

    <input type="email" wire:model="form.customer_email" />
    @error('form.customer_email') <span>{{ $message }}</span> @enderror

    <input type="number" wire:model="form.quantity" min="1" />
    <select wire:model="form.product_id">...</select>
    <textarea wire:model="form.notes"></textarea>

    <button type="submit" wire:loading.attr="disabled">Save</button>
</form>
```

Prefer a separate Blade view? Generate a class component instead: `php artisan make:livewire OrderFormPage --class`.

## Why This Is Better

1. **Validation is in one place** — the form object.
2. **Submission is in one place** — the form object.
3. **The component is tiny** — just wires the form to UI events.
4. **Reusable** — the same form can be used in a quick-create modal, a wizard, or a CLI command.
5. **Testable** — test the form object without Livewire; test the component with a real form.
6. **Attribute-based rules** — `#[Validate]` keeps rules next to the property.
7. **Auto error bag** — Livewire handles the error display.

## When to Use Form Objects

- 3+ form fields.
- 1+ validation rule.
- The same form is used in 2+ places.
- The form has any non-trivial submission logic.

## When NOT to Use Form Objects

```blade
{{-- ✅ resources/views/livewire/toggle-status.blade.php — a single boolean toggle does not need a form object --}}
<?php
use Livewire\Component;

new class extends Component {
    public bool $active = false;

    public function toggle(): void
    {
        $this->active = ! $this->active;
        // simple inline save
    }
}
?>

<button type="button" wire:click="toggle">
    {{ $active ? 'Deactivate' : 'Activate' }}
</button>
```

## Why

1. **Single responsibility**: form object = form, component = UI.
2. **Testability**: test form without Livewire; test component with a fake form.
3. **Reusability**: same form in modal, page, wizard, CLI.
4. **Laravel-aligned**: Form objects map to FormRequest.
5. **Livewire 4 feature**: built-in, no extra package.
6. **Cleaner components**: components stay focused on UI.
7. **Validation DRY**: rules live with the property.
