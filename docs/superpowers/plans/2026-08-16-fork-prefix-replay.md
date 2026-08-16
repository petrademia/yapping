# Fork prefix-reuse replay Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an opt-in `ForkReplayCursor` that parks one forked OCGCore worker per DFS prefix so backtracks do not replay from seed.

**Architecture:** Search process owns a Unix-domain listener and a stack of worker connections. After the seed snapshot, worker 0 is forked and the parent never steps the adapter. Descent asks the deepest matching worker to fork-and-step the suffix. Backtrack kills workers that are not prefixes of the new path. `minimax_replay` is unchanged.

**Tech Stack:** Python 3.10+, `os.fork`, Unix-domain sockets, existing `Snapshot` / `replay` / `search_opening.py`.

## Global Constraints

- Do not change `minimax_replay` or `hidden_minimax_replay`.
- Do not patch OCGCore.
- Default `--replay-mode` remains `cursor`.
- Search process must not `step`/`reset` the adapter after forking worker 0.
- Workers exit with `os._exit`.
- No silent fallback to `ReplayCursor` on IPC failure.
- User did not ask for commits; do not commit unless asked.

---

### Task 1: Prefix helpers and fake-adapter fork cursor

**Files:**
- Create: `tools/fork_replay.py`
- Test: `tests/test_fork_replay.py`

**Interfaces:**
- Produces: `ForkReplayCursor.from_snapshot(adapter, snapshot, controlled_player=0)` and `__call__(path) -> Snapshot`, plus `close()`.
- `snapshot_from_duel` / `action_name` consumed from `analyze_ash`.

- [ ] **Step 1: Write the failing test** for sibling visits leaving the parent adapter unstepped, using a fake adapter that records `step` in a list.

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=src:tools .venv/bin/python -m pytest tests/test_fork_replay.py -v`

Expected: FAIL because `fork_replay` is missing.

- [ ] **Step 3: Implement `ForkReplayCursor`** with Unix-socket worker stack, `from_snapshot`, `__call__`, `close`.

- [ ] **Step 4: Run tests and make sure they pass**

Run: `PYTHONPATH=src:tools .venv/bin/python -m pytest tests/test_fork_replay.py -v`

Expected: PASS on Darwin/`os.fork`.

---

### Task 2: Wire `--replay-mode fork`

**Files:**
- Modify: `tools/search_opening.py`
- Modify: `tools/analyze_ash.py` only if a tiny import re-export is needed (prefer not).
- Test: extend `tests/test_fork_replay.py` with an OCGCore skipif search comparing cursor vs fork on a tiny node budget.

- [ ] **Step 1: Write the failing CLI/search test** (`--replay-mode fork` on a small `run_search`).

- [ ] **Step 2: Wire `ForkReplayCursor` in `run_search`** and close it in `finally`.

- [ ] **Step 3: Run `tests/test_fork_replay.py` and `tests/test_search.py`.**

---

### Task 3: Fixture equivalence and Ghost Ogre measurement

**Files:**
- Modify: `DIRECTION.md` (one Phase 1 sentence naming fork mode).
- Optional: `configs/benchmarks/` only if a tiny ghost-ogre fork vs cursor config is cleaner than a one-off command.

- [ ] **Step 1:** Compare `run_search(..., replay_mode="cursor")` and `fork` on Ash or Veiler at a small node cap: same score, actions, complete.

- [ ] **Step 2:** Time Ghost Ogre cursor vs fork (`search_benchmark.py` or `search_opening.py ghost_ogre`). Record ms/state and whether 10× landed.

- [ ] **Step 3:** If fork is corrupt or slower, keep `cursor` default and write the explanation into the benchmark output / DIRECTION note.
