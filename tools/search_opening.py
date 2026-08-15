"""Search the Albaz fixture from its opening decision against a known hand trap."""

import argparse
import json

from analyze_ash import (CARD_WEIGHTS, ReplayCursor, action_name,
                          endboard_score, evaluation_context, replay,
                          score_breakdown)
from recovery_report import build_recovery_report, format_recovery_report
from trace_albaz_combo import (
    ASH_BLOSSOM,
    CELTIC_GUARDIAN,
    DROLL_LOCK_BIRD,
    EFFECT_VEILER,
    GHOST_OGRE,
    INFINITE_IMPERMANENCE,
    NIBIRU,
    card_id,
    fixture_deck,
    INCREDIBLE_ECCLESIA,
    ROOT,
    SCRIPTS,
)
from yapping import minimax_replay, report_provenance
from yapping._ocgcore import Duel
from matchup_config import load_config


# Cards that can legally interrupt the opponent's first turn from hand.
CARDS = {
    "none": None,
    "ash": ASH_BLOSSOM,
    "veiler": EFFECT_VEILER,
    "impermanence": INFINITE_IMPERMANENCE,
    "droll": DROLL_LOCK_BIRD,
    "nibiru": NIBIRU,
    "ghost_ogre": GHOST_OGRE,
}
SKIP_KINDS = {"battle_phase", "shuffle"}
MAX_PRIORITY = {
    "activate": 0,
    "yes": 0,
    "chain": 0,
    "special_summon": 1,
    "select_card": 1,
    "select_sum": 1,
    "select_toggle": 1,
    "option": 1,
    "place": 2,
    "position": 2,
    "pass": 3,
    "end_phase": 4,
}


def legal(snapshot, config):
    actions = snapshot.decision["actions"]
    ignored_cards = set(config.get("ignored_cards", ()))
    seen = set()
    choices = []
    for index, action in enumerate(actions):
        if action["kind"] in config["skip_kinds"] or action["card"] in ignored_cards:
            continue
        signature = (action["kind"], action["card"], action["description"])
        if signature in seen:
            continue
        seen.add(signature)
        choices.append(index)
    controlled_player = config.get("controlled_player", 0)
    if snapshot.decision["player"] != controlled_player:
        opponent_kinds = set(config.get("opponent_action_kinds", ("pass",)))
        return sorted(choices, key=lambda i: actions[i]["kind"] not in opponent_kinds)
    # Alpha-beta reaches a useful lower bound sooner when high-value legal
    # continuations are examined first; every action remains searchable.
    return sorted(
        choices,
        key=lambda i: (config["move_priority"].get(actions[i]["kind"], 2),
                       -config["weights"].get(actions[i]["card"], 0), i),
    )


def recovery_terminal(snapshot, config):
    return (config["recovery_card"] in snapshot.zones["monster"]
            and any(action == config.get("recovery_activation", "activate:73819701")
                    for action in snapshot.actions))


def terminal(snapshot, config):
    return snapshot.decision["turn"] >= config.get("terminal_turn", 2)


def run_search(interruption="ash", max_nodes=20_000, max_depth=180, opening_hand=None,
               ecclesia_copies=1, recovery_only=False, config=None,
               replay_mode="cursor", adapter=None, controlled_player=0,
               stats=None):
    config = config or load_config()
    config = {**config, "controlled_player": controlled_player}
    matchup = config if config.get("opponent_deck") else None
    card = config["interruptions"].get(interruption)
    adapter = adapter or Duel(str(ROOT / "assets/cards.cdb"), str(SCRIPTS))
    cursor = ReplayCursor(card, opening_hand, ecclesia_copies, adapter, matchup,
                          controlled_player)
    replay_fn = cursor if replay_mode == "cursor" else lambda path: replay(
        path, card, opening_hand, ecclesia_copies, adapter, matchup, controlled_player)
    result = minimax_replay(
        replay_fn,
        lambda snapshot: legal(snapshot, config),
        lambda snapshot: endboard_score(snapshot, config["weights"]),
        (lambda snapshot: recovery_terminal(snapshot, config)) if recovery_only
        else lambda snapshot: terminal(snapshot, config),
        lambda snapshot: snapshot.decision["player"],
        max_depth=max_depth,
        max_nodes=max_nodes,
        stats=stats,
    )
    final = replay_fn(result.actions)
    return result, final, config


def search(interruption="ash", max_nodes=20_000, max_depth=180, opening_hand=None,
           ecclesia_copies=1, recovery_only=False, config=None,
           replay_mode="cursor", adapter=None, controlled_player=0):
    result, final, config = run_search(
        interruption, max_nodes, max_depth, opening_hand, ecclesia_copies,
        recovery_only, config, replay_mode, adapter, controlled_player)
    print(f"Opening-hand minimax against known {interruption}")
    if opening_hand is not None:
        print("opening hand: " + ", ".join(map(str, opening_hand)))
    print(f"Ecclesia copies: {ecclesia_copies}")
    print(f"recovery-only: {recovery_only}")
    print(f"replay-mode: {replay_mode}")
    print(f"turn-order: {'first' if controlled_player == 0 else 'second'}")
    score_label = "score" if result.complete else "provisional score at search limit"
    print(f"{score_label}: {result.score:.2f}")
    print(f"visited states: {result.visited_states}")
    print(f"complete: {result.complete}")
    print("provenance: " + json.dumps(report_provenance(
        database=ROOT / "assets/cards.cdb",
        scripts=SCRIPTS,
        max_nodes=max_nodes,
        max_depth=max_depth,
        complete=result.complete,
        revision_root=ROOT,
    ), sort_keys=True))
    print("actions: " + " -> ".join(final.actions))
    print(f"end board: {final.zones}")
    print("score breakdown: " + json.dumps(score_breakdown(final, config["weights"]), sort_keys=True))
    print("evaluation context: " + json.dumps(evaluation_context(final, config=config), sort_keys=True))
    return result, final


def search_recovery_report(interruption="ash", max_nodes=20_000, max_depth=180,
                           opening_hand=None, ecclesia_copies=1, recovery_only=False,
                           config=None, replay_mode="cursor", adapter=None,
                           controlled_player=0):
    """Pair uninterrupted ceiling with the interrupted line and print attribution."""
    config = config or load_config()
    adapter = adapter or Duel(str(ROOT / "assets/cards.cdb"), str(SCRIPTS))
    if interruption == "none":
        result, final, config = run_search(
            interruption, max_nodes, max_depth, opening_hand, ecclesia_copies,
            recovery_only, config, replay_mode, adapter, controlled_player)
        ceiling_score = interrupted_score = result.score
        ceiling_complete = interrupted_complete = result.complete
    else:
        ceiling_result, _, config = run_search(
            "none", max_nodes, max_depth, opening_hand, ecclesia_copies,
            recovery_only, config, replay_mode, adapter, controlled_player)
        result, final, config = run_search(
            interruption, max_nodes, max_depth, opening_hand, ecclesia_copies,
            recovery_only, config, replay_mode, adapter, controlled_player)
        ceiling_score = ceiling_result.score
        interrupted_score = result.score
        ceiling_complete = ceiling_result.complete
        interrupted_complete = result.complete
    hand = list(opening_hand) if opening_hand is not None else list(
        (config.get("main_deck") or fixture_deck())[:5])
    report = build_recovery_report(
        opening_hand=hand,
        interruption=interruption,
        ceiling_score=ceiling_score,
        interrupted_score=interrupted_score,
        ceiling_complete=ceiling_complete,
        interrupted_complete=interrupted_complete,
        actions=final.actions,
        endboard=final.zones,
        score_breakdown=score_breakdown(final, config["weights"]),
        config=config,
    )
    print(f"Opening-hand minimax recovery report against known {interruption}")
    if opening_hand is not None:
        print("opening hand: " + ", ".join(map(str, opening_hand)))
    print(f"Ecclesia copies: {ecclesia_copies}")
    print(f"recovery-only: {recovery_only}")
    print(f"replay-mode: {replay_mode}")
    print(f"turn-order: {'first' if controlled_player == 0 else 'second'}")
    print("provenance: " + json.dumps(report_provenance(
        database=ROOT / "assets/cards.cdb",
        scripts=SCRIPTS,
        max_nodes=max_nodes,
        max_depth=max_depth,
        complete=report["complete"],
        revision_root=ROOT,
    ), sort_keys=True))
    print(format_recovery_report(report))
    print("evaluation context: " + json.dumps(evaluation_context(final, config=config), sort_keys=True))
    return result, final, report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("interruption", choices=CARDS, default="ash", nargs="?")
    parser.add_argument("--max-nodes", type=int, default=20_000)
    parser.add_argument("--max-depth", type=int, default=180)
    parser.add_argument("--hand", type=card_id, nargs=5, metavar="CARD")
    parser.add_argument("--ecclesia-copies", type=int, default=1)
    parser.add_argument("--recovery-only", action="store_true")
    parser.add_argument("--recovery-report", action="store_true")
    parser.add_argument("--config", type=str)
    parser.add_argument("--replay-mode", choices=["cursor", "oracle"], default="cursor")
    arguments = parser.parse_args()
    config = load_config(arguments.config)
    if arguments.recovery_report:
        search_recovery_report(
            arguments.interruption, arguments.max_nodes, arguments.max_depth,
            arguments.hand, arguments.ecclesia_copies, arguments.recovery_only,
            config, arguments.replay_mode)
    else:
        search(arguments.interruption, arguments.max_nodes, arguments.max_depth,
               arguments.hand, arguments.ecclesia_copies, arguments.recovery_only,
               config, arguments.replay_mode)
