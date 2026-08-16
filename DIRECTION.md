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

## Capability ladder

High-level maturity of YAPPING capabilities. Status reflects what the
repository can do today, not aspirational marketing.

**This ladder describes increasing autonomy, not a strict implementation
sequence.** A higher level should be pursued only when experiments reveal a
limitation that the next method is expected to address.

| Level | Capability | Current status |
| ----- | -------------------------------------------------------- | ---------------------------- |
| 0 | Verify predefined combo lines | 🟢 Implemented |
| 1 | Search alternative lines from a known hand | 🟢 Implemented |
| 2 | Find recovery lines through configured interruptions | 🟢 Implemented |
| 3 | Compare solver utility across opening hands | 🟡 Measurement baseline |
| 4 | Exact search over small hidden-information world sets | 🟢/🟡 Limited implementation |
| 5 | Approximate larger hidden-information spaces by sampling | 🟡 Early implementation |
| 6 | Generate oracle-labelled training data | 🟢 Infrastructure exists |
| 7 | Learn policy/value models from oracle search | ⚪ Planned |
| 8 | Use learned models to guide tree search | ⚪ Planned |
| 9 | MCTS-based combo discovery | ⚪ Experiment only if justified |
| 10 | RL / iterative policy improvement | ⚪ Experiment only if justified |
| 11 | Joint deck-composition + policy optimization | ⚪ Long-term research |
| 12 | General expert Yu-Gi-Oh! agent | 🔴 Explicit non-goal for now |

Strategic banding:

- Levels 0–6: trustworthy experimental foundation
- Levels 7–8: primary near-term learning/planning research
- Levels 9–11: evidence-driven extensions after measured bottlenecks
- Level 12: explicit non-goal

Legend: Implemented = usable and exercised by fixtures/tools;
In development / Limited / Early / Measurement baseline = code exists but
incomplete relative to the stated capability; Planned / Research / Non-goal =
not a near-term deliverable.

Research workflow before advancing a method:

    baseline → measure bottleneck → hypothesis → smallest method → compare → decide

Do not introduce MCTS, RL, or neural guidance merely because it is more
advanced. Levels 0-2 are the inner solver spine. Level 1 includes a
goal-conditioned mode: required endboard pieces, first-hit stop, and a
best-partial result if the node budget hits first
(`tools/search_target_board.py`). Level 3 is the outer loop
(consistency sampling, role-conditioned and quantified utility) plus search
complexity benchmarks that later ML must beat. Levels 4-5 are hidden-
information search. Levels 6-10 consume the deterministic oracle. Level 11 is
Phase 3E / long-horizon research. Level 12 remains an explicit non-goal: the
product is combo resilience and deck consistency analysis, not a general
dueling agent.

### Search measurement baseline

`tools/search_benchmark.py` and `src/yapping/benchmark.py` record exact-search
complexity on fixed scenarios: visited states, search-relevant branching,
cutoffs, transposition hits/misses, runtime, completeness, and score across
node budgets. Future policy-guided comparisons must reuse the same
`scenario_id` values; `future_guided_comparison` fields stay null until Level 8.

Empirical readiness writeup: `reports/level7_readiness.md` (with data under
`reports/data/`). Recommendation there is evidence-based and may be
**CONDITIONAL GO** rather than an automatic advance to training.

### Oracle data readiness (Level 6)

`tools/training_data.py` can export versioned examples with state, legal
actions, oracle action/value, completeness, and provenance. Known gaps: full
per-state action-value tables exist mainly at the search root; deeper
trajectory states currently pin the chosen action's value; there is not yet a
multi-scenario export tied to the search benchmark suite.

## Design assessment (summary)

The four-layer stack is sound and should be preserved:

1. native adapter (`cpp/adapter.cpp`) - deterministic duels, decoded legal
   actions, binary state key, no cloning;
2. generic search library (`src/yapping/`) - replay-based alpha-beta with a
   bound-labeled transposition cache, plus belief-state hidden search;
3. fixture tools (`tools/`) - evaluator weights, action abstraction, terminal
   predicates, currently Albaz-specific;
4. two-layer model - inner per-hand minimax, outer deck-level aggregation
   (opening-hand sampling, role features, and conditioned/quantified utility
   summaries exist; full-deck exact consistency and deck optimization do not).

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

`--replay-mode fork` is the Phase 1 mechanism: one `os.fork` copy-on-write
worker per current DFS prefix. Default `--replay-mode` stays `cursor`.

On macOS this does not land. A child that `step()`s a forked OCGCore duel
segfaults in `libsqlite3` (`sqlite3_reset` → `os_log_type_enabled`) around
140 visits on Ghost Ogre. Fake-adapter IPC is fine; the native card reader
is not fork-safe here. Ghost Ogre cursor baseline on this machine: about
2-3 ms/state. `--replay-mode fork` raises on Darwin unless
`YAPPING_FORK_ALLOW_DARWIN=1`. Linux remains the intended host.

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

Phase 3 is one outer optimization problem layered into smaller foundations.
These are not five independent mega-projects:

### Phase 3A — Card-role model

Multi-label card semantics (`starter`, `extender`, `interaction`, …) loaded
from archetype/matchup config. A card may carry several roles at once; roles
are data-driven strings so the vocabulary can grow without core rewrites.

### Phase 3B — Hand-feature distribution

Map concrete opening hands to role counts and related features
(`P(starter ≥ 1)`, `P(extender = 2)`, overlaps). Prefer exact
hypergeometric/combinatorial treatment for single-role counts; joint role
events need careful enumeration because cards are drawn without replacement
and one card can satisfy multiple roles.

Status: role counts and single-role hypergeometric helpers exist; conditioned
solver-utility aggregation over those features is the bridge into 3C.

### Phase 3C — Deck consistency evaluation

Enumerate or sample opening hands (reusing `--hand` plumbing). Run the
inner solver per hand against the configured interruption set. Weight
results by hypergeometric probability; classify bricks/garnets (legacy) and
role features. Report a consistency distribution, not a single number, and
carry each hand's `complete` flag into the aggregate.

`conditioned_hand_utility` and `quantified_hand_report` summarize
`E[U | role composition]`, utility distributions, and threshold rates
`Playable_T := U >= T` over evaluated hands. Sampled unique-hand runs report
`evaluated_probability_mass` and must not claim full-deck coverage.

**Terminology principle:** every analytical term maps to an observable
quantity, explicit mathematical function, or configurable predicate. Keep
hand features (role counts) distinct from solver outcomes (`U(H,I)`) and
derived metrics (ceiling, interruption loss, floor over the configured
interruption set). Bucket deltas are conditional associations; extender
replacement remains the interventional/counterfactual analysis.

### Phase 3D — Card/ratio sensitivity

Measure how utility changes when copy counts or role densities shift
(counterfactuals such as extender replacement already exist; generalize).

A first primitive is `role_density_opening_profile`: theoretical opening-count
probabilities from deck role-copy counts, reported beside conditioned utility.
Changing the list and re-running search remains the path to ratio decisions.

### Phase 3E — Deck composition optimization

Eventually search deck lists under the outer objective, approximately:

    D* = argmax_D E[ U(π*(H, I)) ]

where `D` is deck composition, `H` is an opening hand drawn from `D`, `I` is
an opponent interruption/scenario, `π*` is the best legal line from the
inner solver, and `U` evaluates the resulting line/state.

This optimizer does **not** exist yet. Maximizing a single density such as
`P(extender ≥ 1)` is not the objective: marginal extender value can fall or
turn negative when hands stack too many engine pieces, so the useful
quantities often look like the full count distribution
`P(extender = 0), P(extender = 1), P(extender = 2), P(extender ≥ 3)`
conditioned on utility from the inner solver.

Exit for the phase-3 spine: one command produces a deck-level report for the
Albaz deck across an enumerated or sampled hand space, with per-hand
provenance and role features available for later sensitivity work.

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

## Dual OCGCore backends (Fluoro + Ignis)

The default oracle stays Fluorohydride/ygopro-core + ygopro-scripts + the
MyCard `cards.cdb` pin. That stack is what current fixtures reproduce.

A second oracle is in scope: edo9300/ygopro-core + ProjectIgnis/CardScripts +
BabelCDB. CardScripts target that stack and Lua 5.3; they are not drop-in on
Fluorohydride. Do not mix the two script trees or the two card databases in
one process.

Canonical card ids in MAPPING exports remain MyCard passwords. Ignis
pre-release ids remap in MAPPING before they reach YAPPING. Each backend
keeps its own cdb, scripts, and adapter. Do not treat Ignis as faster per
search node until the same combo tree is measured after an adapter exists.

The first proof for this Ignis slice is the Albaz combo gate: the adapter can
create a duel, run CardScripts-backed effects, and return legal actions. That
gate rejected the hypothesis that the same scripted line matches across both
backends. Existing Fluoro fixtures must still pass on the Fluoro backend.

### The match hypothesis died at the combo gate

The hypothesis that one scripted line could be replayed on both backends is
dead. `tools/trace_albaz_combo.py --engine ignis` stops at the first Synchro
summon (Ecclesia and the Dark Dragon): Fluorohydride sends
`MSG_SELECT_CARD` then `MSG_SELECT_SUM` for material selection, while
edo9300 + CardScripts sends `MSG_SELECT_UNSELECT_CARD` twice. Both prompts
are well formed, both reach the same board, but the legal action set at each
decision point differs, so a single hardcoded action sequence cannot address
both. Evidence: `reports/ignis_albaz_combo_divergence.txt`.

Consequence: cross-engine comparison needs prompt-protocol-agnostic action
selection (or per-engine lines), not a shared scripted trace. Do not compare
search results across backends until that exists - the two engines do not
expose the same decision tree even when they agree on the game state.
The Ash search comparison has not been run.

## Non-goals for now

- Core-level duel cloning or serialization: phase 1's prefix reuse should be
  exhausted first, since it needs no core patches.
- General gameplay AI: the target remains combo search and deck consistency
  analysis, not playing full matches.
