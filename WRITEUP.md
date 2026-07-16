# Solving Yu-Gi-Oh combos with search instead of ML

*Draft for publication (blog / repo front page). Companion to the LinkedIn
post; technical reference is [README.md](README.md), roadmap is
[DIRECTION.md](DIRECTION.md). All numbers come from fixtures in this repo
and are reproducible from a seed.*

---

I play Yu-Gi-Oh on weekends. I'm also a backend engineer, so when someone
tells me a combo line is "optimal," my first question is how they know.

Modern Yu-Gi-Oh turn one is a hard planning problem. You chain a long
sequence of card effects toward a strong board while your opponent holds
unknown interruptions. A hand trap like Ash Blossom negates one effect at
one moment, and if it's the right moment, your whole line falls apart.
Players argue about the correct response constantly, and the arguments get
settled by whoever has more tournament results, not by anything you could
check.

I wanted something you could check. So I built YAPPING (Yet Another
Program for Parsing Interactive Game Nodes).

## Why not just train a model

The default approach for card game AI right now is reinforcement learning.
That's probably where this project ends up eventually. I didn't start
there, for a reason anyone who runs production systems will recognize: you
can't trust training data from an engine you haven't verified, and you
can't verify a policy that can't show its work.

An RL agent that wins 63% of simulated games gives you a percentage. It
can't tell you the correct response to Ash Blossom in a specific spot, and
if the underlying simulation decodes even one prompt wrong, it will
happily learn from garbage. Before doing any learning I wanted a substrate
where every state and every legal action was something I could trust.

Minimax with alpha-beta pruning is old and boring, but if the search
completes, the answer is optimal under the model. I'll take that trade.

## Making the game deterministic

YAPPING is a four-layer stack. Most of the engineering effort went into
the bottom layer: a native C++ adapter over OCGCore, the same open-source
engine behind the simulators people actually play on. The adapter pins
exact engine and card-script revisions, loads real card data from SQLite,
and decodes every protocol prompt (summons, chains, targets, positions,
zone choices) into explicit legal actions.

Two rules I didn't bend on:

1. Every duel is reproducible from a seed. Same seed, same actions, same
   state, every time. Replay from the seed is the ground truth everything
   else gets checked against.
2. Unsupported protocol messages raise an error instead of guessing. New
   prompt types get added only when a real fixture needs them, and the
   canonical combo fixture runs end to end in tests: two Synchro summons,
   two Fusion summons, ordered chain construction and reverse resolution,
   through both End Phase effects.

Above the adapter sit a generic search library, the analysis tools, and a
two-layer model: the inner problem (given this exact hand and this
interruption, which line survives the worst case?) and the outer problem
(across all likely hands, how consistent is the deck?).

## What the solver actually proves

Give the opponent exactly one Ash Blossom. Across every legal activation
window, against optimal timing, what's the best the combo player can
guarantee?

The search answers by replaying real duels. Not an abstraction of the
game, the actual engine resolving actual card scripts. From the opening
decision, alpha-beta visits 965 replayed states, completes, and lands on a
worst-case score of 8.75. The opponent's best Ash timing turns out to be
the Fallen of the White Dragon deck-summon trigger, and the best recovery
runs through the End Phase to keep the board's interaction and follow-up.

A note on what "proves" can honestly mean here. Nicolosi, Pisciotta, and
Bresolin recently showed that optimal play in unrestricted Yu-Gi-Oh is
undecidable: they encode Turing machines in spell counters and reduce the
Halting Problem to whether a strategy wins
([arXiv:2603.02863](https://arxiv.org/abs/2603.02863)). Their
configurations are deliberately pathological, not tournament positions,
but the conclusion applies: no algorithm can promise optimal play for the
game in general. That's why YAPPING only makes claims about bounded
instances: a fixed deck, a declared action abstraction, an explicit node
budget, and a completeness flag on every answer.

The same treatment covers Effect Veiler (1,317 states), Infinite
Impermanence (1,390), Droll & Lock Bird (8,696), Nibiru (10,975), and
Ghost Ogre (22,756). Each search completes, each interruption gets its own
optimal timing and recovery line. Droll is the interesting one: its worst
case doesn't recover from a negation, it reroutes the whole combo. Which
is why each interruption needs its own search instead of folk wisdom
carried over from a different matchup.

## Playing around a card you can't see

Known-interruption search is diagnosis. Real games are worse, because you
commit to a line before you learn whether the Ash exists.

YAPPING handles this with belief-state search. The solver keeps multiple
worlds alive (Ash and no-Ash) and requires the combo player to pick
actions that are legal in every world, since from the player's seat the
worlds look identical. An opponent's pass keeps the worlds merged, because
a pass looks the same either way. Only a public activation splits them.
The guarantee is maximin: the best score you can lock in against the worst
world.

The hidden-Ash experiment completes in 4,298 state visits and reaches the
same 8.75 worst case as the known-Ash search. For this hand, the optimal
line doesn't need to peek. I did not expect that going in.

## The completeness flag

Every report ends with `complete: True` or `complete: False`.

If the search exhausted the space, the score is a proven bound. If it hit
its node budget, the score gets labeled as a provisional heuristic and is
never presented as optimal. The evaluator weights are printed in the
output and documented as a testable baseline, because that's all they are.

A lot of analysis in this hobby (and a fair number of production
dashboards I've seen) presents guesses formatted like answers. This flag
exists so the system can't do that.

## The current roadblock

I'm not going to hide the unsolved problem, since the whole point of the
project is not doing that.

Replay-from-seed is safe because every search node gets a freshly built,
isolated duel. It's also O(states × path length), and paths run about 180
decisions deep. At Ash's 965 states you don't notice. At Ghost Ogre's
22,756 you notice. For the outer problem, thousands of opening hands, it's
a wall.

The obvious fix, cloning the duel state, doesn't exist. An active OCGCore
duel is a web of pointers between cards, effects, and chains, plus a live
Lua interpreter. Shallow copy is corruption. A hand-written deep clone or
core-level serialization means forking the engine I pinned specifically
because I trust it as-is.

So the plan is a ladder, cheapest rung first:

- cache card rows and script bytes so duel construction stops re-reading
  the database on every replay;
- auto-advance forced single-action prompts, which are most of that depth;
- let one live duel follow the search's descent, replaying only on
  backtrack;
- parallelize the outer loop over opening hands, which is embarrassingly
  parallel;
- when scale actually demands it, use `fork()` as copy-on-write
  snapshotting. The kernel duplicates the whole native state, Lua
  interpreter and RNG included, in under a millisecond, and unlike a
  hand-written clone it can't get the pointers wrong.

Replay-from-seed then becomes what it should have been all along: the
correctness oracle that every faster path is tested against.

## What's next

Near term, deck consistency: enumerate or sample opening hands, run the
solver on each against the interruption set, weight by draw probability,
and report the distribution. "This deck reaches a board worth at least X
through the worst hand trap Y% of the time," computed from real game
states, with provisional scores still labeled provisional.

After that, ML finally shows up. Every completed search already emits
(state, best action, proven score) tuples, which is a training set with
verified provenance - the only kind I was willing to build on. A learned
policy/value model will guide the search with better move ordering and
leaf evaluation, and the search keeps verifying the answers. The model
makes the solver faster. The solver keeps the model honest.

If there's a takeaway, it's the boring one: before reaching for the
expensive tool you can't verify, check whether the problem gives in to the
cheap tool you can. And when your system doesn't know something, make it
say so.

---

*YAPPING is unofficial and is not affiliated with or endorsed by Konami,
Shueisha, or the maintainers of the referenced simulator projects.*
