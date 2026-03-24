#!/usr/bin/env bash
# One-time setup for YAPPING on Linux/WSL: clone and build yapcore, then verify.
# Run from yapping root: ./scripts/setup_wsl.sh
# Prerequisites: git, xmake, cmake, build-essential, libsqlite3-dev, python3 (see docs/WSL_SETUP.md)

set -euo pipefail
YAPPING_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
YGO_ENV_ROOT="${YGO_ENV_ROOT:-$YAPPING_ROOT/vendor/yapcore}"
PYTHON_VERSION="$(tr -d '[:space:]' < "$YAPPING_ROOT/.python-version" 2>/dev/null || true)"
if [[ -z "${PYTHON_VERSION:-}" ]]; then
  PYTHON_VERSION="3.13"
fi

echo "YAPPING root: $YAPPING_ROOT"
echo "yapcore will be at: $YGO_ENV_ROOT"
echo ""

require_cmd() {
  command -v "$1" >/dev/null 2>&1
}

apply_patch_if_needed() {
  local patch_file="$1"
  if [[ ! -f "$patch_file" ]]; then
    return 0
  fi
  if git -C "$YGO_ENV_ROOT" apply --check "$patch_file" >/dev/null 2>&1; then
    echo "Applying patch: $(basename "$patch_file")"
    git -C "$YGO_ENV_ROOT" apply "$patch_file"
  else
    echo "Patch already applied or not needed: $(basename "$patch_file")"
  fi
}

if ! require_cmd git; then
  echo "ERROR: git is not installed."
  exit 1
fi
if ! require_cmd xmake; then
  echo "ERROR: xmake is not installed or not on PATH."
  exit 1
fi
if ! require_cmd python3; then
  echo "ERROR: python3 is not installed."
  exit 1
fi

if [[ -d "$YGO_ENV_ROOT/.git" ]]; then
  echo "vendor/yapcore already exists. Building/updating..."
else
  echo "Cloning adapter into vendor/yapcore..."
  mkdir -p "$YAPPING_ROOT/vendor"
  rm -rf "$YGO_ENV_ROOT"
  git clone https://github.com/petrademia/yapcore.git "$YGO_ENV_ROOT"
fi
cd "$YGO_ENV_ROOT"

echo "Preparing Python environment (.venv)..."
if require_cmd uv; then
  rm -rf .venv
  uv venv --python "$PYTHON_VERSION" --seed .venv
else
  python3 -m venv .venv
  source .venv/bin/activate
  python -m pip install -U pip
fi
source .venv/bin/activate

echo "Resetting scripts checkout (avoids divergent pull errors)..."
rm -rf third_party/ygopro-scripts scripts/script

echo "Installing Python package + downloading assets/scripts (make)..."
make

echo "Applying compatibility patches (if needed)..."
apply_patch_if_needed "$YAPPING_ROOT/patches/ygo_env_spec_ambiguous.patch"
apply_patch_if_needed "$YAPPING_ROOT/patches/ygo_env_ygopro_spec_ambiguous.patch"
apply_patch_if_needed "$YAPPING_ROOT/patches/ygo_env_ygopro_select_card_cid.patch"
apply_patch_if_needed "$YAPPING_ROOT/patches/ygo_env_system_lua.patch"

echo "Building native engine module (xmake)..."
# Remove stale ABI variants before building, so we don't accidentally leave a
# mismatched `.so` that Python can't import.
rm -f ygoenv/ygoenv/ygopro/ygopro_ygoenv.cpython-*.so || true
xmake f -c -m release -y
xmake b ygopro_ygoenv

# Append default deck's card codes to code_list.txt (so re-clone doesn't lose them)
if [[ -f "$YGO_ENV_ROOT/assets/deck/Branded.ydk" ]]; then
  python "$YAPPING_ROOT/scripts/append_deck_codes_to_code_list.py" \
    "$YGO_ENV_ROOT/assets/deck/Branded.ydk" \
    "$YGO_ENV_ROOT/example/code_list.txt" \
    "$YGO_ENV_ROOT/scripts/script" || true
fi

echo ""
echo "Setup done. Verify with:"
echo "  export YGO_ENV_ROOT=\"$YGO_ENV_ROOT\""
echo "  source \"$YGO_ENV_ROOT/.venv/bin/activate\""
echo "  python -c 'import ygoenv; print(\"ygoenv OK\")'"
echo ""
echo "Run Hand Simulator: ./scripts/run_hand_sim.sh --fixed-hand '' --dfs"
