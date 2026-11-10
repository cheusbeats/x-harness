#!/usr/bin/env bash
# Подключает git-хуки репозитория (PLAN-145, E19). Идемпотентен.
cd "$(git rev-parse --show-toplevel)" || exit 1
chmod +x .githooks/*
if [ "$(git config core.hooksPath)" = ".githooks" ]; then
  echo "уже подключено: core.hooksPath=.githooks"
else
  git config core.hooksPath .githooks
  echo "ok: core.hooksPath=$(git config core.hooksPath)"
fi
