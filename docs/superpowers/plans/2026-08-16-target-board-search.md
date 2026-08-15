# Target-board path recovery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** From a configured deck, a 5-card hand, and required endboard pieces, search legal lines and print a combo path (or the best partial path) as JSON lines.

**Architecture:** Pure matching/report/progress helpers in `tools/target_board.py`. Optional `goal_score` and `on_leaf` on `minimax_replay` (defaults preserve current behavior). New CLI `tools/search_target_board.py` reuses `search_opening.run_search` with interruption `none` and a coverage evaluator. Card-weight opening search stays unchanged.

**Tech Stack:** Python 3.10+, pytest, existing OCGCore adapter / ReplayCursor / minimax. Git root is `yapping/`.

## Global Constraints

- Spec: `docs/superpowers/specs/2026-08-16-target-board-search-design.md`
- Matching is multiset subset per named zone; extra cards in that zone are allowed; unlisted zones are ignored.
- Leaf score is the integer count of required pieces present, not card weights.
- First complete match stops search (`goal_score = N`). Budget hit returns the best partial line. Coverage `0/N` is success, not an error.
- Interruption is always `none`. No interruption CLI flag.
- `tools/search_opening.py` default path and card-weight scoring stay identical unless `run_search` gains optional kwargs with today's defaults.
- Do not change hidden-information search, recovery reports, or core cloning.
- Never use em dash in docs or commits.
- Working directory for all commands: the `yapping` repo root.
- Tests: `PYTHONPATH=src:tools .venv/bin/python -m pytest ...`

---

### Task 1: Coverage helpers

**Files:**
- Create: `tests/test_target_board.py`
- Create: `tools/target_board.py`

**Interfaces:**
- Consumes: nothing from later tasks.
- Produces:
  - `ZONES: tuple[str, ...] = ("monster", "spell_trap", "grave", "hand", "banished")`
  - `parse_target(value: str, resolve_card: Callable[[str], int]) -> tuple[str, int]`
  - `parse_targets(values: Sequence[str], resolve_card: Callable[[str], int]) -> tuple[tuple[str, int], ...]`
  - `coverage(zones: Mapping[str, Sequence[int]], targets: Sequence[tuple[str, int]]) -> dict`
  - `validate_targets_in_deck(main_deck: Sequence[int], extra_deck: Sequence[int], targets: Sequence[tuple[str, int]]) -> None`
  - `build_report(...) -> dict` (exact kwargs in the implementation step)

- [ ] **Step 1: Write the failing tests**

Create `tests/test_target_board.py`:

```python
"""Unit tests for required-piece endboard matching (fake zones, no native search)."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[1] / "tools"))
from target_board import (  # noqa: E402
    build_report,
    coverage,
    parse_target,
    parse_targets,
    validate_targets_in_deck,
)

MIRRORJADE = 44146295
RETRIBUTION = 17751597
CARTESIA = 95515789


def test_parse_target_splits_zone_and_card():
    assert parse_target("monster=44146295", int) == ("monster", MIRRORJADE)


def test_parse_target_rejects_unknown_zone():
    with pytest.raises(ValueError, match="unknown zone"):
        parse_target("field=44146295", int)


def test_parse_target_rejects_missing_equals():
    with pytest.raises(ValueError, match="ZONE=CARD"):
        parse_target("monster", int)


def test_parse_targets_preserves_duplicates():
    assert parse_targets(
        ["monster=44146295", "monster=44146295"], int
    ) == (("monster", MIRRORJADE), ("monster", MIRRORJADE))


def test_coverage_counts_present_pieces_and_allows_extras():
    zones = {
        "monster": (MIRRORJADE, CARTESIA),
        "spell_trap": (RETRIBUTION,),
        "grave": (1,),
        "hand": (),
        "banished": (),
    }
    targets = (("monster", MIRRORJADE), ("spell_trap", RETRIBUTION))
    result = coverage(zones, targets)
    assert result["coverage"] == 2
    assert result["required"] == 2
    assert result["complete_match"] is True
    assert result["present"] == [
        {"zone": "monster", "card": MIRRORJADE},
        {"zone": "spell_trap", "card": RETRIBUTION},
    ]
    assert result["missing"] == []


def test_coverage_duplicate_targets_need_duplicate_copies():
    zones = {"monster": (MIRRORJADE,), "spell_trap": (), "grave": (), "hand": (), "banished": ()}
    targets = (("monster", MIRRORJADE), ("monster", MIRRORJADE))
    result = coverage(zones, targets)
    assert result["coverage"] == 1
    assert result["complete_match"] is False
    assert result["missing"] == [{"zone": "monster", "card": MIRRORJADE}]


def test_coverage_ignores_unlisted_zones():
    zones = {
        "monster": (MIRRORJADE,),
        "spell_trap": (RETRIBUTION,),
        "grave": (CARTESIA,),
        "hand": (),
        "banished": (),
    }
    result = coverage(zones, (("monster", MIRRORJADE),))
    assert result["coverage"] == 1
    assert result["complete_match"] is True


def test_coverage_zero_is_valid_partial():
    zones = {"monster": (), "spell_trap": (), "grave": (), "hand": (), "banished": ()}
    result = coverage(zones, (("monster", MIRRORJADE),))
    assert result["coverage"] == 0
    assert result["complete_match"] is False
    assert result["missing"] == [{"zone": "monster", "card": MIRRORJADE}]


def test_validate_targets_in_deck_rejects_card_absent_from_lists():
    with pytest.raises(ValueError, match="44146295"):
        validate_targets_in_deck([1], [2], (("monster", MIRRORJADE),))


def test_validate_targets_in_deck_accepts_extra_deck_boss():
    validate_targets_in_deck([RETRIBUTION], [MIRRORJADE], (("monster", MIRRORJADE),))


def test_build_report_result_shape():
    info = coverage(
        {"monster": (MIRRORJADE,), "spell_trap": (), "grave": (), "hand": (), "banished": ()},
        (("monster", MIRRORJADE), ("spell_trap", RETRIBUTION)),
    )
    report = build_report(
        event="result",
        coverage_info=info,
        targets=(("monster", MIRRORJADE), ("spell_trap", RETRIBUTION)),
        opening_hand=[73819701, 91152256, 91152256, 91152256, 91152256],
        actions=["activate:73819701"],
        endboard={"monster": [MIRRORJADE], "spell_trap": [], "grave": [], "hand": [], "banished": []},
        visited_states=12,
        elapsed_seconds=1.5,
        complete=False,
        max_nodes=20000,
        max_depth=180,
    )
    assert report["event"] == "result"
    assert report["complete_match"] is False
    assert report["coverage"] == 1
    assert report["required"] == 2
    assert report["present"] == [{"zone": "monster", "card": MIRRORJADE}]
    assert report["missing"] == [{"zone": "spell_trap", "card": RETRIBUTION}]
    assert report["actions"] == ["activate:73819701"]
    assert report["visited_states"] == 12
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=src:tools .venv/bin/python -m pytest tests/test_target_board.py -v`

Expected: FAIL with `ModuleNotFoundError: No module named 'target_board'` (or import error).

- [ ] **Step 3: Write minimal implementation**

Create `tools/target_board.py`:

```python
"""Required-piece endboard matching and report payloads for target-board search."""

from collections.abc import Callable, Mapping, Sequence
from typing import Any

ZONES = ("monster", "spell_trap", "grave", "hand", "banished")


def parse_target(value: str, resolve_card: Callable[[str], int]) -> tuple[str, int]:
    if "=" not in value:
        raise ValueError("target must be ZONE=CARD")
    zone, _, card = value.partition("=")
    if zone not in ZONES:
        raise ValueError(f"unknown zone {zone!r}; expected one of {', '.join(ZONES)}")
    if not card:
        raise ValueError("target must be ZONE=CARD")
    return zone, int(resolve_card(card))


def parse_targets(
    values: Sequence[str], resolve_card: Callable[[str], int]
) -> tuple[tuple[str, int], ...]:
    return tuple(parse_target(value, resolve_card) for value in values)


def coverage(
    zones: Mapping[str, Sequence[int]],
    targets: Sequence[tuple[str, int]],
) -> dict[str, Any]:
    remaining: dict[str, list[int]] = {zone: list(zones.get(zone, ())) for zone in ZONES}
    present = []
    missing = []
    for zone, card in targets:
        pile = remaining.setdefault(zone, [])
        try:
            pile.remove(card)
        except ValueError:
            missing.append({"zone": zone, "card": card})
        else:
            present.append({"zone": zone, "card": card})
    return {
        "coverage": len(present),
        "required": len(targets),
        "present": present,
        "missing": missing,
        "complete_match": not missing,
    }


def validate_targets_in_deck(
    main_deck: Sequence[int],
    extra_deck: Sequence[int],
    targets: Sequence[tuple[str, int]],
) -> None:
    pool = set(main_deck) | set(extra_deck)
    for _zone, card in targets:
        if card not in pool:
            raise ValueError(f"required card {card} is not in this deck")


def build_report(
    *,
    event: str,
    coverage_info: Mapping[str, Any],
    targets: Sequence[tuple[str, int]],
    opening_hand: Sequence[int],
    actions: Sequence[str],
    endboard: Mapping[str, Sequence[int]],
    visited_states: int,
    elapsed_seconds: float,
    complete: bool,
    max_nodes: int,
    max_depth: int,
) -> dict[str, Any]:
    return {
        "event": event,
        "complete_match": bool(coverage_info["complete_match"]),
        "coverage": int(coverage_info["coverage"]),
        "required": int(coverage_info["required"]),
        "present": list(coverage_info["present"]),
        "missing": list(coverage_info["missing"]),
        "targets": [{"zone": zone, "card": card} for zone, card in targets],
        "opening_hand": list(opening_hand),
        "actions": list(actions),
        "endboard": {name: list(cards) for name, cards in endboard.items()},
        "visited_states": int(visited_states),
        "elapsed_seconds": float(elapsed_seconds),
        "complete": bool(complete),
        "max_nodes": int(max_nodes),
        "max_depth": int(max_depth),
    }
```

- [ ] **Step 4: Run the tests and make sure they pass**

Run: `PYTHONPATH=src:tools .venv/bin/python -m pytest tests/test_target_board.py -v`

Expected: PASS (all tests in this file).

- [ ] **Step 5: Commit**

```bash
git add tests/test_target_board.py tools/target_board.py
git commit -m "$(cat <<'EOF'
add required-piece endboard coverage helpers

EOF
)"
```

---

### Task 2: Timed best-so-far clock

**Files:**
- Modify: `tests/test_target_board.py`
- Modify: `tools/target_board.py`

**Interfaces:**
- Consumes: `build_report` from Task 1.
- Produces: `class ProgressClock` with
  - `__init__(self, interval_seconds: float, write: Callable[[dict], None], monotonic: Callable[[], float])`
  - `note_leaf(self, score: float, payload: dict) -> None`
  - `best: tuple[float, dict] | None`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_target_board.py`:

```python
from target_board import ProgressClock  # noqa: E402


class FakeClock:
    def __init__(self, times):
        self.times = list(times)

    def __call__(self):
        return self.times.pop(0)


def test_progress_clock_disabled_never_writes():
    writes = []
    clock = ProgressClock(0, writes.append, monotonic=FakeClock([0.0, 10.0]))
    clock.note_leaf(1.0, {"event": "progress", "coverage": 1})
    assert writes == []
    assert clock.best[0] == 1.0


def test_progress_clock_dumps_on_interval_even_without_improvement():
    writes = []
    times = FakeClock([0.0, 1.0, 5.0])
    clock = ProgressClock(5, writes.append, monotonic=times)
    clock.note_leaf(1.0, {"coverage": 1, "actions": ["a"]})
    assert writes == []
    clock.note_leaf(1.0, {"coverage": 1, "actions": ["a"]})
    assert len(writes) == 1
    assert writes[0]["event"] == "progress"
    assert writes[0]["coverage"] == 1
    assert writes[0]["elapsed_seconds"] == 5.0


def test_progress_clock_keeps_higher_score():
    writes = []
    times = FakeClock([0.0, 1.0, 2.0])
    clock = ProgressClock(5, writes.append, monotonic=times)
    clock.note_leaf(1.0, {"coverage": 1})
    clock.note_leaf(2.0, {"coverage": 2})
    assert clock.best[0] == 2.0
    assert clock.best[1]["coverage"] == 2
```

`FakeClock` supplies one time for `__init__` and one time per `note_leaf`. Dumps reuse that `now` for `elapsed_seconds` (no extra `monotonic` call).

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=src:tools .venv/bin/python -m pytest tests/test_target_board.py::test_progress_clock_disabled_never_writes -v`

Expected: FAIL with `ImportError` / `ProgressClock` not defined.

- [ ] **Step 3: Write minimal implementation**

Append to `tools/target_board.py`:

```python
import time


class ProgressClock:
    """Track the best leaf and emit it every interval_seconds (0 disables dumps)."""

    def __init__(
        self,
        interval_seconds: float,
        write: Callable[[dict], None],
        monotonic: Callable[[], float] = time.monotonic,
    ):
        self.interval = float(interval_seconds)
        self.write = write
        self.monotonic = monotonic
        self.started = monotonic()
        self.next_dump = (
            self.started + self.interval if self.interval > 0 else float("inf")
        )
        self.best: tuple[float, dict] | None = None

    def note_leaf(self, score: float, payload: dict) -> None:
        if self.best is None or score > self.best[0]:
            self.best = (float(score), dict(payload))
        now = self.monotonic()
        if self.interval > 0 and now >= self.next_dump and self.best is not None:
            elapsed = now - self.started
            dump = dict(self.best[1])
            dump["event"] = "progress"
            dump["elapsed_seconds"] = elapsed
            self.write(dump)
            while self.next_dump <= now:
                self.next_dump += self.interval
```

- [ ] **Step 4: Run the tests and make sure they pass**

Run: `PYTHONPATH=src:tools .venv/bin/python -m pytest tests/test_target_board.py -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tests/test_target_board.py tools/target_board.py
git commit -m "$(cat <<'EOF'
add timed best-so-far progress clock

EOF
)"
```

---

### Task 3: Minimax first-hit and leaf callback

**Files:**
- Modify: `src/yapping/minimax.py` (`minimax_replay` signature and `visit`)
- Modify: `tests/test_benchmark.py` (reuse the existing tiny tree)

**Interfaces:**
- Consumes: current `minimax_replay(replay, legal_actions, evaluate, terminal, owner, *, max_depth, max_nodes, stats=None) -> MinimaxResult`
- Produces: same function with extra optional kwargs
  - `goal_score: float | None = None`
  - `on_leaf: Callable[[Any, tuple[int, ...], float], None] | None = None`
  - Omitting both must preserve scores, paths, and visit counts of existing tests.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_benchmark.py`:

```python
def _tiny_tree():
    def replay(path):
        depth = len(path)
        return {"key": f"d{depth}:{path}", "depth": depth, "path": path}

    def legal_actions(node):
        return (0, 1) if node["depth"] < 2 else ()

    def evaluate(node):
        return float(sum(node["path"]) if node["path"] else 0)

    def terminal(node):
        return node["depth"] >= 2

    def owner(_node):
        return 0

    return replay, legal_actions, evaluate, terminal, owner


def test_minimax_omitting_goal_score_matches_baseline_visits():
    replay, legal_actions, evaluate, terminal, owner = _tiny_tree()
    baseline = minimax_replay(
        replay, legal_actions, evaluate, terminal, owner,
        max_depth=4, max_nodes=100,
    )
    again = minimax_replay(
        replay, legal_actions, evaluate, terminal, owner,
        max_depth=4, max_nodes=100, goal_score=None, on_leaf=None,
    )
    assert again.score == baseline.score
    assert again.actions == baseline.actions
    assert again.visited_states == baseline.visited_states
    assert again.complete == baseline.complete


def test_minimax_on_leaf_records_each_leaf():
    replay, legal_actions, evaluate, terminal, owner = _tiny_tree()
    leaves = []

    def on_leaf(node, path, score):
        leaves.append((path, score))

    minimax_replay(
        replay, legal_actions, evaluate, terminal, owner,
        max_depth=4, max_nodes=100, on_leaf=on_leaf,
    )
    assert leaves
    assert leaves[0] == ((0, 0), 0.0)


def test_minimax_goal_score_stops_at_first_hit():
    replay, legal_actions, evaluate, terminal, owner = _tiny_tree()
    baseline = minimax_replay(
        replay, legal_actions, evaluate, terminal, owner,
        max_depth=4, max_nodes=100,
    )
    result = minimax_replay(
        replay, legal_actions, evaluate, terminal, owner,
        max_depth=4, max_nodes=100, goal_score=1.0,
    )
    assert result.score >= 1.0
    assert result.visited_states < baseline.visited_states
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=src .venv/bin/python -m pytest tests/test_benchmark.py::test_minimax_goal_score_stops_at_first_hit -v`

Expected: FAIL with `TypeError: minimax_replay() got an unexpected keyword argument 'goal_score'`.

- [ ] **Step 3: Write minimal implementation**

In `src/yapping/minimax.py`, change `minimax_replay` to:

```python
def minimax_replay(
    replay: Callable[[tuple[int, ...]], Any],
    legal_actions: Callable[[Any], Sequence[int]],
    evaluate: Callable[[Any], float],
    terminal: Callable[[Any], bool],
    owner: Callable[[Any], int],
    *,
    max_depth: int,
    max_nodes: int,
    stats: SearchStats | None = None,
    goal_score: float | None = None,
    on_leaf: Callable[[Any, tuple[int, ...], float], None] | None = None,
) -> MinimaxResult:
    """Alpha-beta minimax for deterministic engines reconstructed by replay."""
    visited = 0
    cache = BoundCache()
    root_action_values = {}
    collector = stats

    def visit(path, depth, alpha, beta):
        nonlocal visited
        node = replay(path)
        cache_key = (getattr(node, "key", repr(node)), depth)
        alpha_in, beta_in = alpha, beta
        hit, alpha, beta = cache.probe(cache_key, alpha, beta)
        if hit is not None:
            if collector is not None:
                collector.tt_hits += 1
            return hit
        if collector is not None:
            collector.tt_misses += 1
            collector.max_depth_reached = max(collector.max_depth_reached, depth)
        visited += 1
        actions = tuple(legal_actions(node))
        is_terminal = terminal(node)
        if is_terminal or depth == max_depth or not actions or visited >= max_nodes:
            score = float(evaluate(node))
            if on_leaf is not None:
                on_leaf(node, path, score)
            if collector is not None:
                collector.leaf_evaluations += 1
                if is_terminal:
                    collector.terminal_states += 1
            if is_terminal:
                cache.mark_exact(cache_key, score, tuple())
            return score, tuple(), is_terminal, is_terminal

        if collector is not None:
            collector.expanded_internal_nodes += 1
            collector.branching_factors.append(len(actions))
            collector.branching_by_depth[depth].append(len(actions))

        maximize = owner(node) == 0
        best_score = float("-inf") if maximize else float("inf")
        best_path = tuple()
        complete = True
        for action in actions:
            score, suffix, child_complete, _ = visit(
                path + (action,), depth + 1, alpha, beta
            )
            if depth == 0:
                root_action_values[action] = score
            complete &= child_complete
            if (maximize and score > best_score) or (not maximize and score < best_score):
                best_score, best_path = score, (action,) + suffix
            if maximize:
                alpha = max(alpha, best_score)
            else:
                beta = min(beta, best_score)
            if goal_score is not None and maximize and best_score >= goal_score:
                return best_score, best_path, True, True
            if beta <= alpha:
                if collector is not None:
                    collector.cutoffs += 1
                cache.store_cutoff(cache_key, best_score, best_path,
                                    "lower" if maximize else "upper", complete)
                return best_score, best_path, complete, False
            if visited >= max_nodes:
                complete = False
                break
        exact = cache.store_final(cache_key, alpha_in, beta_in, best_score, best_path, complete)
        return best_score, best_path, complete, complete and exact

    score, actions, complete, _ = visit(tuple(), 0, float("-inf"), float("inf"))
    if collector is not None:
        collector.visited_states = visited
        collector.tt_entries = len(cache)
    return MinimaxResult(actions, score, visited, complete, max_depth, max_nodes,
                         root_action_values, collector)
```

Keep `hidden_minimax_replay` unchanged.

- [ ] **Step 4: Run the tests and make sure they pass**

Run: `PYTHONPATH=src .venv/bin/python -m pytest tests/test_benchmark.py tests/test_search.py -v`

Expected: PASS. If `test_minimax_goal_score_stops_at_first_hit` fails because transposition/order still visits the full tree, inspect `visited_states` for baseline vs `goal_score=1.0` and only then tighten the assertion to the observed reduction. Do not weaken it to `<=`.

- [ ] **Step 5: Commit**

```bash
git add src/yapping/minimax.py tests/test_benchmark.py
git commit -m "$(cat <<'EOF'
add minimax goal_score first-hit and on_leaf hook

EOF
)"
```

---

### Task 4: CLI tool and search wiring

**Files:**
- Modify: `tools/search_opening.py` (`run_search` only: optional `evaluate`, `is_terminal`, `goal_score`, `on_leaf`)
- Create: `tools/search_target_board.py`
- Modify: `tests/test_target_board.py` (parser + validation wiring)
- Modify: `DIRECTION.md` (one sentence under the Level 1 paragraph after the table)

**Interfaces:**
- Consumes: Task 1 helpers, Task 2 `ProgressClock`, Task 3 `minimax_replay` kwargs, `search_opening.run_search` / `legal` / `terminal`, `matchup_config.load_config`, `yapping.hands.validate_hand_in_deck`, `trace_albaz_combo.card_id`.
- Produces:
  - `run_search(..., evaluate=None, is_terminal=None, goal_score=None, on_leaf=None)` with current scoring when those are omitted
  - `build_parser() -> argparse.ArgumentParser`
  - CLI `tools/search_target_board.py`

- [ ] **Step 1: Write the failing parser tests**

Append to `tests/test_target_board.py`:

```python
import argparse
from search_target_board import build_parser  # noqa: E402


def test_parser_requires_target_and_five_card_hand():
    parser = build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args([])
    with pytest.raises(SystemExit):
        parser.parse_args(["--target", "monster=44146295"])
    args = parser.parse_args([
        "--hand", "1", "2", "3", "4", "5",
        "--target", "monster=44146295",
    ])
    assert args.hand == [1, 2, 3, 4, 5]
    assert args.targets == ["monster=44146295"]
    assert args.progress_every == 5.0


def test_parser_rejects_unknown_zone():
    parser = build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args([
            "--hand", "1", "2", "3", "4", "5",
            "--target", "field=1",
        ])


def test_parser_rejects_negative_progress_every():
    parser = build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args([
            "--hand", "1", "2", "3", "4", "5",
            "--target", "monster=1",
            "--progress-every", "-1",
        ])
```

`build_parser` should type `--hand` as `int` for these tests (numeric only). The live CLI can wrap `card_id` after parse, or use `card_id` as argparse type; if `card_id` accepts `"1"`, parser tests may pass `1` as int. Prefer argparse type `card_id` from `trace_albaz_combo` and in the test pass numeric strings (already shown). Then `args.hand` is a list of ints.

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=src:tools .venv/bin/python -m pytest tests/test_target_board.py::test_parser_requires_target_and_five_card_hand -v`

Expected: FAIL with `ModuleNotFoundError: No module named 'search_target_board'`.

- [ ] **Step 3: Extend `run_search` with optional kwargs**

In `tools/search_opening.py`, change `run_search` so the `minimax_replay` call becomes:

```python
def run_search(interruption="ash", max_nodes=20_000, max_depth=180, opening_hand=None,
               ecclesia_copies=1, recovery_only=False, config=None,
               replay_mode="cursor", adapter=None, controlled_player=0,
               stats=None, evaluate=None, is_terminal=None, goal_score=None,
               on_leaf=None):
    config = config or load_config()
    config = {**config, "controlled_player": controlled_player}
    matchup = experiment_matchup(config, opening_hand=opening_hand)
    card = config["interruptions"].get(interruption)
    adapter = adapter or Duel(str(ROOT / "assets/cards.cdb"), str(SCRIPTS))
    cursor = ReplayCursor(card, opening_hand, ecclesia_copies, adapter, matchup,
                          controlled_player)
    replay_fn = cursor if replay_mode == "cursor" else lambda path: replay(
        path, card, opening_hand, ecclesia_copies, adapter, matchup, controlled_player)
    evaluate_fn = evaluate or (lambda snapshot: endboard_score(snapshot, config["weights"]))
    terminal_fn = is_terminal or (
        (lambda snapshot: recovery_terminal(snapshot, config)) if recovery_only
        else lambda snapshot: terminal(snapshot, config)
    )
    result = minimax_replay(
        replay_fn,
        lambda snapshot: legal(snapshot, config),
        evaluate_fn,
        terminal_fn,
        lambda snapshot: snapshot.decision["player"],
        max_depth=max_depth,
        max_nodes=max_nodes,
        stats=stats,
        goal_score=goal_score,
        on_leaf=on_leaf,
    )
    final = replay_fn(result.actions)
    return result, final, config
```

Do not change the `if __name__` CLI of `search_opening.py`.

- [ ] **Step 4: Write `tools/search_target_board.py`**

```python
"""Search a known hand for a line that covers required endboard pieces."""

import argparse
import json
import sys
import time

from matchup_config import load_config
from search_opening import run_search, terminal as opening_terminal
from target_board import (
    ProgressClock,
    ZONES,
    build_report,
    coverage,
    parse_targets,
    validate_targets_in_deck,
)
from trace_albaz_combo import card_id
from yapping.hands import validate_hand_in_deck


def _nonneg_float(value):
    number = float(value)
    if number < 0:
        raise argparse.ArgumentTypeError("progress-every must be >= 0")
    return number


def _target_flag(value):
    if "=" not in value:
        raise argparse.ArgumentTypeError("target must be ZONE=CARD")
    zone, _, card = value.partition("=")
    if zone not in ZONES:
        raise argparse.ArgumentTypeError(
            f"unknown zone {zone!r}; expected one of {', '.join(ZONES)}"
        )
    if not card:
        raise argparse.ArgumentTypeError("target must be ZONE=CARD")
    return value


def build_parser():
    parser = argparse.ArgumentParser(
        description="Recover a combo path that covers required endboard pieces."
    )
    parser.add_argument("--config", type=str)
    parser.add_argument("--hand", type=card_id, nargs=5, metavar="CARD", required=True)
    parser.add_argument("--target", dest="targets", action="append",
                        type=_target_flag, required=True, metavar="ZONE=CARD")
    parser.add_argument("--progress-every", type=_nonneg_float, default=5.0)
    parser.add_argument("--max-nodes", type=int, default=20_000)
    parser.add_argument("--max-depth", type=int, default=180)
    parser.add_argument("--replay-mode", choices=["cursor", "oracle"], default="cursor")
    return parser


def emit(payload):
    json.dump(payload, sys.stdout, sort_keys=True)
    sys.stdout.write("\n")
    sys.stdout.flush()


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        config = load_config(args.config)
        targets = parse_targets(args.targets, card_id)
        validate_hand_in_deck(config["main_deck"], args.hand)
        validate_targets_in_deck(config["main_deck"], config["extra_deck"], targets)
    except ValueError as error:
        print(error, file=sys.stderr)
        return 2

    started = time.monotonic()
    clock = ProgressClock(args.progress_every, emit)
    required = len(targets)

    def evaluate(snapshot):
        return float(coverage(snapshot.zones, targets)["coverage"])

    def is_terminal(snapshot):
        info = coverage(snapshot.zones, targets)
        return info["complete_match"] or opening_terminal(snapshot, config)

    def on_leaf(node, path, score):
        info = coverage(node.zones, targets)
        payload = build_report(
            event="progress",
            coverage_info=info,
            targets=targets,
            opening_hand=args.hand,
            actions=list(node.actions),
            endboard=node.zones,
            visited_states=0,
            elapsed_seconds=time.monotonic() - started,
            complete=False,
            max_nodes=args.max_nodes,
            max_depth=args.max_depth,
        )
        clock.note_leaf(score, payload)

    result, final, config = run_search(
        interruption="none",
        max_nodes=args.max_nodes,
        max_depth=args.max_depth,
        opening_hand=list(args.hand),
        config=config,
        replay_mode=args.replay_mode,
        evaluate=evaluate,
        is_terminal=is_terminal,
        goal_score=float(required),
        on_leaf=on_leaf,
    )
    info = coverage(final.zones, targets)
    emit(build_report(
        event="result",
        coverage_info=info,
        targets=targets,
        opening_hand=args.hand,
        actions=list(final.actions),
        endboard=final.zones,
        visited_states=result.visited_states,
        elapsed_seconds=time.monotonic() - started,
        complete=result.complete,
        max_nodes=args.max_nodes,
        max_depth=args.max_depth,
    ))
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

`on_leaf` does not know `visited` yet. That is acceptable: progress rows may use `visited_states: 0` or omit a live counter. Prefer threading a small mutable `{"visited": 0}` if easy; otherwise leave 0 on progress events and set the real count only on `"event": "result"`. Spec allows the same keys; `0` on progress is honest enough for v1 if documented in the result line.

Add one sentence after the Level 1 table legend in `DIRECTION.md`, still in the capability-ladder section:

```markdown
Level 1 includes a goal-conditioned mode: required endboard pieces, first-hit
stop, and a best-partial result if the node budget hits first
(`tools/search_target_board.py`).
```

Place it after "Levels 0-2 are the inner solver spine." so it does not rewrite the table.

- [ ] **Step 5: Run tests**

Run: `PYTHONPATH=src:tools .venv/bin/python -m pytest tests/test_target_board.py tests/test_benchmark.py tests/test_search.py tests/test_recovery_report.py -q`

Expected: PASS.

Parser tests that import `search_target_board` will import `search_opening`, which imports `yapping._ocgcore`. If that import fails in the portable environment, split `build_parser` into `tools/target_board.py` instead of the CLI module so parser tests do not load the native adapter. If you do that move, keep `build_parser` / `_target_flag` / `_nonneg_float` in `tools/target_board.py` and have `search_target_board.py` call `build_parser()`. Update the test import to `from target_board import build_parser`. Prefer this split if `_ocgcore` import breaks portable pytest.

- [ ] **Step 6: Commit**

```bash
git add tools/search_opening.py tools/search_target_board.py tests/test_target_board.py DIRECTION.md
git commit -m "$(cat <<'EOF'
add target-board path recovery CLI

EOF
)"
```

---

## Self-review (spec coverage)

| Spec section | Task |
| ------------ | ---- |
| CLI `search_target_board.py`, flags, interruption none | 4 |
| Multiset subset, extras, unlisted zones, duplicates | 1 |
| Maximize coverage count, 0/N is success | 1, 4 |
| First-hit `goal_score`, budget partial | 3, 4 |
| JSONL progress/result, interval dump without improvement | 2, 4 |
| Error table (argparse 2, validate hand/deck, native uncaught) | 1, 4 |
| `on_leaf` / omit hooks preserve minimax | 3 |
| `run_search` reuse, `search_opening` defaults | 4 |
| DIRECTION Level 1 one-liner | 4 |
| Out of scope (interruptions, exact snapshot, fixture write, unknown hands) | Global Constraints |

No remaining spec item without a task.
