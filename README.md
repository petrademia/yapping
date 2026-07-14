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
8,359 replayed states, proves the search complete under the fixture's action
abstraction, chooses Titaniklad as the Extra Deck send, and reaches a worst-case
score of 8.75 after the opponent's optimal Ash timing.

The same command accepts `veiler`, `impermanence`, `droll`, `nibiru`, and
`ghost_ogre` to search the opening decision against one known legal hand trap.
Called by the Grave is intentionally not in this list; see its separate model
below.

Pass `--hand` followed by five card IDs to search an exact dealt opening hand,
for example `--hand 73819701 55273560 91152256 91152256 91152256` for Fallen
of the White Dragon plus Incredible Ecclesia and three fillers. Those cards
are removed from the deck before the deterministic deal, so deck searches
correctly account for a card already being in hand.

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

`python tools/search_hidden_ash.py` now connects this model to full opening
branching for Ash versus no Ash. It intersects player-0 actions across both
worlds, retains both worlds after an indistinguishable opponent pass, and
splits them only when Ash is publicly activated. Its belief-state alpha-beta
search reports `complete: false` when its state budget prevents an optimality
claim; move ordering and stronger bounds are the next scaling step.

## Roadmap

1. Add alpha-beta pruning and target-aware exhaustive reports for every
   interruption fixture.
2. Add matchup-specific evaluators and compare results with expert lines.
3. Evaluate deck consistency by weighting the best adversarial line from each
   sampled or enumerated opening hand, including bricks and garnets.
4. Use Monte Carlo Tree Search when unknown hands and interruption
   probabilities make exhaustive branching too large.
5. Train policy/value models only after deterministic search can generate and
   verify trustworthy state, legal-action, and outcome data.

## Development

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[test]'
pytest
```
