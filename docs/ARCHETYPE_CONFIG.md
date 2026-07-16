# Archetype configuration

YAPPING keeps duel execution archetype-independent. A new archetype supplies one JSON file with:

- main_deck and extra_deck: card IDs, repeated for copies.
- interruption_specs: opponent card IDs and activation policies.
- fixtures: paths to deterministic combo/scenario descriptions.
- target_predicates: declarative legality constraints such as race, level, type, and ATK/DEF.
- objectives: evaluator weights; these are policy inputs, not OCGCore rules.

Load it with:

    from yapping import load_archetype
    archetype = load_archetype("configs/archetypes/branded.json")

The generic layers consume card identity, location, legal actions, and current duel state. They must not branch on names such as Fallen or Ecclesia. Archetype-specific behavior belongs in fixture data, predicates, interruption policies, and objective weights.

Branded remains the regression archetype. A second archetype should only need a new JSON file plus its own fixture files; the adapter, ReplayCursor, minimax, hidden-world search, and scoring primitives should be reused.
