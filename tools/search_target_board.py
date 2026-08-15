"""Search a known hand for a line that covers required endboard pieces."""

import argparse
import json
import sys
import time

from matchup_config import load_config
from search_opening import run_search, terminal as opening_terminal
from target_board import (
    ProgressClock,
    ZONES,
    build_report,
    choose_result,
    coverage,
    parse_targets,
    validate_hand_in_deck,
    validate_targets_in_deck,
)
from trace_albaz_combo import card_id


def _nonneg_float(value):
    number = float(value)
    if number < 0:
        raise argparse.ArgumentTypeError("progress-every must be >= 0")
    return number


def _target_flag(value):
    if "=" not in value:
        raise argparse.ArgumentTypeError("target must be ZONE=CARD")
    zone, _, card = value.partition("=")
    if zone not in ZONES:
        raise argparse.ArgumentTypeError(
            f"unknown zone {zone!r}; expected one of {', '.join(ZONES)}"
        )
    if not card:
        raise argparse.ArgumentTypeError("target must be ZONE=CARD")
    return value


def build_parser():
    parser = argparse.ArgumentParser(
        description="Recover a combo path that covers required endboard pieces."
    )
    parser.add_argument("--config", type=str)
    parser.add_argument("--hand", type=card_id, nargs=5, metavar="CARD", required=True)
    parser.add_argument("--target", dest="targets", action="append",
                        type=_target_flag, required=True, metavar="ZONE=CARD")
    parser.add_argument("--progress-every", type=_nonneg_float, default=5.0)
    parser.add_argument("--max-nodes", type=int, default=20_000)
    parser.add_argument("--max-depth", type=int, default=180)
    parser.add_argument("--replay-mode", choices=["cursor", "oracle"], default="cursor")
    return parser


def emit(payload):
    json.dump(payload, sys.stdout, sort_keys=True)
    sys.stdout.write("\n")
    sys.stdout.flush()


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        config = load_config(args.config)
        targets = parse_targets(args.targets, card_id)
        validate_hand_in_deck(config["main_deck"], args.hand)
        validate_targets_in_deck(config["main_deck"], config["extra_deck"], targets)
    except (ValueError, FileNotFoundError, OSError) as error:
        print(error, file=sys.stderr)
        return 2

    started = time.monotonic()
    clock = ProgressClock(args.progress_every, emit)
    required = len(targets)

    def evaluate(snapshot):
        return float(coverage(snapshot.zones, targets)["coverage"])

    def is_terminal(snapshot):
        info = coverage(snapshot.zones, targets)
        return info["complete_match"] or opening_terminal(snapshot, config)

    def on_leaf(node, path, score):
        info = coverage(node.zones, targets)
        payload = build_report(
            event="progress",
            coverage_info=info,
            targets=targets,
            opening_hand=args.hand,
            actions=list(node.actions),
            endboard=node.zones,
            visited_states=0,
            elapsed_seconds=time.monotonic() - started,
            complete=False,
            max_nodes=args.max_nodes,
            max_depth=args.max_depth,
        )
        clock.note_leaf(score, payload)

    result, final, config = run_search(
        interruption="none",
        max_nodes=args.max_nodes,
        max_depth=args.max_depth,
        opening_hand=list(args.hand),
        config=config,
        replay_mode=args.replay_mode,
        evaluate=evaluate,
        is_terminal=is_terminal,
        goal_score=float(required),
        on_leaf=on_leaf,
    )
    info = coverage(final.zones, targets)
    search_payload = build_report(
        event="result",
        coverage_info=info,
        targets=targets,
        opening_hand=args.hand,
        actions=list(final.actions),
        endboard=final.zones,
        visited_states=result.visited_states,
        elapsed_seconds=time.monotonic() - started,
        complete=result.complete,
        max_nodes=args.max_nodes,
        max_depth=args.max_depth,
    )
    best_score, best_payload = clock.best if clock.best is not None else (None, None)
    payload = dict(choose_result(info["coverage"], search_payload, best_score, best_payload))
    payload["event"] = "result"
    payload["visited_states"] = result.visited_states
    payload["elapsed_seconds"] = time.monotonic() - started
    payload["complete"] = result.complete
    emit(payload)
    return 0


if __name__ == "__main__":
    sys.exit(main())
