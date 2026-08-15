"""Build a per-hand recovery report from paired ceiling / interrupted searches."""

import json


def filler_cards(config):
    """Union of configured filler identities that should not count as recovery."""
    cards = set(config.get("ignored_cards", ()))
    filler = config.get("main_deck_filler")
    if filler and "card" in filler:
        cards.add(filler["card"])
    if "counterfactual_filler" in config:
        cards.add(config["counterfactual_filler"])
    return {int(card) for card in cards}


def interruption_card(interruption, config):
    """Resolved interruption card id, or None for `none` / unknown."""
    if interruption in (None, "none"):
        return None
    card = (config or {}).get("interruptions", {}).get(interruption)
    return int(card) if card is not None else None


def choke_point(actions, interruption=None, config=None):
    """First chain of the configured interruption card in the line, else None.

    Friendly chains (e.g. Ecclesia) also use `chain:` tokens, so matching any
    chain would mis-attribute the choke. Prefer the known interruption card.
    """
    if interruption == "none":
        return None
    card = interruption_card(interruption, config)
    if card is not None:
        target = f"chain:{card}"
        for action in actions:
            if action == target:
                return action
        return None
    for action in actions:
        if action.startswith("chain:"):
            return action
    return None


def _card_from_action(action):
    if ":" not in action:
        return None
    _, _, rest = action.partition(":")
    if not rest.isdigit():
        return None
    return int(rest)


def recovery_cards_used(opening_hand, actions, config, interruption=None):
    """Opening-hand cards that appear in post-choke actions, minus fillers."""
    choke = choke_point(actions, interruption=interruption, config=config)
    if choke is None:
        return []
    index = list(actions).index(choke)
    suffix = actions[index + 1:]
    fillers = filler_cards(config)
    hand = {int(card) for card in opening_hand}
    used = []
    seen = set()
    for action in suffix:
        card = _card_from_action(action)
        if card is None or card in fillers or card not in hand or card in seen:
            continue
        seen.add(card)
        used.append(card)
    return used


def build_recovery_report(
    *,
    opening_hand,
    interruption,
    ceiling_score,
    interrupted_score,
    ceiling_complete,
    interrupted_complete,
    actions,
    endboard,
    score_breakdown,
    config,
):
    return {
        "opening_hand": list(opening_hand),
        "interruption": interruption,
        "ceiling_score": ceiling_score,
        "interrupted_score": interrupted_score,
        "score_loss": ceiling_score - interrupted_score,
        "complete": bool(ceiling_complete and interrupted_complete),
        "ceiling_complete": bool(ceiling_complete),
        "interrupted_complete": bool(interrupted_complete),
        "choke_point": choke_point(actions, interruption=interruption, config=config),
        "recovery_cards_used": recovery_cards_used(
            opening_hand, actions, config, interruption=interruption),
        "actions": list(actions),
        "endboard": endboard,
        "score_breakdown": score_breakdown,
    }


def format_recovery_report(report):
    lines = [
        "Recovery report",
        f"opening_hand: {report['opening_hand']}",
        f"interruption: {report['interruption']}",
        f"ceiling_score: {report['ceiling_score']:.2f}",
        f"interrupted_score: {report['interrupted_score']:.2f}",
        f"score_loss: {report['score_loss']:.2f}",
        f"complete: {report['complete']}",
        f"ceiling_complete: {report['ceiling_complete']}",
        f"interrupted_complete: {report['interrupted_complete']}",
        f"choke_point: {report['choke_point']}",
        f"recovery_cards_used: {report['recovery_cards_used']}",
        "actions: " + " -> ".join(report["actions"]),
        f"endboard: {json.dumps(report['endboard'], sort_keys=True)}",
        "score breakdown: "
        + json.dumps(report["score_breakdown"], sort_keys=True),
        "recovery report json: " + json.dumps(report, sort_keys=True),
    ]
    return "\n".join(lines)
