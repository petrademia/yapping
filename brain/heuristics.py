"""
Board evaluation and scoring — the "Yap Score".

Ranks end-boards (and intermediate states) by:
- Interrupts (negates, hand traps)
- Resource count (follow-up, card advantage)
- Floodgate presence

Used by search to prune weak branches and prefer high-value lines.
"""

# TODO: implement score(state) -> float
# - query board from env/wrapper
# - weight negates, follow-up, floodgates
# - return comparable scalar (Yap Score)
