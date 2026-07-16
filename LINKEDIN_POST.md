# LinkedIn post - backend-identity framing

Status: draft v3 (de-shined), 2026-07-15. Angle: absurd hobby, unreasonable
rigor - correctness is the backend virtue nobody posts about. Humor lands
upward (the punchline raises the stakes), never apologizes for the hobby.

## Post

Everyone on my feed is shipping AI products. I spent my weekends teaching
a computer to play a children's card game, with mathematical proofs.

I'm a backend engineer. The obvious approach here was reinforcement
learning, and that's probably where this project ends up eventually. But I
didn't start there, for a very backend reason: you can't trust training
data from an engine you haven't verified, and you can't verify a policy
that can't show its work.

So I did what backend people do and made everything deterministic first:

→ A native adapter over the real game engine, every duel reproducible from
a seed
→ Exhaustive search over actual legal game states, not an abstraction of
the game
→ A belief-state variant for hidden information, so the search plays
around a card it cannot see

The result: my program finds the optimal way to play through an opponent's
Ash Blossom interruption. Not "usually wins in simulation" - 965 states
searched, search complete, worst case known exactly.

My favorite feature is one boolean. When search hits its node budget, the
report says `complete: False` and labels the score provisional. I've seen
production dashboards with less integrity than that flag.

The lesson I keep relearning: before reaching for the expensive tool you
can't verify, check whether the problem gives in to the cheap tool you
can. Minimax is old and boring. It also comes with a guarantee.

(ML does enter the roadmap eventually, but only once the solver can
generate training data trustworthy enough to learn from. Verified system
first.)

Next up: deck-consistency analysis. "This deck survives the worst hand
trap X% of the time," computed from real game states, not spreadsheet
theory.

There's a bigger lesson in here about how we build and verify agent
loops, but that's its own post.

Repo and write-up coming soon. If you're into game AI, search algorithms,
or you just have strong opinions about Ash Blossom timing, I'd love to
hear them.

## Reader takeaways (the post fails if these don't land)

1. Any engineer: try the boring, verifiable tool before the expensive,
   unverifiable one - and label unproven results as unproven.
2. Backend people: production instincts (determinism, reproducibility,
   honest reporting) transfer to problems that look like another
   discipline's territory.
3. Career-watchers: a public hobby project can demonstrate engineering
   judgment better than work you can't talk about.

## Editorial notes

- De-shine rule (v3): no mic-drop one-liners, no "Proves." style
  repetition, no triple parallelism. Never use the em dash "—"; use the
  plain dash "-" instead. Punchy is fine; performed is not. If an edit
  reintroduces keynote cadence, flatten it.
- Opening joke is self-aware, not self-diminishing: never tell readers the
  post isn't impressive. The gap between "children's card game" and
  "mathematical proofs" is the humor; no apology needed.
- "Proofs" appears in line two on purpose - it's the differentiator and the
  "see more" bait.
- Exactly one named card (Ash Blossom); more jargon loses non-players.
- One number per claim: 965 states, `complete` flag. Don't add more stats.
- The `complete: False` paragraph is the shareable core - keep it even if
  the post gets trimmed.
- The ML parenthetical preempts "why not RL" comments and sets up a sequel
  post when phase 5 (learned models, see DIRECTION.md) ships.
- The agent-loops bridge line plants the flag for post #2 (enumerable
  unknowns) without importing its argument. Keep it to one sentence and
  keep it jargon-free; post #1 stays the story, post #2 makes the claim.
- No scalability claims - the flex is integrity, which the code backs up.
- Never disclaim ML identity ("not an ML person") - the author may pursue
  an ML-adjacent master's later. The claim is sequence ("didn't start
  with ML"), not identity ("ML isn't me"). The post should read as
  evidence of methodological maturity to an admissions reviewer.

## Attachment: one image, output not code

Do not paste code - LinkedIn mangles it and it shifts the genre from story
to tutorial. Attach one tightly-cropped terminal screenshot (dark theme) of
`python tools/search_opening.py ash` showing:

```
Opening-hand minimax against known ash
score: 8.75
visited states: 965
complete: True
```

(Verified against a live run on 2026-07-15; crop out the raw card-ID
action line and the Ecclesia/recovery flags.) That is the post's claim in
physical form. Optional second image: the README interruption-coverage
table (all rows "Complete") - but one image is enough.

## Optional line (use at most once, verbatim framing matters)

Researchers recently proved optimal play in unrestricted Yu-Gi-Oh is
literally undecidable (arXiv:2603.02863). That's why the flag matters:
in a game where the general question is unsolvable, an honestly bounded
proof is the strongest claim available. - If used, place it after the
`complete: False` paragraph. Never phrase it as "my solver tackles an
undecidable problem"; the claim is that boundedness is the right target,
not that YAPPING defeats undecidability.

## Variants by goal

- **Employer visibility:** add one stack line, e.g. "C++ engine bindings,
  Python search layer, SQLite, pinned-revision CI."
- **Collaborators:** swap the last line for a direct ask, e.g. "if you play
  a deck you'd want analyzed, tell me which one."

## Before posting checklist

- "Repo and write-up coming soon" must be true - soften it if the repo is
  still private on posting day. The write-up is WRITEUP.md; once public,
  replace that line with a direct link to it.
- Regenerate the screenshot from a fresh run so the numbers match the repo.
