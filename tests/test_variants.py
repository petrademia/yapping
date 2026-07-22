import pytest

from yapping import DeckVariant, SlotCandidate


def test_deck_variants_are_immutable_and_role_labeled():
    base = DeckVariant("base", (1, 2, 2), (10,))
    candidate = SlotCandidate(3, "extender", "Extender X")
    variant = base.replace_one(2, candidate.card_id, "base+extender")
    assert base.main_deck == (1, 2, 2)
    assert variant.main_deck == (1, 3, 2)
    assert candidate.role == "extender"


def test_variant_rejects_missing_slot():
    with pytest.raises(ValueError, match="not in base"):
        DeckVariant("base", (1,)).replace_one(2, 3)


def test_variant_candidates_preserve_role_labels():
    base = DeckVariant("base", (1, 2))
    variants = base.variants((SlotCandidate(3, "board_breaker", "Breaker"),), 2)
    assert variants[0].name == "base+Breaker"
    assert variants[0].main_deck == (1, 3)
