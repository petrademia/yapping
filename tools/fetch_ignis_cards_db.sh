#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TARGET="$ROOT/assets/ignis/cards.cdb"
COMMIT="172462f1e7405c7544cc256471d3310df6e6b7c3"
EXPECTED="061c2fbd1c541d66d5b06989a2c2a1ef4539a4f82802f31382e72a5955ef180d"
URL="https://raw.githubusercontent.com/ProjectIgnis/BabelCDB/$COMMIT/cards.cdb"

command -v curl >/dev/null || {
  echo "error: curl is required" >&2
  exit 1
}
mkdir -p "$(dirname "$TARGET")"
tmp="$(mktemp)"
trap 'rm -f "$tmp"' EXIT

curl --fail --silent --show-error --location "$URL" --output "$tmp"

if command -v sha256sum >/dev/null; then
  actual="$(sha256sum "$tmp" | cut -d' ' -f1)"
else
  actual="$(shasum -a 256 "$tmp" | cut -d' ' -f1)"
fi

if [[ "$actual" != "$EXPECTED" ]]; then
  echo "error: downloaded cards.cdb checksum mismatch" >&2
  echo "expected: $EXPECTED" >&2
  echo "actual:   $actual" >&2
  exit 1
fi

mv "$tmp" "$TARGET"
trap - EXIT
echo "installed $TARGET"
echo "sha256: $actual"
