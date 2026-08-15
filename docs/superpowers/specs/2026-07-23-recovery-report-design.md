# Milestone 1 — Recovery report with extender attribution

Status: approved 2026-07-23.

## Goal

After a known-hand opening search, report ceiling vs interrupted scores and which
opening-hand cards were used in the best recovery line after the choke.

## CLI

```bash
# unchanged: single search
python tools/search_opening.py ash --hand ...

# paired none + interrupted + attribution
python tools/search_opening.py ash --hand ... --recovery-report
```

When `--recovery-report` and interruption is `none`: one run; ceiling equals
that score; `choke_point` / `recovery_cards_used` empty/null as appropriate.

## Report fields

| Field | Definition |
|-------|------------|
| `opening_hand` | The 5 cards searched |
| `interruption` | e.g. `ash` |
| `ceiling_score` | Best score for same hand with interruption `none` |
| `interrupted_score` | Best score under the given interruption |
| `score_loss` | `ceiling_score - interrupted_score` |
| `complete` | Both searches completed (also surface per-run flags if provisional) |
| `choke_point` | First `chain:` action in interrupted best line; null if none |
| `recovery_cards_used` | Opening-hand cards appearing in post-choke actions, minus fillers |
| actions / endboard / score breakdown | Existing interrupted-line detail |

## Attribution rules

- Derive from the final interrupted action line; no Ash→Ecclesia hardcoding.
- `choke_point` is the first `chain:<interruption_card_id>` for the named
  interruption (friendly `chain:` tokens are ignored). Null when interruption
  is `none` or that card never chained in the PV.
- `recovery_cards_used` is opening-hand cards appearing after that choke, minus
  fillers. Empty when there is no choke (including play-around PVs).
- Fillers = union of `ignored_cards`, `main_deck_filler.card` (if present),
  `counterfactual_filler` (if present).
- Do **not** require membership in `extenders`.

## Implementation shape

- Pure helpers in `tools/recovery_report.py`.
- Wire `--recovery-report` only in `tools/search_opening.py`.
- Unit tests on fake action lines.
- No ceiling cache, deck sampling, RL, or core changes.
