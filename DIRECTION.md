# YAPPING direction plan

Status: draft, 2026-07-15.

This document records the agreed development direction on top of the current
architecture (see [README.md](README.md)). It sequences the work, states why
each phase comes before the next, and gives each phase a concrete exit
criterion.

## Product definition

YAPPING's product is a matchup-aware combo resilience analyzer:

> Given an opening hand and an opponent-interaction model, find and measure
> the strongest legal line and the value it preserves after interruption.

OCGCore regression fixtures are infrastructure and correctness gates. They
verify that card effects, prompts, chains, and replay behave correctly, but
they are not the final analysis product.

The analysis has three nested questions:

1. **Uninterrupted ceiling:** what is the strongest legal line from this hand
   with no opponent interaction?
2. **Recovery:** what is the strongest legal line after a known or hidden
   interruption, including the use of extenders?
3. **Deck resilience:** across opening-hand probabilities, how much endboard,
   interaction, and follow-up value does the deck retain?

The uninterrupted result is an upper-bound baseline, not the definition of a
good deck. Reports should preserve score breakdowns and completeness flags so
resilience can be compared without hiding the tradeoff between board strength,
follow-up, and interaction.

## Design assessment (summary)

The four-layer stack is sound and should be preserved:

1. native adapter (`cpp/adapter.cpp`) - deterministic duels, decoded legal
   actions, binary state key, no cloning;
2. generic search library (`src/yapping/`) - replay-based alpha-beta with a
   bound-labeled transposition cache, plus belief-state hidden search;
3. fixture tools (`tools/`) - evaluator weights, action abstraction, terminal
   predicates, currently Albaz-specific;
4. two-layer model - inner per-hand minimax, outer deck-level aggregation
   (only `opening_probability` exists today).

Strengths to keep: honest `complete` flags, replay determinism as ground
truth, public-action-key world grouping in hidden search.

Pressure points, in the order they will bite:

- **Replay cost.** Every node replays its full path from seed:
  O(states × depth) engine steps at depth ≈ 180. Invisible at Ash's 965
  states, already millions of steps at Ghost Ogre's 22,756, and the outer
  problem multiplies everything by hand count.
- **Fixture leakage.** `analyze_ash.py` owns `CARD_WEIGHTS`, `SKIP_KINDS`,
  move ordering, and `recovery_terminal`; other tools import them sideways.
  A second deck currently means copying a 221-line script.
- **Hidden-search opponent model.** `hidden_minimax_replay` enumerates
  `product(*choices)` over scenarios - fine for two worlds, exponential in
  world count. The probabilistic hidden-hand experiment needs a different
  formulation, not an extension of this one.

## Phase 1 - prefix-reuse replay

Replace full-path replay with incremental stepping. Alpha-beta is
depth-first, so consecutive visits share long prefixes: keep a small pool of
live duels at recent prefixes (or one duel per DFS depth) and replay from
seed only on a pool miss. The change is contained in the replay callback;
`minimax_replay` and `hidden_minimax_replay` do not change.

- Prerequisite for phases 3-4; do first.
- Measure states/second on the Ghost Ogre fixture before and after.
- Exit: all existing fixtures produce identical scores, action lines, and
  `complete` flags; Ghost Ogre wall-clock improves by an order of magnitude
  or the measurement explains why not.

## Phase 2 - de-fixture the toolchain

Move deck- and matchup-specific knowledge out of `tools/analyze_ash.py` into
a declarative matchup config consumed by the tools:

- deck lists and fixture aliases;
- evaluator weights and score-breakdown fields;
- action-abstraction rules (skip kinds, dedup signature, ignored cards);
- move-ordering priorities;
- terminal and recovery predicates (named strategies, not inline lambdas).

The Albaz fixture becomes the first config instance, not the hardcoded
center.

- Exit: a second deck or matchup runs through `search_opening.py` without
  copying or editing any tool script - config only. Existing Albaz results
  are byte-identical.

## Phase 3 - outer loop: deck consistency

Roadmap item 2, and the distinctive deliverable: nothing else in the
ecosystem produces "this deck reaches a ≥X board through the worst hand trap
Y% of the time" from verified game states.

- Enumerate or sample opening hands (reusing `--hand` plumbing).
- Run the inner solver per hand against the configured interruption set.
- Weight results by hypergeometric probability (`probability.py` grows
  here); classify bricks and garnets explicitly.
- Report a consistency distribution, not a single number, and carry each
  hand's `complete` flag into the aggregate so provisional scores stay
  labeled.
- Exit: one command produces a deck-level report for the Albaz deck across
  an enumerated or sampled hand space, with per-hand provenance.

## Phase 4 - many-world hidden search

Only after phase 3: replace policy-product enumeration for the probabilistic
hidden-hand experiment with determinization/sampling or MCTS (README roadmap
item 3). Two-world maximin (`hidden_minimax_replay`) stays as-is for the
guaranteed-hidden experiment.

When touching this code, extract the transposition-cache bound bookkeeping
duplicated between `minimax_replay` and `hidden_minimax_replay` (including
the trailing `cache.get(...)[2] == "exact"` re-lookup) so the two cannot
drift.

- Exit: the probabilistic experiment completes on an opponent deck model
  with more than two worlds, with an explicit statement of what guarantee
  (bound, sample confidence) the reported score carries.

## Phase 5 - learned models

The OCGCore-backed search remains the correctness oracle. It determines legal
actions, resolves card effects, and labels resulting states and endboards.

The first learned system should be supervised policy/value imitation trained
on those oracle-labelled recovery states:

- the policy predicts the oracle's preferred legal action;
- the value model predicts the oracle/search evaluation of the state;
- the action mask remains authoritative and learned policies may only select
  actions currently legal in OCGCore.

This is not reinforcement learning by itself: the model learns from fixed
oracle labels rather than discovering behavior through reward-driven
exploration. The Gymnasium environment (`env.py`) should wrap the real
OCGCore engine for rollout and evaluation only after phases 1-4 produce
trustworthy data at scale. Constrained or offline RL may follow once the
imitation baseline is reliable, but it must not replace OCGCore legality or
the exact search oracle.

## Non-goals for now

- Core-level duel cloning or serialization: phase 1's prefix reuse should be
  exhausted first, since it needs no core patches.
- General gameplay AI: the target remains combo search and deck consistency
  analysis, not playing full matches.
