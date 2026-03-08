#!/usr/bin/env bash
# Run YAPPING Hand Simulator with ygo-env.
# Usage: ./scripts/run_hand_sim.sh [deck.ydk]
#   If no deck given, uses ygo-env's assets/deck/Branded.ydk.
#
# Note: The engine (ygopro_ygoenv) builds only on Linux. On macOS, run this
# on Linux, in WSL, or in a Linux container.
#
# ygo-env lives at yapping/vendor/ygo-env so you can modify it if needed.

set -e
YAPPING_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
YGO_ENV_ROOT="${YGO_ENV_ROOT:-$YAPPING_ROOT/vendor/ygo-env}"

if [[ ! -d "$YGO_ENV_ROOT" ]]; then
  echo "YGO_ENV_ROOT not a directory: $YGO_ENV_ROOT"
  echo "Set it: export YGO_ENV_ROOT=/path/to/ygo-env"
  exit 1
fi

DECK="${1:-$YGO_ENV_ROOT/assets/deck/Branded.ydk}"
if [[ ! -f "$DECK" ]]; then
  echo "Deck not found: $DECK"
  exit 1
fi

export YGO_ENV_ROOT
# Prefer local vendor/ygo-env so "import ygoenv" finds the full package (including ygopro)
export PYTHONPATH="$YGO_ENV_ROOT:$YAPPING_ROOT:$PYTHONPATH"
# Engine looks for Lua scripts in cwd
cd "$YGO_ENV_ROOT"
python -m mouth.cli hand-sim --deck "$DECK" --ygo-env "$YGO_ENV_ROOT"
