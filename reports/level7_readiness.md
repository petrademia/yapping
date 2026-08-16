# Level 7 readiness — experimental baseline

Status: evidence report re-run after bumping OCGCore, ygopro-scripts, and cards.cdb. Measured on commit `ef7f6b5` plus local pin updates.

Research workflow: baseline → measure bottleneck → hypothesis → smallest method → compare → decide.

This handoff **does not** implement MCTS, RL, or neural search guidance.

---

## A. Environment

| Item | Value |
|------|-------|
| Commit | `ef7f6b57940b9b388b9f90ba586c14b0f334a5e9` — Agent/level7 readiness experiments (#5) |
| Platform | Darwin 25.6.0 arm64 (Apple Silicon) |
| Python | 3.14.6 |
| C++ | Apple clang 21.0.0 |
| OCGCore | `ee5c2ec7d6acfb583bfb7e26e6ee667db46677fa` |
| cards.cdb SHA-256 | `f81958a2e0c238ddf5060482e1a2fc2c0d4a7f75917e76c388cab1a28fa43d4c` (matches README pin) |
| Scripts | `090e881772f488e1256c456b827d5cbed4facf79` (adjacent `fluorohydride-ygopro-scripts`) |
| Tests | **107 passed** (`PYTHONPATH=src:tools .venv/bin/python -m pytest -q`) |

Machine-readable copy: `reports/data/environment.json`.

### Small fix required to run the search sweep

`tools/search_benchmark.py` created a new OCGCore adapter per case and failed with `only one OCGCore adapter may be active`. The experiment branch reuses one adapter across the sweep and records `ms_per_visited_state` as a coarse overhead proxy. This is instrumentation only; no replay redesign.

---

## B. Search baseline

Fixed scenarios from `configs/benchmarks/albaz_search_baseline.json` (default Albaz opening hand). Raw data: `reports/data/search_baseline.json`.

| Scenario | Budget | States | Runtime (s) | Complete | Utility | Line len |
|----------|-------:|-------:|------------:|----------|--------:|---------:|
| none | 1,000 | 1,000 | 1.41 | no | 16.00 | 40 |
| none | 5,000 | 5,000 | 7.36 | no | 16.00 | 42 |
| none | 10,000 | 10,000 | 23.86 | no | 16.00 | 42 |
| none | 50,000 | 10,975 | 18.40 | **yes** | 16.00 | 42 |
| ash | 1,000 | 1,000 | 1.51 | no | 5.75 | 48 |
| ash | 5,000 | 5,000 | 7.38 | no | 7.75 | 20 |
| ash | 10,000 | 10,000 | 15.97 | no | 10.75 | 41 |
| ash | 50,000 | 13,643 | 22.30 | **yes** | **8.25** | 45 |
| impermanence | 1,000 | 1,000 | 1.39 | no | 8.75 | 46 |
| impermanence | 5,000 | 5,000 | 7.34 | no | 14.00 | 53 |
| impermanence | 10,000 | 10,000 | 17.05 | no | 13.00 | 43 |
| impermanence | 50,000 | 12,528 | 21.22 | **yes** | **8.75** | 34 |

Completion budgets (this fixture): none ≈ 11k states, ash ≈ 14k, impermanence ≈ 13k.

---

## C. Search complexity

Branching here is **search-relevant** legal actions after `search_opening.legal` skip/dedup — **not** raw OCGCore prompt branching.

At complete runs:

| Scenario | Mean branch | Median | p90 | Max | TT hit rate | Cutoffs / expand |
|----------|------------:|-------:|----:|----:|------------:|-----------------:|
| none | 1.30 | 1.0 | 2.0 | 7.0 | 8.2% | 0.35 |
| ash | 1.32 | 1.0 | 2.0 | 7.0 | 7.9% | 0.33 |
| impermanence | 1.61 | 2.0 | 2.0 | 7.0 | 11.7% | 0.41 |

Depth bands (complete impermanence): largest mean branching in bands `11–20` and `21–40` (~1.66–1.70), not at the root.

**Interpretation:** effective branching is low. Exact search cost on this fixture is dominated by **how many nodes are visited × per-node work**, not by an exploding fan-out.

---

## D. Compute → quality behavior

1. **none:** utility is already 16.00 at 1k nodes and stays there through completion. Extra compute buys completeness/line polish, not utility.
2. **ash / impermanence:** provisional utilities are **non-monotonic** and can **overshoot** the complete-search utility (ash 10.75 at 10k → 8.25 complete; imperm 14.00 at 5k → 8.75 complete). Best-line length also jumps around before completion.
3. **Completeness** is reached before 50k for all three scenarios on this fixture.
4. **Most expensive complete run:** ash (13.6k states, 22.3s).
5. Runtime scales roughly with visited states (~1.3–1.9 ms/state).

**Critical label hygiene:** incomplete-search utilities are not safe oracle targets for learning.

---

## E. Replay-cost analysis

Proxy metric: `runtime_seconds / visited_states` (includes ReplayCursor reconstruction + legal + eval + bookkeeping; **not** a separated timer).

| Statistic | ms / visited state |
|-----------|-------------------:|
| Mean | 1.62 |
| Median | 1.55 |

Evidence:

- Per-state cost is stable across budgets/scenarios.
- Search-relevant branching is small (~1.3–1.6), so fan-out alone does not explain cost.
- DIRECTION’s replay-pressure hypothesis is **consistent** with these measurements, but without separated timers we cannot prove replay dominates evaluator/legal/bookkeeping.

**Verdict:** replay/reconstruction overhead is **material** (order ~1.6 ms/state on this machine for this fixture). Ranked **dominant among measured factors for this fixture**, with the caveat that the split is still coarse. Utilities, completeness, and visited-state counts are unchanged versus the previous pin.

Detailed micro-timing (replay vs eval vs legal) was **not** added; it would require more invasive hooks than this handoff allows.

---

## F. Consistency experiment (Level 3)

Raw data: `reports/data/consistency_baseline.json`.

Setup:

- config: `albaz.json` (fixture deck + Celtic Guardian filler);
- 16 unique sampled hands, seed 7;
- interruptions: none, ash, impermanence;
- max_nodes 20,000 (all evaluated hands completed);
- `--conditioned` / quantified thresholds T ∈ {5,10,15}.

Sampling honesty:

| Field | Value |
|-------|------:|
| evaluated_hands | 16 |
| evaluated_probability_mass | 0.593 |
| covers_full_deck_distribution | **false** |

Weighted utilities among evaluated mass:

| Interruption | Weighted U | Complete fraction | Sample P(U≥5) | Sample P(U≥10) |
|--------------|-----------:|------------------:|--------------:|---------------:|
| none | 3.31 | 1.0 | 0.263 | 0.010 |
| ash | 2.92 | 1.0 | 0.182 | 0.010 |
| impermanence | 2.94 | 1.0 | 0.193 | 0.010 |
| floor (configured) | 2.92 | — | — | — |

Hand-feature access (input composition, **not** playability), evaluated-sample rates:

| Feature | Sample rate |
|---------|------------:|
| starter_access | 0.091 |
| extender_access | 0.252 |
| recovery_access | 0.091 |
| interaction_access | 0.000 |
| brick_free | 0.909 |

**Note:** random hands on the filler-heavy Albaz list mostly terminate quickly (often tens of visited states). That is a property of this toy deck distribution, not a failure of the consistency tooling.

A branded `branded_albaz_v1.json` consistency pass was started (12 hands, seed 7, 20k nodes) but stopped after 38 minutes without a finished report. A concurrent branded multi-hand oracle export was already using the same machine. This re-run does not replace that limitation with new branded consistency numbers.

---

## G. Conditioned hand analysis

Observational only (not counterfactual extender replacement).

Among evaluated Albaz sample hands, starter-conditioned buckets were sparse:

| Condition (none) | Hands | Mass | Normalized U |
|------------------|------:|-----:|-------------:|
| starter≥1, extender=0 | 0 | 0 | — |
| starter≥1, extender=1 | 3 | 0.054 | 3.82 |
| starter≥1, extender=2 | 0 | 0 | — |
| starter≥1, extender≥3 | 0 | 0 | — |

Ash/imperm joints matched the same three hands with **weighted_score_loss = 0** on this sample (low-utility lines; interruption did not change score in-bucket).

**Do not conclude** “one extender adds utility” from these buckets. The sample lacks extender-count contrast given starter access.

Tooling works; this deck+sample does not yet stress-test extender marginals.

---

## H. Oracle-data readiness (Level 6)

Raw data: `reports/data/oracle_readiness.json`, examples under `reports/data/oracle/`.

Exported complete searches for default-hand trajectories: none / ash / impermanence (max_nodes 50k).

| Metric | Value |
|--------|------:|
| total examples | 121 |
| unique state keys | 118 |
| duplicate state rows | 3 |
| root examples | 3 |
| trajectory examples | 118 |
| complete-search examples | 121 |
| incomplete-search examples | 0 |
| full action-value labels | 92 |
| chosen-action-only labels | 105 |

Multi-legal quality (the meaningful policy-learning subset):

| Metric | Value |
|--------|------:|
| multi-legal examples (|A|>1) | 37 |
| multi-legal with full AV table | 8 |
| multi-legal chosen-only | 21 |
| root multi-legal full AV | 3 / 3 |
| trajectory multi-legal chosen-only | 21 |

Depth spans 0–44 across three interruptions. Oracle action kinds are dominated by `pass` (63), then `select_card` / `yes` / `place`.

Tabular plumbing check (`TabularPolicyValue`): policy agreement ≈ 0.89, value MAE ≈ 8.5 on a random holdout. This can memorize state keys — **not** Level 7 generalization.

### Gaps blocking a strong Level 7 start

1. **Opening-hand diversity is near-zero** (one default fixture hand × 3 interruptions).
2. **Trajectory multi-legal states usually lack full action values** (known export limitation confirmed).
3. **Value targets from incomplete search are unsafe** (Section D).

Schema fields themselves validate; provenance/completeness flags are present.

---

## I. Bottleneck ranking (measured)

Derived from this fixture/machine, not assumed a priori:

1. **Per-visited-state overhead (~1.6 ms), consistent with material replay/reconstruction cost** — primary cost driver given low branching.
2. **Need for complete-search budgets before trusting utilities** — incomplete labels mislead.
3. **Oracle action-value coverage on multi-legal trajectory states** — blocks broad policy imitation.
4. **Oracle / consistency dataset diversity** (hands, real deck lists) — current exports are too narrow for learning claims.
5. **Search-relevant branching** — low (~1.3–1.6); **not** the dominant issue on this benchmark.

---

## Final recommendation

# CONDITIONAL GO

Level 7 is **conditionally** justified.

Exact search can produce trustworthy **complete** labels, the export schema works, and a tiny supervised plumbing path exists. But the current oracle corpus is too narrow and trajectory action-value labels are too incomplete for a meaningful generalization experiment.

### Must fix before a real Level 7 run

1. **Export oracle trajectories from many distinct opening hands** (and ideally a real non-filler deck path), keeping only `complete=true` searches.
2. **Either** restrict the first policy dataset to states with full legal action-value tables (today: mainly roots / trivial single-legal states) **or** extend export so multi-legal trajectory states store full root-style action values (larger change; only if needed after (1)).

### Smallest Level 7 experiment (define now, do not implement here)

**Policy task**

- Input: observation/state features + legal-action mask  
- Target: oracle preferred legal action  
- Metrics: top-1 accuracy, legal-only accuracy, optionally top-k  

**Value task**

- Input: observation/state features  
- Target: oracle/search value from **complete** searches only  
- Metrics: MAE, RMSE, rank correlation  

**Split**

- Group by opening hand / scenario / trajectory — **not** i.i.d. row splits — to prevent duplicate-state leakage.

**Success bar for proceeding to Level 8**

- Non-trivial policy accuracy on held-out hands/scenarios (above majority / pass baseline).
- Value errors small enough that ranking of sibling root actions remains useful.

### Level 8 evaluation target (same scenario IDs)

When guidance exists, compare on `albaz_default_none|ash|impermanence`:

| Field | Meaning |
|-------|---------|
| baseline_nodes / guided_nodes | visited states |
| baseline_runtime / guided_runtime | wall time |
| oracle_utility / guided_utility | complete-search scores |
| search_speedup | baseline_nodes / guided_nodes |
| utility_gap | oracle_utility − guided_utility |

Research question:

> Can learned policy/value guidance recover near-oracle utility using substantially less search?

Do not populate speedup numbers until guided search exists.

### Explicitly not justified yet

- **MCTS:** no evidence branching explosion requires it on this fixture.
- **RL / PPO / DQN:** no evidence imitation on trustworthy labels has been tried and failed.
- **General expert agent:** still an explicit non-goal.

### Likely next commit after this report

Not “train a net immediately”, but:

1. multi-hand complete-oracle export + dataset audit, **then**
2. smallest imitation baseline with hand-grouped validation.

Classical prefix-reuse remains the top **search-engine** optimization hypothesis if wall-clock must fall before larger data collection.
