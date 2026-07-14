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
is to enter the End Phase and use Titaniklad to add Guiding Quem as follow-up.

`python tools/analyze_monster_negation.py veiler` and the corresponding
`impermanence` command enumerate both legal timing windows and legal monster
targets. The native adapter decodes zone choices from the selecting player's
perspective, so player 1 can legally activate Infinite Impermanence from hand.

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

`robust_choice` and `expected_choice` provide the hidden-scenario aggregation
without leaking the opponent's private card into the player's earlier choice.
The next search milestone connects those aggregators to full branching from
the opening hand; the current card reports hold the known combo prefix fixed
until the interruption and then search legal recovery actions.

## Roadmap

1. Add real fixtures for Effect Veiler, Infinite Impermanence, Ghost Ogre,
   Droll & Lock Bird, Nibiru, and Called by the Grave.
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
