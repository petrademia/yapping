#!/usr/bin/env bash
# Run this script inside WSL from the yapping project root:
#   cd /mnt/c/Users/petrus/Projects/yapping
#   chmod +x scripts/run_in_wsl.sh
#   ./scripts/run_in_wsl.sh
#
# It will: install xmake if needed, build ygo-env, install Python deps, run the hand simulator.

set -e
YAPPING_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$YAPPING_ROOT"

echo "=== YAPPING run (WSL) ==="
echo "Project root: $YAPPING_ROOT"
echo ""

# 1. Ensure xmake is available
if ! command -v xmake &>/dev/null; then
  echo "xmake not found. Installing xmake..."
  curl -fsSL https://xmake.io/shget.text | bash
  export PATH="$HOME/.local/bin:$PATH"
  if [[ -f "$HOME/.xmake/profile" ]]; then
    source "$HOME/.xmake/profile"
  fi
  if ! command -v xmake &>/dev/null; then
    echo "After install, run: source ~/.bashrc  or  source ~/.xmake/profile"
    echo "Then run this script again."
    exit 1
  fi
fi
echo "xmake: $(xmake --version | head -1)"
echo ""

# 2. Build ygo-env
YGO_ENV_ROOT="$YAPPING_ROOT/vendor/ygopro-adapter"
if [[ ! -d "$YGO_ENV_ROOT" ]]; then
  echo "Cloning ygo-env..."
  mkdir -p "$YAPPING_ROOT/vendor"
  git clone https://github.com/petrademia/ygo-env.git "$YGO_ENV_ROOT"
fi
# Apply patches (system Lua + Spec<> ambiguity fixes for newer compilers + select_card cid fix)
for p in "$YAPPING_ROOT/patches/ygo_env_system_lua.patch" "$YAPPING_ROOT/patches/ygo_env_spec_ambiguous.patch" "$YAPPING_ROOT/patches/ygo_env_ygopro_spec_ambiguous.patch" "$YAPPING_ROOT/patches/ygo_env_ygopro_select_card_cid.patch"; do
  if [[ -f "$p" ]]; then
    (cd "$YGO_ENV_ROOT" && patch -p1 -s -f < "$p" 2>/dev/null) || true
  fi
done
cd "$YGO_ENV_ROOT"
echo "Building engine in $YGO_ENV_ROOT ..."
xmake f -m release -y
xmake
echo "Fetching assets and card scripts (no pip install - we use PYTHONPATH)..."
make assets scripts
# Append default deck's card codes to code_list.txt so they survive re-clone (no "Card not found")
if [[ -f "$YGO_ENV_ROOT/assets/deck/Branded.ydk" ]]; then
  python3 "$YAPPING_ROOT/scripts/append_deck_codes_to_code_list.py" \
    "$YGO_ENV_ROOT/assets/deck/Branded.ydk" \
    "$YGO_ENV_ROOT/example/code_list.txt" \
    "$YGO_ENV_ROOT/scripts/script" || true
fi
echo ""

# 3. Python venv (isolated): yapping deps + ygoenv
cd "$YAPPING_ROOT"
if [[ ! -d .venv ]]; then
  echo "Creating Python venv (.venv)..."
  python3 -m venv .venv
fi
source .venv/bin/activate
pip install -q -r requirements.txt
echo "Installing ygoenv into venv (editable)..."
pip install -q -e "$YGO_ENV_ROOT/ygoenv"
echo ""

# 4. Run hand simulator (venv has ygoenv; only yapping on PYTHONPATH for cli.cli)
export YGO_ENV_ROOT
export PYTHONPATH="$YAPPING_ROOT:$PYTHONPATH"
cd "$YGO_ENV_ROOT"
echo "=== Running Hand Simulator ==="
python -m cli.cli hand-sim --deck "$YGO_ENV_ROOT/assets/deck/Branded.ydk" --ygo-env "$YGO_ENV_ROOT"
