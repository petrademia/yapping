#!/usr/bin/env bash
# Run YAPPING sample-hands with ygo-env (generate multiple hands, output card names).
# Usage: ./scripts/run_sample_hands.sh [deck.ydk] [options...]
#   If no deck given, uses ygo-env's assets/deck/Branded.ydk.
#   Options are passed to sample-hands, e.g.:
#     ./scripts/run_sample_hands.sh --num-hands 20 --format json --out hands.json
#     ./scripts/run_sample_hands.sh my.ydk --num-hands 5
#
# Note: The engine builds only on Linux. On Windows use WSL.
# See docs/WSL_SETUP.md for setup.

set -e

_info() { echo "  [setup] $*"; }
_ok()   { echo "  [setup] $* ✓"; }

echo ""
echo "════════════════════════════════════════"
echo "  YAPPING  —  Sample hands"
echo "════════════════════════════════════════"

YAPPING_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
YGO_ENV_ROOT="${YGO_ENV_ROOT:-$YAPPING_ROOT/vendor/ygo-env}"

_info "Yapping root : $YAPPING_ROOT"
_info "ygo-env root : $YGO_ENV_ROOT"

if [[ ! -d "$YGO_ENV_ROOT" ]]; then
  echo ""
  echo "  ERROR: YGO_ENV_ROOT not a directory: $YGO_ENV_ROOT"
  echo "         Set it: export YGO_ENV_ROOT=/path/to/ygo-env"
  exit 1
fi

YGOENV_SO_DIR="$YGO_ENV_ROOT/ygoenv/ygoenv/ygopro"
SO_FILE="$(compgen -G "$YGOENV_SO_DIR/ygopro_ygoenv"*.so 2>/dev/null | head -1)"
if [[ -z "$SO_FILE" ]]; then
  echo ""
  echo "  ERROR: Native extension missing: $YGOENV_SO_DIR/ygopro_ygoenv*.so"
  echo "         Build it: cd $YGO_ENV_ROOT && xmake f -m release -y && xmake"
  echo "         See docs/WSL_SETUP.md for full setup."
  exit 1
fi
_ok "Engine .so   : $(basename "$SO_FILE")"

# First arg: deck path if it looks like a .ydk or existing file; else default deck
if [[ -n "$1" && ( "$1" == *.ydk || -f "$1" ) ]]; then
  DECK="$1"
  shift
else
  DECK="$YGO_ENV_ROOT/assets/deck/Branded.ydk"
fi
if [[ ! -f "$DECK" ]]; then
  echo ""
  echo "  ERROR: Deck not found: $DECK"
  exit 1
fi
_ok "Deck         : $(basename "$DECK")"

export YGO_ENV_ROOT

if [[ ! -d "$YGO_ENV_ROOT/script" && -d "$YGO_ENV_ROOT/scripts/script" ]]; then
  ln -sfn scripts/script "$YGO_ENV_ROOT/script"
  _ok "Lua symlink  : script → scripts/script  (created)"
elif [[ -d "$YGO_ENV_ROOT/script" ]]; then
  _ok "Lua symlink  : script/  (already present)"
fi

if [[ -d "$YAPPING_ROOT/.venv" ]]; then
  source "$YAPPING_ROOT/.venv/bin/activate"
  export PYTHONPATH="$YAPPING_ROOT:$PYTHONPATH"
  _ok "Python env   : .venv"
else
  export PYTHONPATH="$YGO_ENV_ROOT:$YAPPING_ROOT:$PYTHONPATH"
  _ok "Python env   : system PYTHONPATH"
fi

python -m mouth.cli add-deck-codes-to-list --deck "$DECK" --ygo-env "$YGO_ENV_ROOT" 2>/dev/null || true

echo "════════════════════════════════════════"
echo ""

cd "$YGO_ENV_ROOT"
python -m mouth.cli sample-hands --deck "$DECK" --ygo-env "$YGO_ENV_ROOT" "$@"
