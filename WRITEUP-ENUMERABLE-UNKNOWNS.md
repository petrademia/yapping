# Making unknowns enumerable

*Draft essay, companion piece to [WRITEUP.md](WRITEUP.md). Post #2 in the
series: the ideas piece. Same rules as the main write-up: every number
comes from a fixture in this repo and reproduces from a seed. Quotes from
the loop-engineering material should be re-verified against the sources
before publication.*

---

Loop engineering became a named discipline in mid-2026. The term,
popularized by Addy Osmani building on ideas from Boris Cherny and Peter
Steinberger, describes a real shift: stop hand-crafting prompts and design
the system that prompts your agent instead. The canonical loop has five
components - a trigger, a goal, actions, verification, and memory - and
the pitch is leverage: one designed loop replaces a hundred manual
prompts.

I think the discipline is real and the shift is real. I also think the
most important sentences in its literature are the ones nobody leads
with. From the community's own reference material: "unattended loops make
unattended mistakes," and, on reproducibility, "two people can run the
same loop and get opposite results."

Those aren't footnotes. Those are the product description.

So here's my contrarian claim, stated carefully. Verification is listed as
one component out of five, a peer of scheduling and memory. I think it's
the only load-bearing one, and the current practice has it backwards: in
most loops, the thing checking the stochastic worker is more stochastic
machinery. An LLM verifying an LLM, evals sampled from the same
distribution as the failures. The loop doesn't remove uncertainty from
your system. It relocates uncertainty into the machinery and abstracts it
away, and "opposite results from the same loop" is what that looks like
from the outside.

I spent the last while building a system with the opposite shape, in the
least serious domain imaginable, and it taught me what I actually want
from uncertainty. I don't want fewer unknowns. I want my unknowns
enumerable.

That sounds almost too plain to be a discipline, so let me define it. An
unknown is enumerable, in the sense I mean, when:

1. its possibility space is a list, not an open end;
2. every state transition, given any resolution of the unknown, is
   reproducible;
3. every claim is a worst case or a probability weight over that space;
4. and when the space exceeds the budget, the system says so instead of
   rounding "didn't finish" up to "done."

Uncertainty about the world is fine. Uncertainty about your own machinery
is the defect.

## A hidden card, handled with bookkeeping

The system is YAPPING, a solver for Yu-Gi-Oh combo lines (background in
the [main write-up](WRITEUP.md)). The relevant problem: you execute a long
turn-one combo while your opponent may or may not be holding Ash Blossom,
a card that can negate one effect at one moment of their choosing. You
commit to your line before you learn whether the card exists. This is
genuine uncertainty of the kind no loop can retry away. There is no
phased rollout in a duel. You get one attempt.

The loop-engineering instinct here would be to sample: play the line a
few thousand times against a randomized opponent and report a win rate.
The number would even be useful. But it answers a different question than
the one I care about, which is: what is the best result I can guarantee?

YAPPING answers by making the unknown enumerable. The opponent's hidden
card becomes a list of two worlds, Ash and no-Ash, and the solver requires
the player to pick actions that are legal in both, because from the
player's seat the worlds are indistinguishable. When the opponent passes,
the worlds stay merged; a pass looks identical whether or not they hold
the card. Only a public activation splits the belief state. Underneath,
every duel in every world is deterministic to the seed. The unknown is
real, but it's the only unknown in the building. The machinery contributes
nothing.

The search completes in 4,298 state visits and guarantees a worst-case
score of 8.75. Separately, a search that knows the Ash is there completes
in 965 visits and also lands on 8.75. Those two numbers agreeing is a real
result: for this hand, the optimal line doesn't need to peek. I didn't
expect that, and no amount of sampling would have told me it with a proof
attached.

Two people can run this loop. They get the same result, to the byte.

## This is still a loop

Here's the part I find funny. Judged by the five components, YAPPING *is*
loop engineering: a trigger (the CLI invocation), a goal (a verifiable
end-state score), actions (the decoded legal moves), verification (the
deterministic engine itself, plus a completeness flag), and memory (a
transposition table that caches proven bounds). I didn't reject the
discipline. I followed it to what I think is its logical conclusion, which
is that the verification component should be the design center, and it
should be made of different stuff than the thing it checks.

A checker built from the same stochastic material as the maker can be
wrong in the same ways at the same time. A deterministic checker can't.
That's the whole argument, and none of it is specific to card games.

## Even the limits are enumerated

There's a boundary worth admitting, because enumerable unknowns are a
discipline, not a superpower. Nicolosi, Pisciotta, and Bresolin recently
proved that optimal play in unrestricted Yu-Gi-Oh is undecidable; they
encode Turing machines in the game's mechanics and reduce the Halting
Problem to whether a strategy wins
([arXiv:2603.02863](https://arxiv.org/abs/2603.02863)). No algorithm can
promise optimal play in general, in this game, ever.

I find this clarifying rather than discouraging. The general problem being
unsolvable is precisely why bounded claims with explicit scope are the
right product: a fixed deck, a declared action abstraction, a node budget,
a completeness flag. Even the system's ignorance is on the list. That is
what I'd ask of any loop: not that it never fails, but that its failure
modes are enumerated somewhere, not discovered in production.

## Where the stochastic parts belong

This isn't a purity lecture; stochastic methods are on my own roadmap.
Monte Carlo search enters when opponent hands get too numerous to
enumerate one by one, and learned models enter after that, to guide the
search with better move ordering and leaf evaluation.

The difference is the contract, and it's the maker/checker split that
loop engineering already believes in, taken seriously. When sampling
arrives, its reports carry sample counts and confidence, not vibes. When
a learned model arrives, it only proposes; the deterministic search still
verifies every answer, and the training data itself comes from completed
searches, so every example is a state, a best action, and a proven score.
The stochastic parts get to make things faster. They never get to make
the claims.

Loop engineering optimizes for how often things go right. I think the
better target, most of the time, is knowing exactly how wrong things can
go. Make your unknowns enumerable before you make your loops longer.

---

*YAPPING is unofficial and is not affiliated with or endorsed by Konami,
Shueisha, or the maintainers of the referenced simulator projects.*

---

## LinkedIn post version (post #2)

Status: draft v3, de-shined, re-grounded against the real loop-engineering
term (Osmani/Cherny/Steinberger framing; Greyling's reference repo),
retitled to the enumerable-unknowns angle. Hook comes from the
loop-engineering side and quotes its own literature; Yu-Gi-Oh arrives
mid-post as evidence, never as the hook. Post after post #1 has run, with
a link back to it and to this essay.

### Post

Buried in loop engineering's own reference material is this sentence:
"two people can run the same loop and get opposite results."

I think that sentence deserves more attention than the rest of the
movement combined.

To be clear, I buy the shift. Designing the system that prompts your
agent beats hand-prompting, and the five components (trigger, goal,
actions, verification, memory) are a real framework. My contrarian claim
is narrower: verification is listed as one component of five, and it's
the only load-bearing one. And in most loops today, the thing checking
the stochastic worker is more stochastic machinery. Same distribution,
same blind spots, wrong in the same ways at the same time.

The alternative I want is almost embarrassingly plain: make your unknowns
enumerable.

An unknown is enumerable when:

→ its possibility space is a list, not an open end
→ every transition, given any resolution, is reproducible
→ every claim is a worst case or a probability weight over that space
→ when the space exceeds the budget, the system reports incomplete
instead of rounding up to done

Uncertainty about the world is fine. Uncertainty about your own machinery
is the defect.

My receipt comes from the least serious domain I could have picked: a
solver for Yu-Gi-Oh combo lines. The hard version of the problem: commit
to your whole line before learning whether your opponent holds the one
card that wrecks it. One attempt. No retries, no phased rollout.

The solver doesn't sample a win rate. It turns the hidden card into a
list of two worlds (card exists, card doesn't), requires every choice to
be legal in both, and splits the worlds only when the opponent publicly
reveals which one you're in. Underneath, every duel is deterministic to
the seed.

The result that sold me: the search that cannot see the card guarantees
the same worst-case score as the search that can. 8.75, both proven
complete. A million samples would have suggested that. Bookkeeping proved
it.

And the punchline: by the five components, my solver IS a loop. Trigger,
goal, actions, verification, memory - all present. The difference is that
the checker is made of different stuff than the maker. Two people can run
this loop. They get the same result, to the byte.

Stochastic methods are still coming to this project, under contract: they
propose, deterministic search verifies. They make it faster. They don't
get to make the claims.

Make your unknowns enumerable before you make your loops longer.

(Full essay and repo linked below. Background story in my previous post.)

### Editorial notes

- Title = thesis = closing line ("make your unknowns enumerable"). If any
  edit breaks that triangle, restore it.
- Hook identity: this post owns the loop-engineering hook; post #1 owns
  the hobby hook. Never swap or blend them.
- The hook quotes the movement's own material - that's the shield against
  strawman accusations. Re-verify both quotes ("opposite results",
  "unattended loops make unattended mistakes") against the explainx.ai
  post and Greyling's repo before publishing, and link whichever source
  the quote actually comes from.
- Steelman before striking: the post concedes the shift is real and the
  framework useful before making the narrow claim. Keep the concession
  even when trimming; it converts "loops bad" readers into "verification
  first" readers.
- The term arrives after the critique, as the alternative - it is the
  payoff, not the bait. The quote is the bait. "Almost embarrassingly
  plain" is deliberate positioning: modesty, not branding.
- One stat, stated once: the 8.75 agreement between hidden and known
  search. Do not import post #1's numbers (965, the boolean paragraph).
- "My solver IS a loop" is the disarm for loop-engineering practitioners;
  it reframes the post from attack to extension. Keep it.
- Close on a position, not an artifact. Idea-posts end with claims.
- De-shine rule applies as in post #1's notes.

### Attachment

One image: side-by-side (or stacked) terminal output of
`python tools/search_opening.py ash` and
`python tools/search_hidden_ash.py ash`, cropped to show both reports
ending in the same worst-case score with `complete: True`. The visual
argument is two different searches, one guarantee. Regenerate from a
fresh run before posting; crop out raw card-ID action lines.

### Before posting checklist

- Post #1 must already be published; the closing line references it.
- Re-verify the two loop-engineering quotes against their sources and
  attribute correctly (explainx.ai article vs. cobusgreyling/loop-
  engineering repo).
- Verify the hidden-search output still reports 4,298 visits / 8.75 /
  complete before screenshotting (the essay cites these).
- Replace "linked below" with the actual essay URL once public.
- Tone check: the post should read as extending loop engineering, not
  dunking on it. If a reader could summarize it as "agents are overrated,"
  revise.