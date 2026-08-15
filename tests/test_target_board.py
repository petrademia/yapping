"""Unit tests for required-piece endboard matching (fake zones, no native search)."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[1] / "tools"))
from target_board import (  # noqa: E402
    ProgressClock,
    build_report,
    choose_result,
    coverage,
    parse_target,
    parse_targets,
    validate_hand_in_deck,
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


def test_validate_hand_in_deck_accepts_subset():
    validate_hand_in_deck([1, 2, 2, 3, 4, 5, 6], [1, 2, 2, 3, 4])


def test_validate_hand_in_deck_rejects_missing_card():
    with pytest.raises(ValueError):
        validate_hand_in_deck([1, 2, 3, 4, 5], [1, 2, 3, 4, 99])
    with pytest.raises(ValueError):
        validate_hand_in_deck([1, 2, 3, 4, 5], [1, 2, 2, 3, 4])


def test_validate_hand_in_deck_rejects_wrong_length():
    with pytest.raises(ValueError):
        validate_hand_in_deck([1, 2, 3, 4, 5, 6], [1, 2, 3, 4])
    with pytest.raises(ValueError):
        validate_hand_in_deck([1, 2, 3, 4, 5, 6], [1, 2, 3, 4, 5, 6])


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


def test_choose_result_prefers_clock_best_when_coverage_is_higher():
    search = {"event": "result", "coverage": 1, "actions": ["search"]}
    best = {"event": "progress", "coverage": 2, "actions": ["best"]}
    assert choose_result(1, search, 2.0, best) is best


def test_choose_result_keeps_search_when_best_is_missing_or_not_better():
    search = {"event": "result", "coverage": 2, "actions": ["search"]}
    best = {"event": "progress", "coverage": 2, "actions": ["best"]}
    assert choose_result(2, search, None, None) is search
    assert choose_result(2, search, 2.0, best) is search
    assert choose_result(2, search, 1.0, best) is search


from search_target_board import build_parser, main  # noqa: E402


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


def test_main_missing_config_returns_2(capsys):
    code = main([
        "--config", "/no/such/config.json",
        "--hand", "1", "2", "3", "4", "5",
        "--target", "monster=1",
    ])
    assert code == 2
    assert capsys.readouterr().err
