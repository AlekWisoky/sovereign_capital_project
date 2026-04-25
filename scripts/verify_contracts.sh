#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
CONTRACTS_DIR="$ROOT_DIR/contracts"
if ! command -v forge >/dev/null 2>&1; then
  echo "forge_not_installed"
  echo "Install Foundry: https://book.getfoundry.sh/getting-started/installation"
  echo "Then run: cd contracts && forge test -q"
  exit 2
fi
cd "$CONTRACTS_DIR"
forge test -q
