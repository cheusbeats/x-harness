#!/usr/bin/env bash
# Auto semver tag (stable vX.Y.Z only, no pre-releases) on main.
# Bump from conventional commits since the last stable tag:
#   BREAKING CHANGE / "type!:"  -> major (while 0.x: minor)
#   feat                        -> minor
#   fix|perf|refactor|revert    -> patch
#   docs|test|chore|ci|style    -> no tag
# Local only, never pushes: git push origin --tags. Idempotent.
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"

[ "$(git branch --show-current)" = main ] || exit 0
git describe --exact-match --tags --match 'v[0-9]*' HEAD 2>/dev/null | grep -qE '^v[0-9]+\.[0-9]+\.[0-9]+$' && exit 0

last=$(git tag --merged HEAD --list 'v[0-9]*' --sort=-v:refname | grep -E '^v[0-9]+\.[0-9]+\.[0-9]+$' | head -1 || true)
last=${last:-v0.0.0}
range=$([ "$last" = v0.0.0 ] && echo HEAD || echo "$last..HEAD")
log=$(git log "$range" --no-merges --format='%s%n%b')
[ -n "$log" ] || exit 0

IFS=. read -r maj min pat <<<"${last#v}"
if grep -qE '^BREAKING[ -]CHANGE|^[a-z]+(\([^)]*\))?!:' <<<"$log"; then
  if [ "$maj" -eq 0 ]; then min=$((min+1)); pat=0; else maj=$((maj+1)); min=0; pat=0; fi
elif grep -qE '^feat(\(|:)' <<<"$log"; then min=$((min+1)); pat=0
elif grep -qE '^(fix|perf|refactor|revert)(\(|:|!)' <<<"$log"; then pat=$((pat+1))
else exit 0
fi

tag="v$maj.$min.$pat"
git tag -a "$tag" -m "Release $tag"
echo "release-tag: $last -> $tag (not pushed: git push origin $tag)"
