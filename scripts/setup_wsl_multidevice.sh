#!/usr/bin/env bash
# Unified WSL setup for YAPPING + cross-device dev tools.
# This is separate from setup_wsl.sh by request.

set -euo pipefail

YAPPING_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
YGO_ENV_ROOT="${YGO_ENV_ROOT:-$YAPPING_ROOT/vendor/ygo-env}"
BASHRC="${HOME}/.bashrc"
PYTHON_VERSION="$(tr -d '[:space:]' < "$YAPPING_ROOT/.python-version" 2>/dev/null || true)"
if [[ -z "${PYTHON_VERSION:-}" ]]; then
  PYTHON_VERSION="3.13"
fi

echo "YAPPING root: $YAPPING_ROOT"
echo "YGO_ENV_ROOT : $YGO_ENV_ROOT"
echo ""

require_cmd() {
  command -v "$1" >/dev/null 2>&1
}

echo "==> 1) System packages + 1Password CLI repo"
if [[ ! -f /usr/share/keyrings/1password-archive-keyring.gpg ]]; then
  curl -sS https://downloads.1password.com/linux/debian/gpg/1password.asc \
    | sudo gpg --dearmor --output /usr/share/keyrings/1password-archive-keyring.gpg
fi
if [[ ! -f /etc/apt/sources.list.d/1password.list ]]; then
  echo 'deb [arch=amd64 signed-by=/usr/share/keyrings/1password-archive-keyring.gpg] https://downloads.1password.com/linux/debian/amd64 stable main' \
    | sudo tee /etc/apt/sources.list.d/1password.list >/dev/null
fi
sudo apt update
sudo apt install -y \
  build-essential curl git zip unzip \
  cmake pkg-config libsqlite3-dev \
  python3 python3-dev python3-venv python3-pip \
  1password-cli

echo "==> 2) Git credential bridge (Windows GCM)"
git config --global credential.helper "/mnt/c/Program\ Files/Git/mingw64/bin/git-credential-manager.exe"

echo "==> 3) Rust toolchain"
if ! require_cmd rustup; then
  curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y
fi
source "$HOME/.cargo/env" || true

echo "==> 4) fnm + Node LTS"
if ! require_cmd fnm; then
  curl -fsSL https://fnm.vercel.app/install | bash -s -- --skip-shell
fi
export PATH="$HOME/.local/share/fnm:$PATH"

echo "==> 5) uv + Python installs"
if ! require_cmd uv; then
  curl -LsSf https://astral.sh/uv/install.sh | sh
fi
source "$HOME/.local/bin/env" 2>/dev/null || true
uv python install 3.12 "$PYTHON_VERSION"

echo "==> 6) xmake"
if ! require_cmd xmake; then
  curl -fsSL https://xmake.io/shget.text | bash
fi
if [[ -f "$HOME/.xmake/profile" ]]; then
  source "$HOME/.xmake/profile"
fi

echo "==> 7) Normalize .bashrc + 1Password SSH bridge"
if [[ -f "$BASHRC" ]]; then
  sed -i '/fnm env/d' "$BASHRC"
  sed -i '/alias ssh=/d' "$BASHRC"
  sed -i '/alias ssh-add=/d' "$BASHRC"
  sed -i '/SSH_AUTH_SOCK/d' "$BASHRC"
  sed -i '/1password/d' "$BASHRC"
fi

cat << 'EOF' >> "$BASHRC"

# --- Dev Environment & 1Password Sync ---
export PATH="$HOME/.local/share/fnm:$PATH"
eval "$(fnm env --use-on-cd)"
[ -f "$HOME/.xmake/profile" ] && source "$HOME/.xmake/profile"
[ -f "$HOME/.cargo/env" ] && source "$HOME/.cargo/env"
[ -f "$HOME/.local/bin/env" ] && source "$HOME/.local/bin/env"

# Redirect SSH commands to Windows 1Password Agent
alias ssh='/mnt/c/Windows/System32/OpenSSH/ssh.exe'
alias ssh-add='/mnt/c/Windows/System32/OpenSSH/ssh-add.exe'
EOF

echo "==> 8) Git SSH command via Windows OpenSSH"
git config --global core.sshCommand "ssh.exe"

echo "==> 9) Build ygo-env in vendor/"
mkdir -p "$YAPPING_ROOT/vendor"
if [[ ! -d "$YGO_ENV_ROOT/.git" ]]; then
  rm -rf "$YGO_ENV_ROOT"
  git clone https://github.com/petrademia/ygo-env.git "$YGO_ENV_ROOT"
fi

cd "$YGO_ENV_ROOT"
rm -rf .venv
uv venv --python "$PYTHON_VERSION" --seed .venv
source .venv/bin/activate

# Recreate scripts checkout if previous run left divergent refs.
if [[ -d third_party/ygopro-scripts/.git ]]; then
  rm -rf third_party/ygopro-scripts scripts/script
fi

make
# Remove stale ABI variants before building.
rm -f ygoenv/ygoenv/ygopro/ygopro_ygoenv.cpython-*.so || true
xmake f -c -m release -y
xmake b ygopro_ygoenv

# Append default deck codes to code_list.txt.
if [[ -f "$YGO_ENV_ROOT/assets/deck/Branded.ydk" ]]; then
  python "$YAPPING_ROOT/scripts/append_deck_codes_to_code_list.py" \
    "$YGO_ENV_ROOT/assets/deck/Branded.ydk" \
    "$YGO_ENV_ROOT/example/code_list.txt" \
    "$YGO_ENV_ROOT/scripts/script" || true
fi

echo ""
echo "✅ WSL setup complete."
echo "Next shell:"
echo "  source ~/.bashrc"
echo "Verify ygoenv:"
echo "  source \"$YGO_ENV_ROOT/.venv/bin/activate\""
echo "  python -c 'import ygoenv; print(\"ygoenv OK\")'"
echo "Run hand sim:"
echo "  cd \"$YAPPING_ROOT\" && bash scripts/run_hand_sim.sh --fixed-hand '' --dfs"
