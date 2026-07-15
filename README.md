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

## Continuous integration

GitHub Actions builds the C++ adapter, checks out the pinned Lua scripts, and
runs the portable test suite on every push and pull request. The full Albaz
fixture remains conditionally skipped in public CI because `assets/cards.cdb`
is intentionally untracked; provide that database through a private artifact
or secret-backed download only if you want CI to run the full card fixture.

## Native adapter

`yapping._ocgcore.Duel` currently supports:

- deterministic two-player duel creation and deck loading;
- SQLite `cards.cdb` card-data callbacks;
- global and per-card Lua script loading;
- idle, chain, yes/no, option, position, zone, card, sum, and toggle decisions;
- legal actions that retain player, card, location, sequence, and description;
- field counts, card identities by zone, and a binary field-state key.

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

## Adversarial combo search

`python tools/analyze_ash.py` gives the opponent exactly one Ash Blossom,
discovers every legal activation window in the canonical combo, replays each
negation, and searches real legal continuations to the next turn. The current
fixture exposes seven windows and identifies the Fallen of the White Dragon
deck-summon trigger as the strongest choke point. Its best discovered recovery
is to enter the End Phase, use Titaniklad to Special Summon Guiding Quem, send
Blazing Cartesia, and return Cartesia to hand.

`python tools/search_opening.py ash` runs alpha-beta minimax from the opening
decision rather than fixing the combo prefix. On the canonical hand it visits
965 replayed states, proves the search complete under the fixture's action
abstraction, chooses Titaniklad as the Extra Deck send, and reaches a worst-case
score of 8.75 after the opponent's optimal Ash timing.

The same command accepts `veiler`, `impermanence`, `droll`, `nibiru`, and
`ghost_ogre` to search the opening decision against one known legal hand trap.
Called by the Grave is intentionally not in this list; see its separate model
below.

For the one-card baseline, known Effect Veiler and Infinite Impermanence also
complete from the opening (1,317 and 1,390 states respectively). Both optimally
negate Fallen and leave the same 8.75 recovery line: Titaniklad supplies Guiding
Quem, which sends and returns Blazing Cartesia.

Known Droll & Lock Bird also completes from the opening in 8,696 states. Its
15.75 worst-case line changes the route instead of merely recovering from a
negated Fallen, demonstrating why each interruption needs its own search.

Pass `--hand` followed by five card IDs or fixture aliases to search an exact
dealt opening hand, for example `--hand fallen incredible_ecclesia
celtic_guardian celtic_guardian celtic_guardian`. Those cards are removed from
the deck before the deterministic deal, so deck searches correctly account for
a card already being in hand.

An opening report is optimal only when it says `complete: True`. At a node
limit, its displayed value is explicitly a provisional heuristic score rather
than a proven bound.
Each opening report also prints the evaluator breakdown: board monsters,
spell/traps, named follow-up in hand, and generic hand advantage.

`python tools/analyze_monster_negation.py veiler` and the corresponding
`impermanence` command enumerate both legal timing windows and legal monster
targets. The native adapter decodes zone choices from the selecting player's
perspective, so player 1 can legally activate Infinite Impermanence from hand.

Called by the Grave is modeled separately as an already Set card. It is not a
turn-one hand trap: an opponent who starts with it in hand cannot Set and
activate it during the combo player's first turn. Its fixture therefore models
a turn-two or pre-established-backrow scenario and does not use a hand-opening
probability in its report.

The initial evaluator is deliberately visible in `tools/analyze_ash.py`. It
weights live interaction such as Mirrorjade and Branded Retribution, reusable
engines such as Guiding Quem and Cartesia, follow-up in hand, and generic card
advantage. The opponent minimizes this end-board score; the combo player
maximizes it. These weights are a testable baseline, not learned truth.

### Current interruption coverage

| Interaction | Opening minimax | Fixture coverage |
| --- | --- | --- |
| Ash Blossom | Complete (965 states) | Timing and recovery report |
| Effect Veiler | Complete (1,317 states) | Timing and target report |
| Infinite Impermanence | Complete (1,390 states) | Timing and target report |
| Droll & Lock Bird | Complete (8,696 states) | Timing and recovery report |
| Ghost Ogre | Complete (22,756 states) | Legal timing/recovery fixture |
| Nibiru | Complete (10,975 states) | Legal multi-tribute timing/recovery fixture |
| Called by the Grave | Not a turn-one hand-trap model | Pre-set backrow fixture |

“Provisional” means the node limit evaluated nonterminal leaves with the
heuristic; it is deliberately not presented as an optimal score.

The canonical hidden-hand experiments also complete for Ash (4,298 states),
Veiler (4,043), Infinite Impermanence (4,075), and Droll (4,851). Each forces
the combo player to choose before seeing whether the interruption exists.

## Two-layer optimization model

**Inner problem:** Given an exact opening hand and legal opponent responses,
which line survives the worst interruption? Deterministic replay and minimax
solve this tactical problem.

**Outer problem:** Across all likely opening hands, how consistently can the
deck reach a valuable board, recover through disruption, and avoid bricks or
excessive garnets? Hypergeometric probabilities, hand enumeration, and later
sampling aggregate the inner solver's results into deck-level analysis.

YAPPING models three adversarial experiments:

- **Known interruption:** optimize against one named card for diagnosis.
- **Guaranteed hidden interruption:** choose one pre-reveal action whose worst
  outcome is strongest across a set of possible hidden cards.
- **Probabilistic hidden hand:** choose one pre-reveal action with the highest
  probability-weighted outcome from an opponent deck model.

`python tools/search_hidden_ash.py ash` now connects this model to full opening
branching for Ash versus no Ash; replace `ash` with any known hand-trap name to
run the same experiment. It intersects player-0 actions across both worlds,
retains both worlds after an indistinguishable opponent pass, and splits them
only when the interruption is publicly activated. Its belief-state alpha-beta
search completes the canonical Ash/no-Ash fixture in 4,298 state visits with
the same 8.75 worst-case score as the known-Ash search. It still reports
`complete: false` if a future hand exceeds the configured state budget.
The canonical Veiler/no-Veiler experiment also completes (4,043 states, 8.75
worst-case score).

Like known-interruption search, hidden-hand-trap search accepts `--hand` plus
five card IDs, so its pre-reveal decision can be optimized from an exact
opening hand rather than only the one-card baseline.

For larger hidden-world sets, `python tools/search_sampled_hidden.py ash`
uses sampled determinization instead of enumerating every opponent policy
product. It reports the random seed, sample count, estimated action score,
standard error, 95% interval, and whether every sampled sub-search completed.
This is an estimate, not a guarantee; `search_hidden_ash.py` remains the exact
two-world maximin mode. The outer consistency report is available with
`python tools/analyze_consistency.py --hands 20` and preserves each hand's
hypergeometric weight and complete/provisional status.

The learned-model stage starts with oracle data rather than the Gymnasium
environment: `python tools/training_data.py export artifacts/training.jsonl`
writes state keys, legal actions, oracle actions, values, and completion flags.
`python tools/training_data.py evaluate artifacts/training.jsonl` evaluates the
reproducible lookup baseline. Node-limited examples remain provisional and
must not be treated as solved labels.

`python tools/compare_hidden.py ash` compares the sampled expected-value result
with exact hidden maximin on the same input. The reported gap is an information
modeling diagnostic: sampled determinization may use the sampled world after
the first action, while hidden maximin retains uncertainty. The exact result
is labeled as a worst-case guarantee; the sampled result includes its seed,
standard error, confidence interval, and completion flag.

## Roadmap

1. Add matchup-specific evaluators and compare results with expert lines.
2. Evaluate deck consistency by weighting the best adversarial line from each
   sampled or enumerated opening hand, including bricks and garnets.
3. Use Monte Carlo Tree Search when unknown hands and interruption
   probabilities make exhaustive branching too large.
4. Train policy/value models only after deterministic search can generate and
   verify trustworthy state, legal-action, and outcome data.

## Development

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[test]'
pytest
```
# Validation results

The search has two replay modes: the default `ReplayCursor` search mode and
the slower replay-from-seed oracle mode. Use
`python tools/verify_replay_equivalence.py ghost_ogre` to compare their
decoded score, action line, completion flag, endboard, and score breakdown.
The production-depth Ghost Ogre A/B matched byte-for-byte; the cursor took
about 48 seconds versus about 245 seconds for the oracle at 22,756 nodes.

Sampled hidden search uses the configured hypergeometric prior. With the
Albaz config, Ash's probability in a 40-card opponent deck is 0.3375506.
An eight-sample Ash comparison at 5,000 nodes found exact hidden-world
maximin 8.75 (complete) versus sampled determinization mean 12.375
(incomplete), with a 95% interval of [9.69, 15.06]. Treat this as a
provisional strategy-fusion measurement until the sampled worlds complete.

The first 50-hand Ash consistency report is saved at
`reports/consistency-ash-50.json`. It used 5,000 nodes and depth 180 per
hand: weighted score 4.03965, brick fraction 0.58, complete fraction 0.88,
and 6 provisional hands.
