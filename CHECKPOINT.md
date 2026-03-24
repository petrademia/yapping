# Combo Recording Checkpoint
**Date:** 2026-03-24
**Branch:** main
**Seed used:** 18

---

## Status: COMPLETE (engine-actual path recorded)

`data/combos/branded_full_combo.json` is written with all 13 real engine sigs.

---

## What Was Done

### Infrastructure (all committed)
- `script/` symlink at yapping root → `vendor/ygo-env/script/` ← **CRITICAL: must exist or engine can't find Lua scripts**
- `data/decks/Branded.ydk` — Granguignol (24915933) added, CRLF stripped
- Modules renamed: `vocal_chords→engine`, `mouth→cli`, `scripture→data`
- `brain/combo.py` — combo runner (sig+label hybrid)
- `cli/cli.py` — `combo-run` / `combo-record` commands
- `brain/search.py` — transposition detection

### Engine Discoveries (important for future work)

| Issue | Detail |
|---|---|
| Cartesia (95515790) | **No Lua script** — can be material but her effects don't fire |
| Branded Fusion material list | FotWD & FoAlbaz don't appear (engine pools all deck cards; filtering bug) |
| Albion's re-fusion `filter2` | `IsLevelBelow(8)` → excludes Granguignol (Level 8) |
| Step 14 `select_card` | Mirrorjade's quick effect: cost = send Fusion from extra deck to GY |

### Completed Recipe: 13 Steps (seed 18)

```
 1. Activate Branded Fusion (effect 1)   sig=[57,23,232,1,8,0,1,0,0,0,0,0]
 2. Place → s1                            sig=[0,0,0,11,0,0,0,0,0,0,8,0]
 3. Select Albion the Branded Dragon      sig=[65,46,109,3,0,0,0,0,0,0,0,0]
 4. Select Blazing Cartesia               sig=[11,53,75,9,0,0,0,0,0,0,0,0]
 5. Select Gold Sarcophagus (2nd mat)     sig=[2,40,66,9,0,0,0,0,0,0,0,0]
 6. Place → m1                            sig=[0,0,0,11,0,0,0,0,0,0,1,0]
 7. Set position: face-up ATK             sig=[0,46,109,5,0,0,0,0,1,0,0,0]
 8. Yes (Albion trigger effect)           sig=[58,46,109,6,8,0,36,0,0,0,0,0]
 9. Select Mirrorjade                     sig=[74,23,202,3,0,0,0,0,0,0,0,0]
10. Select Albion (material for MJ)       sig=[58,46,109,9,0,0,0,0,0,0,0,0]
11. Place → m1                            sig=[0,0,0,11,0,0,0,0,0,0,1,0]
12. Set position: face-up ATK             sig=[0,23,202,5,0,0,0,0,1,0,0,0]
13. Select Alba-Lenatus (MJ cost)         sig=[72,1,228,3,0,0,0,0,0,0,0,0]
```
→ Returns to main phase idle with Mirrorjade on field.

---

## Steps to Reproduce from Scratch

```bash
cd /home/petru/code/yapping

# 1. Ensure script/ symlink exists
ls -la script/     # should be: script -> vendor/ygo-env/script
# If missing:
ln -sfn vendor/ygo-env/script script

# 2. Run the combo (label-only, will fuzzy match)
.venv/bin/python -m cli.cli combo-run \
  --recipe data/combos/branded_full_combo.json \
  --seed 18

# 3. Or run the debug trace scripts directly
.venv/bin/python /tmp/full_trace.py 2>/dev/null
.venv/bin/python /tmp/trace_combo2.py 2>/dev/null
.venv/bin/python /tmp/trace_combo3.py 2>/dev/null
```

---

## Known Issues / Next Steps

1. **Granguignol path**: Albion's Lua `filter2` uses `IsLevelBelow(8)`, blocking Level-8 Granguignol.
   - Fix: Modify `c87746184.lua` to change `IsLevelBelow(8)` → `IsLevelBelow(9)` (or remove level filter)
   - OR: Use Branded Fusion to fuse Granguignol directly (Cartesia + LIGHT/DARK, different Lua)

2. **Cartesia effects**: Need `c95515790.lua` in the scripts directory. The card exists in third_party/ygopro-scripts path as absent — newer card not yet in engine script set.
   - Fix: Add the script from the OCG script repo

3. **FotWD as Branded Fusion material**: FotWD (73819701) has `aux.AddCodeList(c,68468459)` so it IS a valid Fallen of Albaz substitute. But the engine's `GetFusionMaterial` pools all deck cards equally, and `SelectFusionMaterial` filtering may be bugged.
   - Fix: Debug why `SelectFusionMaterial` skips FotWD/FoAlbaz when they should pass Albion's material check.

4. **Full TCG combo**: Not achievable with current engine Lua set. Would require fixes 1+2+3 above.

---

## File Reference
- Recipe: `data/combos/branded_full_combo.json`
- Deck: `data/decks/Branded.ydk`
- Debug traces: `/tmp/trace_combo.py`, `/tmp/trace_combo2.py`, `/tmp/trace_combo3.py`
- Engine scripts: `vendor/ygo-env/scripts/script/` (checked out), `vendor/ygo-env/third_party/ygopro-scripts/`
- Key Lua scripts: `script/c87746184.lua` (Albion), `script/c44362883.lua` (Branded Fusion), `script/c24915933.lua` (Granguignol)

---

## Addendum: 2026-03-25 Follow-up Findings

This section supersedes several assumptions above.

### Confirmed Fixes / Corrections

- `data/decks/Branded.ydk` now uses `95515789` for Blazing Cartesia instead of `95515790`.
- The earlier "Branded Fusion is offering random spells/traps as materials" issue was a `ygo-env` decode bug, not a core material-selection bug.
- Root cause was `MSG_SELECT_UNSELECT_CARD` in `vendor/ygo-env/ygoenv/ygoenv/ygopro/ygopro.h` not preserving the raw card code on `LegalAction`.
- Fix applied: set `la.cid_ = c_get_card_id(code)` in that adapter path.
- After that fix, the Branded line improved immediately:
  - Branded Fusion offers `Fallen of the White Dragon`
  - Albion offers `Granguignol the Dusk Dragon`
  - `Granguignol -> Albion the Shrouded Dragon` works
  - `Branded Sword` can add back `Fallen of the White Dragon` if Granguignol uses `Blazing Cartesia + Fallen of the White Dragon`

### Confirmed Runtime Behavior

- The exact post-addback idle state still does **not** offer `Activate Fallen of the White Dragon`.
- Raw idle payload confirmed:
  - FotWD appears in `summonable`
  - FotWD appears in `mset`
  - FotWD does **not** appear in `activate`
- So the missing FotWD hand ignition is below the Python/YAPPING layer.

### Core / Upstream Experiments

- `vendor/ygo-env` was switched to `mycard/ygopro-core` `0.0.4`.
- Scripts were already effectively on `mycard/ygopro-scripts`.
- The intended early combo branch still works on that core, but FotWD hand ignition is still missing.

### Important Debugging Pitfall Found

- For a while, debugging was being done against the wrong Python extension binary.
- At the time of that bug, the runtime Python was `.venv/bin/python` = Python `3.13.x`.
- That interpreter loads:
  - `vendor/ygo-env/ygoenv/ygoenv/ygopro/ygopro_ygoenv.cpython-313-x86_64-linux-gnu.so`
- Earlier rebuilds were producing:
  - `ygopro_ygoenv.cpython-314-x86_64-linux-gnu.so`
- That is why early core instrumentation appeared to "do nothing".
- `vendor/ygo-env` was later reconfigured with `.venv/bin` on `PATH`, and the correct `cp313` module was rebuilt.

### Python 3.14 Migration Status

- The workspace has now been migrated to Python `3.14`.
- `.python-version` is `3.14`.
- `.venv/bin/python` is Python `3.14.3`.
- `vendor/ygopro-adapter` now rebuilds and loads:
  - `vendor/ygopro-adapter/ygoenv/ygoenv/ygopro/ygopro_ygoenv.cpython-314-x86_64-linux-gnu.so`
- The Branded end-phase regression passes on the real `cp314` build, so the migration is viable.

### Current Best Understanding

- `ygo-env` is handing correct `card_data` to the core for the cards checked:
  - `35269905` (`Triple Tactics Thrust`) -> `type=2`
  - `73819701` (`Fallen of the White Dragon`) -> `type=33`
  - `68468459` (`Fallen of Albaz`) -> `type=33`
  - `sizeof(card_data)=80`
- So the adapter-to-core `card_data` handoff currently looks correct.
- Also, `register_card()` in the core calls `load_card_script(pcard->data.code)` before checking `is_load_script(data)`.
- Therefore a line like:
  - `Script not found: ./script/c35269905.lua`
  does **not** by itself prove `type` corruption. The core attempts a script load before the later gating check.

### Open Investigation

- The remaining real bug is still:
  - why FotWD's hand ignition effect never reaches idle `activate` after being returned to hand by `Branded Sword`
- The best next target is the core-side effect registration / activation pipeline for FotWD on the correct `cp313` runtime, now that:
  - the `MSG_SELECT_UNSELECT_CARD` decode bug is fixed
  - the right Python extension binary is being rebuilt and loaded
  - `card_data` handoff from `ygo-env` looks sane

### Files Touched During This Investigation

- `data/decks/Branded.ydk`
- `vendor/ygo-env/example/code_list.txt`
- `vendor/ygo-env/xmake.lua`
- `vendor/ygo-env/repo/packages/y/ygopro-core/xmake.lua`
- `vendor/ygo-env/ygoenv/ygoenv/ygopro/ygopro.h`

### Temporary Debug State

- `vendor/ygo-env/ygoenv/ygoenv/ygopro/ygopro.h` currently contains temporary debug logging for `card_data` reads.
- Cached `~/.xmake/.../ygopro-core` source also contains temporary debug instrumentation from this investigation.
- Before final cleanup or commit, those debug-only changes should be reviewed and either kept intentionally or reverted.
