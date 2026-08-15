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
