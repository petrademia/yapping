import json
from pathlib import Path

ROOT = Path(__file__).parents[1]

def test_high_spirits_interruption_matrix_uses_known_policies_and_cards():
    matrix = json.loads((
        ROOT / "configs/combos/high_spirits_interruptions.json"
).read_text())
    assert matrix["opening_hand"][:2] == [
        "Branded in High Spirits",
        "Blazing Cartesia, the Virtuous",
    ]
    assert {scenario["card_id"] for scenario in matrix["scenarios"]} == {
        14558127, 94145021, 97268402, 10045474,
    }
    assert {scenario["policy"] for scenario in matrix["scenarios"]} == {
        "activate_at_first_legal_search",
        "activate_after_first_search",
        "activate_on_Fallen_or_Ecclesia",
    }
