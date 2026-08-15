# Level 1 — Recover a combo path to required endboard pieces

Status: draft, 2026-08-16.

## Goal

Given a configured deck, a 5-card opening hand, and required endboard
pieces, search legal lines and return a combo path. The author does not
supply the action list. The board is assumed reachable; the tool does not
exist to prove impossibility.

This is a Level 1 search mode with a different leaf objective, not a new
ladder number. Output can be saved as a Level 0 combo fixture later. That
authoring step is out of scope here.

## CLI

New tool. `tools/search_opening.py` is unchanged.

```bash
PYTHONPATH=src:tools python tools/search_target_board.py \
  --config configs/albaz.json \
  --hand 73819701 91152256 91152256 91152256 91152256 \
  --target monster=44146295 \
  --target spell_trap=17751597 \
  --progress-every 5
```

| Flag | Meaning |
| ---- | ------- |
| `--config` | Matchup/deck JSON. Same loader as opening search. Default follows `load_config()`. |
| `--hand` | Exactly five cards. Same `card_id` parser as `search_opening.py` (numeric id or Albaz fixture alias). |
| `--target ZONE=CARD` | Repeatable. ZONE is one of `monster`, `spell_trap`, `grave`, `hand`, `banished`. CARD is a numeric id or fixture alias. Repeating the same pair requires that many copies in that zone. |
| `--progress-every N` | Write best-so-far JSON every N seconds. Default `5`. `0` disables timed dumps. |
| `--max-nodes` | Same meaning as opening search. Default `20000`. |
| `--max-depth` | Same meaning as opening search. Default `180`. |
| `--replay-mode` | `cursor` (default) or `oracle`. |

Interruption is always `none`. There is no interruption argument.

## Matching and score

Matching is a **multiset subset** per named zone.

- `--target monster=44146295` succeeds if `44146295` appears at least once in `zones["monster"]`.
- `--target monster=44146295 --target monster=44146295` needs two copies.
- Extra cards in that zone are allowed.
- Zones with no `--target` are ignored.

Leaf score is the integer count of required pieces present (`0..N`). Search
maximizes that count. `N` is the number of `--target` occurrences.

A line with every piece present is a complete match. Search stops at the
first such line (`goal_score = N`). If the node budget hits first, return
the best partial line. Coverage `0/N` is a valid result, not an error.

## Search wiring

- Reuse `search_opening.run_search` for duel setup, `legal()`, ReplayCursor,
  and minimax. Pass interruption `"none"`.
- Replace `endboard_score` with the coverage count. Do not use card weights.
- `terminal` stays turn-based (`terminal_turn`, default 2), **or** a complete
  match at the current node (no need to keep playing after the pieces are
  already present).
- Add optional `goal_score` to `minimax_replay`: when a maximizer node
  reaches that score, return that path immediately. Existing callers omit it
  and behave as today.
- Add optional `on_leaf(node, path, score)` to `minimax_replay`, invoked
  whenever a leaf is evaluated. The tool uses this to track best-so-far.
  Existing callers omit it.

## Progress dumps and final report

Stdout is JSON lines.

Timed dumps use `"event": "progress"`. The final line uses `"event": "result"`.
Both share the same payload besides `event`.

If search finishes before the first interval, only the result line is
printed. A dump is also written when the interval fires, even if coverage
has not improved since the last dump (still the best leaf seen). Best-so-far
updates on every leaf; the clock only controls when that snapshot is
printed.

Payload:

```json
{
  "event": "result",
  "complete_match": false,
  "coverage": 1,
  "required": 2,
  "present": [{"zone": "monster", "card": 44146295}],
  "missing": [{"zone": "spell_trap", "card": 17751597}],
  "targets": [{"zone": "monster", "card": 44146295}, {"zone": "spell_trap", "card": 17751597}],
  "opening_hand": [73819701, 91152256, 91152256, 91152256, 91152256],
  "actions": ["activate:73819701", "..."],
  "endboard": {"hand": [], "monster": [44146295], "spell_trap": [], "grave": [], "banished": []},
  "visited_states": 1200,
  "elapsed_seconds": 5.01,
  "complete": false,
  "max_nodes": 20000,
  "max_depth": 180
}
```

`complete` is the search-exhaustion flag from minimax (same as opening
search). `complete_match` is whether every required piece is present.
`actions` are the human-readable names from the replay snapshot, not raw
indices.

## Error handling

Exit code `2` for usage and validation failures. Print the error to stderr.
Do not print a result JSON on these failures.

| Condition | Behavior |
| --------- | -------- |
| `--hand` missing or not exactly five values | argparse error |
| `--target` missing (zero targets) | argparse error: at least one `--target` is required |
| `--target` not `ZONE=CARD` | argparse error |
| Unknown ZONE | argparse error listing the five legal zones |
| CARD neither a fixture alias nor an integer | argparse / `card_id` error |
| `--progress-every` negative | argparse error |
| `--config` missing or invalid | existing `load_config` error |
| Hand not a 5-card multiset subset of `main_deck` | `validate_hand_in_deck` ValueError |
| A required card id is not in `main_deck ∪ extra_deck` | ValueError naming the card. The duel cannot legally produce a card that is not in the list. |
| Native adapter / `cards.cdb` / scripts missing | same failure as `search_opening.py`; do not catch and rewrite |
| Coverage `0/N` after search | success, `complete_match: false` |
| Search hits `--max-nodes` with a partial board | success, `complete: false`, `complete_match` as observed |
| Stdout write failure during a dump | let it propagate; stdout is the product |
| `--progress-every 0` | no progress events; still print the result line |

Do not treat "I know this board is possible" as an engine invariant. If the
hand cannot make the pieces, the tool still returns the best partial path
inside the budget. That is data, not a crash.

## Tests

Pure unit tests in `tests/test_target_board.py` (fake zones, no native
engine), same style as `tests/test_recovery_report.py`.

- Coverage counts present pieces; extras in the zone do not reduce the score.
- Duplicate targets require duplicate copies.
- Unlisted zones are ignored.
- Missing pieces are listed; `complete_match` is false when any are missing.
- Progress payload has the same keys as result besides `event`.
- CLI/parser rejects unknown zones, missing targets, and bad `--progress-every`.

Minimax hooks in the existing fake-tree tests:

- `goal_score` stops at the first maximizer hit of that score.
- Omitting `goal_score` preserves current scores, paths, and visit counts.
- `on_leaf` sees increasing leaf evaluations.

No new native OCGCore fixture in v1. Wiring to `run_search` is exercised
manually with the Albaz command above.

## Implementation shape

- Create: `yapping/tools/target_board.py` (parse targets, coverage, report dict, progress clock).
- Create: `yapping/tools/search_target_board.py` (CLI + search wiring).
- Create: `yapping/tests/test_target_board.py`.
- Modify: `yapping/src/yapping/minimax.py` (`goal_score`, `on_leaf` only; default off).
- Modify: existing minimax unit tests for the two hooks.
- Optional one-line note in `DIRECTION.md` under Level 1: goal-conditioned
  first-hit search is a Level 1 mode.

Do not change card weights, opening-search defaults, recovery reports, or
hidden-information search.

## Out of scope

- Interruptions and recovery.
- Exact zone snapshots.
- Snapshots at each newly appeared piece.
- Writing a combo fixture file from the result.
- Searching over unknown opening hands.
- Interaction-count evaluators (separate DIRECTION discussion).
