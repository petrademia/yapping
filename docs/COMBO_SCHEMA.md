# Combo schema

Combo fixtures use explicit card names and structured metadata. Human titles are
descriptive; the fields below are authoritative for search and learning data.

Each compendium also carries a top-level `card_ids` catalog. Exact cards in
machine-facing fields use numeric IDs; symbolic values such as
`any_spellcaster` remain predicates and are not individual cards.

```json
{
  "card_ids": {"Fallen of the White Dragon": 73819701},
  "id": "branded_fallen_white_dragon_droll_recovery",
  "archetype": "branded_albaz",
  "title": "Fallen of the White Dragon — Droll recovery",
  "line_type": "baseline",
  "starting_hand": ["Fallen of the White Dragon"],
  "starting_hand_ids": [73819701],
  "required_cards": [],
  "opponent_interruption": "Droll & Lock Bird",
  "interruption_timing": "after_first_search",
  "steps": [],
  "endboard": [],
  "validation": {"status": "unverified", "engine": "OCGCore"}
}
```

Use `baseline`, `extension`, `alternative`, or `recovery` for `line_type`.
Avoid shorthand names such as “Walbaz”; use the full card name instead.
