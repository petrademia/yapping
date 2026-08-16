# Ignis second engine (edo9300)

Status: draft, 2026-08-16.

## Goal

Ship edo9300/ygopro-core as a **second** native module beside the existing
Fluorohydride adapter. Fluoro stays the default oracle. The first proof is
not Ekhajar coverage and not Phase 1 fork speed. It is:

> Albaz search on Ignis matches Fluoro.

Match is a bounded opening search, `--replay-mode cursor`, interruption
`ash`. Compare `score`, `complete`, and the principal line as
`(kind, card)` strings (`action_name`, already `kind:card` or bare `kind`).

Do not require identical `state_key` bytes, prompt `description` integers,
visited-state counts, or wall-clock.

## Why a second module

CardScripts target edo9300's C API (`OCG_CreateDuel`, `OCG_DuelProcess`,
`OCG_DuelGetMessage`, `OCG_DuelSetResponse`, …), Lua 5.3, and Ignis
`utility.lua`. They are not drop-in on Fluorohydride `ocgapi.h` and Lua
5.4.7. Mixing script trees or card databases in one duel is out of scope.

A tag swap on the current `FetchContent` ocgcore pin would replace the
oracle that existing fixtures reproduce. This slice adds a module instead.

## Python surface

Callers keep using a `Duel` object. The Ignis class is a different C++
type in a different extension, with the same methods and argument names
as `yapping._ocgcore.Duel`:

| Method | Contract |
| ------ | -------- |
| `Duel(database, scripts)` | Paths to that engine's cdb and script tree |
| `reset(deck0, deck1, extra0=[], extra1=[], seed=0, start_hand=5, set0=[], set1=[])` | Returns a decision dict |
| `step(index)` | Apply `decision["actions"][index]`, return the next decision |
| `counts()` | Zone counts (`hand0`, `monster0`, …) |
| `cards(player, location)` | Card codes in that zone |
| `state_key()` | Opaque bytes for that engine. Not comparable across engines |

Decision dict keys stay `actions`, `player`, `turn`, `phase`, `winner`,
`events`. Each action keeps `kind`, `card`, `controller`, `location`,
`sequence`, `description`, `cards`. Kind strings stay the Fluoro vocabulary
(`activate`, `summon`, `pass`, `chain`, `select_card`, …) so
`ReplayCursor`, `legal()`, and `minimax_replay` do not branch on engine.

`yapping._ocgcore` is unchanged. New extension: `yapping._ocgcore_ignis`.
Do not import Ignis from `yapping/__init__.py`.

Factory (new small module, e.g. `src/yapping/ocg.py`):

- `make_duel("fluoro" | "ignis")` constructs the matching `Duel` with that
  engine's default database and script paths.
- Do not construct Fluoro and Ignis `Duel` objects in one process. Each
  module has its own `active_adapter`; that does not serialize across
  `.so` files. Comparison uses two subprocesses.
- Import only the requested extension.

`--engine {fluoro,ignis}` (default `fluoro`) on `tools/search_opening.py`
and `tools/trace_albaz_combo.py` only. Other tools stay Fluoro-only.

## Native build

`CMakeLists.txt` keeps the Fluoro stack: Lua 5.4.7, Fluorohydride
`ee5c2ec`, `_ocgcore`.

Add a parallel stack linked **only** into `_ocgcore_ignis`:

- Lua 5.3 tarball hash in `CMakeLists.txt` (CardScripts are not Lua 5.4).
- `edo9300/ygopro-core` commit pin in `CMakeLists.txt`.
- New `cpp/adapter_ignis.cpp`. Do not compile this file into `_ocgcore`.

Both modules are statically linked. Set hidden symbol visibility on the
Ignis module (and Fluoro if needed) so `lua_*` / `OCG_*` / `create_duel`
do not collide if a process ever loads both extensions.

Fluoro `cpp/adapter.cpp` is not refactored in this slice except as required
to keep building. Decoder logic may be duplicated in `adapter_ignis.cpp`.
Share it later only if message layouts are proven identical.

edo9300 talks through `ocgapi.h` / `ocgapi_types.h`. The adapter maps that
C API onto the Python `Duel` contract above. `common.h` stays an
implementation detail.

## Assets

Two closed stacks. Never pass Fluoro scripts to the Ignis `Duel`, or
BabelCDB to the Fluoro `Duel`.

| Engine | Database | Scripts |
| ------ | -------- | ------- |
| Fluoro | `yapping/assets/cards.cdb` (existing MyCard pin) | sibling `fluorohydride-ygopro-scripts` @ `090e881` |
| Ignis | `yapping/assets/ignis/cards.cdb` (pinned BabelCDB `cards.cdb`) | sibling `projectignis-card-scripts` at a commit pin |

Albaz fixture card ids are official passwords. The same deck list feeds
both engines. MAPPING aliases are not used here.

New fetch script, same shape as `tools/fetch_cards_db.sh`: URL, commit,
sha256, install into `assets/ignis/cards.cdb`. CardScripts stay a sibling
clone plus checkout, documented next to the Fluoro clone in README.

Missing Ignis assets: tests skip, same pattern as missing Fluoro scripts.
This slice does not add a CardScripts clone to GitHub Actions.

## Comparison protocol

Two subprocesses. One engine per process. `--replay-mode cursor` only.

### Gate

`tools/trace_albaz_combo.py --engine ignis` prints `FULL COMBO COMPLETE`.

If this gate fails, stop. Do not run the search comparison. A scripted
line that already diverges makes a minimax diff unreadable.

### Search

```bash
PYTHONPATH=src:tools python tools/search_opening.py ash \
  --engine fluoro --replay-mode cursor --max-nodes 2000 --max-depth 180
PYTHONPATH=src:tools python tools/search_opening.py ash \
  --engine ignis --replay-mode cursor --max-nodes 2000 --max-depth 180
```

Default fixture hand and Ecclesia copies. Fluoro Ash completes around 965
visited states today, so 2000 nodes is enough for `complete` to be
achievable on Fluoro. The same budget is used on Ignis.

### Equality

From each run, take `result.score`, `result.complete`, and
`final.actions` (the `action_name` tuple already printed as `actions:`).

Pass if all three match. Fail if any differs.

On failure, the test writes both payloads and the first index where the
action tuples differ. That index is the artifact.

### What to fix vs what to report

- Adapter/decoder bug (wrong kind, dropped prompt, bad response bytes):
  fix `adapter_ignis.cpp`.
- Script or core semantics differ (same kind vocabulary, different legal
  set or different chosen line): **stop**. Do not patch CardScripts,
  Fluoro scripts, or evaluator weights to force agreement. Record the
  divergence. This slice is done as an experiment, not as a greenwashed
  match.

`state_key`, `description`, `events`, visited counts, and runtime are
logged, not asserted.

## Tests

1. Ignis module loads, `make_duel("ignis")` constructs, `reset` of a tiny
   two-card deck returns a decision with `actions`. Skip without assets.
2. Gate: subprocess `trace_albaz_combo.py --engine ignis` contains
   `FULL COMBO COMPLETE`. Skip without assets.
3. Comparison: both engines, Ash, 2000/180/cursor, assert score /
   complete / `final.actions`. Skip without **both** stacks.

Existing Fluoro fixtures stay on `_ocgcore` and must keep passing.

## Non-goals

- Replacing Fluoro as default.
- `--engine` on every tool.
- Phase 1 `--replay-mode fork` on Ignis, or using Ignis to unstick Darwin
  fork/SQLite.
- Ekhajar / pre-release placeholder ids.
- Speed claims.
- Windows.
- Sharing one process-wide Lua or sqlite connection across engines.
- Core clone/serialize.
- Changing minimax, ReplayCursor, or evaluator weights.

## Exit

- `_ocgcore_ignis` builds next to `_ocgcore`.
- `--engine ignis` runs Albaz `search_opening` with `cursor`.
- Fluoro fixtures still pass on Fluoro.
- Either the Ash comparison asserts equal, or the first `(kind, card)`
  divergence is recorded and this spec's match hypothesis is rejected.

DIRECTION.md's earlier Ignis smoke ("load a card Fluoro lacks") is a later
slice. This spec's exit replaces it as the first Ignis proof.

## Relationship to Phase 1

Phase 1 stays Fluoro prefix-reuse replay. This slice does not move that
exit, does not change `--replay-mode` defaults, and does not treat Ignis
as a faster replay engine.
