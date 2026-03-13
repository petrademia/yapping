# Setting up the engine that uses OCGCore

YAPPING needs a **headless** Yu-Gi-Oh! engine that uses OCGCore for correct card logic. The recommended option is **izzak98/ygo-env**, a minimal fork of ygo-agent focused on the environment only.

---

## Option 1: **izzak98/ygo-env** (recommended)

**[izzak98/ygo-env](https://github.com/izzak98/ygo-env)** is a maintained fork of [sbl1996/ygo-agent](https://github.com/sbl1996/ygo-agent) stripped down to the **environment and engine interface**—no RL agents or training stack. It’s a good fit for YAPPING.

### Why this fork

- **Gymnasium-compatible** (modern RL env API).
- **Minimal**: only ygoenv + assets; no ygoai, JAX, or training scripts.
- **Integrated assets**: `make` downloads card databases and official MyCard scripts into `assets/` and `third_party/ygopro-scripts`.
- **Same C++/Lua core** as ygo-agent (ygopro-core); you get the same game logic with a lighter repo.

### Requirements

- **Linux** (per their README). The C++ engine (**ygopro-core**) does **not** build on macOS/arm64; use Linux, WSL, or a Linux container to run the simulator.
- **Python**
- **xmake** — [install](https://xmake.io/#/getting_started)
- System packages: `libsqlite3-dev`, `git`, `build-essential`

### Where to clone

**Recommended:** put **ygo-env inside yapping** so you can edit it easily:

```
yapping/
├── vendor/
│   └── ygo-env/          ← clone here (git clone ... vendor/ygo-env)
├── brain/
├── mouth/
...
```

- Scripts and docs assume `YGO_ENV_ROOT` = `yapping/vendor/ygo-env` by default (no env var needed when using the run script).
- `vendor/` is in `.gitignore`; remove that line if you want to commit your ygo-env fork.

To clone and build:

```bash
cd /path/to/yapping
mkdir -p vendor
git clone https://github.com/izzak98/ygo-env.git vendor/ygo-env
cd vendor/ygo-env
xmake f -m release -y
xmake
make
```

If you prefer a sibling repo instead, clone to e.g. `~/Projects/ygo-env` and set `export YGO_ENV_ROOT=/path/to/ygo-env`.

### Setup

1. **Clone and build** (from yapping root, into `vendor/ygo-env`)

   ```bash
   cd /path/to/yapping
   mkdir -p vendor
   git clone https://github.com/izzak98/ygo-env.git vendor/ygo-env
   cd vendor/ygo-env
   xmake f -m release -y
   xmake
   make
   ```

   This will:

   - Build the C++ engine and Python bindings.
   - Download card databases and text files into `assets/locale/en` and `assets/locale/zh`.
   - Clone official scripts into `third_party/ygopro-scripts` and link them to `scripts/script`.

2. **Run from a directory that has Lua scripts**

   When you run code that uses the environment, a **symlink to `third_party/ygopro-scripts` must exist in the directory you run from** (so the engine can find the Lua card scripts). Either run your Python from inside `ygo-env`, or create a symlink from your run directory to `ygo-env/third_party/ygopro-scripts`.

3. **Quick check**

   ```bash
   python - <<'PY'
   import ygoenv
   print("ygoenv loaded successfully:", ygoenv.__name__)
   PY
   ```

4. **Usage example**

   See `example/test_init.py` in the ygo-env repo.

### Wiring ygo-env into YAPPING

- **`vocal_chords/environment.py`**: Create the env using ygoenv’s API (Gymnasium-style).
- **`vocal_chords/wrapper.py`**: Wrap it so YAPPING sees `reset(deck_path, hand?)`, `get_legal_actions()`, `step(action)`.
- **`vocal_chords/actions.py`**: Map between ygoenv’s action encoding and your high-level actions.

Put your decks in `yapping/scripture/decks/` and pass the path to the wrapper when creating the env. For how cards are loaded (cdb vs code list vs Lua scripts), see **[docs/CARDS_CDB_AND_SCRIPTS.md](CARDS_CDB_AND_SCRIPTS.md)**. You can reuse or symlink `ygo-env`’s assets (e.g. `cards.cdb`) with `yapping/scripture/` if you want a single place for card data.

### Run the Hand Simulator (raw data)

After ygo-env is built, you can run YAPPING’s **Hand Simulator**: draw 5, list the first 10 legal actions. This confirms the bridge works before you build the full combo map.

```bash
# From yapping root; run script uses vendor/ygo-env by default
./scripts/run_hand_sim.sh scripture/decks/YourDeck.ydk
```

Or manually (e.g. from Linux after building the engine):

```bash
cd /path/to/yapping
export YGO_ENV_ROOT="$(pwd)/vendor/ygo-env"
cd vendor/ygo-env
python -m mouth.cli hand-sim --deck "$YGO_ENV_ROOT/assets/deck/Branded.ydk" --ygo-env "$YGO_ENV_ROOT"
```

You should see the current hand (indices) and the first 10 legal actions. Next step is Path A (best path) or Path B (full combo map); see **docs/COMBO_MAP_GOALS.md**.

**From the yapping repo** you can also run: `./scripts/run_hand_sim.sh [deck.ydk]` (sets `YGO_ENV_ROOT` and uses a deck from ygo-env if none given). On macOS the engine will not run until built on Linux/WSL.

---

## Option 2: sbl1996/ygo-agent (full repo, pre-built binaries)

If you want **pre-built binaries** (no compile) or the **full RL stack** (training, JAX, etc.), use the original **[sbl1996/ygo-agent](https://github.com/sbl1996/ygo-agent)**.

- **Quick start (Ubuntu 22.04+)**: Pre-built `.so` for cp310/cp311/cp312; no xmake needed. See their README “Quick start”.
- **Build from source**: `xmake f -y` then `make dev` (needs JAX, flax, etc.).
- Heavier than ygo-env (ygoai, scripts/, training, eval).

Use this if you’re on supported Linux and want to avoid building, or if you plan to use their agents/tooling.

---

## Option 3: Build ygopro-core yourself and bind to Python

If you don’t use either repo, you can build **[Fluorohydride/ygopro-core](https://github.com/Fluorohydride/ygopro-core)** and expose it via your own or third-party Python bindings (e.g. [hinihatetsu/ygo-core-python](https://github.com/hinihatetsu/ygo-core-python)). More work; only needed for maximum control or custom integration.

---

## Summary

| Goal | Action |
|------|--------|
| **Use the engine YAPPING is designed for** | Set up **[izzak98/ygo-env](https://github.com/izzak98/ygo-env)** (Option 1); implement `vocal_chords` against its Gymnasium env. |
| **No compile, Ubuntu 22.04** | Use **[sbl1996/ygo-agent](https://github.com/sbl1996/ygo-agent)** with pre-built binary (Option 2). |
| **Custom/core-only** | Build ygopro-core and bindings yourself (Option 3). |

Once the engine is set up, Lua runs inside the core; you don’t set up a Lua environment in Python—you set up the **engine interface** (ygo-env or ygo-agent’s ygoenv) that uses that core.
