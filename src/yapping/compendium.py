"""Small bridge from verified archetype compendia to optimizer reports."""

from .archetype import Archetype


def summarize_compendium(archetype: Archetype, candidates=()):
    """Describe which candidate cards are already covered by verified data."""
    known = set(archetype.main_deck) | set(archetype.extra_deck) | set(archetype.card_weights)
    fixtures = [
        {"id": fixture.id, "path": str(fixture.path), "available": fixture.path.is_file()}
        for fixture in archetype.fixtures
    ]
    return {
        "name": archetype.name,
        "verified_fixtures": sum(item["available"] for item in fixtures),
        "fixtures": fixtures,
        "candidates": {
            str(candidate.card_id): {
                "label": candidate.label,
                "role": candidate.role,
                "known_to_compendium": candidate.card_id in known,
                "card_weight": archetype.card_weights.get(candidate.card_id),
            }
            for candidate in candidates
        },
    }
