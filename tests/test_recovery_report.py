"""Unit tests for recovery-report attribution (fake action lines, no native search)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "tools"))
from recovery_report import (  # noqa: E402
    build_recovery_report,
    choke_point,
    filler_cards,
    format_recovery_report,
    recovery_cards_used,
)

FALLEN = 73819701
ECCLESIA = 55273560
CELTIC = 91152256
ASH = 14558127

CONFIG = {
    "ignored_cards": [CELTIC],
    "interruptions": {"ash": ASH, "veiler": 97268402},
}


def test_filler_cards_unions_ignored_and_filler_keys():
    config = {
        "ignored_cards": [CELTIC],
        "main_deck_filler": {"card": 1, "count": 2},
        "counterfactual_filler": 2,
    }
    assert filler_cards(config) == {CELTIC, 1, 2}


def test_filler_cards_handles_missing_keys():
    assert filler_cards({"ignored_cards": [CELTIC]}) == {CELTIC}
    assert filler_cards({}) == set()


def test_choke_point_matches_configured_interruption_chain():
    actions = (
        f"activate:{FALLEN}",
        f"chain:{ASH}",
        f"summon:{ECCLESIA}",
        f"chain:{ECCLESIA}",
        f"activate:{ECCLESIA}",
    )
    assert choke_point(actions, "ash", CONFIG) == f"chain:{ASH}"


def test_choke_point_ignores_friendly_chains_before_interrupt():
    actions = (
        f"activate:{FALLEN}",
        f"chain:{ECCLESIA}",
        f"summon:{ECCLESIA}",
    )
    assert choke_point(actions, "ash", CONFIG) is None


def test_choke_point_null_when_no_chain():
    assert choke_point((f"activate:{FALLEN}", "end_phase"), "ash", CONFIG) is None


def test_choke_point_null_for_none_interruption():
    actions = (f"activate:{FALLEN}", f"chain:{ASH}", f"summon:{ECCLESIA}")
    assert choke_point(actions, "none", CONFIG) is None


def test_recovery_cards_used_from_post_ash_hand_cards():
    hand = [FALLEN, ECCLESIA, CELTIC, CELTIC, CELTIC]
    actions = (
        f"activate:{FALLEN}",
        f"chain:{ASH}",
        f"summon:{ECCLESIA}",
        f"activate:{ECCLESIA}",
        "end_phase",
    )
    used = recovery_cards_used(hand, actions, CONFIG, interruption="ash")
    assert used == [ECCLESIA]


def test_recovery_cards_used_excludes_fillers_even_if_in_suffix():
    hand = [FALLEN, ECCLESIA, CELTIC, CELTIC, CELTIC]
    actions = (
        f"activate:{FALLEN}",
        f"chain:{ASH}",
        f"summon:{CELTIC}",
        f"summon:{ECCLESIA}",
    )
    used = recovery_cards_used(
        hand, actions,
        {**CONFIG, "counterfactual_filler": CELTIC},
        interruption="ash",
    )
    assert used == [ECCLESIA]


def test_recovery_cards_used_empty_without_matching_choke():
    hand = [FALLEN, ECCLESIA, CELTIC, CELTIC, CELTIC]
    # Friendly chain only — Ash never fired in this line.
    actions = (f"activate:{FALLEN}", f"chain:{ECCLESIA}", f"summon:{ECCLESIA}")
    assert recovery_cards_used(hand, actions, CONFIG, interruption="ash") == []


def test_recovery_cards_used_does_not_require_extenders_list():
    hand = [FALLEN, ECCLESIA, CELTIC, CELTIC, CELTIC]
    actions = (f"activate:{FALLEN}", f"chain:{ASH}", f"summon:{ECCLESIA}")
    assert recovery_cards_used(hand, actions, CONFIG, interruption="ash") == [ECCLESIA]


def test_build_recovery_report_pairs_scores_and_attribution():
    hand = [FALLEN, ECCLESIA, CELTIC, CELTIC, CELTIC]
    actions = (f"activate:{FALLEN}", f"chain:{ASH}", f"summon:{ECCLESIA}")
    report = build_recovery_report(
        opening_hand=hand,
        interruption="ash",
        ceiling_score=10.0,
        interrupted_score=3.25,
        ceiling_complete=True,
        interrupted_complete=True,
        actions=actions,
        endboard={"monster": [ECCLESIA]},
        score_breakdown={"monster": 2.0},
        config=CONFIG,
    )
    assert report["opening_hand"] == hand
    assert report["interruption"] == "ash"
    assert report["ceiling_score"] == 10.0
    assert report["interrupted_score"] == 3.25
    assert report["score_loss"] == 6.75
    assert report["complete"] is True
    assert report["ceiling_complete"] is True
    assert report["interrupted_complete"] is True
    assert report["choke_point"] == f"chain:{ASH}"
    assert report["recovery_cards_used"] == [ECCLESIA]
    assert report["actions"] == list(actions)
    assert report["endboard"] == {"monster": [ECCLESIA]}
    assert report["score_breakdown"] == {"monster": 2.0}


def test_build_recovery_report_none_interruption_skips_pair_semantics():
    hand = [FALLEN, ECCLESIA, CELTIC, CELTIC, CELTIC]
    actions = (f"activate:{FALLEN}", f"summon:{ECCLESIA}")
    report = build_recovery_report(
        opening_hand=hand,
        interruption="none",
        ceiling_score=10.0,
        interrupted_score=10.0,
        ceiling_complete=True,
        interrupted_complete=True,
        actions=actions,
        endboard={},
        score_breakdown={},
        config=CONFIG,
    )
    assert report["score_loss"] == 0.0
    assert report["choke_point"] is None
    assert report["recovery_cards_used"] == []


def test_build_recovery_report_complete_false_if_either_provisional():
    report = build_recovery_report(
        opening_hand=[FALLEN],
        interruption="ash",
        ceiling_score=10.0,
        interrupted_score=5.0,
        ceiling_complete=True,
        interrupted_complete=False,
        actions=(f"chain:{ASH}",),
        endboard={},
        score_breakdown={},
        config=CONFIG,
    )
    assert report["complete"] is False


def test_format_recovery_report_includes_key_fields():
    report = build_recovery_report(
        opening_hand=[FALLEN, ECCLESIA, CELTIC, CELTIC, CELTIC],
        interruption="ash",
        ceiling_score=10.0,
        interrupted_score=3.25,
        ceiling_complete=True,
        interrupted_complete=True,
        actions=(f"activate:{FALLEN}", f"chain:{ASH}", f"summon:{ECCLESIA}"),
        endboard={"monster": [ECCLESIA]},
        score_breakdown={},
        config=CONFIG,
    )
    text = format_recovery_report(report)
    assert "ceiling_score: 10.00" in text
    assert "interrupted_score: 3.25" in text
    assert "score_loss: 6.75" in text
    assert f"choke_point: chain:{ASH}" in text
    assert f"recovery_cards_used: [{ECCLESIA}]" in text
    assert '"score_loss": 6.75' in text
