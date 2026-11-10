#!/usr/bin/env bash
# tests/acceptance.sh — приёмка пакета: манифест, установка в чистый git-репозиторий, parity, smoke,
# приёмка планировочного профиля (tests/acceptance-planning.sh) и строгого слоя (tests/acceptance-strict.sh).
set -euo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
TMP="$(mktemp -d "${TMPDIR:-/tmp}/xh-accept.XXXXXX")"
cleanup() { rm -rf "$TMP"; }
trap cleanup EXIT

echo "1/9 манифест и harness/"
bash "$ROOT/verify.sh" --quiet
python3 "$ROOT/tests/test-codex-agents.py"
python3 "$ROOT/tests/test_merge_gate_configuration.py"
python3 "$ROOT/tests/test_agent_hook.py"
python3 "$ROOT/tests/test_no_origin_identity.py"

echo "2/9 установка в чистый git-репозиторий ($TMP/project)"
mkdir -p "$TMP/project"
git -C "$TMP/project" init -q
git -C "$TMP/project" config user.email accept@example.invalid
git -C "$TMP/project" config user.name accept
( cd "$TMP/project" && git commit -q --allow-empty -m init )
HOME="$TMP/home" bash "$ROOT/install.sh" --project "$TMP/project" --clients none --skills none --no-verify

echo "3/9 parity"
bash "$ROOT/verify.sh" --project "$TMP/project"

echo "4/9 smoke (xh doctor в установленном проекте)"
( cd "$TMP/project" && bash "$ROOT/bin/xh" doctor >/dev/null 2>&1 || true )
printf 'CLAUDE.md size: '; wc -c < "$TMP/project/CLAUDE.md"

echo "5/9 приёмка планировочного профиля (--profile planning)"
bash "$ROOT/tests/acceptance-planning.sh"

echo "6/9 строгая приёмка strict-слоя (--profile planning, STRICT)"
bash "$ROOT/tests/acceptance-strict.sh"

echo "7/9 безопасность установщика"
bash "$ROOT/tests/acceptance-install-safety.sh"

echo "8/9 установка навыков из upstream"
bash "$ROOT/tests/acceptance-upstream-skills.sh"

echo "9/9 установка из копии скилла без Git"
bash "$ROOT/tests/acceptance-skill-bootstrap.sh"

echo "acceptance: OK"
