---
id: core-premature-abstraction
title: Avoid Premature Abstraction
category: core-principles
priority: critical
tags: [abstraction, duplication, design, decision]
related: [core-dry, core-yagni, core-arch-decision-test]
---

# Avoid Premature Abstraction

Do not create abstractions because code looks similar. Similar syntax is not the same concept. A small amount of duplication is acceptable when the alternative is an incorrect or premature abstraction. Wait for evidence — repeated behavior, shared concept, or concrete architectural need — before generalizing.

## Bad Example

```php
// ❌ One user, one order, but interface + repo + service for "flexibility"
interface UserRepositoryInterface
{
    public function find(int $id): ?User;
    public function create(array $data): User;
    public function update(User $user, array $data): User;
}

final class EloquentUserRepository implements UserRepositoryInterface
{
    public function find(int $id): ?User
    {
        return User::find($id);
    }
    // ... etc
}

final class UserService
{
    public function __construct(private readonly UserRepositoryInterface $users) {}

    public function register(array $data): User
    {
        return $this->users->create($data);
    }
}

// Problems:
// 1. One implementation, no test double needed
// 2. Eloquent already is the repository
// 3. Service adds nothing — controller can call User::create directly
// 4. 3 files, 50 lines, 1 line of behavior
```

## Good Example

```php
// ✅ Plain Eloquent
final class User extends Model
{
    protected $fillable = ['name', 'email', 'password'];

    protected function casts(): array
    {
        return ['password' => 'hashed'];
    }
}

// In controller:
final class RegisterController extends Controller
{
    public function store(RegisterRequest $request): RedirectResponse
    {
        $user = User::create($request->validated());
        Auth::login($user);

        return redirect()->route('home');
    }
}

// Benefits:
// 1. No abstraction
// 2. Eloquent is the abstraction
// 3. Easy to test: `User::factory()->create()` in tests
// 4. Add repository later IF you need to swap the data source
```

## Why

1. **Wrong abstraction is worse than duplication** — coupling unrelated concepts.
2. **Abstractions leak** — every layer leaks something; fewer layers = less leakage.
3. **Reading cost** — every layer is a context switch.
4. **Premature generalization is permanent** — hard to remove without rewriting.
5. **Test cost** — more types = more mocks = more test code.
6. **Real DRY comes from real patterns** — three uses, not two.
7. **YAGNI alignment** — do not build for hypothetical flexibility.

## When to Apply

- Before creating a Repository, Service, or Manager class with one method.
- Before extracting a trait, interface, or abstract class.
- Before writing a "generic" helper for one specific case.
- Before adding a "Base" class for two subclasses that look similar today.

## When NOT to Apply

When abstraction is justified by real evidence:

```php
// ✅ Abstract because there are 2 real implementations today
interface PaymentGateway
{
    public function charge(Order $order): PaymentResult;
}

final class StripeGateway implements PaymentGateway { /* real */ }
final class YooKassaGateway implements PaymentGateway { /* real */ }

// ✅ Abstract because logic is genuinely shared and stable
abstract class Migration
{
    use DatabaseMigration;

    public function up(): void { /* contract */ }
    public function down(): void { /* contract */ }
}
```

The rule is: **wait for evidence**, not "never abstract."

## Rule of Three

Wait until the third real occurrence before extracting. Two similar pieces might be coincidence. Three indicates a real pattern.
