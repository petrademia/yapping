# Setting up the engine that uses OCGCore

YAPPING needs a **headless** Yu-Gi-Oh! adapter that uses OCGCore for correct card logic. The recommended setup for this project is the vendored **`yapcore`** in `vendor/yapcore`, which carries YAPPING-oriented build fixes and local decoder patches on top of upstream `ygopro-core` and `ygopro-scripts`.

---

## Option 1: **yapcore** (recommended)

`yapcore` is the engine repo used with YAPPING: a maintained adapter/runtime focused on the environment and engine interface, with upstream `mycard/ygopro-core` and `mycard/ygopro-scripts` kept as dependencies.

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

**Recommended:** put **yapcore inside yapping** so you can edit it easily:

```
yapping/
├── vendor/
│   └── yapcore/   ← clone here (git clone ... vendor/yapcore)
├── brain/
├── cli/
...
```

- Scripts and docs assume `YGO_ENV_ROOT` = `yapping/vendor/yapcore` by default (no env var needed when using the run script).
- `vendor/` is in `.gitignore`; see **Locking yapcore changes** below if you want those patches in Git.

### Locking yapcore changes (fork + commit)

`vendor/yapcore` is usually a **separate Git clone** (it has its own `.git`). YAPPING’s root repo ignores `vendor/*`, so **xmake / recipe / `ygopro.h` edits are committed inside that clone**, not in `yapping` unless you use a submodule.

1. **Commit in the engine repo** (paths are examples — adjust to what you changed):

   ```bash
   cd vendor/yapcore
   git status
   git add xmake.lua \
     repo/packages/y/ygopro-core/xmake.lua \
     ygoenv/ygoenv/ygopro/ygopro.h
   git commit -m "build: pin Lua 5.3, link ygopro-core+lua group, core API shims"
   ```

2. **Push to your fork** (recommended) so teammates can clone your fork instead of upstream:

   ```bash
   git remote add myfork https://github.com/<you>/yapcore.git   # once
   git push -u myfork main    # or your branch name
   ```

3. **In YAPPING**, point people at that fork/branch in this doc or in chat, e.g.  
   `git clone <your-adapter-repo> vendor/yapcore`

**Optional — track `vendor/yapcore` from the YAPPING repo:** use a **git submodule** (`git submodule add <url> vendor/yapcore`) and remove or narrow the `vendor/*` ignore rule so the submodule pointer is committed. That records an exact commit of the engine in every YAPPING revision.

If you prefer a sibling repo instead of `vendor/yapcore`, clone to e.g. `~/Projects/yapcore` and set `export YGO_ENV_ROOT=/path/to/yapcore`.

### Setup

1. **Clone and build** (from yapping root, into `vendor/yapcore`)

   ```bash
   cd /path/to/yapping
   mkdir -p vendor
   git clone <your-adapter-repo> vendor/yapcore
   cd vendor/yapcore
   PATH=/path/to/yapping/.venv/bin:$PATH xmake f -m release -y
   PATH=/path/to/yapping/.venv/bin:$PATH xmake
   make
   ```

   After `git pull` in `vendor/yapcore` when build recipes changed, force a clean configure and rebuild **only** the Python extension:

   ```bash
   cd vendor/yapcore
   PATH=/path/to/yapping/.venv/bin:$PATH xmake f -c -m release -y
   PATH=/path/to/yapping/.venv/bin:$PATH xmake b -r ygopro_ygoenv   # or: make build_ext
   ```

   For this workspace, the project venv is Python `3.14`, so the extension that must be produced and loaded is:

   - `vendor/yapcore/ygoenv/ygoenv/ygopro/ygopro_ygoenv.cpython-314-x86_64-linux-gnu.so`

   Do not mix interpreter versions. If both `cp313` and `cp314` `.so` files are present and you rebuild only the wrong one, Python will keep importing the stale interpreter-matching binary and native debugging/fixes will appear to have no effect.

   This will:

   - Build the C++ engine and Python bindings.
   - Download card databases and text files into `assets/locale/en` and `assets/locale/zh`.
   - Clone official scripts into `third_party/ygopro-scripts` and link them to `scripts/script`.

2. **Run from a directory that has Lua scripts**

   When you run code that uses the environment, a **symlink to `third_party/ygopro-scripts` must exist in the directory you run from** (so the engine can find the Lua card scripts). Either run your Python from inside `yapcore`, or create a symlink from your run directory to `yapcore/third_party/ygopro-scripts`.

3. **Quick check**

   ```bash
   python - <<'PY'
   import ygoenv
   print("ygoenv loaded successfully:", ygoenv.__name__)
   PY
   ```

4. **Usage example**

   See `example/test_init.py` in the yapcore repo.

### Python dependencies (single venv)

YAPPING uses Python dependencies from your **repo venv** (e.g. `./.venv` at the project root).
You typically do **not** want a separate venv inside `vendor/`.

From the `yapping/` repo root:

```bash
# 1) create/activate a venv (example shown; adjust as you prefer)
python -m venv .venv
source .venv/bin/activate

# 2) repo deps
pip install -r requirements.txt

# 3) install ygoenv Python bindings (pulls gymnasium + other deps)
pip install -e vendor/yapcore/ygoenv

# 4) verify imports
python -c "import ygoenv; import gymnasium; print('ygoenv + gymnasium OK')"
```

### Wiring yapcore into YAPPING

- **`engine/environment.py`**: Create the env using ygoenv’s API (Gymnasium-style).
- **`engine/wrapper.py`**: Wrap it so YAPPING sees `reset(deck_path, hand?)`, `get_legal_actions()`, `step(action)`.
- **`engine/actions.py`**: Map between ygoenv’s action encoding and your high-level actions.

Put your decks in `yapping/data/decks/` and pass the path to the wrapper when creating the env. For how cards are loaded (cdb vs code list vs Lua scripts), see **[docs/CARDS_CDB_AND_SCRIPTS.md](CARDS_CDB_AND_SCRIPTS.md)**. You can reuse or symlink yapcore’s assets (e.g. `cards.cdb`) with `yapping/data/` if you want a single place for card data.

### Run the Hand Simulator (raw data)

After yapcore is built, you can run YAPPING’s **Hand Simulator**: draw 5, list the first 10 legal actions. This confirms the bridge works before you build the full combo map.

```bash
# From yapping root; run script uses vendor/yapcore by default
./scripts/run_hand_sim.sh data/decks/YourDeck.ydk
```

Or manually (e.g. from Linux after building the engine):

```bash
cd /path/to/yapping
export YGO_ENV_ROOT="$(pwd)/vendor/yapcore"
cd vendor/yapcore
python -m cli.cli hand-sim --deck "$YGO_ENV_ROOT/assets/deck/Branded.ydk" --engine-root "$YGO_ENV_ROOT"
```

You should see the current hand (indices) and the first 10 legal actions. Next step is Path A (best path) or Path B (full combo map); see **docs/COMBO_MAP_GOALS.md**.

**From the yapping repo** you can also run: `./scripts/run_hand_sim.sh [deck.ydk]` (sets `YGO_ENV_ROOT` and uses a deck from yapcore if none given). On macOS the engine will not run until built on Linux/WSL.

---

## Option 2: sbl1996/ygo-agent (full repo, pre-built binaries)

If you want **pre-built binaries** (no compile) or the **full RL stack** (training, JAX, etc.), use the original **[sbl1996/ygo-agent](https://github.com/sbl1996/ygo-agent)**.

- **Quick start (Ubuntu 22.04+)**: Pre-built `.so` for cp310/cp311/cp312; no xmake needed. See their README “Quick start”.
- **Build from source**: `xmake f -y` then `make dev` (needs JAX, flax, etc.).
- Heavier than yapcore (ygoai, scripts/, training, eval).

Use this if you’re on supported Linux and want to avoid building, or if you plan to use their agents/tooling.

---

## Option 3: Build ygopro-core yourself and bind to Python

If you don’t use either repo, you can build **[Fluorohydride/ygopro-core](https://github.com/Fluorohydride/ygopro-core)** and expose it via your own or third-party Python bindings (e.g. [hinihatetsu/ygo-core-python](https://github.com/hinihatetsu/ygo-core-python)). More work; only needed for maximum control or custom integration.

---

## Summary

| Goal | Action |
|------|--------|
| **Use the engine YAPPING is designed for** | Set up **[petrademia/yapcore](https://github.com/petrademia/yapcore)** in `vendor/yapcore` (Option 1); implement `engine` against its Gymnasium env. |
| **No compile, Ubuntu 22.04** | Use **[sbl1996/ygo-agent](https://github.com/sbl1996/ygo-agent)** with pre-built binary (Option 2). |
| **Custom/core-only** | Build ygopro-core and bindings yourself (Option 3). |

Once the engine is set up, Lua runs inside the core; you don’t set up a Lua environment in Python—you set up the **engine interface** (yapcore or ygo-agent’s ygoenv) that uses that core.
