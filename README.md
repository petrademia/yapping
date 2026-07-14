# YAPPING

**Yet Another Program for Parsing Interactive Game Nodes**

YAPPING is an independent Yu-Gi-Oh combo-search project built on top of a
maintained OCGCore adapter. Its focus is deterministic duel execution, exact
legal-action decoding, and search over real game states. Reinforcement
learning may later guide search, but it is not the current training target.

YAPPING is unofficial and is not affiliated with or endorsed by Konami,
Shueisha, or the maintainers of the referenced simulator projects.

## Architecture

```text
objective function
       |
bounded combo search
       |
YAPPING engine contract
       |
original native OCGCore adapter
       |
card database + Lua scripts
```

The initial search replays every candidate sequence from the same seed. This
is intentionally simple and deterministic. State cloning, parallel search,
and learned heuristics come after engine correctness.

## Engine choice

The adapter targets these aligned revisions:

- `Fluorohydride/ygopro-core`:
  `db4fd16a99991802511b9a89e0025dd2f51f5e36`
- `Fluorohydride/ygopro-scripts`:
  `72a1be24bb5a4eab9af3a71e53561abcd467aff6`

The core is fetched during the native build and is not stored in this
repository. Card scripts and `cards.cdb` are runtime inputs supplied by the
user.

## Native adapter

`yapping._ocgcore.Duel` currently supports:

- deterministic two-player duel creation and deck loading;
- SQLite `cards.cdb` card-data callbacks;
- global and per-card Lua script loading;
- idle, chain, yes/no, option, position, zone, card, sum, and toggle decisions;
- legal actions that retain player, card, location, sequence, and description;
- field counts and a binary field-state key.

The main integration fixture executes the complete deterministic line in
[`combos/albaz_swordsoul_full.yaml`](combos/albaz_swordsoul_full.yaml), including:

```text
Fallen of the White Dragon -> Titaniklad
  -> two Synchro summons and two Fusion summons
  -> ordered chain construction and reverse resolution
  -> Dogmatika Ecclesia -> The Fallen & The Virtuous
  -> Devours the Dogma -> Mercourier
  -> Set Branded Retribution
  -> both End Phase return effects
```

Run `python tools/trace_albaz_combo.py` for a prompt-by-prompt trace. The full
fixture test runs when `assets/cards.cdb` and the adjacent
`fluorohydride-ygopro-scripts` checkout are available; otherwise it is skipped.
Unsupported protocol messages raise an explicit error, and new prompt types are
added only when canonical fixtures require them.

## Development

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[test]'
pytest
```
