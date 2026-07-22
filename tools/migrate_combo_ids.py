"""One-time migration of exact combo card references to numeric IDs."""

import json
import sqlite3
from pathlib import Path


ROOT = Path(__file__).parents[1]
DATABASE = ROOT / "assets/cards.cdb"
FILES = sorted((ROOT / "configs/combos").glob("*.json"))
EXACT_KEYS = {
    "card", "target", "alternative", "opponent_interruption", "endboard",
    "choices", "target_variants",
}
LIST_KEYS = {"starting_hand", "required_cards", "target_variants", "materials", "endboard", "choices"}


def main():
    connection = sqlite3.connect(DATABASE)
    names = {}
    for card_id, name in connection.execute("SELECT id, name FROM texts"):
        names.setdefault(name, card_id)
    connection.close()
    for path in FILES:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, list):
            # Legacy fixture already uses numeric IDs throughout.
            path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            continue
        cards = data.get("cards", [])
        known_ids = {
            int(item["id"] if isinstance(item, dict) else item)
            for item in cards
        }

        def convert(value, key=None):
            if isinstance(value, dict):
                return {field: convert(item, field) for field, item in value.items()}
            if isinstance(value, list):
                return [convert(item, key) for item in value]
            if isinstance(value, str) and key in EXACT_KEYS | LIST_KEYS:
                if value in names:
                    known_ids.add(names[value])
                    return names[value]
            return value

        data = convert(data)
        data["cards"] = sorted(known_ids)
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
