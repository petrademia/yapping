#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TARGET="$ROOT/assets/cards.cdb"
COMMIT="a4f8313a0c82b747ac5b3fb9e744fb7f5ed989e6"
EXPECTED="c54901ab8dc1b2edec17b7ea65e309ab050b8fd05e0d314ebaab7f02db2ed70f"
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
