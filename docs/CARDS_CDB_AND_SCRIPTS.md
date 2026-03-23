# How the engine loads cards (cdb, code list, scripts)

The ygo-env engine needs three things for each card it uses:

| What | Role |
|------|------|
| **cards.cdb** | SQLite database: card *data* (name, type, level, ATK/DEF, etc.). "What is this card?" |
| **code_list.txt** | Whitelist of card *codes* to load at init. Only codes in this file are loaded; if your deck uses a code not in the list, you get "Card not found". |
| **c{code}.lua** | Lua script: card *effects* and behavior. "What does this card do when played, destroyed, etc.?" |

## Card in cdb but not in code_list

The engine never loads it → **"Card not found"** when the deck or game references that code. YAPPING (1) merges your deck's codes into `example/code_list_merged.txt` at runtime and **also copies that over `example/code_list.txt`** so the engine sees the merged list even if it reads the default path, and (2) you can append those codes for good with `add-deck-codes-to-list` (see below).

## Card in cdb and code_list, but no script yet

The card *is* loaded (name, type, stats from the DB). There is no effect script, so:

- The card **exists** for the engine (no crash).
- It effectively behaves as a **vanilla** (no effect).
- When **building paths**, it can still be in hand/field/grave and be summoned or set.
- When you try to **activate** its effect, the core has nothing to run, so the card does nothing.

So: the card does nothing effect-wise until a script is added; path building can still see the card and use it as a body.

## Scripts

Scripts live under `scripts/script/` (e.g. `c76666602.lua`) and are usually from [mycard/ygopro-scripts](https://github.com/mycard/ygopro-scripts) or similar. If a card exists in cdb and has a script, adding it to the code list (or using a deck so the wrapper merges it) is enough for it to work fully.

## Adding deck codes to the list for good

**Setup scripts** (`./scripts/run_in_wsl.sh` and `./scripts/setup_wsl.sh`) automatically append the default deck’s card codes (Branded.ydk) to `example/code_list.txt` after `make assets scripts`. So on a fresh clone, running setup again repopulates the list and you don’t get “Card not found” for that deck. The helper is `scripts/append_deck_codes_to_code_list.py` (stdlib only).

To add another deck’s codes manually, run once:

```bash
# From yapping root; uses YGO_ENV_ROOT or --ygo-env
python -m cli.cli add-deck-codes-to-list --deck vendor/ygo-env/assets/deck/Branded.ydk
# or your deck
python -m cli.cli add-deck-codes-to-list --deck data/decks/MyDeck.ydk
```

This appends any codes from the deck that are missing from `example/code_list.txt` (with `1` or `0` depending on whether `c{code}.lua` exists). After that, that deck’s cards are in the list for good until you re-clone ygo-env (then run the command again or re-apply your code list).

## Mapping codes to names (for deck builder UI)

To get a **code → name** map so you can look up culprits (e.g. "Card not found: 76666602") in your deck builder:

```bash
# From yapping root; uses YGO_ENV_ROOT or --ygo-env for cards.cdb
python -m cli.cli export-card-names

# Writes data/card_code_to_name.json by default. To write CSV:
python -m cli.cli export-card-names --format csv --out data/card_code_to_name.csv

# Custom cdb path
python -m cli.cli export-card-names --cdb /path/to/cards.cdb --out names.json
```

JSON format: `{ "76666602": "Number 76: Harmonizer Gradielle", ... }` (string keys so codes are easy to look up).
