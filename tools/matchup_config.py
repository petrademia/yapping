import json
from pathlib import Path


ROOT = Path(__file__).parents[1]


def load_config(path=None):
    config_path = Path(path) if path else ROOT / "configs/albaz.json"
    config = json.loads(config_path.read_text())
    if "base" in config:
        base = load_config(config_path.parent / config.pop("base"))
        base.update(config)
        config = base
    deck = list(config["main_deck"])
    filler = config.get("main_deck_filler")
    if filler:
        deck.extend([filler["card"]] * filler["count"])
    config["main_deck"] = deck
    config["weights"] = {int(card): value for card, value in config["weights"].items()}
    return config
