# YAPPING

**Yet Another Program for Parsing Interactive Game Nodes**

YAPPING is an independent Yu-Gi-Oh! combo-search and duel-analysis project. It uses a pinned OCGCore build through a small native adapter to execute real Lua card effects, decode exact legal prompts, and search from real game states.

Current focus:

- deterministic duel execution;
- exact legal-action decoding;
- replay-based search and minimax;
- interruption and hidden-hand analysis;
- declarative archetype, deck, fixture, and scoring configuration.

Reinforcement learning is a later consumer of verified search data, not the current source of truth.

YAPPING is unofficial and is not affiliated with or endorsed by Konami, Shueisha, or the maintainers of the referenced simulator projects.

## How the system works

```
deck / archetype configuration
        |
combo fixture and interruption scenario
        |
legal-action decoder
        |
ReplayCursor or replay-from-seed oracle
        |
OCGCore + Lua scripts + cards.cdb
        |
location-aware evaluator
        |
minimax, hidden-world search, or consistency report
```

The native engine knows game rules and legal actions. Archetype configuration supplies deck-specific data such as card lists, target predicates, interruption policies, fixture references, and objective weights. Search code should not contain branches such as "if this is Fallen" or "if this is Ecclesia."

Two replay modes are kept permanently:

- Oracle mode replays every path from the initial seed and remains the correctness reference.
- Search mode uses ReplayCursor to reuse the current forward path and must match the oracle.

The oracle creates a fresh native duel and replays the complete action path for each candidate. ReplayCursor keeps one active duel aligned with the current depth-first search prefix, steps forward when descending, and reconstructs from the seed only after backtracking to a different branch. It is an optimization, not a native duel clone.

## Repository structure

```
yapping/
|-- cpp/
|   +-- adapter.cpp                 Pybind11 OCGCore adapter
|-- src/yapping/
|   |-- archetype.py                Declarative archetype loader
|   |-- card_rules.py               cards.cdb metadata and predicates
|   |-- engine.py                   Generic engine protocol
|   |-- evaluation.py               Location/state-aware evaluator
|   |-- minimax.py                  Minimax and hidden-world search
|   |-- search.py                   Search result and orchestration types
|   |-- probability.py              Hypergeometric opening probabilities
|   +-- env.py                      Gymnasium-compatible environment shell
|-- configs/
|   |-- archetypes/                 Complete archetype configurations
|   |-- combos/                     Declarative combo/interruption fixtures
|   +-- *.json                      Earlier matchup/search configurations
|-- combos/
|   +-- albaz_swordsoul_full.yaml   Canonical deterministic combo fixture
|-- tools/
|   |-- trace_*.py                  Prompt-by-prompt engine fixtures
|   |-- search_*.py                 Search and minimax entry points
|   |-- analyze_*.py                Interruption/consistency reports
|   |-- run_*_fixture.py            Deterministic fixture runners
|   |-- training_data.py             Oracle-data export and baseline evaluation
|   +-- verify_replay_equivalence.py ReplayCursor/oracle comparison
|-- tests/                          Unit and native integration tests
|-- docs/                           Architecture and configuration docs
|-- reports/                        Reproducible experiment outputs
|-- assets/cards.cdb                Optional local card database
|-- CMakeLists.txt                  Native build and pinned OCGCore setup
|-- pyproject.toml                  Python package and test configuration
+-- DIRECTION.md                    Project direction and phase decisions
```

## Engine and dependencies

The adapter targets:

- [Fluorohydride/ygopro-core](https://github.com/Fluorohydride/ygopro-core), pinned to db4fd16a99991802511b9a89e0025dd2f51f5e36;
- [Fluorohydride/ygopro-scripts](https://github.com/Fluorohydride/ygopro-scripts), pinned to 72a1be24bb5a4eab9af3a71e53561abcd467aff6;
- Lua 5.4.7, fetched by CMake;
- SQLite for cards.cdb;
- Python, pybind11, Gymnasium, NumPy, and pytest.

OCGCore is fetched during the native build and is not copied into this repository. Card scripts and cards.cdb are runtime inputs.

Linux or WSL is the recommended development environment because the native build and optional fork-based replay experiments target Linux process semantics.

## Setup on Linux or WSL

Install native prerequisites:

```bash
sudo apt-get update
sudo apt-get install -y cmake ninja-build libsqlite3-dev
```

Clone the pinned script repository beside YAPPING:

```bash
cd ~/projects/yugioh
git clone https://github.com/Fluorohydride/ygopro-scripts.git fluorohydride-ygopro-scripts
git -C fluorohydride-ygopro-scripts checkout 72a1be24bb5a4eab9af3a71e53561abcd467aff6
cd yapping
```

Create the environment and install the package:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e '.[test]'
```

The editable install builds the native yapping._ocgcore extension. Full card-effect fixtures also need a compatible assets/cards.cdb, intentionally untracked from the public repository.

## Providing cards.cdb

cards.cdb is the SQLite card database used by the adapter for names, races, levels, ATK/DEF, and other card metadata. It is intentionally ignored by Git and should be obtained from a compatible EDOPro/YGOPro installation or database distribution.

Option 1: copy it from an existing EDOPro installation:

```bash
mkdir -p assets
cp /path/to/EDOPro/cards.cdb assets/cards.cdb
```

Option 2: run the checked downloader from the repository root:

```bash
./tools/fetch_cards_db.sh
```

The validated database comes from [mycard/ygopro-database](https://github.com/mycard/ygopro-database/blob/master/locales/en-US/cards.cdb), pinned by the downloader to commit f3d9f81e619ec51427dd66d39e09b10f5ee2a41c. The script verifies the SHA-256 before replacing the local file.

[Project Ignis BabelCDB](https://github.com/ProjectIgnis/BabelCDB) is another EDOPro-compatible source, but its database may not be byte-identical to the MyCard database and should not be mixed when reproducing an existing result.

Check the file:

```bash
sha256sum assets/cards.cdb
PYTHONPATH=src python -m pytest -q tests/test_card_rules.py
```

The database used for the validated Branded fixtures has SHA-256:

```text
c54901ab8dc1b2edec17b7ea65e309ab050b8fd05e0d314ebaab7f02db2ed70f
```

A different compatible database may still work, but exact experiment results should record its checksum.

## Running tests

```bash
PYTHONPATH=src python -m pytest -q
```

Tests requiring cards.cdb or the adjacent Lua scripts skip when those runtime assets are unavailable. The portable suite remains runnable in clean CI.

Useful native traces:

```bash
PYTHONPATH=src python tools/trace_albaz_combo.py
PYTHONPATH=src python tools/trace_high_spirits.py
```

## Representative fixtures

The deterministic fixtures are small, inspectable engine tests:

- The full Fallen line validates chained effects, Synchro/Fusion materials, End Phase triggers, and ordered chain resolution.
- The Fallen + Incredible Ecclesia recovery fixture validates that Ash Blossom, Effect Veiler, or Infinite Impermanence can negate Fallen while the Normal Summon remains available, allowing Ecclesia to continue the line.
- The High Spirits fixture validates database-backed target predicates and the uninterrupted continuation through Quem, Kitt, and Three Champions.

Run the two-card recovery fixture with:

```bash
python tools/run_fallen_ecclesia_fixture.py
```

A fixture is a correctness and regression case. It is not itself a learned policy; search must still enumerate legal alternatives and score the resulting states.

## Archetype configuration

Variant comparison can optionally reuse a verified archetype compendium when
annotating candidates:

```sh
PYTHONPATH=tools:src .venv/bin/python tools/compare_variants.py \
  --config configs/albaz.json --replace 91152256 \
  --candidate 44146295:board_breaker:Mirrorjade \
  --archetype configs/archetypes/branded.json
```

The report records which fixtures are available and whether each candidate is
already covered by the archetype's verified deck, weights, or fixture data.

A new archetype should be represented by configuration rather than a new engine implementation. The Branded example is configs/archetypes/branded.json.

It contains:

- main_deck and extra_deck: repeated card IDs encode quantities;
- interruption_specs: opponent card IDs and activation policies;
- fixtures: combo/scenario files to validate;
- target_predicates: constraints such as level, race, Fusion type, and ATK/DEF;
- card_weights: card-specific values supplied to the evaluator;
- objectives: weights for generic goals such as follow-up and disruption survival.

Load it from Python:

```python
from yapping import load_archetype

archetype = load_archetype("configs/archetypes/branded.json")
print(archetype.deck_counts)
print(archetype.interruptions["ash"])
```

The High Spirits fixture uses a declarative target predicate:

```python
from yapping.card_rules import CardDatabase

predicate = archetype.target_predicates["high_spirits"]
targets = CardDatabase("assets/cards.cdb").matching_targets(
    revealed_card=95515789,
    extra_deck=list(archetype.extra_deck),
    predicate=predicate,
)
```

The evaluator receives card identity, current zone, and game-state facts:

```python
from yapping import EndboardEvaluator, EvaluationState

evaluator = EndboardEvaluator(archetype.card_weights, archetype.objectives)
state = EvaluationState(
    zones={"monster": (...), "spell_trap": (...), "hand": (...), "grave": (...)},
    facts={"opponent_interrupted": True},
)
score = evaluator.score(state)
```

See docs/ARCHETYPE_CONFIG.md for the plug-in contract.

## Search and analysis commands

Known-interruption opening search:

```bash
python tools/search_opening.py ash
python tools/search_opening.py veiler
python tools/search_opening.py impermanence
python tools/search_opening.py droll
python tools/search_opening.py nibiru
python tools/search_opening.py ghost_ogre
```

Search an exact five-card hand:

```bash
python tools/search_opening.py ash --hand fallen incredible_ecclesia celtic_guardian celtic_guardian celtic_guardian
```

Other analysis modes:

```bash
python tools/analyze_ash.py
python tools/analyze_monster_negation.py veiler
python tools/analyze_monster_negation.py impermanence
python tools/search_hidden_ash.py ash
python tools/search_sampled_hidden.py ash
python tools/analyze_consistency.py --hands 20
python tools/analyze_consistency.py --hands 20 --conditioned
python tools/analyze_consistency.py --hands 20 --conditioned --thresholds 5,10,15
python tools/compare_hidden.py ash
python tools/verify_replay_equivalence.py ghost_ogre
```

With `--conditioned`, the JSON report adds:

- role-conditioned utility buckets (`E[U | hand features]`)
- a `quantified` block separating **hand features** from **solver outcomes**
- threshold rates `Playable_T := U >= T` with `T` from `--thresholds` (default `5,10,15`)
- a theoretical role-density opening profile when `card_roles` are set

Example shape for extender counts among evaluated hands:

| Extender count | probability mass (evaluated) | normalized weighted utility |
| --- | --- | --- |
| 0 | sum of P(h) in bucket | E[U \| extender=0] |
| 1 | … | E[U \| extender=1] |
| 2 | … | E[U \| extender=2] |
| 3+ | … | E[U \| extender≥3] |

Joint buckets such as `starter≥1, extender=1` answer “how useful is opening N
extenders **given** a starter?”, not “what is the globally optimal number of
extenders in the 40.” The latter needs changing the deck list and re-evaluating
the induced hand distribution (Phase 3D/3E).

Roles are input hypotheses. Solver utility (and `U >= T`) is the outcome.
`starter_access` is not playability. Sampled unique hands report
`evaluated_probability_mass` that is typically far below 1.0; do not read
`evaluated_sample_success_rate` as a full-deck fraction.


Output distinguishes proven searches from provisional node-limited evaluations. A score is not presented as optimal unless the search reports completion.

## What is being optimized?

YAPPING separates tactical line selection from deck-level consistency.

Inner problem: given an exact opening hand and opponent responses, choose the best legal line under the selected objective.

Outer problem: across likely opening hands, measure how often the deck reaches a valuable board, survives disruption, bricks, or consumes too many garnets. Role-conditioned summaries estimate `E[U | hand features]` from solver rows; they do not yet optimize deck ratios.

Current methods:

- deterministic replay for correctness;
- minimax for known interruptions;
- exact belief-state search for small hidden-world sets;
- sampled determinization for larger hidden-world estimates;
- hypergeometric weighting for opening-hand consistency;
- multi-label card roles and conditioned hand-utility aggregation;
- oracle-labelled data for later policy/value models.

Monte Carlo Tree Search and learned policy/value models remain future stages. They should be evaluated against the deterministic oracle.

## Current limitations

- cards.cdb and Lua scripts are external runtime assets;
- full native fixture tests skip when those assets are absent;
- search budgets can produce provisional rather than proven values;
- sampled determinization can suffer from strategy fusion;
- card weights are an explicit baseline, not universal truth;
- core-level duel serialization is out of scope; replay remains the correctness primitive.

## Development and documentation

- [DIRECTION.md](DIRECTION.md): phase plan and architectural decisions;
- [docs/ARCHETYPE_CONFIG.md](docs/ARCHETYPE_CONFIG.md): adding another archetype;
- [WRITEUP.md](WRITEUP.md): technical project writeup;
- [WRITEUP-ENUMERABLE-UNKNOWNS.md](WRITEUP-ENUMERABLE-UNKNOWNS.md): hidden-information methodology;
- [LINKEDIN_POST.md](LINKEDIN_POST.md): public-facing project angle;
- [X-THREAD.md](X-THREAD.md): shorter project narrative.

CI builds the native adapter and runs the portable test suite on pushes and pull requests. Before opening a pull request:

```bash
python -m pytest -q
git diff --check
```

## License and attribution

YAPPING is an independent project. The OCGCore adapter, card scripts, card database, and referenced simulator projects retain their respective licenses and attribution requirements. Review upstream licenses before redistributing runtime assets.
