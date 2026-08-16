import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT.parent / "fluorohydride-ygopro-scripts"
CARDS = ROOT / "assets/cards.cdb"
sys.path.insert(0, str(ROOT / "tools"))

from analyze_ash import snapshot_from_duel  # noqa: E402


class FakeAdapter:
    """In-process stand-in for OCGCore: two actions per depth until depth 3."""

    def __init__(self):
        self.seq = []

    def step(self, index):
        self.seq.append(index)
        return self.decision()

    def decision(self):
        depth = len(self.seq)
        n = 0 if depth >= 3 else 2
        actions = [
            {"kind": "play", "card": i + 1, "description": 0, "controller": 0,
             "location": 0, "sequence": 0}
            for i in range(n)
        ]
        return {"player": 0, "turn": 1, "actions": actions}

    def cards(self, player, location):
        return list(self.seq)

    def counts(self):
        return {"hand0": 5, "monster0": len(self.seq)}

    def state_key(self):
        return bytes(self.seq)


def seed_snapshot(adapter):
    return snapshot_from_duel(adapter, adapter.decision(), (), 0)


@pytest.mark.skipif(not hasattr(os, "fork"), reason="os.fork is required")
def test_fork_cursor_sibling_does_not_step_parent_adapter():
    from fork_replay import ForkReplayCursor

    adapter = FakeAdapter()
    cursor = ForkReplayCursor.from_snapshot(adapter, seed_snapshot(adapter))
    try:
        first = cursor((0,))
        second = cursor((1,))
        assert first.actions == ("play:1",)
        assert second.actions == ("play:2",)
        assert first.key != second.key
        assert adapter.seq == []
    finally:
        cursor.close()


@pytest.mark.skipif(not hasattr(os, "fork"), reason="os.fork is required")
def test_fork_cursor_descent_then_backtrack_matches_in_process_keys():
    from fork_replay import ForkReplayCursor

    adapter = FakeAdapter()
    cursor = ForkReplayCursor.from_snapshot(adapter, seed_snapshot(adapter))
    try:
        deep = cursor((0, 1))
        sibling = cursor((0, 0))
        assert deep.actions == ("play:1", "play:2")
        assert sibling.actions == ("play:1", "play:1")
        assert adapter.seq == []
    finally:
        cursor.close()


@pytest.mark.skipif(not hasattr(os, "fork"), reason="os.fork is required")
def test_fork_cursor_handles_a_long_forced_line():
    from fork_replay import ForkReplayCursor

    class DeepAdapter(FakeAdapter):
        def decision(self):
            depth = len(self.seq)
            n = 0 if depth >= 40 else 1
            actions = [
                {"kind": "play", "card": 1, "description": 0, "controller": 0,
                 "location": 0, "sequence": 0}
                for _ in range(n)
            ]
            return {"player": 0, "turn": 1, "actions": actions}

    adapter = DeepAdapter()
    cursor = ForkReplayCursor.from_snapshot(adapter, seed_snapshot(adapter))
    try:
        snapshot = None
        for depth in range(1, 41):
            snapshot = cursor(tuple(0 for _ in range(depth)))
        assert snapshot.actions == tuple("play:1" for _ in range(40))
        assert adapter.seq == []
    finally:
        cursor.close()


@pytest.mark.skipif(sys.platform != "darwin", reason="macOS OCGCore fork guard")
def test_ocgcore_fork_is_rejected_on_macos():
    from fork_replay import ForkReplayCursor

    with pytest.raises(RuntimeError, match="macOS"):
        ForkReplayCursor()


@pytest.mark.skipif(
    not hasattr(os, "fork")
    or not CARDS.is_file()
    or not (SCRIPTS / "constant.lua").is_file(),
    reason="os.fork, card database, and ygopro scripts are required",
)
def test_search_opening_accepts_fork_replay_mode():
    result = subprocess.run(
        [sys.executable, str(ROOT / "tools/search_opening.py"), "ash",
         "--replay-mode", "fork", "--max-nodes", "8", "--max-depth", "12"],
        cwd=ROOT, capture_output=True, text=True,
    )
    if sys.platform == "darwin":
        assert result.returncode != 0
        assert "macOS" in result.stderr
        return
    assert result.returncode == 0, result.stderr[-2000:]
    assert "replay-mode: fork" in result.stdout


def _opening_fields(mode, interruption="ash", max_nodes=80, max_depth=40):
    result = subprocess.run(
        [sys.executable, str(ROOT / "tools/search_opening.py"), interruption,
         "--replay-mode", mode, "--max-nodes", str(max_nodes),
         "--max-depth", str(max_depth)],
        cwd=ROOT, capture_output=True, text=True, check=True,
    )
    lines = result.stdout.splitlines()

    def field(prefix):
        return next(line for line in lines if line.startswith(prefix))

    return field("score"), field("complete:"), field("actions:"), field("visited states:")


@pytest.mark.skipif(
    sys.platform == "darwin"
    or not hasattr(os, "fork")
    or not CARDS.is_file()
    or not (SCRIPTS / "constant.lua").is_file(),
    reason="OCGCore fork is Linux-only; needs os.fork, cards, and scripts",
)
def test_fork_matches_cursor_on_bounded_ash():
    cursor = _opening_fields("cursor")
    fork = _opening_fields("fork")
    assert fork == cursor
