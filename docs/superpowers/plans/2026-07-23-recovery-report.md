# Recovery Report Implementation Plan

> **For agentic workers:** Implement task-by-task. Steps use checkbox syntax.

**Goal:** Flag-gated recovery report with ceiling pairing and post-choke hand-card attribution.

**Architecture:** Pure attribution/report builders in `tools/recovery_report.py`; extract quiet `run_search` from `search_opening.py`; `--recovery-report` pairs `none` + interrupted and prints human + JSON.

**Tech Stack:** Python stdlib, existing minimax/`search_opening`/`matchup_config`.

## Global Constraints

- Default `search_opening` path stays single-search (no silent 2×).
- No new scoring system; reuse existing evaluator/weights.
- No MCTS/RL/deck aggregation/core changes.
- Never use em dash in docs/commits.

---

### Task 1: Attribution helpers + unit tests

**Files:**
- Create: `yapping/tools/recovery_report.py`
- Create: `yapping/tests/test_recovery_report.py`

- [x] Write failing tests for `filler_cards`, `choke_point`, `recovery_cards_used`, `build_recovery_report`
- [x] Implement pure helpers
- [x] Run `pytest tests/test_recovery_report.py` — pass

### Task 2: Wire CLI

**Files:**
- Modify: `yapping/tools/search_opening.py`

- [x] Extract `run_search` (no print) from `search`
- [x] Add `--recovery-report`; pair ceiling when interruption ≠ `none`
- [x] Print human summary + structured JSON
- [x] Keep default path behavior identical

### Task 3: Smoke

- [x] Default ash `--recovery-report` shows ceiling/interrupted/loss/choke
- [x] Unit tests cover Fallen+Ecclesia post-ash attribution
- [ ] Note: live Fallen+Ecclesia PVs often play around ash (no `chain:ash`), so `recovery_cards_used` stays empty until ash resolves in the PV
