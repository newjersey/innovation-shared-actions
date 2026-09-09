#!/usr/bin/env bash
set -euo pipefail

if [ -f pnpm-lock.yaml ]; then
  PACKAGE_MANAGER="pnpm"
elif [ -f package-lock.json ]; then
  PACKAGE_MANAGER="npm"
else
  PACKAGE_MANAGER="none"
  echo "No package-lock.json or pnpm-lock.yaml found."
fi

echo "PACKAGE_MANAGER=$PACKAGE_MANAGER" >> "$GITHUB_ENV"
echo "package-manager=$PACKAGE_MANAGER" >> "$GITHUB_OUTPUT"
