# Ignis second engine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `yapping._ocgcore_ignis` beside Fluoro and prove Albaz Ash search on Ignis against Fluoro (`score`, `complete`, `(kind, card)` line), or record the first divergence.

**Architecture:** Second statically linked pybind module talks to edo9300 via `OCG_CreateDuel` / `OCG_DuelProcess` / `OCG_DuelGetMessage` / `OCG_DuelSetResponse`. Python callers see the same `Duel` methods as `_ocgcore`. `make_duel("fluoro"|"ignis")` picks the extension and that engine's cdb/scripts. Comparison runs two subprocesses. Fluoro remains default.

**Tech Stack:** CMake FetchContent, Lua 5.3.6, edo9300/ygopro-core `9a0c558`, pybind11, existing `ReplayCursor` / `search_opening.py` / `trace_albaz_combo.py`.

## File map

| File | Role |
| ---- | ---- |
| `CMakeLists.txt` | Second Lua 5.3 lib, edo9300 static lib, `_ocgcore_ignis` module |
| `cpp/adapter_ignis.cpp` | edo9300 adapter; same Python `Duel` surface; decoder ported from `cpp/adapter.cpp` |
| `src/yapping/ocg.py` | `make_duel(engine)` and default asset paths |
| `tools/fetch_ignis_cards_db.sh` | Pin BabelCDB `cards.cdb` into `assets/ignis/cards.cdb` |
| `tools/trace_albaz_combo.py` | `--engine`, default Fluoro |
| `tools/search_opening.py` | `--engine`, default Fluoro |
| `tests/test_ocgcore_ignis.py` | Module load, tiny duel, combo gate, Ash comparison |
| `README.md`, `DIRECTION.md` | Clone pins, dual-oracle exit |

Do not edit `cpp/adapter.cpp` except if Fluoro stops building. Do not import `_ocgcore_ignis` from `src/yapping/__init__.py`.

## Global Constraints

- Fluoro stays the default oracle (`--engine fluoro`).
- Never pass Fluoro scripts to the Ignis `Duel`, or BabelCDB to the Fluoro `Duel`.
- Same Python methods as `yapping._ocgcore.Duel`: `reset`, `step`, `counts`, `cards`, `state_key`.
- Decision/action dict keys and kind strings stay the Fluoro vocabulary.
- `--engine` only on `search_opening.py` and `trace_albaz_combo.py`.
- Comparison uses `--replay-mode cursor`, Ash, `--max-nodes 2000`, `--max-depth 180`, two subprocesses.
- Assert `score`, `complete`, and `final.actions` (`kind:card` / bare `kind`). Do not assert `state_key`, `description`, visited counts, or runtime.
- Adapter/decoder bugs: fix `adapter_ignis.cpp`. Script/core semantic mismatch: stop, write the divergence artifact, do not patch scripts or weights.
- No `--engine` on other tools. No Ignis fork mode. No Ekhajar. No CI CardScripts clone.
- Do not construct Fluoro and Ignis `Duel` objects in one process.
- User did not ask for commits; do not commit unless asked.

### Pins (lock these in the named files)

| Piece | Pin |
| ----- | --- |
| Lua 5.3.6 tarball | `https://www.lua.org/ftp/lua-5.3.6.tar.gz` SHA256 `fc5fd69bb8736323f026672b1b7235da613d7177e72558893a0bdcd320466d60` |
| edo9300/ygopro-core | `9a0c558c2d686542f7914a6d529fd7aa57746aed` |
| ProjectIgnis/CardScripts | sibling `projectignis-card-scripts` @ `9a5738639924bbbf3b86c4599f3f7e70ea8711a6` |
| BabelCDB `cards.cdb` | commit `172462f1e7405c7544cc256471d3310df6e6b7c3`, SHA256 `061c2fbd1c541d66d5b06989a2c2a1ef4539a4f82802f31382e72a5955ef180d` |

---

### Task 1: Ignis asset fetch and path helpers

**Files:**
- Create: `tools/fetch_ignis_cards_db.sh`
- Create: `src/yapping/ocg.py`
- Modify: `README.md` (clone + fetch next to the Fluoro instructions)
- Test: `tests/test_ocgcore_ignis.py`

**Interfaces:**
- Consumes: repo layout (`assets/`, sibling script clones)
- Produces: `make_duel(engine: str)`, `engine_paths(engine: str) -> tuple[Path, Path]`, `ignis_assets_ready() -> bool`, `fluoro_assets_ready() -> bool`

- [ ] **Step 1: Write the failing factory tests** in `tests/test_ocgcore_ignis.py`.

```python
from pathlib import Path

import pytest

from yapping.ocg import (
    engine_paths,
    fluoro_assets_ready,
    ignis_assets_ready,
    make_duel,
)

REPO = Path(__file__).resolve().parents[1]


def test_engine_paths_do_not_cross_stacks():
    fluoro_cdb, fluoro_scripts = engine_paths("fluoro")
    ignis_cdb, ignis_scripts = engine_paths("ignis")
    assert fluoro_cdb == REPO / "assets" / "cards.cdb"
    assert ignis_cdb == REPO / "assets" / "ignis" / "cards.cdb"
    assert fluoro_scripts.name == "fluorohydride-ygopro-scripts"
    assert ignis_scripts.name == "projectignis-card-scripts"
    assert fluoro_cdb != ignis_cdb
    assert fluoro_scripts != ignis_scripts


def test_make_duel_rejects_unknown_engine():
    with pytest.raises(ValueError, match="engine"):
        make_duel("edo")


@pytest.mark.skipif(not fluoro_assets_ready(), reason="Fluoro cdb/scripts missing")
def test_make_duel_fluoro_returns_existing_adapter():
    duel = make_duel("fluoro")
    assert type(duel).__module__ == "yapping._ocgcore"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `PYTHONPATH=src .venv/bin/python -m pytest tests/test_ocgcore_ignis.py -v`

Expected: FAIL because `yapping.ocg` is missing.

- [ ] **Step 3: Implement `src/yapping/ocg.py` and the fetch script**

`src/yapping/ocg.py`:

```python
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
FLUORO_CDB = REPO / "assets" / "cards.cdb"
IGNIS_CDB = REPO / "assets" / "ignis" / "cards.cdb"
FLUORO_SCRIPTS = REPO.parent / "fluorohydride-ygopro-scripts"
IGNIS_SCRIPTS = REPO.parent / "projectignis-card-scripts"


def engine_paths(engine: str) -> tuple[Path, Path]:
    if engine == "fluoro":
        return FLUORO_CDB, FLUORO_SCRIPTS
    if engine == "ignis":
        return IGNIS_CDB, IGNIS_SCRIPTS
    raise ValueError(f"unknown engine: {engine}")


def fluoro_assets_ready() -> bool:
    cdb, scripts = engine_paths("fluoro")
    return cdb.is_file() and (scripts / "constant.lua").is_file()


def ignis_assets_ready() -> bool:
    cdb, scripts = engine_paths("ignis")
    return cdb.is_file() and (scripts / "constant.lua").is_file()


def make_duel(engine: str = "fluoro"):
    database, scripts = engine_paths(engine)
    if engine == "fluoro":
        from yapping._ocgcore import Duel
        return Duel(str(database), str(scripts))
    from yapping._ocgcore_ignis import Duel
    return Duel(str(database), str(scripts))
```

`tools/fetch_ignis_cards_db.sh` is a copy of `tools/fetch_cards_db.sh` with:

```bash
TARGET="$ROOT/assets/ignis/cards.cdb"
COMMIT="172462f1e7405c7544cc256471d3310df6e6b7c3"
EXPECTED="061c2fbd1c541d66d5b06989a2c2a1ef4539a4f82802f31382e72a5955ef180d"
URL="https://raw.githubusercontent.com/ProjectIgnis/BabelCDB/$COMMIT/cards.cdb"
```

README: after the Fluoro clone block, add:

```bash
git clone https://github.com/ProjectIgnis/CardScripts.git projectignis-card-scripts
git -C projectignis-card-scripts checkout 9a5738639924bbbf3b86c4599f3f7e70ea8711a6
cd yapping
./tools/fetch_ignis_cards_db.sh
```

State that BabelCDB is Ignis-only and must not replace `assets/cards.cdb`.

- [ ] **Step 4: Run the factory tests**

Run: `PYTHONPATH=src .venv/bin/python -m pytest tests/test_ocgcore_ignis.py -v`

Expected: the three tests PASS. `make_duel("ignis")` is not called yet.

---

### Task 2: CMake second module that imports

**Files:**
- Modify: `CMakeLists.txt`
- Create: `cpp/adapter_ignis.cpp` (pybind surface only; methods may throw until Task 3)
- Test: `tests/test_ocgcore_ignis.py`

**Interfaces:**
- Consumes: Task 1 `make_duel("ignis")`
- Produces: `yapping._ocgcore_ignis.Duel(database: str, scripts: str)` with the Fluoro method names

- [ ] **Step 1: Write the failing import test**

```python
@pytest.mark.skipif(not ignis_assets_ready(), reason="Ignis cdb/scripts missing")
def test_ignis_module_imports():
    from yapping._ocgcore_ignis import Duel
    cdb, scripts = engine_paths("ignis")
    duel = Duel(str(cdb), str(scripts))
    assert hasattr(duel, "reset")
    assert hasattr(duel, "step")
    assert hasattr(duel, "counts")
    assert hasattr(duel, "cards")
    assert hasattr(duel, "state_key")
```

- [ ] **Step 2: Run it to verify it fails**

Run: `PYTHONPATH=src .venv/bin/python -m pytest tests/test_ocgcore_ignis.py::test_ignis_module_imports -v`

Expected: FAIL `ModuleNotFoundError: yapping._ocgcore_ignis`.

- [ ] **Step 3: Add the Ignis stack to `CMakeLists.txt` after the Fluoro `install` line**

Keep the existing Lua 5.4.7 / Fluorohydride / `_ocgcore` block unchanged.

```cmake
FetchContent_Declare(
  lua53
  URL https://www.lua.org/ftp/lua-5.3.6.tar.gz
  URL_HASH SHA256=fc5fd69bb8736323f026672b1b7235da613d7177e72558893a0bdcd320466d60
  DOWNLOAD_EXTRACT_TIMESTAMP TRUE
)
FetchContent_MakeAvailable(lua53)
file(GLOB LUA53_SOURCES CONFIGURE_DEPENDS "${lua53_SOURCE_DIR}/src/*.c")
list(REMOVE_ITEM LUA53_SOURCES "${lua53_SOURCE_DIR}/src/lua.c" "${lua53_SOURCE_DIR}/src/luac.c")
add_library(yapping_lua53 STATIC ${LUA53_SOURCES})
target_include_directories(yapping_lua53 PUBLIC "${lua53_SOURCE_DIR}/src")
if(APPLE)
  target_compile_definitions(yapping_lua53 PRIVATE LUA_USE_MACOSX)
elseif(UNIX)
  target_compile_definitions(yapping_lua53 PRIVATE LUA_USE_LINUX)
endif()

FetchContent_Declare(
  ocgcore_ignis
  GIT_REPOSITORY https://github.com/edo9300/ygopro-core.git
  GIT_TAG 9a0c558c2d686542f7914a6d529fd7aa57746aed
  GIT_SHALLOW FALSE
  SOURCE_SUBDIR cmake-unused
)
FetchContent_MakeAvailable(ocgcore_ignis)

file(GLOB IGNIS_CORE_SOURCES CONFIGURE_DEPENDS "${ocgcore_ignis_SOURCE_DIR}/*.cpp")
add_library(yapping_ocgcore_ignis STATIC ${IGNIS_CORE_SOURCES})
target_include_directories(yapping_ocgcore_ignis PUBLIC "${ocgcore_ignis_SOURCE_DIR}")
target_link_libraries(yapping_ocgcore_ignis PUBLIC yapping_lua53)
target_compile_features(yapping_ocgcore_ignis PUBLIC cxx_std_17)
if(APPLE)
  set_source_files_properties(
    "${ocgcore_ignis_SOURCE_DIR}/processor_visit.cpp"
    PROPERTIES COMPILE_OPTIONS "-fno-exceptions")
endif()

pybind11_add_module(_ocgcore_ignis MODULE cpp/adapter_ignis.cpp)
target_link_libraries(_ocgcore_ignis PRIVATE yapping_ocgcore_ignis SQLite::SQLite3)
target_compile_features(_ocgcore_ignis PRIVATE cxx_std_17)
set_target_properties(_ocgcore_ignis PROPERTIES
  C_VISIBILITY_PRESET hidden
  CXX_VISIBILITY_PRESET hidden
  VISIBILITY_INLINES_HIDDEN ON)
install(TARGETS _ocgcore_ignis DESTINATION yapping)
```

If edo9300 `interpreter.h` includes Lua without `extern "C"`, apply the same fetched-tree patch pattern already used for Fluoro.

`cpp/adapter_ignis.cpp` at this task only needs a constructible `Duel` class with the pybind methods. `reset`/`step` may throw `std::runtime_error("ignis adapter not implemented")` until Task 3. Constructor must open the sqlite path (or at least store the two strings) so `Duel(cdb, scripts)` does not crash.

Rebuild:

```bash
.venv/bin/python -m pip install -e '.[test]'
```

- [ ] **Step 4: Run the import test**

Run: `PYTHONPATH=src .venv/bin/python -m pytest tests/test_ocgcore_ignis.py::test_ignis_module_imports -v`

Expected: PASS when Ignis assets exist. If CardScripts/cdb are missing, the test is skipped; the module must still import in a one-off:

```bash
.venv/bin/python -c "from yapping._ocgcore_ignis import Duel; print(Duel)"
```

Expected: prints the class. Fluoro tests still pass:

```bash
PYTHONPATH=src .venv/bin/python -m pytest tests/test_ocgcore_integration.py tests/test_search.py -q
```

---

### Task 3: edo9300 `reset` / `step` / decoder

**Files:**
- Modify: `cpp/adapter_ignis.cpp`
- Test: `tests/test_ocgcore_ignis.py`

**Interfaces:**
- Consumes: edo9300 `ocgapi.h` / `ocgapi_types.h` / `ocgapi_constants.h`
- Produces: working `reset`/`step`/`counts`/`cards`/`state_key` with Fluoro kind strings

API map (do not call Fluoro `create_duel` / `process` / `get_message`):

| Fluoro (`adapter.cpp`) | Ignis |
| ---------------------- | ----- |
| `create_duel` / `end_duel` | `OCG_CreateDuel` / `OCG_DestroyDuel` |
| `set_player_info` | `OCG_DuelOptions.team1/team2` (`startingLP=8000`, `startingDrawCount=start_hand`, `drawCountPerTurn=1`) |
| `new_card` | `OCG_DuelNewCard` (`OCG_NewCardInfo`) |
| `start_duel` | `OCG_StartDuel` |
| `process` | `OCG_DuelProcess` returns `OCG_DUEL_STATUS_*` |
| `get_message` | `OCG_DuelGetMessage(duel, &length)` |
| `set_responsei` / `set_responseb` | `OCG_DuelSetResponse`; int responses as 4-byte little-endian |
| `query_field_count` | `OCG_DuelQueryCount` |
| `query_field_card` | `OCG_DuelQueryLocation` |
| `query_field_info` | `OCG_DuelQueryField` |
| `set_script_reader` | `OCG_DuelOptions.scriptReader` calling `OCG_LoadScript` |
| `set_card_reader` | `OCG_DuelOptions.cardReader` filling `OCG_CardData`; `cardReaderDone` frees `setcodes` |

`advance()` loop:

```cpp
for (int iterations = 0; iterations < 10000; ++iterations) {
  const int status = OCG_DuelProcess(duel_);
  uint32_t length = 0;
  void* message = OCG_DuelGetMessage(duel_, &length);
  if (length && message) {
    const auto* bytes = static_cast<const uint8_t*>(message);
    if (decode(std::vector<uint8_t>(bytes, bytes + length))) return;
  }
  if (!errors_.empty()) throw std::runtime_error(errors_.back());
  if (status == OCG_DUEL_STATUS_END) return;
  if (status == OCG_DUEL_STATUS_AWAITING && actions_.empty()) continue;
  if (status == OCG_DUEL_STATUS_CONTINUE) continue;
}
throw std::runtime_error("OCGCore processing did not settle");
```

Copy `Reader`, `Action`, `decision()`, and every `decode_*` plus the `MSG_*` switch from `cpp/adapter.cpp`. Do not include Fluoro `ocgapi.h`. Take `MSG_*` and location constants from edo9300 `ocgapi_constants.h` (values should match; if a name is missing, define the Fluoro numeric literal next to the switch).

Script reader: `Path(requested).filename()`, then try `scripts/`, `scripts/official/`, `scripts/pre-release/`, `scripts/unofficial/`. On hit, `OCG_LoadScript(duel, buffer, size, name)` and return 1; else 0.

Card reader: same sqlite query as Fluoro (`alias,setcode,type,atk,def,level,race,attribute`). `OCG_CardData.setcodes` is a `uint16_t*` terminated by 0; allocate in the reader and free in `cardReaderDone`.

Duel flags: use edo9300 constants equivalent to Fluoro `(CURRENT_RULE << 16) | DUEL_PSEUDO_SHUFFLE` (`DUEL_MODE_MR5` / `DUEL_PSEUDO_SHUFFLE` in `ocgapi_constants.h`). Seed: put the Python `seed` into `options.seed[0]`; fill the other three words with 0, or a splitmix64 expansion of `seed` if the core rejects an all-zero remaining seed (`OCG_DUEL_CREATION_NULL_RNG_SEED`).

Constructor: `sqlite3_open_v2` readonly, prepare the card statement. Destructor: destroy duel, finalize statement, close db.

- [ ] **Step 1: Write the failing Pot-of-Greed test** (Ignis scripts + tiny cdb, same cards as `tests/test_ocgcore_integration.py`).

```python
import sqlite3

POT_OF_GREED = 55144522
CELTIC_GUARDIAN = 91152256


def _tiny_cdb(path):
    database = sqlite3.connect(path)
    database.execute(
        """CREATE TABLE datas (
            id INTEGER PRIMARY KEY, ot INTEGER, alias INTEGER, setcode INTEGER,
            type INTEGER, atk INTEGER, def INTEGER, level INTEGER,
            race INTEGER, attribute INTEGER, category INTEGER
        )"""
    )
    database.executemany(
        "INSERT INTO datas VALUES (?, 0, 0, 0, ?, ?, ?, ?, ?, ?, 0)",
        [
            (POT_OF_GREED, 0x2, 0, 0, 0, 0, 0),
            (CELTIC_GUARDIAN, 0x11, 1400, 1200, 4, 0x1, 0x1),
        ],
    )
    database.commit()
    database.close()


def _choose(duel, decision, kind, card=None):
    for index, action in enumerate(decision["actions"]):
        if action["kind"] == kind and (card is None or action["card"] == card):
            return duel.step(index)
    raise AssertionError(f"missing {kind} {card}: {decision['actions']}")


@pytest.mark.skipif(not ignis_assets_ready(), reason="Ignis cdb/scripts missing")
def test_ignis_spell_then_normal_summon(tmp_path):
    from yapping._ocgcore_ignis import Duel

    _, scripts = engine_paths("ignis")
    assert (scripts / f"c{POT_OF_GREED}.lua").is_file() or (
        scripts / "official" / f"c{POT_OF_GREED}.lua"
    ).is_file()
    database = tmp_path / "cards.cdb"
    _tiny_cdb(database)
    deck = [POT_OF_GREED, CELTIC_GUARDIAN] * 20
    duel = Duel(str(database), str(scripts))
    decision = duel.reset(deck, deck, seed=7, start_hand=5)
    assert {action["kind"] for action in decision["actions"]} >= {"activate", "summon"}
    decision = _choose(duel, decision, "activate", POT_OF_GREED)
    while any(action["kind"] in {"place", "pass"} for action in decision["actions"]):
        kind = "place" if any(a["kind"] == "place" for a in decision["actions"]) else "pass"
        decision = _choose(duel, decision, kind)
    assert duel.counts()["grave0"] == 1
    decision = _choose(duel, decision, "summon", CELTIC_GUARDIAN)
    while any(action["kind"] == "place" for action in decision["actions"]):
        decision = _choose(duel, decision, "place")
    assert duel.cards(0, 4) == [CELTIC_GUARDIAN]
```

- [ ] **Step 2: Run it to verify it fails**

Run: `PYTHONPATH=src .venv/bin/python -m pytest tests/test_ocgcore_ignis.py::test_ignis_spell_then_normal_summon -v`

Expected: FAIL (`ignis adapter not implemented` or empty actions).

- [ ] **Step 3: Implement `reset` / `step` / `advance` / decoder in `adapter_ignis.cpp`**

Rebuild with `pip install -e '.[test]'`.

- [ ] **Step 4: Run the Ignis unit tests and Fluoro integration**

Run:

```bash
PYTHONPATH=src .venv/bin/python -m pytest tests/test_ocgcore_ignis.py tests/test_ocgcore_integration.py -v
```

Expected: new tests PASS (or skip without assets). Fluoro integration still PASS.

---

### Task 4: `--engine` on the two Albaz tools

**Files:**
- Modify: `tools/trace_albaz_combo.py`
- Modify: `tools/search_opening.py`
- Test: `tests/test_ocgcore_ignis.py`

**Interfaces:**
- Consumes: `make_duel(engine)` from `yapping.ocg`
- Produces: CLI `--engine {fluoro,ignis}`, default `fluoro`

- [ ] **Step 1: Write the failing CLI tests**

```python
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.skipif(not fluoro_assets_ready(), reason="Fluoro cdb/scripts missing")
def test_search_opening_default_engine_is_fluoro():
    result = subprocess.run(
        [sys.executable, str(ROOT / "tools/search_opening.py"), "ash",
         "--max-nodes", "8", "--max-depth", "12"],
        cwd=ROOT, capture_output=True, text=True, check=True,
    )
    assert "engine: fluoro" in result.stdout


@pytest.mark.skipif(not ignis_assets_ready(), reason="Ignis cdb/scripts missing")
def test_search_opening_accepts_engine_ignis():
    result = subprocess.run(
        [sys.executable, str(ROOT / "tools/search_opening.py"), "ash",
         "--engine", "ignis", "--max-nodes", "8", "--max-depth", "12"],
        cwd=ROOT, capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr[-2000:]
    assert "engine: ignis" in result.stdout
```

- [ ] **Step 2: Run them to verify they fail**

Run: `PYTHONPATH=src:tools .venv/bin/python -m pytest tests/test_ocgcore_ignis.py::test_search_opening_default_engine_is_fluoro tests/test_ocgcore_ignis.py::test_search_opening_accepts_engine_ignis -v`

Expected: FAIL (`unrecognized arguments: --engine` and/or missing `engine:` line).

- [ ] **Step 3: Wire `--engine`**

In `tools/search_opening.py`:

- `from yapping.ocg import make_duel`
- Replace `Duel(str(ROOT / "assets/cards.cdb"), str(SCRIPTS))` with `adapter or make_duel(engine)`
- Thread `engine="fluoro"` through `run_search` / `search` / argparse
- `parser.add_argument("--engine", choices=["fluoro", "ignis"], default="fluoro")`
- Print `engine: {engine}` next to `replay-mode:`
- Provenance `database`/`scripts` must come from `engine_paths(engine)`, not the Fluoro constants

In `tools/trace_albaz_combo.py`:

- Add argparse `--engine` (this file currently uses `main()` without argparse; add a small parser for `--engine` only, keep env-based interruption as-is)
- `new_duel(..., adapter=adapter)` already exists; `main()` should call `make_duel(engine)` and pass it in
- Print `engine: {engine}` before the first `show(...)`

- [ ] **Step 4: Re-run the CLI tests plus `tests/test_fork_replay.py` and `tests/test_albaz_combo.py`**

Expected: new tests PASS. Existing Fluoro CLI tests still PASS (default engine).

---

### Task 5: Scripted Albaz gate on Ignis

**Files:**
- Test: `tests/test_ocgcore_ignis.py`
- Modify: `tools/trace_albaz_combo.py` only if the gate cannot choose actions because a kind is missing (adapter bug)

**Interfaces:**
- Consumes: `trace_albaz_combo.py --engine ignis`
- Produces: gate result used by Task 6 (do not run comparison if this fails)

- [ ] **Step 1: Write the failing gate test**

```python
@pytest.mark.skipif(not ignis_assets_ready(), reason="Ignis cdb/scripts missing")
def test_ignis_albaz_combo_completes():
    result = subprocess.run(
        [sys.executable, str(ROOT / "tools/trace_albaz_combo.py"), "--engine", "ignis"],
        cwd=ROOT, capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr[-2000:]
    assert "FULL COMBO COMPLETE" in result.stdout
```

- [ ] **Step 2: Run it**

Run: `PYTHONPATH=src:tools .venv/bin/python -m pytest tests/test_ocgcore_ignis.py::test_ignis_albaz_combo_completes -v`

Expected: FAIL until Task 3 decoder covers the combo prompts, then PASS. If it fails with `missing activate 73819701` (or similar) and Fluoro still completes, inspect whether the kind is wrong (fix adapter) or the card is not scripted under `official/` (asset pin).

- [ ] **Step 3: If the scripted line diverges after a correct decoder, stop**

Write `reports/ignis_albaz_combo_divergence.txt` with stdout/stderr. Do not start Task 6. Do not edit CardScripts or Fluoro scripts. Update `DIRECTION.md` that the match hypothesis died at the combo gate.

- [ ] **Step 4: Confirm Fluoro combo still passes**

Run: `PYTHONPATH=src:tools .venv/bin/python -m pytest tests/test_albaz_combo.py::test_full_albaz_swordsoul_combo -v`

Expected: PASS.

---

### Task 6: Ash search comparison

**Files:**
- Test: `tests/test_ocgcore_ignis.py`
- Create on failure only: `reports/ignis_albaz_ash_divergence.json`
- Modify: `DIRECTION.md`

**Interfaces:**
- Consumes: `search_opening.py ash --engine {fluoro,ignis} --replay-mode cursor --max-nodes 2000 --max-depth 180`
- Produces: pass if `score`, `complete`, and `actions` match; otherwise a JSON artifact and a failed test

```python
import json
import re


def parse_search_stdout(text: str):
    score = None
    complete = None
    actions = None
    for line in text.splitlines():
        if line.startswith("score:") or line.startswith("provisional score"):
            score = float(line.rsplit(":", 1)[1].strip())
        elif line.startswith("complete:"):
            complete = line.split(":", 1)[1].strip() == "True"
        elif line.startswith("actions:"):
            payload = line.split(":", 1)[1].strip()
            actions = tuple(part.strip() for part in payload.split("->")) if payload else ()
    if score is None or complete is None or actions is None:
        raise AssertionError(f"unparseable search output:\n{text[-2000:]}")
    return {"score": score, "complete": complete, "actions": actions}


def first_action_diff(fluoro, ignis):
    for index, (left, right) in enumerate(zip(fluoro, ignis)):
        if left != right:
            return {"index": index, "fluoro": left, "ignis": right}
    if len(fluoro) != len(ignis):
        return {
            "index": min(len(fluoro), len(ignis)),
            "fluoro": fluoro[len(ignis):][:1] or None,
            "ignis": ignis[len(fluoro):][:1] or None,
        }
    return None


@pytest.mark.skipif(
    not fluoro_assets_ready() or not ignis_assets_ready(),
    reason="both engine stacks required",
)
def test_ignis_ash_search_matches_fluoro():
    def run(engine):
        result = subprocess.run(
            [sys.executable, str(ROOT / "tools/search_opening.py"), "ash",
             "--engine", engine, "--replay-mode", "cursor",
             "--max-nodes", "2000", "--max-depth", "180"],
            cwd=ROOT, capture_output=True, text=True,
        )
        assert result.returncode == 0, result.stderr[-2000:]
        return parse_search_stdout(result.stdout)

    fluoro = run("fluoro")
    ignis = run("ignis")
    payload = {
        "fluoro": fluoro,
        "ignis": ignis,
        "first_action_diff": first_action_diff(fluoro["actions"], ignis["actions"]),
    }
    if (
        fluoro["score"] != ignis["score"]
        or fluoro["complete"] != ignis["complete"]
        or fluoro["actions"] != ignis["actions"]
    ):
        report = ROOT / "reports" / "ignis_albaz_ash_divergence.json"
        report.write_text(json.dumps(payload, indent=2) + "\n")
        pytest.fail(
            "Ignis Ash search diverged from Fluoro; wrote "
            f"{report} first_action_diff={payload['first_action_diff']}"
        )
```

- [ ] **Step 1: Add the test (it is allowed to fail as the experiment result)**

- [ ] **Step 2: Run it**

Run: `PYTHONPATH=src:tools .venv/bin/python -m pytest tests/test_ocgcore_ignis.py::test_ignis_ash_search_matches_fluoro -v`

- [ ] **Step 3: Classify the failure**

If `first_action_diff` shows a nonsense kind (empty actions, `select_sum` crash, truncated prompt): fix `adapter_ignis.cpp` and re-run. That is still Task 6 work.

If both lines are well-formed `(kind, card)` strings and they disagree: **stop**. Leave the JSON in `reports/`. Do not change CardScripts, Fluoro scripts, or `CARD_WEIGHTS`.

- [ ] **Step 4: Update `DIRECTION.md` Dual OCGCore section**

Replace the previous Ignis smoke exit with:

- Default oracle remains Fluoro.
- `_ocgcore_ignis` exists.
- First proof was Albaz Ash search (`cursor`, 2000/180).
- Result: **match** or **rejected** with pointer to `reports/ignis_albaz_ash_divergence.json`.
- Ekhajar coverage remains a later slice.
- Phase 1 fork stays Fluoro-only.

- [ ] **Step 5: Run the Fluoro suite that this slice must not break**

```bash
PYTHONPATH=src:tools .venv/bin/python -m pytest tests/test_ocgcore_integration.py tests/test_albaz_combo.py tests/test_fork_replay.py tests/test_search.py tests/test_ocgcore_ignis.py -q
```

Expected: Fluoro tests PASS. Ignis tests PASS or skip without assets. Comparison either PASS or FAIL with the divergence file present.

---

## Self-review

Spec coverage:

- Second module, not a replacement: Task 2
- Own cdb + CardScripts: Task 1
- Same `Duel` surface: Tasks 2-3
- `--engine` only on two tools: Task 4
- Combo gate then Ash comparison: Tasks 5-6
- No fork/Ekhajar/CI clone/speed claims: Global Constraints
- DIRECTION update: Task 6
- Decoder bugs vs semantic stop: Tasks 5-6
