# X thread - post #1 story, native thread format

Status: draft v1, de-shined, 2026-07-15. Post same day as LinkedIn post
#1 (see LINKEDIN_POST.md). One idea per tweet; every tweet must survive
being quoted alone. Screenshot on tweet 5. Repo link in the final tweet
only - X downranks link-leading posts.

## Thread

**1/**
Everyone's shipping AI products. I spent my weekends teaching a computer
to play a children's card game, with mathematical proofs.

A thread on why I refused to train a model (at first):

**2/**
Modern Yu-Gi-Oh turn one is a hard planning problem: long effect chains
toward a strong board while your opponent holds hidden interruptions that
can collapse the line at one moment.

Players argue about optimal play constantly. It gets settled by
reputation, not proof.

**3/**
The default approach is RL. I didn't start there, for one reason:

You can't trust training data from an engine you haven't verified. And
you can't verify a policy that can't show its work.

A 63% win rate is a percentage with a shrug attached.

**4/**
So I did the backend engineer thing and made everything deterministic
first.

Native adapter over the real game engine. Every duel reproducible from a
seed. Every prompt decoded into explicit legal actions. Unsupported
messages raise errors instead of guessing.

**5/**
Then: alpha-beta minimax over real replayed duels.

Give the opponent exactly one Ash Blossom. Search every legal activation
window, every response.

965 states later: search complete, worst case known exactly, optimal
recovery line proven.

[ATTACH: cropped terminal screenshot - score 8.75 / 965 states /
complete: True]

**6/**
The harder version: you don't know if the Ash exists - you commit before
finding out.

The solver keeps both worlds alive, splitting them only on a public
reveal. The blind search guarantees the same worst case as the sighted
one.

The optimal line doesn't need to peek. Didn't expect that.

**7/**
My favorite feature is one boolean.

If search exhausts the space: proven bound. If it hits its node budget:
`complete: False`, score labeled provisional, never presented as optimal.

I've seen production dashboards with less integrity than that flag.

**8/**
Fun fact: optimal play in unrestricted Yu-Gi-Oh was recently proven
undecidable - researchers encoded Turing machines in the game's mechanics
(arXiv:2603.02863).

In a game where the general question is unsolvable, an honestly bounded
proof is the strongest claim available.

**9/**
ML does enter the roadmap eventually. Every completed search emits
(state, best action, proven score) - training data with verified
provenance, the only kind I wanted.

The model will make the solver faster. The solver keeps the model honest.

**10/**
There's a bigger lesson in here about how we build and verify agent
loops. That one's its own post, coming soon.

**11/**
Old and boring beats new and unverifiable more often than my industry
admits. Minimax is from the 1950s. It comes with a guarantee.

Repo + full write-up: [LINK]

If you have strong opinions about Ash Blossom timing, my replies are
open.

## Editorial notes

- Tweet 1 mirrors LinkedIn post #1's hook on purpose - same-day posts,
  same story, native formats. Do not run the loop-engineering angle here;
  that's post #2's identity.
- Each tweet stands alone when quoted. If an edit makes a tweet depend on
  the previous one to parse, restore independence.
- One stat per tweet, no stat repeated. 965 lives in tweet 5, the flag in
  tweet 7, undecidability in tweet 8.
- Tweet 6 deliberately omits the number pair (4,298 / 8.75 twice) - on X
  the sentence "the optimal line doesn't need to peek" carries it; the
  numbers live in the write-up.
- Tweet 8 is droppable if the thread needs to shrink; tweets 1-7 + 9-11
  are the spine. Never phrase 8 as "my solver tackles an undecidable
  problem."
- Tweet 10 is the bridge to post #2 (enumerable unknowns). Keep it
  jargon-free; it plants the flag, it does not make the argument. When
  post #2 ships, quote-tweet this thread from it.
- Link only in the final tweet. If engagement warrants, reply to tweet 5
  with the score-breakdown output as a bonus artifact.
- De-shine rule applies (see LINKEDIN_POST.md notes), with one X-specific
  allowance: fragments are native to the medium and fine here.

## Before posting checklist

- Verify each tweet is ≤280 characters after any edits.
- Same screenshot as LinkedIn post #1 (fresh run, cropped, dark theme).
- Replace [LINK] with the public repo URL; post the thread the same day
  as LinkedIn post #1.
- Check arXiv:2603.02863 renders as a card or add the full URL in tweet 8
  if not.
