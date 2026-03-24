# YAPPING

YAPPING is a Yu-Gi-Oh combo search project built on top of a maintained OCGCore adapter. The current focus is deterministic duel execution, exact legal-action decoding, and search over real game states, not RL training.

## Architecture

1. **Rules:** upstream `ygopro-core` plus Lua scripts from `ygopro-scripts`
2. **Adapter:** local `ygopro-adapter` in `vendor/ygopro-adapter`
3. **Search:** Python combo tracing, replay, and DFS-style exploration

## Current direction

- make the adapter trustworthy for search-critical prompts
- replay exact combo lines deterministically
- add regression traces for known lines before expanding DFS
- keep RL compatibility incidental, not a project goal

## Project structure

```text
yapping/
├── brain/          # Search, replay, heuristics
├── engine/         # Adapter wrapper and action decoding
├── cli/            # CLI entry points
├── data/           # Decks, combo recipes, names
├── docs/           # Engine and debugging notes
├── scripts/        # Setup, regression, helper scripts
├── vendor/         # ygopro-adapter and related notes
└── main.py
```

## Setup

Use Linux/WSL. Build the adapter against the same Python minor version you run YAPPING with.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cd vendor/ygopro-adapter
PATH=/home/petru/code/yapping/.venv/bin:$PATH xmake f -c -m release -y
PATH=/home/petru/code/yapping/.venv/bin:$PATH xmake b -r ygopro_ygoenv
make assets scripts
pip install -e ygoenv
```

For the current workspace, `.venv/bin/python` is now Python `3.14`, so the loaded native module must be the `cp314` build. The important rule is still ABI matching: rebuild `ygopro-adapter` with the same interpreter you use to run the repo, or Python will keep importing a stale interpreter-matching extension. See [vendor/README.md](/home/petru/code/yapping/vendor/README.md) and [docs/ENGINE_SETUP.md](/home/petru/code/yapping/docs/ENGINE_SETUP.md).

## Useful commands

```bash
./scripts/run_hand_sim.sh data/decks/Branded.ydk
python scripts/regression_branded_end_phase.py
python vendor/ygopro-adapter/scripts/check_upstreams.py
```

## Notes

- `vendor/ygo-env` is now a compatibility symlink to `vendor/ygopro-adapter`
- the adapter repo is maintained separately from the main repo
- temporary one-off debug scripts still exist in the root; they should not be treated as stable interfaces
