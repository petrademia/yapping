# Running YAPPING on Linux / WSL

The Yu-Gi-Oh! engine (**ygopro-core**) only builds on **Linux**. On Windows, use **WSL** (Windows Subsystem for Linux). These steps assume you're in a WSL terminal (e.g. Ubuntu).

---

## 1. Install system dependencies (one-time)

Install everything needed for the engine and its dependencies (Lua, zlib, etc.):

```bash
sudo apt update
sudo apt install -y python3 python3-pip python3-venv git build-essential libsqlite3-dev \
  liblua5.4-dev zlib1g-dev libffi-dev ninja-build cmake
```

The yapping repo is patched so **ygopro-core** uses system Lua (`liblua5.4-dev`) instead of building Lua from source, which avoids “toolchain not found” and related build failures.

Install **xmake** (build system for yapcore):

```bash
# Official install script
curl -fsSL https://xmake.io/shget.text | bash
# Or: wget https://xmake.io/shget.text -O - | bash
# Then reload shell or: source ~/.xmake/profile
```

If you use a different method (e.g. `apt install xmake`), ensure `xmake` is on your PATH.

---

## 2. Clone and build the engine (one-time)

From your **yapping** project root (in WSL):

```bash
cd /mnt/c/Users/petrus/Projects/yapping   # adjust if your path differs
mkdir -p vendor
git clone https://github.com/petrademia/ygopro-adapter.git vendor/yapcore
cd vendor/yapcore
xmake f -m release -y
xmake
make assets scripts
```

Do **not** run plain `make` here: it tries `pip install -e ./ygoenv` system-wide, which fails on modern Linux (externally-managed environment). Use **`make assets scripts`** only; then install ygoenv into the project venv (step 3). When that finishes, the native extension (`.so`) will be in `ygoenv/ygoenv/ygopro/`. You're then ready to run YAPPING.

---

## 3. Python venv (one-time, isolated)

Use a single venv so both yapping and ygoenv are isolated from the system Python:

```bash
cd /mnt/c/Users/petrus/Projects/yapping
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -e vendor/yapcore/ygoenv
```

The editable install of **ygoenv** puts the engine package in the venv; no system-wide `pip install` and no `PYTHONPATH` hack for ygoenv.

---

## 4. Run the Hand Simulator

**One-shot (if xmake is already installed):** from **yapping** root in WSL:

```bash
./scripts/run_in_wsl.sh
```

Otherwise, from **yapping** root in WSL:

```bash
cd /mnt/c/Users/petrus/Projects/yapping
source .venv/bin/activate   # if you use a venv
./scripts/run_hand_sim.sh
```

With a specific deck:

```bash
./scripts/run_hand_sim.sh data/decks/YourDeck.ydk
# Or use the deck that came with yapcore:
./scripts/run_hand_sim.sh vendor/yapcore/assets/deck/Branded.ydk
```

Manual run (same effect):

```bash
export YGO_ENV_ROOT="$(pwd)/vendor/yapcore"
export PYTHONPATH="$YGO_ENV_ROOT:$(pwd):$PYTHONPATH"
cd vendor/yapcore
python -m cli.cli hand-sim --deck "$YGO_ENV_ROOT/assets/deck/Branded.ydk" --ygo-env "$YGO_ENV_ROOT"
```

---

## Troubleshooting

| Issue | Fix |
|-------|-----|
| `YGO_ENV_ROOT not a directory` | Run step 2; ensure `vendor/yapcore` exists and contains built files. |
| `Could not import ygoenv` | Run the Python command from inside `vendor/yapcore` (the script does this), and ensure `PYTHONPATH` includes both `YGO_ENV_ROOT` and the yapping root. |
| `cards.cdb not found` | Run `make` inside `vendor/yapcore` to download assets. |
| `xmake: command not found` | Install xmake (step 1) and reload your shell or `source ~/.xmake/profile`. |
| Path with spaces | Quote paths: `./scripts/run_hand_sim.sh "path/to/deck.ydk"`. |
| **xmake fails on libffi, zlib, lua, ninja** | Install deps: `sudo apt install -y liblua5.4-dev zlib1g-dev libffi-dev ninja-build cmake build-essential`. Clear failed package cache: `rm -rf ~/.xmake/cache/packages/2603` (or the parent number shown in the error path). Then in `vendor/yapcore` run `xmake f -m release -y` and `xmake` again. |
| **`make` → externally-managed-environment / pip** | Don’t run plain `make` in yapcore. Run only `make assets scripts`. Install ygoenv into the project venv: `pip install -e vendor/yapcore/ygoenv` (with venv activated). |

| **`ModuleNotFoundError: ... ygopro_ygoenv`** | The native extension wasn't built. In `vendor/yapcore` run: `xmake f -m release -y && xmake`. The `.so` is copied to `ygoenv/ygoenv/ygopro/`. Then run the hand sim again. |
| **`[card_reader_callback] Card not found: XXXXX`** | The wrapper merges deck codes into `example/code_list_merged.txt` and passes absolute paths to the engine. The run script also ensures a top-level `script` symlink exists (→ `scripts/script`) so the engine finds Lua scripts. If it still fails, the card may be in `cards.cdb` **texts** but not **datas** (engine needs both); try a deck whose cards are in the bundled DB or update the DB from mycard/ygopro-database. |

Your repo is under `C:\Users\petrus\Projects\yapping`; in WSL that is typically `/mnt/c/Users/petrus/Projects/yapping`. If you cloned the repo inside WSL instead, use that path (e.g. `~/Projects/yapping`).
