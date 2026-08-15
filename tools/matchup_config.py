import json
from pathlib import Path


ROOT = Path(__file__).parents[1]


def scenarios(config, requested=None):
    """Return named interruption/opponent worlds with normalized weights."""
    declared = config.get("matchup_scenarios")
    if declared:
        result = [dict(item) for item in declared]
    else:
        names = requested or ["none"]
        result = [{"name": name, "interruption": name, "weight": 1.0}
                  for name in names]
    total = sum(float(item.get("weight", 1.0)) for item in result) or 1.0
    for item in result:
        item["weight"] = float(item.get("weight", 1.0)) / total
        item.setdefault("name", item.get("interruption", "none"))
        item.setdefault("interruption", "none")
    return result


def experiment_matchup(config, opening_hand=None):
    """Choose configured-deck construction vs deterministic fixture construction.

    Fixture duel construction remains the default for regression searches that
    omit an opening hand and do not opt into configured-deck mode. When an
    opening hand is supplied (consistency / multi-hand oracle), the configured
    ``main_deck`` must drive OCGCore construction so sampled cards cannot fail
    merely because they are absent from ``fixture_deck()``.

    Explicit flags:
      - ``use_fixture_deck``: force fixture construction
      - ``use_configured_deck``: force configured ``main_deck`` / extra / opponent
    """
    if not config:
        return None
    if config.get("use_fixture_deck"):
        return None
    if config.get("use_configured_deck"):
        return config
    if opening_hand is not None and "main_deck" in config:
        return config
    # Legacy path: matchups that already embed an opponent deck list.
    if config.get("opponent_deck") is not None and "main_deck" in config:
        return config
    return None


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
    opponent_deck = config.get("opponent_deck")
    if isinstance(opponent_deck, str):
        opponent_path = Path(opponent_deck)
        if not opponent_path.is_absolute():
            opponent_path = config_path.parent / opponent_path
        loaded = json.loads(opponent_path.read_text())
        config["opponent_deck"] = loaded.get("main_deck", loaded) if isinstance(loaded, dict) else loaded
    if config.get("opponent_deck") is not None and len(config["opponent_deck"]) < 40:
        raise ValueError("opponent_deck must contain at least 40 cards")
    config["weights"] = {int(card): value for card, value in config["weights"].items()}
    return config
