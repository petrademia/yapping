"""
Mappings for Selection / Activation logic.

Translates between high-level "do this with these cards" and the
low-level action codes expected by ygo-env (e.g. select card index,
activate, set, summon). Used by wrapper and search to enumerate
and apply legal moves.
"""

from __future__ import annotations


def action_index_to_label(action_index: int) -> str:
    """
    Human-readable label for an action index (for display / logs).
    Full mapping (action type, card, targets) is engine-specific; this gives a stable id.
    """
    return f"action_{action_index}"
