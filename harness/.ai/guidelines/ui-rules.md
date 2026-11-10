## Обязательные скиллы проекта

- **Always apply the `laravel-best-practices` skill on any Laravel work.** This is not optional — invoke it at the start of any change to controllers, models, migrations, services, validation, queues, or Eloquent. The skill ships 31 rules across 7 categories (architecture, Eloquent, controllers/routing, validation, security, performance, API design); use them as the default reference. If existing code violates a rule, flag it (and offer a fix) rather than silently following the bad pattern.
- **Always use the `search-docs` tool before writing an API call.** Laravel 13, Livewire 4 and Filament 5 differ from older versions in ways that are easy to get wrong from memory. Никогда не писать вызов API по памяти, когда документация в одном тул-колле.

## No native browser dialogs anywhere in user-facing UI

Do NOT use `wire:confirm`, `window.confirm()`, `alert()`, or `prompt()` — they are not styleable, look broken on mobile, and break the app's visual identity. Use the global popup primitives from `resources/views/layouts/app.blade.php`:

- **Confirm dialog**: `<x-confirm-modal>` listens for the `open-confirm` Alpine event. Trigger from any button with `x-on:click="$dispatch('open-confirm', { message: '...', confirmLabel: '...', tone: 'danger'|'warning'|'primary', onConfirm: () => $wire.method(args) })"`.
- **Toast notification**: `<x-toast>` listens for the Livewire `toast` event. From PHP: `$this->dispatch('toast', message: '...', type: 'success'|'error'|'warning'|'info')`. Session flash (`session()->flash('status', ...)`) is also auto-converted to a toast after redirects.
- When adding a new destructive action, default the tone to `danger`; for archival/reversible actions use `warning`; for affirmative confirmations use `primary` (the default).

## NO PHP logic in Blade templates

`@php ... @endphp` blocks are forbidden. Blade is presentation only — variable echoing, directives (`@if`, `@foreach`, `@auth`), and component composition. Anything more belongs elsewhere:

- **Data assembly** (computed properties, derived collections, aggregates): build it in the Livewire component's `render()` or a controller, pass to the view ready-to-use. Не собирать значения в блоке `@php` в начале вьюхи.
- **Display formatting** (currency, dates, severity → CSS class): put in a model accessor, a value-object method, or a dedicated Blade component (`<x-severity-badge :level="..." />`) with backing logic in its class.
- **Conditional CSS classes**: extract to a method on the model or to an Alpine `:class` if it depends on client state. Не вычислять класс тернарником в `@php`.
- **Iteration logic** (sorting, filtering, grouping): pre-process in the component before passing to the view. The view consumes a ready collection.
- **Constants and config**: pass them in from the component, not inlined as a `use`-импорт внутри `@php`.
- **Forms** (any GET/POST that touches the DB): use a FormRequest class with `rules()` / `authorize()` / `messages()`. No inline validation in controllers, no `$request->all()`.
- **Existing `@php` blocks** are technical debt — when you touch a file that contains one, move the logic to the proper layer as part of the same change. Don't add new ones.
