#!/usr/bin/env bash
# Run YAPPING Hand Simulator with yapcore.
# Usage: ./scripts/run_hand_sim.sh [deck.ydk]
#   If no deck given, uses yapcore's assets/deck/Branded.ydk.
#
# Note: The engine (ygopro_ygoenv) builds only on Linux. On macOS, run this
# on Linux, in WSL, or in a Linux container.
#
# yapcore lives at yapping/vendor/yapcore so you can modify it if needed.

set -e

_info() { echo "  [setup] $*"; }
_ok()   { echo "  [setup] $* ✓"; }

echo ""
echo "════════════════════════════════════════"
echo "  YAPPING  —  Hand Simulator"
echo "════════════════════════════════════════"

YAPPING_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
YGO_ENV_ROOT="${YGO_ENV_ROOT:-$YAPPING_ROOT/vendor/yapcore}"

_info "Yapping root : $YAPPING_ROOT"
_info "yapcore root : $YGO_ENV_ROOT"

if [[ ! -d "$YGO_ENV_ROOT" ]]; then
  echo ""
  echo "  ERROR: YGO_ENV_ROOT not a directory: $YGO_ENV_ROOT"
  echo "         Set it: export YGO_ENV_ROOT=/path/to/yapcore"
  exit 1
fi

# Native extension must exist (built by xmake and copied to ygopro/)
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

# If first arg looks like a flag (e.g. --dfs), use default deck and pass all args to CLI
if [[ "$1" == -* ]]; then
  DECK="$YGO_ENV_ROOT/assets/deck/Branded.ydk"
  HAND_SIM_ARGS=("$@")
else
  DECK="${1:-$YGO_ENV_ROOT/assets/deck/Branded.ydk}"
  HAND_SIM_ARGS=("${@:2}")
fi
if [[ ! -f "$DECK" ]]; then
  echo ""
  echo "  ERROR: Deck not found: $DECK"
  exit 1
fi

# Count main / extra / side cards in the .ydk file
_count_deck() {
  local deck="$1" section="main" main=0 extra=0 side=0
  while IFS= read -r line; do
    line="${line%%$'\r'}"
    case "$line" in
      "#extra") section="extra" ;;
      "!side")  section="side"  ;;
      "#"*|"")  ;;
      *) if [[ "$line" =~ ^[0-9]+$ ]]; then
           case "$section" in
             main)  ((main++))  ;;
             extra) ((extra++)) ;;
             side)  ((side++))  ;;
           esac
         fi ;;
    esac
  done < "$deck"
  echo "${main}m / ${extra}ex / ${side}side"
}
DECK_COUNTS="$(_count_deck "$DECK")"
_ok "Deck         : $(basename "$DECK")  ($DECK_COUNTS)"

export YGO_ENV_ROOT

# Engine expects ./script/ when cwd is YGO_ENV_ROOT; Makefile creates scripts/script only
if [[ ! -d "$YGO_ENV_ROOT/script" && -d "$YGO_ENV_ROOT/scripts/script" ]]; then
  ln -sfn scripts/script "$YGO_ENV_ROOT/script"
  _ok "Lua symlink  : script → scripts/script  (created)"
elif [[ -d "$YGO_ENV_ROOT/script" ]]; then
  _ok "Lua symlink  : script/  (already present)"
fi

# Use project venv if present (ygoenv installed there); else fall back to PYTHONPATH
if [[ -d "$YAPPING_ROOT/.venv" ]]; then
  source "$YAPPING_ROOT/.venv/bin/activate"
  export PYTHONPATH="$YAPPING_ROOT:$PYTHONPATH"
  PY_VER="$(python --version 2>&1)"
  _ok "Python env   : .venv  ($PY_VER)"
else
  export PYTHONPATH="$YGO_ENV_ROOT:$YAPPING_ROOT:$PYTHONPATH"
  _ok "Python env   : system PYTHONPATH  (no .venv found)"
fi

# Ensure deck's codes are in code_list.txt so "Card not found" is avoided
CODE_LIST="$YGO_ENV_ROOT/example/code_list.txt"
CODES_BEFORE="$(wc -l < "$CODE_LIST" 2>/dev/null || echo '?')"
CODE_MSG="$(python -m cli.cli add-deck-codes-to-list --deck "$DECK" --ygo-env "$YGO_ENV_ROOT" 2>&1)" || true
CODES_AFTER="$(wc -l < "$CODE_LIST" 2>/dev/null || echo '?')"
if echo "$CODE_MSG" | grep -q "Nothing to add"; then
  _ok "Code list    : all deck codes present  ($CODES_AFTER entries)"
else
  ADDED="$(echo "$CODE_MSG" | grep -oE '[0-9]+ card' | head -1 || echo '?')"
  _ok "Code list    : $ADDED codes added  ($CODES_BEFORE → $CODES_AFTER entries)"
fi

echo "════════════════════════════════════════"
echo ""

# Engine looks for Lua scripts in cwd
cd "$YGO_ENV_ROOT"
python -m cli.cli hand-sim --deck "$DECK" --ygo-env "$YGO_ENV_ROOT" "${HAND_SIM_ARGS[@]}"
