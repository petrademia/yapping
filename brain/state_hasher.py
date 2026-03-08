"""
Unique board identification to avoid loops.

Produces a canonical hash (or fingerprint) of a game state so that
different move sequences leading to the same board are recognized
and redundant paths can be pruned (transposition detection).
"""

# TODO: implement hash_state(state) -> hashable
# - normalize board representation (card positions, zones, public info)
# - return stable hash for use in search visited-set
