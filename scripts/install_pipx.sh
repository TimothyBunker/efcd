#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if ! command -v pipx >/dev/null 2>&1; then
  python -m pip install --user pipx
  python -m pipx ensurepath
  echo "pipx installed. You may need to restart your shell."
fi

if pipx list | grep -q "efcd"; then
  pipx upgrade efcd
else
  pipx install -e "$ROOT_DIR"
fi

echo "efcd installed. Try: efcd --help"
