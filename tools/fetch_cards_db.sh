#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TARGET="$ROOT/assets/cards.cdb"
COMMIT="8f36c87c2faea4d24a6062410f9dfe0cd6848865"
EXPECTED="f81958a2e0c238ddf5060482e1a2fc2c0d4a7f75917e76c388cab1a28fa43d4c"
URL="https://raw.githubusercontent.com/mycard/ygopro-database/$COMMIT/locales/en-US/cards.cdb"

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
