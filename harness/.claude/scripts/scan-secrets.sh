#!/usr/bin/env bash
# Скан добавленных строк диффа на секреты. Дифф читается со stdin.
#
# Запуск:  git diff --cached -U0 | .claude/scripts/scan-secrets.sh
# Самотест: .claude/scripts/scan-secrets.sh --self-test
#
# Выход: 0 — чисто, 1 — найдено (строки в stderr).
#
# Логика намеренно разбита на три независимых правила, а не один мега-регекс:
# первая версия была одной строкой и ловила 1 находку из 4, причём ветка про
# PEM-заголовок была мертва по построению (требовала разделитель `=`, которого
# в PEM-заголовке приватного ключа нет). Разбитое правило проверяемо по частям.

set -uo pipefail

# Строка — индирекция, а не секрет: env(), config(), ${VAR}, $var, placeholder.
is_indirection() {
  printf '%s' "$1" | grep -qE '(env\(|config\(|getenv\(|\$\{|\$[A-Za-z_]|<[a-z_]+>|your[_-]|change[_-]?me|xxx+|\*\*\*)'
}

# Явная пометка «это не секрет» — для тестовых фикстур и документации про секреты.
# Без неё сканер ловит сам себя: собственные пробы самотеста и комментарий про
# PEM-заголовок заблокировали реальный коммит при первом же боевом срабатывании.
is_marked_safe() {
  printf '%s' "$1" | grep -q 'not-a-secret'
}

scan() {
  local found=0 line body
  while IFS= read -r line; do
    case "$line" in
      +++*) continue ;;
      +*) body="${line#+}" ;;
      *) continue ;;
    esac

    is_marked_safe "$body" && continue

    # Правило 2: PEM-заголовок приватного ключа — сам по себе, без разделителей.
    if printf '%s' "$body" | grep -qE -- '-----BEGIN [A-Z ]*PRIVATE KEY-----'; then
      printf 'приватный ключ: %s\n' "$body" >&2; found=1; continue
    fi

    # Правило 3: узнаваемые формы токенов — где бы в строке ни стояли.
    if printf '%s' "$body" | grep -qE '(sk-[A-Za-z0-9_-]{16,}|gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|AKIA[0-9A-Z]{16}|xox[baprs]-[A-Za-z0-9-]{10,}|eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,})'; then
      is_indirection "$body" || { printf 'токен: %s\n' "$body" >&2; found=1; continue; }
    fi

    # Правило 1: присваивание длинного литерала ключу с «секретным» именем.
    # Между именем и разделителем допускаем кавычку и любые слова через _ —
    # это ловит и AWS_SECRET_ACCESS_KEY=..., и 'api_key' => '...'.
    if printf '%s' "$body" \
      | grep -qEi '(api[_-]?key|secret|password|passwd|passphrase|private[_-]?key|access[_-]?token|auth[_-]?token|client[_-]?secret)[A-Za-z0-9_]*["'"'"']?[[:space:]]*(=>|[=:])[[:space:]]*["'"'"']?[A-Za-z0-9/+_.-]{12,}'; then
      is_indirection "$body" || { printf 'секрет в присваивании: %s\n' "$body" >&2; found=1; }
    fi
  done
  return $found
}

self_test() {
  local fails=0
  probe() { # probe <ожидание block|pass> <строка>
    local want="$1" line="$2" got
    if printf '%s\n' "$line" | scan 2>/dev/null; then got=pass; else got=block; fi
    if [ "$got" = "$want" ]; then
      printf '  ok   %-8s %s\n' "$want" "${line:0:60}"
    else
      printf '  FAIL ждали %-6s получили %-6s %s\n' "$want" "$got" "${line:0:60}"; fails=1
    fi
  }

  echo "должны блокироваться:"
  probe block "+DB_PASSWORD=sup3rS3cretPa55word"  # not-a-secret
  probe block "+    'api_key' => 'sk-proj-8fZk29dLmQpR4vNxTTTT',"  # not-a-secret
  probe block "+AWS_SECRET_ACCESS_KEY=wJalrXUtnFEMIK7MDENGbPxRfiCY"  # not-a-secret
  probe block "+-----BEGIN RSA PRIVATE KEY-----"  # not-a-secret
  probe block "+Authorization: bearer eyJhbGciOiJIUzI1NiI.eyJzdWIiOiIxMjM0"  # not-a-secret
  probe block "+    'client_secret' => 'abc123def456ghi789',"  # not-a-secret
  probe block "+AKIAIOSFODNN7EXAMPLE"  # not-a-secret

  echo "должны проходить:"
  probe pass "+    'password' => env('DB_PASSWORD'),"  # not-a-secret
  probe pass "+DB_PASSWORD=\${DB_PASSWORD}"  # not-a-secret
  probe pass "+    \$user->password = Hash::make(\$request->password);"  # not-a-secret
  probe pass "+    'api_key' => config('services.yandex.key'),"  # not-a-secret
  probe pass "+    \$table->string('password_hash');"  # not-a-secret
  probe pass "+// сбрасываем password при смене email"  # not-a-secret
  probe pass "+DB_PASSWORD=your_password_here"  # not-a-secret
  probe pass "+APP_KEY="  # not-a-secret
  probe pass "+DB_PASSWORD=realLookingSecret9876 // not-a-secret"  # маркер снимает блок

  [ "$fails" -eq 0 ] && echo "самотест зелёный" || echo "САМОТЕСТ УПАЛ"
  return $fails
}

if [ "${1:-}" = "--self-test" ]; then
  self_test
  exit $?
fi

scan
exit $?
