import json
from pathlib import Path

def get_card_ids(card_names: list[str]) -> dict:
    db_path = Path("data/card_code_to_name.json")
    if not db_path.exists(): return {}
    with open(db_path, "r", encoding="utf-8") as f:
        mapping = json.load(f)
        
    results = {}
    for name in card_names:
        name_lower = name.lower()
        exact = None
        partials = []
        for code, cname in mapping.items():
            if cname.lower() == name_lower:
                exact = (code, cname)
                break
            if name_lower in cname.lower():
                partials.append((code, cname))
                
        if exact:
            results[name] = {"id": int(exact[0]), "name": exact[1]}
        elif partials:
            results[name] = {"id": int(partials[0][0]), "name": partials[0][1]}
        else:
            results[name] = {"id": 0, "name": name}
    return results

if __name__ == "__main__":
    names = [
        "Fallen of Albaz", "Branded Opening", "Incredible Ecclesia, the Virtuous",
        "Blazing Cartesia, the Virtuous", "Granguignol the Dusk Dragon",
        "Titaniklad the Ash Dragon", "Guiding Quem, the Virtuous",
        "Branded in High Spirits", "Aluber the Jester of Despia",
        "Branded in Red", "Lubellion the Searing Dragon",
        "Mirrorjade the Iceblade Dragon", "Albion the Branded Dragon"
    ]
    ids = get_card_ids(names)
    
    # User's combo mapping:
    combo = [
        {"action": "Send to Graveyard", "card_name": "Fallen of Albaz", "card_code": ids["Fallen of Albaz"]["id"]},
        {"action": "Send to Graveyard", "card_name": "Albion the Branded Dragon", "card_code": ids["Albion the Branded Dragon"]["id"]},
        {"action": "Summon", "card_name": "Incredible Ecclesia, the Virtuous", "card_code": ids["Incredible Ecclesia, the Virtuous"]["id"]},
        {"action": "Synchro Summon", "card_name": "Incredible Ecclesia, the Virtuous", "card_code": ids["Incredible Ecclesia, the Virtuous"]["id"]},
        {"action": "Activate Effect", "card_name": "Incredible Ecclesia, the Virtuous", "card_code": ids["Incredible Ecclesia, the Virtuous"]["id"]},
        {"action": "Special Summon", "card_name": "Blazing Cartesia, the Virtuous", "card_code": ids["Blazing Cartesia, the Virtuous"]["id"]},
        {"action": "Activate Effect", "card_name": "Blazing Cartesia, the Virtuous", "card_code": ids["Blazing Cartesia, the Virtuous"]["id"]},
        {"action": "Fusion Summon", "card_name": "Granguignol the Dusk Dragon", "card_code": ids["Granguignol the Dusk Dragon"]["id"]},
        {"action": "Activate Effect", "card_name": "Granguignol the Dusk Dragon", "card_code": ids["Granguignol the Dusk Dragon"]["id"]},
        {"action": "Send to Graveyard", "card_name": "Titaniklad the Ash Dragon", "card_code": ids["Titaniklad the Ash Dragon"]["id"]},
        {"action": "Cancel", "card_name": "End Phase", "card_code": 0},
        {"action": "Activate Effect", "card_name": "Titaniklad the Ash Dragon", "card_code": ids["Titaniklad the Ash Dragon"]["id"]},
        {"action": "Special Summon", "card_name": "Guiding Quem, the Virtuous", "card_code": ids["Guiding Quem, the Virtuous"]["id"]},
        {"action": "Activate Effect", "card_name": "Guiding Quem, the Virtuous", "card_code": ids["Guiding Quem, the Virtuous"]["id"]},
        {"action": "Send to Graveyard", "card_name": "Branded in High Spirits", "card_code": ids["Branded in High Spirits"]["id"]},
        {"action": "Activate Effect", "card_name": "Albion the Branded Dragon", "card_code": ids["Albion the Branded Dragon"]["id"]},
        {"action": "Activate Effect", "card_name": "Incredible Ecclesia, the Virtuous", "card_code": ids["Incredible Ecclesia, the Virtuous"]["id"]},
        {"action": "Activate Effect", "card_name": "Blazing Cartesia, the Virtuous", "card_code": ids["Blazing Cartesia, the Virtuous"]["id"]},
        {"action": "Activate Effect", "card_name": "Branded in High Spirits", "card_code": ids["Branded in High Spirits"]["id"]},
        {"action": "Activate Card", "card_name": "Branded Opening", "card_code": ids["Branded Opening"]["id"]},
        {"action": "Special Summon", "card_name": "Aluber the Jester of Despia", "card_code": ids["Aluber the Jester of Despia"]["id"]},
        {"action": "Activate Effect", "card_name": "Aluber the Jester of Despia", "card_code": ids["Aluber the Jester of Despia"]["id"]},
        {"action": "Add to Hand", "card_name": "Branded in Red", "card_code": ids["Branded in Red"]["id"]},
        {"action": "Activate Card", "card_name": "Branded in Red", "card_code": ids["Branded in Red"]["id"]},
        {"action": "Fusion Summon", "card_name": "Lubellion the Searing Dragon", "card_code": ids["Lubellion the Searing Dragon"]["id"]},
        {"action": "Activate Effect", "card_name": "Lubellion the Searing Dragon", "card_code": ids["Lubellion the Searing Dragon"]["id"]},
        {"action": "Activate Effect", "card_name": "Guiding Quem, the Virtuous", "card_code": ids["Guiding Quem, the Virtuous"]["id"]},
        {"action": "Fusion Summon", "card_name": "Mirrorjade the Iceblade Dragon", "card_code": ids["Mirrorjade the Iceblade Dragon"]["id"]}
    ]
    
    out_path = Path("data/combos/example_branded.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(combo, f, indent=2)
    print("Wrote combo to", out_path)
