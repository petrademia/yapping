"""
Command-line tool to run simulations.

Usage:
  # Hand Simulator (raw data: draw 5, first 10 legal actions)
  YGO_ENV_ROOT=/path/to/yapcore python -m cli.cli hand-sim --deck data/decks/MyDeck.ydk

  # Combo executor (best-path DFS)
  python -m cli.cli combo --deck data/decks/MyDeck.ydk
  python -m cli.cli combo --deck data/decks/MyDeck.ydk --mode best --export json --out combo.json
"""

from __future__ import annotations

import argparse
import csv
import json
import sqlite3
import sys
from pathlib import Path

DEFAULT_FIXED_HAND = "68468459,60242223,45883110,29948294,95515789"
# Default opening-hand used by `--fixed-hand` when the flag is omitted.
#
# Verified against `vendor/yapcore/assets/deck/Branded.ydk`:
# - 68468459 Fallen of Albaz: present
# - 60242223 Bystial Saronir: present
# - 45883110 Guiding Quem, the Virtuous: present
# - 29948294 Branded in High Spirits: present
# - 95515789 Blazing Cartesia, the Virtuous: present


def _default_adapter_root(yapping_root: Path) -> Path:
    return yapping_root / "vendor" / "yapcore"


def _resolve_deck_path(deck: Path, yapping_root: Path, ygo_env_root: Path | None) -> Path:
    """
    Resolve `--deck` into an existing `.ydk` file path.

    This keeps `--deck` path-specific (you must pass a path ending in `.ydk`);
    if it doesn't exist, we try fallbacks using the same basename:
    - `data/decks/<basename>` (preferred)
    - bundled engine decks (from the engine assets / vendor/yapcore)
    """
    deck_path = Path(deck)
    if deck_path.suffix.lower() != ".ydk":
        print(f"Error: --deck must point to a .ydk file (got: {deck_path})", file=sys.stderr)
        sys.exit(2)

    # Enforce "specific path" usage: reject bare `Branded.ydk` (parent == '.').
    if not deck_path.is_absolute() and deck_path.parent == Path("."):
        print(
            "Error: --deck must be a specific path ending in .ydk (e.g. "
            "'data/decks/Branded.ydk' or an absolute '/path/to/Branded.ydk').\n"
            f"Got: {deck_path}",
            file=sys.stderr,
        )
        sys.exit(2)

    if deck_path.is_file():
        return deck_path.resolve()

    basename = deck_path.name  # includes .ydk

    candidates: list[Path] = []
    # If caller passed a relative path, also try it under project root.
    if not deck_path.is_absolute():
        candidates.append((yapping_root / deck_path).resolve())

    # data first (preferred UX)
    candidates.append(yapping_root / "data" / "decks" / basename)

    # then bundled engine decks
    if ygo_env_root is not None:
        candidates.append(Path(ygo_env_root) / "assets" / "deck" / basename)

    candidates.append(_default_adapter_root(yapping_root) / "assets" / "deck" / basename)

    seen: set[str] = set()
    uniq: list[Path] = []
    for c in candidates:
        key = str(c)
        if key in seen:
            continue
        seen.add(key)
        uniq.append(c)

    for c in uniq:
        if c.is_file():
            return c.resolve()

    print(
        f"Error: deck not found: {deck_path}\n"
        f"Tried:\n" + "\n".join(f"  - {c}" for c in uniq),
        file=sys.stderr,
    )
    sys.exit(1)


def _add_engine_root_arg(parser: argparse.ArgumentParser, *, help_text: str, default: Path | None = None) -> None:
    parser.add_argument(
        "--engine-root",
        "--ygo-env",
        dest="engine_root",
        type=Path,
        default=default,
        help=help_text,
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="YAPPING — combo path analyzer (Hand Simulator + Combo Map).",
    )
    subparsers = parser.add_subparsers(dest="command", help="Command")

    # ---- hand-sim: draw 5, list first N legal actions ----
    hand_sim = subparsers.add_parser("hand-sim", help="Hand Simulator: draw 5, show first N legal actions (raw data).")
    hand_sim.add_argument("--deck", type=Path, required=True, help="Path to .ydk deck file")
    hand_sim.add_argument("--num-draw", type=int, default=5, help="Hand size (default: 5)")
    hand_sim.add_argument("--max-actions", type=int, default=10, help="Max legal actions to print (default: 10)")
    _add_engine_root_arg(hand_sim, help_text="Root of the engine repo (default: env YGO_ENV_ROOT; legacy alias: --ygo-env)")
    hand_sim.add_argument("--seed", type=int, default=None, help="RNG seed for reproducible hand")
    hand_sim.add_argument(
        "--take-action",
        type=int,
        default=None,
        metavar="N",
        help="After showing state, take action index N and show next state (e.g. 0 = first action)",
    )
    hand_sim.add_argument(
        "--interactive",
        action="store_true",
        help="Enter a manual prompt-by-prompt loop so you can choose engine actions yourself.",
    )
    hand_sim.add_argument(
        "--dfs",
        action="store_true",
        help="Run DFS from current state: explore each action until max-depth or no actions",
    )
    hand_sim.add_argument(
        "--activate-trace",
        action="store_true",
        help="Run one linear prompt trace: try to activate/yes/chain whenever possible (no DFS).",
    )
    hand_sim.add_argument(
        "--scored-trace",
        action="store_true",
        help="Run one linear prompt trace using local scoring (action goals + state delta + card-specific prompt bias).",
    )
    hand_sim.add_argument(
        "--engine-transcript",
        action="store_true",
        help="Run engine-first transcript trace with raw prompt/action metadata (no DFS).",
    )
    hand_sim.add_argument(
        "--engine-transcript-json",
        type=Path,
        default=None,
        help="Output JSON path for --engine-transcript (default: rep_engine_transcript.json).",
    )
    hand_sim.add_argument(
        "--engine-transcript-max-steps",
        type=int,
        default=300,
        help="Max prompt steps for --engine-transcript (default: 300).",
    )
    hand_sim.add_argument(
        "--engine-verbose",
        action="store_true",
        help="Enable native engine verbose logs (C++ notify output).",
    )
    hand_sim.add_argument(
        "--trace-max-steps",
        type=int,
        default=200,
        help="Max prompt steps for --activate-trace (default: 200).",
    )
    hand_sim.add_argument(
        "--lock-initial-player",
        action="store_true",
        default=True,
        help="For --activate-trace: when to_play != initial player, force passive choices if legal.",
    )
    hand_sim.add_argument(
        "--allow-opponent-actions",
        dest="lock_initial_player",
        action="store_false",
        help="Allow non-initial-player prompts to take active choices instead of defaulting to passive ones.",
    )
    hand_sim.add_argument("--max-depth", type=int, default=6, help="DFS max depth (default: 6)")
    hand_sim.add_argument("--max-nodes", type=int, default=500, help="DFS max nodes (default: 500)")
    hand_sim.add_argument(
        "--dfs-json",
        type=Path,
        default=None,
        help="Optional path to write DFS report JSON (best path + prompt nodes + states).",
    )
    hand_sim.add_argument(
        "--dfs-json-all",
        type=Path,
        default=None,
        help="Optional path to write full DFS debug JSON (all visited nodes + skips).",
    )
    hand_sim.add_argument(
        "--fail-fast-drift",
        action="store_true",
        help="For --dfs: exit immediately on first transcript replay drift (debug determinism).",
    )
    hand_sim.add_argument(
        "--goal-mzone",
        type=str,
        default="",
        help="Comma-separated target card codes desired on your MZONE at end state.",
    )
    hand_sim.add_argument(
        "--goal-szone",
        type=str,
        default="",
        help="Comma-separated target card codes desired on your SZONE at end state.",
    )
    hand_sim.add_argument(
        "--goal-grave",
        type=str,
        default="",
        help="Comma-separated target card codes desired in your GY at end state.",
    )
    hand_sim.add_argument(
        "--goal-banish",
        type=str,
        default="",
        help="Comma-separated target card codes desired in your banish at end state.",
    )
    hand_sim.add_argument(
        "--goal-hand",
        type=str,
        default="",
        help="Comma-separated target card codes desired in your hand at end state.",
    )
    hand_sim.add_argument(
        "--goal-hit-bonus",
        type=int,
        default=40,
        help="Bonus score per matched target card instance (default: 40).",
    )
    hand_sim.add_argument(
        "--meaningful-action-bonus",
        type=int,
        default=5,
        help="Bonus score per meaningful action (default: 5).",
    )
    hand_sim.add_argument(
        "--action-goals-json",
        type=Path,
        default=None,
        help="Optional JSON file with action-sequence bonus rules (contains/order bonuses).",
    )
    hand_sim.add_argument(
        "--first-turn",
        action="store_true",
        default=True,
        help="Assume first turn: Pass = end of turn, no Main Phase 2 (default: True)",
    )
    hand_sim.add_argument("--no-first-turn", dest="first_turn", action="store_false", help="Allow Main Phase 2 after Pass")
    hand_sim.add_argument(
        "--target-code",
        type=int,
        default=None,
        metavar="CODE",
        help="Keep drawing until hand contains this card code (e.g. 73819701 = Fallen of the White Dragon), then run sim/DFS",
    )
    hand_sim.add_argument(
        "--fixed-hand",
        type=str,
        default=DEFAULT_FIXED_HAND,
        metavar="CODES",
        help=(
            "Comma-separated exact opening hand codes (default: Branded 5-card combo). "
            "Use --fixed-hand '' to disable and respect --seed for the opening draw."
        ),
    )

    # ---- combo: best-path DFS executor ----
    combo = subparsers.add_parser("combo", help="Combo search: execute best-path DFS from an opening hand.")
    combo.add_argument("--deck", type=Path, required=True, help="Path to .ydk deck file")
    combo.add_argument(
        "--mode",
        choices=("best", "all", "surprise"),
        default="best",
        help="Search mode. Only 'best' is implemented right now (default: best).",
    )
    combo.add_argument("--export", choices=("json", "flowchart"), help="Export format. Only json is implemented.")
    combo.add_argument("--out", type=Path, help="Output file path")
    _add_engine_root_arg(combo, help_text="Root of the engine repo (default: env YGO_ENV_ROOT; legacy alias: --ygo-env)")
    combo.add_argument("--seed", type=int, default=None, help="RNG seed for reproducible hand")
    combo.add_argument("--depth", type=int, default=6, help="Max DFS depth (default: 6)")
    combo.add_argument("--max-branches", type=int, default=500, help="Max DFS nodes to explore (default: 500)")
    combo.add_argument("--target-code", type=int, default=None, metavar="CODE", help="Keep drawing until the opening hand contains this card code")
    combo.add_argument(
        "--fixed-hand",
        type=str,
        default=DEFAULT_FIXED_HAND,
        metavar="CODES",
        help="Comma-separated exact opening hand codes. Use '' to disable fixed-hand search.",
    )
    combo.add_argument("--lock-initial-player", action="store_true", help="Prefer passive choices when prompts switch to the non-initial player")
    combo.add_argument(
        "--allow-opponent-actions",
        dest="lock_initial_player",
        action="store_false",
        help="Allow non-initial-player prompts to take active choices instead of defaulting to passive ones.",
    )
    combo.add_argument(
        "--first-turn",
        action="store_true",
        default=True,
        help="Assume first turn: Pass = end of turn (default: True)",
    )
    combo.add_argument("--no-first-turn", dest="first_turn", action="store_false", help="Allow post-pass continuation")
    combo.add_argument("--goal-mzone", type=str, default="", help="Comma-separated target card codes desired on your MZONE at end state")
    combo.add_argument("--goal-szone", type=str, default="", help="Comma-separated target card codes desired on your SZONE at end state")
    combo.add_argument("--goal-grave", type=str, default="", help="Comma-separated target card codes desired in your GY at end state")
    combo.add_argument("--goal-banish", type=str, default="", help="Comma-separated target card codes desired in your banish at end state")
    combo.add_argument("--goal-hand", type=str, default="", help="Comma-separated target card codes desired in your hand at end state")
    combo.add_argument("--goal-hit-bonus", type=int, default=40, help="Bonus score per matched target card instance")
    combo.add_argument("--meaningful-action-bonus", type=int, default=5, help="Bonus score per meaningful action")
    combo.add_argument("--action-goals-json", type=Path, default=None, help="Optional JSON file with action-sequence bonus rules")

    # ---- export-card-names: code -> name for deck builder UI ----
    export_names = subparsers.add_parser(
        "export-card-names",
        help="Export card code -> name from cards.cdb (for deck builder lookups).",
    )
    export_names.add_argument(
        "--cdb",
        type=Path,
        default=None,
        help="Path to cards.cdb (default: $YGO_ENV_ROOT/assets/locale/en/cards.cdb)",
    )
    _add_engine_root_arg(export_names, help_text="Engine root (default: env YGO_ENV_ROOT; used if --cdb not set; legacy alias: --ygo-env)")
    export_names.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Output path (default: data/card_code_to_name.json)",
    )
    export_names.add_argument(
        "--format",
        choices=("json", "csv"),
        default="json",
        help="Output format (default: json)",
    )

    # ---- add-deck-codes-to-list: append missing deck codes to example/code_list.txt ----
    add_codes = subparsers.add_parser(
        "add-deck-codes-to-list",
        help="Append card codes from a deck to the engine example/code_list.txt (so they are loaded without runtime merge).",
    )
    add_codes.add_argument("--deck", type=Path, required=True, help="Path to .ydk deck file")
    _add_engine_root_arg(add_codes, help_text="Engine root (default: env YGO_ENV_ROOT; legacy alias: --ygo-env)")

    # ---- rollout: generate trajectories (state, action, reward) for MDP / RL ----
    rollout = subparsers.add_parser(
        "rollout",
        help="Generate trajectories: run episodes with a policy, log (state, action, reward).",
    )
    rollout.add_argument("--deck", type=Path, required=True, help="Path to .ydk deck file")
    rollout.add_argument("--episodes", type=int, default=5, help="Number of episodes (default: 5)")
    rollout.add_argument("--max-depth", type=int, default=10, help="Max steps per episode (default: 10)")
    rollout.add_argument(
        "--policy",
        choices=("random", "greedy_pass_last"),
        default="random",
        help="Policy: random or prefer non-Pass (default: random)",
    )
    rollout.add_argument(
        "--reward",
        choices=("step", "final_only"),
        default="step",
        help="Reward: board score each step or only at end (default: step)",
    )
    rollout.add_argument("--log", type=Path, default=None, help="Write trajectories to this JSON file")
    _add_engine_root_arg(rollout, help_text="Engine root (default: env YGO_ENV_ROOT; legacy alias: --ygo-env)")

    # ---- sample-hands: generate multiple hands from deck, output card names ----
    sample = subparsers.add_parser(
        "sample-hands",
        help="Generate a set of hands from a .ydk deck and output card names (one hand per line or JSON).",
    )
    sample.add_argument("--deck", type=Path, required=True, help="Path to .ydk deck file")
    sample.add_argument(
        "--num-hands",
        type=int,
        default=10,
        help="Number of hands to sample (default: 10)",
    )
    sample.add_argument(
        "--num-draw",
        type=int,
        default=5,
        help="Cards per hand (default: 5)",
    )
    _add_engine_root_arg(sample, help_text="Engine root (default: env YGO_ENV_ROOT; legacy alias: --ygo-env)")
    sample.add_argument("--seed", type=int, default=None, help="Base RNG seed for reproducible samples (seed, seed+1, ...)")
    sample.add_argument("--out", type=Path, default=None, help="Output file (default: stdout)")
    sample.add_argument(
        "--format",
        choices=("text", "json"),
        default="text",
        help="Output format: text = one hand per line, comma-separated names; json = full structure (default: text)",
    )

    # ---- parse-yrp3d: inspect replay structure, compression, and metadata ----
    parse_yrp3d = subparsers.add_parser(
        "parse-yrp3d",
        help="Parse/introspect a .yrp3d replay and output metadata/probes as JSON.",
    )
    parse_yrp3d.add_argument("--replay", type=Path, required=True, help="Path to .yrp3d replay file")
    parse_yrp3d.add_argument("--out", type=Path, default=None, help="Optional output JSON path")

    # ---- combo-run: execute a scripted combo recipe ----
    combo_run = subparsers.add_parser(
        "combo-run",
        help="Execute a scripted combo recipe JSON against the engine.",
    )
    combo_run.add_argument(
        "--recipe", type=Path, required=True,
        help="Path to combo recipe JSON (see data/combos/ for examples).",
    )
    combo_run.add_argument(
        "--deck", type=Path, default=None,
        help="Override the deck path from the recipe.",
    )
    combo_run.add_argument(
        "--seed", type=int, default=None,
        help="Override the seed from the recipe.",
    )
    _add_engine_root_arg(combo_run, help_text="Root of the engine repo (default: env YGO_ENV_ROOT or vendor/yapcore; legacy alias: --ygo-env)")

    # ---- combo-record: interactively record a combo recipe ----
    combo_record = subparsers.add_parser(
        "combo-record",
        help="Interactively record a combo step-by-step and save as a recipe JSON.",
    )
    combo_record.add_argument("--deck", type=Path, required=True, help="Path to .ydk deck file")
    combo_record.add_argument("--out", type=Path, required=True, help="Output recipe JSON path")
    combo_record.add_argument("--name", type=str, default=None, help="Human-readable name for this combo")
    combo_record.add_argument("--seed", type=int, default=None, help="RNG seed for reproducible hand")
    _add_engine_root_arg(combo_record, help_text="Root of the engine repo (default: env YGO_ENV_ROOT or vendor/yapcore; legacy alias: --ygo-env)")

    combo_validate = subparsers.add_parser(
        "combo-validate",
        help="Execute a recipe, capture a strict transcript, and replay-validate it.",
    )
    combo_validate.add_argument(
        "--recipe", type=Path, required=True,
        help="Path to combo recipe JSON.",
    )
    combo_validate.add_argument(
        "--deck", type=Path, default=None,
        help="Override the deck path from the recipe.",
    )
    combo_validate.add_argument(
        "--seed", type=int, default=None,
        help="Override the seed from the recipe.",
    )
    _add_engine_root_arg(combo_validate, help_text="Root of the engine repo (default: env YGO_ENV_ROOT or vendor/yapcore; legacy alias: --ygo-env)")

    args = parser.parse_args()
    yapping_root = Path(__file__).resolve().parent.parent

    if args.command == "hand-sim":
        from cli.hand_simulator import run as hand_sim_run

        deck_path = _resolve_deck_path(args.deck, yapping_root, args.engine_root)

        fixed_hand = None
        if args.fixed_hand is not None and str(args.fixed_hand).strip() != "":
            try:
                fixed_hand = [int(x.strip()) for x in str(args.fixed_hand).split(",") if x.strip()]
            except ValueError:
                print("Error: --fixed-hand must be comma-separated integer card codes.", file=sys.stderr)
                sys.exit(1)

        hand_sim_run(
            deck=deck_path,
            num_draw=args.num_draw,
            max_actions=args.max_actions,
            ygo_env_root=args.engine_root,
            seed=args.seed,
            take_action=args.take_action,
            interactive=args.interactive,
            dfs=args.dfs,
            activate_trace=args.activate_trace,
            scored_trace=args.scored_trace,
            engine_transcript=args.engine_transcript,
            engine_transcript_json=args.engine_transcript_json,
            engine_transcript_max_steps=args.engine_transcript_max_steps,
            engine_verbose=args.engine_verbose,
            trace_max_steps=args.trace_max_steps,
            lock_initial_player=args.lock_initial_player,
            max_depth=args.max_depth,
            max_nodes=args.max_nodes,
            first_turn=args.first_turn,
            target_code=args.target_code,
            fixed_hand=fixed_hand,
            dfs_json=args.dfs_json,
            dfs_json_all=args.dfs_json_all,
            fail_fast_drift=args.fail_fast_drift,
            goal_mzone=args.goal_mzone,
            goal_szone=args.goal_szone,
            goal_grave=args.goal_grave,
            goal_banish=args.goal_banish,
            goal_hand=args.goal_hand,
            goal_hit_bonus=args.goal_hit_bonus,
            meaningful_action_bonus=args.meaningful_action_bonus,
            action_goals_json=args.action_goals_json,
        )
        return

    if args.command == "combo":
        if args.mode != "best":
            print(f"Combo mode '{args.mode}' is not implemented yet. Use '--mode best'.", file=sys.stderr)
            sys.exit(2)
        if args.export == "flowchart":
            print("Flowchart export is not implemented yet. Use '--export json' or omit --export.", file=sys.stderr)
            sys.exit(2)

        from cli.hand_simulator import run as hand_sim_run

        deck_path = _resolve_deck_path(args.deck, yapping_root, args.engine_root)

        fixed_hand = None
        if args.fixed_hand is not None and str(args.fixed_hand).strip() != "":
            try:
                fixed_hand = [int(x.strip()) for x in str(args.fixed_hand).split(",") if x.strip()]
            except ValueError:
                print("Error: --fixed-hand must be comma-separated integer card codes.", file=sys.stderr)
                sys.exit(1)

        hand_sim_run(
            deck=deck_path,
            num_draw=5,
            max_actions=0,
            ygo_env_root=args.engine_root,
            seed=args.seed,
            dfs=True,
            max_depth=args.depth,
            max_nodes=args.max_branches,
            first_turn=args.first_turn,
            target_code=args.target_code,
            fixed_hand=fixed_hand,
            dfs_json=args.out if args.export == "json" else None,
            lock_initial_player=args.lock_initial_player,
            goal_mzone=args.goal_mzone,
            goal_szone=args.goal_szone,
            goal_grave=args.goal_grave,
            goal_banish=args.goal_banish,
            goal_hand=args.goal_hand,
            goal_hit_bonus=args.goal_hit_bonus,
            meaningful_action_bonus=args.meaningful_action_bonus,
            action_goals_json=args.action_goals_json,
        )
        return

    if args.command == "combo-run":
        _run_combo_run(
            recipe_path=args.recipe,
            deck_override=args.deck,
            seed_override=args.seed,
            ygo_env_root=args.engine_root,
        )
        return

    if args.command == "combo-record":
        _run_combo_record(
            deck=args.deck,
            out=args.out,
            name=args.name,
            seed=args.seed,
            ygo_env_root=args.engine_root,
        )
        return

    if args.command == "combo-validate":
        _run_combo_validate(
            recipe_path=args.recipe,
            deck_override=args.deck,
            seed_override=args.seed,
            ygo_env_root=args.engine_root,
        )
        return

    if args.command == "export-card-names":
        _run_export_card_names(
            cdb_path=args.cdb,
            ygo_env_root=args.engine_root,
            out_path=args.out,
            fmt=args.format,
        )
        return

    if args.command == "add-deck-codes-to-list":
        deck_path = _resolve_deck_path(args.deck, yapping_root, args.engine_root)
        _run_add_deck_codes_to_list(deck_path=deck_path, ygo_env_root=args.engine_root)
        return

    if args.command == "rollout":
        _run_rollout(
            deck_path=_resolve_deck_path(args.deck, yapping_root, args.engine_root),
            ygo_env_root=args.engine_root,
            num_episodes=args.episodes,
            max_depth=args.max_depth,
            policy=args.policy,
            reward_shape=args.reward,
            log_path=args.log,
        )
        return

    if args.command == "sample-hands":
        from cli.hand_simulator import run_sample_hands

        run_sample_hands(
            deck=_resolve_deck_path(args.deck, yapping_root, args.engine_root),
            num_hands=args.num_hands,
            num_draw=args.num_draw,
            ygo_env_root=args.engine_root,
            seed=args.seed,
            out_path=args.out,
            format=args.format,
        )
        return

    if args.command == "parse-yrp3d":
        from cli.replay_parser import parse_yrp3d as parse_replay_yrp3d

        report = parse_replay_yrp3d(args.replay)
        s = json.dumps(report, ensure_ascii=False, indent=2)
        if args.out:
            out = Path(args.out).resolve()
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(s + "\n", encoding="utf-8")
            print(f"Wrote yrp3d report to {out}")
        else:
            print(s)
        return

    parser.print_help()
    return


def _run_rollout(
    deck_path: Path,
    ygo_env_root: Path | None,
    num_episodes: int,
    max_depth: int,
    policy: str,
    reward_shape: str,
    log_path: Path | None,
) -> None:
    """Run rollout episodes and optionally log trajectories to JSON."""
    import os

    deck_path = Path(deck_path).resolve()
    if not deck_path.is_file():
        print(f"Error: deck not found: {deck_path}", file=sys.stderr)
        sys.exit(1)

    root = Path(ygo_env_root).resolve() if ygo_env_root else None
    if root is None or not root.is_dir():
        root = os.environ.get("YGO_ENV_ROOT")
        root = Path(root).resolve() if root else None
    if root is None or not root.is_dir():
        yapping_root = Path(__file__).resolve().parent.parent
        root = _default_adapter_root(yapping_root)
    if not root.is_dir():
        print("Error: need --engine-root or YGO_ENV_ROOT; or vendor/yapcore must exist. Legacy alias: --ygo-env.", file=sys.stderr)
        sys.exit(1)

    yapping_root = Path(__file__).resolve().parent.parent
    if str(yapping_root) not in sys.path:
        sys.path.insert(0, str(yapping_root))

    from engine.environment import create_env
    from brain.rollout import run_rollouts

    # Load card_id -> code (code_list) and code -> name (scripture)
    cid_map = {}
    code_list_file = root / "example" / "code_list.txt"
    if code_list_file.is_file():
        with open(code_list_file, encoding="utf-8", errors="replace") as f:
            for i, line in enumerate(f, start=1):
                parts = line.strip().split()
                if parts and parts[0].isdigit():
                    cid_map[i] = int(parts[0])
    name_map = {}
    json_path = yapping_root / "data" / "card_code_to_name.json"
    if json_path.is_file():
        with open(json_path, encoding="utf-8") as f:
            name_map = json.load(f)

    print("Creating env and running rollouts...")
    env = create_env(deck_path=deck_path, ygo_env_root=root, seed=None)
    run_rollouts(
        env,
        cid_map,
        name_map,
        num_episodes=num_episodes,
        max_depth=max_depth,
        policy=policy,
        reward_shape=reward_shape,
        log_path=log_path,
        verbose=True,
    )


def _run_export_card_names(
    cdb_path: Path | None,
    ygo_env_root: Path | None,
    out_path: Path | None,
    fmt: str,
) -> None:
    """Export card code -> name from cards.cdb for deck builder lookups."""
    import os

    if cdb_path is None:
        root = ygo_env_root
        if root is None or not root.is_dir():
            env_root = os.environ.get("YGO_ENV_ROOT")
            root = Path(env_root).resolve() if env_root else None
        if root is None or not root.is_dir():
            # Default: vendor/yapcore relative to this repo
            yapping_root = Path(__file__).resolve().parent.parent
            root = _default_adapter_root(yapping_root)
        if not root.is_dir():
            print("Error: need --cdb path or --engine-root or YGO_ENV_ROOT; or vendor/yapcore must exist. Legacy alias: --ygo-env.", file=sys.stderr)
            sys.exit(1)
        cdb_path = root / "assets" / "locale" / "en" / "cards.cdb"
    if not cdb_path.is_file():
        print(f"Error: cards.cdb not found: {cdb_path}", file=sys.stderr)
        sys.exit(1)

    # texts table: id, name (column 1), desc (column 2), str1, ...
    conn = sqlite3.connect(cdb_path)
    conn.row_factory = sqlite3.Row
    cur = conn.execute("SELECT id, name FROM texts")
    rows = cur.fetchall()
    conn.close()

    # Map code (int) -> name; use string keys in JSON for readability
    code_to_name = {str(row["id"]): row["name"] for row in rows}

    if out_path is None:
        # default under project data/
        script_dir = Path(__file__).resolve().parent.parent
        out_path = script_dir / "data" / "card_code_to_name.json"
        if fmt == "csv":
            out_path = script_dir / "data" / "card_code_to_name.csv"
    out_path = out_path.resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)

    if fmt == "json":
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(code_to_name, f, ensure_ascii=False, indent=2)
    else:
        with open(out_path, "w", encoding="utf-8", newline="") as f:
            w = csv.writer(f)
            w.writerow(["code", "name"])
            for code, name in sorted(code_to_name.items(), key=lambda x: int(x[0])):
                w.writerow([code, name])

    print(f"Wrote {len(code_to_name)} cards to {out_path}")


def _run_add_deck_codes_to_list(deck_path: Path, ygo_env_root: Path | None) -> None:
    """Append missing deck card codes to the engine example/code_list.txt."""
    import os

    root = ygo_env_root
    if root is None or not root.is_dir():
        env_root = os.environ.get("YGO_ENV_ROOT")
        root = Path(env_root).resolve() if env_root else None
    if root is None or not root.is_dir():
        yapping_root = Path(__file__).resolve().parent.parent
        root = _default_adapter_root(yapping_root)
    if not root.is_dir():
        print("Error: need --engine-root or YGO_ENV_ROOT; or vendor/yapcore must exist. Legacy alias: --ygo-env.", file=sys.stderr)
        sys.exit(1)
    code_list_file = root / "example" / "code_list.txt"
    script_dir = root / "scripts" / "script"
    if not code_list_file.is_file():
        print(f"Error: code_list.txt not found: {code_list_file}", file=sys.stderr)
        sys.exit(1)
    if not deck_path.is_file():
        print(f"Error: deck not found: {deck_path}", file=sys.stderr)
        sys.exit(1)

    from engine.wrapper import YgoEnvWrapper

    deck_codes = YgoEnvWrapper._deck_codes(deck_path)
    existing: set[int] = set()
    with open(code_list_file, encoding="utf-8", errors="replace") as f:
        for line in f:
            parts = line.strip().split()
            if parts and parts[0].isdigit():
                existing.add(int(parts[0]))
    missing = sorted(deck_codes - existing)
    if not missing:
        print("All deck codes are already in code_list.txt. Nothing to add.")
        return

    with open(code_list_file, "a", encoding="utf-8") as f:
        for code in missing:
            has_script = 1 if (script_dir / f"c{code}.lua").is_file() else 0
            f.write(f"{code} {has_script}\n")
    print(f"Appended {len(missing)} card codes to {code_list_file}")


def _run_combo_run(
    recipe_path: Path,
    deck_override: Path | None,
    seed_override: int | None,
    ygo_env_root: Path | None,
) -> None:
    """Execute a scripted combo recipe JSON against the engine."""
    import os

    yapping_root = Path(__file__).resolve().parent.parent

    # Resolve engine root
    root = ygo_env_root
    if root is None or not root.is_dir():
        root = os.environ.get("YGO_ENV_ROOT")
        root = Path(root).resolve() if root else None
    if root is None or not root.is_dir():
        root = _default_adapter_root(yapping_root)
    if not root.is_dir():
        print("Error: need --engine-root or YGO_ENV_ROOT; or vendor/yapcore must exist. Legacy alias: --ygo-env.", file=sys.stderr)
        sys.exit(1)

    # Load recipe
    from brain.combo import load_recipe, run_combo_from_recipe
    from brain.search import _reset_to_main_phase_idle
    from engine.environment import create_env

    recipe = load_recipe(recipe_path)

    # Resolve deck
    deck_raw = deck_override or recipe.get("deck")
    if not deck_raw:
        print("Error: no deck specified in recipe or --deck.", file=sys.stderr)
        sys.exit(1)
    deck_path = _resolve_deck_path(Path(deck_raw), yapping_root, root)

    # Override seed if provided
    if seed_override is not None:
        recipe["seed"] = seed_override

    # Load cid/name maps
    cid_map: dict = {}
    code_list_file = root / "example" / "code_list.txt"
    if code_list_file.is_file():
        with open(code_list_file, encoding="utf-8", errors="replace") as f:
            for i, line in enumerate(f, start=1):
                parts = line.strip().split()
                if parts and parts[0].isdigit():
                    cid_map[i] = int(parts[0])
    name_map: dict = {}
    json_path = yapping_root / "data" / "card_code_to_name.json"
    if json_path.is_file():
        with open(json_path, encoding="utf-8") as f:
            name_map = json.load(f)

    print(f"Recipe  : {recipe.get('name', recipe_path.stem)}", flush=True)
    print(f"Deck    : {deck_path.name}", flush=True)
    print(f"Seed    : {recipe.get('seed', '(random)')}", flush=True)
    print(f"Steps   : {len(recipe.get('steps', []))}", flush=True)
    print(flush=True)

    env = create_env(deck_path=deck_path, ygo_env_root=root, seed=recipe.get("seed"))
    result = run_combo_from_recipe(recipe, env, cid_map, name_map)

    print(result)
    print(flush=True)

    if result.success:
        board = result.board
        def _resolve(cid: int) -> str:
            code = cid_map.get(cid)
            return name_map.get(str(code), str(code) if code else str(cid))
        hand = [_resolve(c) for c in board.get("hand", [])]
        mzone = [_resolve(c) for c in board.get("field_mzone", [])]
        szone = [_resolve(c) for c in board.get("field_szone", [])]
        grave = [_resolve(c) for c in board.get("grave", [])]
        print("Final board:")
        print(f"  hand ={hand}")
        print(f"  mzone={mzone}")
        print(f"  szone={szone}")
        print(f"  grave={grave}")
    else:
        sys.exit(1)


def _run_combo_record(
    deck: Path,
    out: Path,
    name: str | None,
    seed: int | None,
    ygo_env_root: Path | None,
) -> None:
    """Interactively record a combo and save it as a hybrid sig+label recipe JSON."""
    import os

    yapping_root = Path(__file__).resolve().parent.parent

    root = ygo_env_root
    if root is None or not root.is_dir():
        root = os.environ.get("YGO_ENV_ROOT")
        root = Path(root).resolve() if root else None
    if root is None or not root.is_dir():
        root = _default_adapter_root(yapping_root)
    if not root.is_dir():
        print("Error: need --engine-root or YGO_ENV_ROOT; or vendor/yapcore must exist. Legacy alias: --ygo-env.", file=sys.stderr)
        sys.exit(1)

    deck_path = _resolve_deck_path(deck, yapping_root, root)

    from brain.combo import record_combo
    from brain.search import _reset_to_main_phase_idle
    from engine.environment import create_env

    cid_map: dict = {}
    code_list_file = root / "example" / "code_list.txt"
    if code_list_file.is_file():
        with open(code_list_file, encoding="utf-8", errors="replace") as f:
            for i, line in enumerate(f, start=1):
                parts = line.strip().split()
                if parts and parts[0].isdigit():
                    cid_map[i] = int(parts[0])
    name_map: dict = {}
    json_path = yapping_root / "data" / "card_code_to_name.json"
    if json_path.is_file():
        with open(json_path, encoding="utf-8") as f:
            name_map = json.load(f)

    env = create_env(deck_path=deck_path, ygo_env_root=root, seed=seed)
    actual_seed = env._seed

    print(f"Deck : {deck_path.name}", flush=True)
    print(f"Seed : {actual_seed}", flush=True)
    print("Resetting to Main Phase idle...", flush=True)

    if not _reset_to_main_phase_idle(env, cid_map, name_map):
        print("Error: failed to reach Main Phase idle.", file=sys.stderr)
        sys.exit(1)

    print("Ready. Pick actions to record. Type 'done' or press Enter with no input to finish.")
    steps = record_combo(env, cid_map, name_map)

    if not steps:
        print("No steps recorded — nothing saved.")
        return

    recipe = {
        "name": name or out.stem,
        "deck": str(deck_path.relative_to(yapping_root)) if deck_path.is_relative_to(yapping_root) else str(deck_path),
        "seed": actual_seed,
        "steps": steps,
    }

    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(recipe, f, indent=2, ensure_ascii=False)

    print(f"\nSaved {len(steps)}-step recipe to {out}")


def _run_combo_validate(
    recipe_path: Path,
    deck_override: Path | None,
    seed_override: int | None,
    ygo_env_root: Path | None,
) -> None:
    import os

    yapping_root = Path(__file__).resolve().parent.parent
    root = ygo_env_root
    if root is None or not root.is_dir():
        root = os.environ.get("YGO_ENV_ROOT")
        root = Path(root).resolve() if root else None
    if root is None or not root.is_dir():
        root = _default_adapter_root(yapping_root)
    if not root.is_dir():
        print("Error: need --engine-root or YGO_ENV_ROOT; or vendor/yapcore must exist. Legacy alias: --ygo-env.", file=sys.stderr)
        sys.exit(1)

    from brain.combo import load_recipe, validate_recipe_replay
    from engine.environment import create_env

    recipe = load_recipe(recipe_path)
    deck_raw = deck_override or recipe.get("deck")
    if not deck_raw:
        print("Error: no deck specified in recipe or --deck.", file=sys.stderr)
        sys.exit(1)
    deck_path = _resolve_deck_path(Path(deck_raw), yapping_root, root)
    if seed_override is not None:
        recipe["seed"] = seed_override

    cid_map: dict = {}
    code_list_file = root / "example" / "code_list.txt"
    if code_list_file.is_file():
        with open(code_list_file, encoding="utf-8", errors="replace") as f:
            for i, line in enumerate(f, start=1):
                parts = line.strip().split()
                if parts and parts[0].isdigit():
                    cid_map[i] = int(parts[0])
    name_map: dict = {}
    json_path = yapping_root / "data" / "card_code_to_name.json"
    if json_path.is_file():
        with open(json_path, encoding="utf-8") as f:
            name_map = json.load(f)

    env = create_env(deck_path=deck_path, ygo_env_root=root, seed=recipe.get("seed"))
    validation = validate_recipe_replay(recipe, env, cid_map, name_map)

    print(f"Recipe  : {recipe.get('name', recipe_path.stem)}")
    print(f"Deck    : {deck_path.name}")
    print(f"Seed    : {recipe.get('seed', '(random)')}")
    print(f"Steps   : {len(recipe.get('steps', []))}")
    print(f"Trace   : {len(validation.trace)}")
    print(f"Combo   : {'OK' if validation.result.success else 'FAILED'}")
    print(f"Replay  : {'OK' if validation.replay_ok else f'FAILED ({validation.replay_reason} at step {validation.replay_step})'}")
    if not validation.success:
        if validation.result.error:
            print(f"Error   : {validation.result.error}")
        sys.exit(1)


if __name__ == "__main__":
    main()
