#!/usr/bin/env bash
# One-time setup for YAPPING on Linux/WSL: clone and build ygo-env, then verify.
# Run from yapping root: ./scripts/setup_wsl.sh
# Prerequisites: git, xmake, build-essential, libsqlite3-dev, python3 (see docs/WSL_SETUP.md)

set -e
YAPPING_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
YGO_ENV_ROOT="$YAPPING_ROOT/vendor/ygo-env"

echo "YAPPING root: $YAPPING_ROOT"
echo "ygo-env will be at: $YGO_ENV_ROOT"
echo ""

if [[ -d "$YGO_ENV_ROOT" ]]; then
  echo "vendor/ygo-env already exists. Building/updating..."
  cd "$YGO_ENV_ROOT"
else
  echo "Cloning izzak98/ygo-env into vendor/ygo-env..."
  mkdir -p "$YAPPING_ROOT/vendor"
  git clone https://github.com/izzak98/ygo-env.git "$YGO_ENV_ROOT"
  cd "$YGO_ENV_ROOT"
fi

echo "Building engine (xmake)..."
xmake f -m release -y
xmake

echo "Downloading assets and card scripts (make assets scripts)..."
make assets scripts

# Append default deck's card codes to code_list.txt (so re-clone doesn't lose them)
if [[ -f "$YGO_ENV_ROOT/assets/deck/Branded.ydk" ]]; then
  python3 "$YAPPING_ROOT/scripts/append_deck_codes_to_code_list.py" \
    "$YGO_ENV_ROOT/assets/deck/Branded.ydk" \
    "$YGO_ENV_ROOT/example/code_list.txt" \
    "$YGO_ENV_ROOT/scripts/script" || true
fi

echo ""
echo "Setup done. Verify with:"
echo "  export YGO_ENV_ROOT=\"$YGO_ENV_ROOT\""
echo "  export PYTHONPATH=\"\$YGO_ENV_ROOT:$YAPPING_ROOT:\$PYTHONPATH\""
echo "  cd \"\$YGO_ENV_ROOT\""
echo "  python -c 'import ygoenv; print(\"ygoenv OK\")'"
echo ""
echo "Run Hand Simulator: ./scripts/run_hand_sim.sh"
