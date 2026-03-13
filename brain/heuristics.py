"""
Board evaluation and scoring — the "Yap Score".

The DFS maximizes this score to choose the best path. So the combo we return
is exactly "argmax path evaluate_line(obs, labels)". To get the correct best
combo, we need the reward to reflect what matters: board presence, negates,
follow-up. Right now we use simple weights; extend with negate/floodgate data later.

Ranks end-boards (and intermediate states) by:
- Board presence (monsters > spell/trap > hand)
- Path penalty (too many summons = Nibiru risk)
- TODO: negates, follow-up, floodgates
"""

from __future__ import annotations

import numpy as np

# Location in obs cards (col 2). Engine may use 1-based ids: hand=2, mzone=3, szone=4, grave=5.
# If GY isn't counted, engine may use bitflags (e.g. grave=16); add elif loc == 16 then.
LOC_DECK = 1
LOC_HAND = 2
LOC_MZONE = 3
LOC_SZONE = 4
LOC_GRAVE = 5
LOC_GRAVE_ALT = 16  # some encodings use 0x10 for grave
LOC_REMOVED = 6
LOC_EXTRA = 7

# Weights: tune these so "best" path matches what you consider the best combo
WEIGHT_MONSTER = 15   # monster on field (boss/negate value)
WEIGHT_SPELL_TRAP = 6 # set/face-up spell or trap
WEIGHT_HAND = 1       # card in hand (resource)
WEIGHT_GRAVE = 2      # card in graveyard (follow-up, Branded, etc.)

# Optional-trigger bias (DFS branch preference)
BONUS_CHAIN_TAKE = 3          # e.g. "Chain X"
BONUS_TRIGGER_YES = 2         # e.g. "Yes (...)"
PENALTY_DONT_CHAIN = 3        # e.g. "Pass / don't chain"
PENALTY_TRIGGER_NO = 2        # e.g. "No (...)"


def evaluate_board(
    obs,
    weight_monster: int = WEIGHT_MONSTER,
    weight_spell_trap: int = WEIGHT_SPELL_TRAP,
    weight_hand: int = WEIGHT_HAND,
    weight_grave: int = WEIGHT_GRAVE,
) -> int:
    """Score the board. DFS maximizes this to pick the best path.
    Includes field, hand, and graveyard (follow-up / GY-focused decks)."""
    if obs is None:
        return 0
    cards = obs.get("obs:cards_") if hasattr(obs, "get") else None
    if cards is None:
        cards = obs.get("cards_") if hasattr(obs, "get") else None
    if cards is None:
        return 0
    arr = np.asarray(cards, dtype=np.uint8)
    if arr.ndim == 3:
        arr = arr[0]
    if arr.ndim < 2 or arr.shape[1] < 5:
        return 0
    score = 0
    for row in range(arr.shape[0]):
        if int(arr[row, 4]) != 0:
            continue
        loc = int(arr[row, 2])
        if loc == LOC_MZONE:
            score += weight_monster
        elif loc == LOC_SZONE:
            score += weight_spell_trap
        elif loc == LOC_HAND:
            score += weight_hand
        elif loc in (LOC_GRAVE, LOC_GRAVE_ALT):
            score += weight_grave
    return score


def path_summon_penalty(action_labels: list[str], threshold: int = 5, penalty_per_summon: int = 2) -> int:
    """Penalty for going past 'threshold' summons (Nibiru risk). Encourages shorter/earlier-negate lines.
    Returns a non-positive value to subtract from score."""
    summon_prefixes = ("Summon", "SpSummon", "MSet")  # MSet is set monster, counts as a "summon" for length
    n = sum(1 for lbl in action_labels if lbl.strip().startswith(summon_prefixes))
    if n <= threshold:
        return 0
    return -penalty_per_summon * (n - threshold)


def optional_trigger_bias(action_labels: list[str]) -> int:
    """Bias toward using optional triggers instead of skipping them."""
    score = 0
    for raw in action_labels:
        lbl = (raw or "").strip()
        low = lbl.lower()
        if "don't chain" in low:
            score -= PENALTY_DONT_CHAIN
            continue
        if lbl.startswith("Chain "):
            score += BONUS_CHAIN_TAKE
            continue
        if lbl.startswith("Yes"):
            score += BONUS_TRIGGER_YES
            continue
        if lbl.startswith("No"):
            score -= PENALTY_TRIGGER_NO
            continue
    return score


def evaluate_line(
    obs,
    action_labels: list[str],
    use_summon_penalty: bool = True,
    use_optional_trigger_bias: bool = True,
) -> int:
    """Board score plus path-based adjustments."""
    score = evaluate_board(obs)
    if use_summon_penalty:
        score += path_summon_penalty(action_labels)  # path_summon_penalty returns 0 or negative
    if use_optional_trigger_bias:
        score += optional_trigger_bias(action_labels)
    return score


# TODO: extend with Yap Score (negates, follow-up, floodgates)
