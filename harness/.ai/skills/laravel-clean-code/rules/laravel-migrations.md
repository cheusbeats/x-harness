---
id: laravel-migrations
title: Additive, Safe Migrations
category: laravel-architecture
priority: critical
tags: [migrations, schema, database, additive, safety]
related: [core-error-handling, laravel-config-env]
---

# Additive, Safe Migrations

Migrations must be additive: add columns and tables, never drop or rename in a way that loses data. Never edit a migration that has already been deployed to any environment. To change a column, include all previous attributes in the new migration. Each migration is a one-way door — open it carefully.

## Bad Example

```php
// ❌ Editing a deployed migration
// Original (deployed 6 months ago):
// database/migrations/2025_01_15_create_orders_table.php
public function up(): void
{
    Schema::create('orders', function (Blueprint $table) {
        $table->id();
        $table->string('name');
    });
}

// Now: developer edits the original, changes $table->string('name') to $table->string('title')
// Result: local works, staging breaks, prod panics — the migration was already run on prod

// ❌ Destructive column change
public function up(): void
{
    Schema::table('orders', function (Blueprint $table) {
        $table->dropColumn('legacy_status');
        $table->string('status')->change(); // loses the comment, default, etc.
    });
}
// Result: lost data + lost column attributes
```

## Good Example

```php
// ✅ Never edit a deployed migration — create a new one

// Original (DO NOT EDIT):
// database/migrations/2025_01_15_create_orders_table.php
public function up(): void
{
    Schema::create('orders', function (Blueprint $table) {
        $table->id();
        $table->string('name');
        $table->timestamps();
    });
}

// New migration (renames column safely):
// database/migrations/2026_08_07_rename_orders_name_to_title.php
public function up(): void
{
    Schema::table('orders', function (Blueprint $table) {
        $table->renameColumn('name', 'title');
    });
}

public function down(): void
{
    Schema::table('orders', function (Blueprint $table) {
        $table->renameColumn('title', 'name');
    });
}

// ✅ Adding a column — pure additive
// database/migrations/2026_08_07_add_phone_to_users.php
public function up(): void
{
    Schema::table('users', function (Blueprint $table) {
        $table->string('phone')->nullable()->after('email');
    });
}

public function down(): void
{
    Schema::table('users', function (Blueprint $table) {
        $table->dropColumn('phone');
    });
}

// ✅ Modifying a column — include ALL previous attributes
// Original column: $table->string('status')->default('pending');
// New column:     $table->string('status')->default('pending')->comment('Order status');
// New migration:
public function up(): void
{
    Schema::table('orders', function (Blueprint $table) {
        $table->string('status')
            ->default('pending')      // ← keep
            ->comment('Order status') // ← add new
            ->change();
    });
}
```

## Destructive Operations Need a Plan

If you must drop a column, drop a table, or rename something:

```php
// ✅ Multi-step process
// 1. Migration: add the new column (or table) — additive
// 2. Deploy: code now writes to both old and new
// 3. Migration: backfill the new column from the old
// 4. Deploy: code now reads from the new
// 5. Deploy: code stops writing to the old
// 6. Migration: drop the old column (next release)

// ⚠️ NEVER in one migration:
// - Drop a column with data
// - Rename a column without a transition
// - Drop a table that is still referenced
```

## The Rule

- **Add** columns: new migration, `nullable()` or with default.
- **Modify** columns: include ALL previous attributes.
- **Rename** columns: 2-step (add new, copy data, drop old) for prod data.
- **Drop** columns: only after the column is unused everywhere.
- **Edit** a deployed migration: never.

## When to Apply

- Every migration.
- Every schema change.
- Every column rename.
- Every index change.

## Why

1. **Migrations are a contract**: deployed migrations must always succeed.
2. **Rollback safety**: dropping a column cannot be undone.
3. **Multi-environment**: dev, staging, prod must stay in sync.
4. **CI safety**: a non-additive migration breaks the build.
5. **Team safety**: another developer may have already pulled the migration.
6. **Laravel-aligned**: framework convention (don't edit migrations).
7. **Reversible changes** = lower risk.
