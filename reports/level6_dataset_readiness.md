# Level 6 dataset readiness — real-deck multi-hand oracle

Status: evidence report for branch `agent/level6-multihand-oracle` (base commit `ef7f6b5`).

Research question: can YAPPING generate a diverse, trustworthy oracle corpus from realistic opening hands suitable for generalization testing rather than memorization?

This handoff does **not** implement Level 7, MCTS, RL, or prefix-reuse replay.

---

## A. Construction fix

### Why realistic deck hands previously failed

`tools/search_opening.run_search` only treated a config as a duel matchup when `opponent_deck` was present:

```python
matchup = config if config.get("opponent_deck") else None
```

`configs/branded_albaz_v1.json` has `main_deck` / `extra_deck` but no `opponent_deck` list. Hands were sampled from the branded main deck, while `ReplayCursor` / `replay` fell back to `fixture_deck()`. Cards such as Aluber / Branded Fusion then raised:

`opening hand card … is not in this deck`

### What changed

- Added `experiment_matchup(config, opening_hand=…)` in `tools/matchup_config.py`.
- Configured `main_deck` is used when an opening hand is supplied, or when `use_configured_deck` is true.
- Fixture construction remains the default for regression searches with no opening hand.
- `branded_albaz_v1.json` sets `use_configured_deck: true`.
- Multi-hand export reuses `analyze_consistency.sample_hands` (backed by `yapping.hands.sample_unique_hands`).

### Why deterministic fixtures remain correct

Default Albaz searches without `--hand` still resolve `experiment_matchup(...) is None` and use `fixture_deck()`. Existing combo / recovery fixtures are unchanged.

---

## B. Generation configuration

| Item | Value |
|------|-------|
| Base commit | `ef7f6b57940b9b388b9f90ba586c14b0f334a5e9` |
| Deck / config | `configs/branded_albaz_v1.json` |
| RNG seed | 7 |
| Hand count | 16 unique opening hands |
| Interruptions | `none`, `ash`, `impermanence` |
| Node / depth limits | `max_nodes=10000`, `max_depth=180` |
| Label policy | `--complete-only` (incomplete rows → diagnostic JSONL) |
| cards.cdb SHA-256 | `f81958a2e0c238ddf5060482e1a2fc2c0d4a7f75917e76c388cab1a28fa43d4c` (README pin) |
| Scripts | adjacent `fluorohydride-ygopro-scripts` |
| Outputs | `reports/data/oracle/branded_multi_hand.jsonl`, `…_incomplete.jsonl`, `…_summary.json` |
| Machine-readable audit | `reports/data/level6_dataset_audit.json` |

CLI:

```bash
PYTHONPATH=src:tools python tools/training_data.py export-multi \
  reports/data/oracle/branded_multi_hand.jsonl \
  --config configs/branded_albaz_v1.json \
  --sample-hands 16 --seed 7 \
  --interruptions none,ash,impermanence \
  --max-nodes 10000 --max-depth 180 --complete-only \
  --incomplete-output reports/data/oracle/branded_multi_hand_incomplete.jsonl \
  --summary-output reports/data/oracle/branded_multi_hand_summary.json
```

---

## C. Runtime

| Metric | Value |
|--------|------:|
| Requested hands | 16 |
| Searched hands | 16 |
| Searched scenarios | 48 |
| Complete searches | 6 (12.5%) |
| Incomplete searches | 42 |
| Total runtime | **4896 s (~81.6 min)** |
| Mean runtime / hand | 306 s |
| Mean runtime / search | 102 s |
| Runtime range / search | ~0.7 s (brick completes) to ~460 s (interactive incomplete) |

Follow-up budget probe on one previously incomplete interactive hand (`hand_id=2357f6e5c5ffb75c`):

| Budget | Complete | Visited | Score | Runtime |
|-------:|----------|--------:|------:|--------:|
| 20k | no | 20k | 18.25 | 65 s |
| 50k | no | 50k | 19.00 | 166 s |

Provisional score still moved at 50k. Fixture Albaz completes around 11k–14k nodes; realistic branded lines often do **not** complete at the old 50k fixture budget.

---

## D. Dataset size (complete-only Level 7 file)

| Metric | Value |
|--------|------:|
| Examples | 69 |
| Unique states | 57 |
| Unique opening hands | **2** |
| Trajectories (complete searches) | 6 |
| Duplicate-state rate | 17.4% |
| Examples / requested hand | 4.3 |

Diagnostic incomplete file (generated, not committed due to size; regenerate via the CLI above):

`reports/data/oracle/branded_multi_hand_incomplete.jsonl` — **3478** examples across **14** unique hands (not for training).

---

## E. Policy usefulness (complete-only)

| Metric | Value |
|--------|------:|
| Single-legal | 36 |
| Multi-legal | 33 (47.8%) |
| Pass percentage | 56.5% |
| Action kinds | pass 39, place 12, set 12, end_phase 6 |

The complete corpus is tiny and dominated by two short brick-ish trajectories. It is not a meaningful policy-learning set.

Incomplete diagnostic corpus (not labels): multi-legal ~47.8%, pass ~44.9%, 14 hands — diversity exists in the search stream, but without complete labels.

---

## F. Label quality

| Metric | Complete-only set |
|--------|------------------:|
| Complete labels | 69 / 69 |
| Incomplete labels in export | 0 (excluded) |
| Full action-value coverage | 60 |
| Chosen-only coverage | 36 |
| Multi-legal + full AV | 24 |
| Multi-legal + chosen-only | 0 |

Incomplete searches are recorded separately; their utilities are **not** treated as oracle truth (consistent with Level 7 readiness findings on non-monotonic provisional scores).

Full sibling Q(s,a) for every trajectory state was **not** implemented. Behavior cloning needs `(s, a*)`; the complete set already exposes root AV tables where minimax provides them.

---

## G. Diversity

- Complete-only: **2** hands, depths 0–12, balanced across three interruptions for those two hands only.
- Incomplete diagnostic: 14 hands, broader depth / action mix, but unsafe labels.
- 100 distinct hands at complete-search quality is **not** practical at current per-state cost on this deck.

---

## H. Leakage risk

On the complete-only set:

- state keys shared across hands: **0**
- across scenarios: **0**
- across trajectories: **0**

Duplicate rows are within-trajectory repeats (12 / 69). Provenance fields `hand_id`, `scenario_id`, `trajectory_id`, `opening_hand` support grouped train/val/test splits when the corpus grows.

---

## I. Level 3 sanity check (branded, same seed/deck)

Command: `run_consistency_baseline.py --config configs/branded_albaz_v1.json --hands 12 --seed 7 --max-nodes 10000`.

Role-count buckets (none interruption; mass is sample mass only):

| Bucket | Hands | Mass | Normalized utility | Complete fraction |
|--------|------:|-----:|-------------------:|------------------:|
| starter = 0 | 7 | 3.8e-5 | 17.62 | 0.14 |
| starter ≥ 1, extender = 1 | 3 | 1.8e-5 | 16.29 | 0.33 |
| starter ≥ 1, extender = 2 | 2 | 8e-6 | 20.56 | 0.00 |
| starter ≥ 1, extender = 0 | 0 | — | — | — |
| starter ≥ 1, extender ≥ 3 | 0 | — | — | — |

Realistic sampling now yields starter/extender role variation (unlike filler-only bricks). Utilities are mostly **incomplete** at 10k nodes — do not treat bucket deltas as causal.

---

## Decision

**CONDITIONAL GO**

Construction and provenance work. Complete-only export correctly refuses incomplete labels. Grouped identifiers exist.

The remaining blocker is clearly scoped: **complete oracle collection on realistic branded hands is too slow / rare** at current budgets (12.5% complete at 10k; a typical interactive hand still incomplete at 50k with moving provisional score). The complete multi-hand corpus (2 hands, 69 examples) is insufficient for a first generalization experiment.

### Smallest next handoff (do not implement here)

1. **Preferred if compute stays expensive:** prefix-reuse / cheaper replay, measured against the existing search baseline and this branded multi-hand wall-time.
2. **Otherwise:** a high-budget complete-only collection job (>>50k nodes or longer wall-time) targeting tens of distinct complete hands before Level 7.

### If compute later yields tens of complete hands — smallest Level 7 experiment

Supervised oracle imitation only (not RL):

- Policy: `πθ(a | s, legal_mask)` → oracle action; evaluate on **held-out opening hands**; report multi-legal accuracy separately from single-legal.
- Value: `Vθ(s)` → complete-search oracle value; MAE / RMSE / rank correlation on held-out hands.
- Baselines: random legal, majority action, majority action-kind, existing move ordering if meaningful.

---

## Explicitly not done

MCTS, PPO/DQN/actor-critic, self-play, policy-guided search, GNN/transformers for learning, fake card-effect semantics, replacing OCGCore legality, premature full sibling Q export, premature replay redesign beyond measurement.
