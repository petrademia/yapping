"""
Hand Simulator — raw data from the engine.

Takes a deck, shuffles and draws 5, then lists the first N legal actions.
Use this to see the "raw" interface before building the full combo map.

Usage:
  export YGO_ENV_ROOT=/path/to/yapcore
  cd /path/to/yapcore   # so Lua scripts are found
  python -m cli.hand_simulator --deck /path/to/yapping/data/decks/MyDeck.ydk

  Or from yapping repo with deck path:
  YGO_ENV_ROOT=/path/to/yapcore python -m cli.hand_simulator --deck data/decks/MyDeck.ydk
  (Run from yapcore dir if the engine looks for scripts in cwd.)
"""

from __future__ import annotations

import argparse
import json
import os
import random
import re
import sqlite3
import sys
import time
from pathlib import Path
from typing import Optional
from collections import Counter

from engine.state_delta import summarize_state_delta

_MSG_ID_TO_NAME = {
    0: "none",
    1: "select_idle",
    2: "select_chain",
    3: "select_card",
    4: "select_tribute",
    5: "select_position",
    6: "select_effectyn",
    7: "select_yesno",
    8: "select_battle",
    9: "select_unselect",
    10: "select_option",
    11: "select_place",
    12: "select_sum",
    13: "select_disfield",
    14: "announce_attrib",
    15: "announce_number",
    16: "announce_card",
}


def _default_adapter_root(yapping_root: Path) -> Path:
    primary = yapping_root / "vendor" / "yapcore"
    if primary.is_dir():
        return primary
    compat = yapping_root / "vendor" / "ygopro-adapter"
    if compat.is_dir():
        return compat
    return yapping_root / "vendor" / "ygo-env"


# ---------------------------------------------------------------------------
# Progress helpers
# ---------------------------------------------------------------------------

def _step(label: str) -> float:
    """Print a 'step...' prefix and return the start timestamp."""
    print(f"  {label}...", end="", flush=True)
    return time.perf_counter()


def _done(t0: float, extra: str = "") -> None:
    """Complete the _step line with elapsed time and optional info."""
    elapsed = time.perf_counter() - t0
    note = f"  ({extra})" if extra else ""
    print(f"  done{note}  [{elapsed:.2f}s]")


def _load_code_to_name(yapping_root: Path, ygo_root: Optional[Path]) -> dict[str, str]:
    """Load code -> name from data/card_code_to_name.json or cards.cdb."""
    json_path = yapping_root / "data" / "card_code_to_name.json"
    if json_path.is_file():
        try:
            with open(json_path, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    if ygo_root:
        cdb = ygo_root / "assets" / "locale" / "en" / "cards.cdb"
        if cdb.is_file():
            try:
                conn = sqlite3.connect(cdb)
                conn.row_factory = sqlite3.Row
                cur = conn.execute("SELECT id, name FROM texts")
                out = {str(row["id"]): row["name"] for row in cur.fetchall()}
                conn.close()
                return out
            except Exception:
                pass
    return {}


def _load_card_id_to_code(ygo_root: Optional[Path]) -> dict[int, int]:
    """Load card_id (1-based line index in code_list) -> card code from example/code_list.txt."""
    if not ygo_root:
        return {}
    path = ygo_root / "example" / "code_list.txt"
    if not path.is_file():
        return {}
    out = {}
    with open(path, encoding="utf-8", errors="replace") as f:
        for i, line in enumerate(f, start=1):
            parts = line.strip().split()
            if parts and parts[0].isdigit():
                out[i] = int(parts[0])
    return out


def _hand_to_names(
    hand: list,
    code_to_name: dict[str, str],
    card_id_to_code: Optional[dict[int, int]] = None,
) -> list[str]:
    """Convert hand (card_ids or codes) to list of card names. Unknown -> str(code)."""
    id_to_code = card_id_to_code or {}
    names = []
    for val in hand:
        cid = int(val) if val is not None else 0
        code = id_to_code.get(cid, cid)
        key = str(code)
        name = code_to_name.get(key)
        names.append(name if name is not None else key)
    return names


def _format_hand_with_names(
    hand: list,
    code_to_name: dict[str, str],
    card_id_to_code: Optional[dict[int, int]] = None,
) -> str:
    """Format hand as '[code (name), ...]'. hand may be card_ids (engine) or codes; use card_id_to_code when present."""
    id_to_code = card_id_to_code or {}
    parts = []
    for val in hand:
        cid = int(val) if val is not None else 0
        code = id_to_code.get(cid, cid)  # if not in map, treat as code
        key = str(code)
        name = code_to_name.get(key)
        if name is not None:
            parts.append(f"{code} ({name})")
        else:
            parts.append(str(code))
    return "[" + ", ".join(parts) + "]"


def _load_script_effect_hints(script_path: Path) -> dict[int, str]:
    """
    Best-effort parse of effect-id hints from a card script.
    Maps Stringid(id, N) -> nearest preceding Lua comment text.
    """
    out: dict[int, str] = {}
    if not script_path.is_file():
        return out
    last_comment = ""
    pat = re.compile(r"SetDescription\s*\(\s*aux\.Stringid\s*\(\s*id\s*,\s*(\d+)\s*\)\s*\)")
    try:
        for raw in script_path.read_text(encoding="utf-8", errors="replace").splitlines():
            line = raw.strip()
            if line.startswith("--"):
                c = line[2:].strip()
                if c:
                    last_comment = c
                continue
            m = pat.search(line)
            if m:
                eid = int(m.group(1))
                if last_comment:
                    out[eid] = last_comment
    except Exception:
        return {}
    return out


def _load_code_to_effect_texts(ygo_root: Optional[Path]) -> dict[int, dict[int, str]]:
    """
    Load card effect strings from cards.cdb texts table.
    Returns {code: {effect_index: text}}, where effect_index follows decode labels (1,2,...).
    """
    out: dict[int, dict[int, str]] = {}
    if not ygo_root:
        return out
    cdb = ygo_root / "assets" / "locale" / "en" / "cards.cdb"
    if not cdb.is_file():
        return out
    try:
        conn = sqlite3.connect(cdb)
        cur = conn.execute("PRAGMA table_info(texts)")
        cols = [str(r[1]) for r in cur.fetchall()]
        # Common YGOPro schema uses str1..str16 (or more depending on DB).
        str_cols = []
        for c in cols:
            low = c.lower()
            if low.startswith("str") and low[3:].isdigit():
                str_cols.append((int(low[3:]), c))
        if not str_cols:
            conn.close()
            return out
        str_cols.sort(key=lambda x: x[0])
        sel = "id, " + ", ".join(c for _, c in str_cols)
        cur2 = conn.execute(f"SELECT {sel} FROM texts")
        for row in cur2.fetchall():
            code = int(row[0])
            m: dict[int, str] = {}
            for i, (n, _cname) in enumerate(str_cols, start=1):
                txt = row[i]
                if txt is None:
                    continue
                s = str(txt).strip()
                if s:
                    m[n] = s
            if m:
                out[code] = m
        conn.close()
    except Exception:
        return {}
    return out


def _load_effect_label_overrides(yapping_root: Path) -> dict[int, dict[int, str]]:
    """Load curated card-code/effect-id -> human label overrides."""
    path = yapping_root / "data" / "effect_labels.json"
    out: dict[int, dict[int, str]] = {}
    if not path.is_file():
        return out
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return out
    if not isinstance(data, dict):
        return out
    for raw_code, mapping in data.items():
        try:
            code = int(raw_code)
        except (TypeError, ValueError):
            continue
        if not isinstance(mapping, dict):
            continue
        inner: dict[int, str] = {}
        for raw_eff, text in mapping.items():
            try:
                eff = int(raw_eff)
            except (TypeError, ValueError):
                continue
            s = str(text).strip()
            if s:
                inner[eff] = s
        if inner:
            out[code] = inner
    return out


def _effect_hint_for_action(
    feat: list | None,
    card_id_to_code: dict[int, int],
    ygo_root: Path,
    cache: dict[int, dict[int, str]],
    effect_overrides: dict[int, dict[int, str]] | None = None,
    cdb_effects: dict[int, dict[int, str]] | None = None,
) -> str:
    """Return effect hint text for Activate(... effect N) action from card script comments."""
    if feat is None or len(feat) < 7:
        return ""
    act_id = int(feat[4])
    effect_id = int(feat[6])
    if act_id != 8 or effect_id <= 0:
        return ""
    cid = int(feat[1]) * 256 + int(feat[2])
    code = int(card_id_to_code.get(cid, cid))
    if code <= 0:
        return ""
    if effect_overrides:
        hint = effect_overrides.get(code, {}).get(effect_id, "")
        if hint:
            return hint
    if code not in cache:
        sp = ygo_root / "scripts" / "script" / f"c{code}.lua"
        cache[code] = _load_script_effect_hints(sp)
    hint = cache.get(code, {}).get(effect_id, "")
    if hint:
        return hint
    if cdb_effects:
        return cdb_effects.get(code, {}).get(effect_id, "")
    return ""


def _label_with_effect_hint(
    label: str,
    feat: list | None,
    card_id_to_code: dict[int, int],
    ygo_root: Path,
    cache: dict[int, dict[int, str]],
    effect_overrides: dict[int, dict[int, str]] | None = None,
    cdb_effects: dict[int, dict[int, str]] | None = None,
) -> str:
    """Append script-derived effect hint to label when available."""
    hint = _effect_hint_for_action(
        feat,
        card_id_to_code,
        ygo_root,
        cache,
        effect_overrides=effect_overrides,
        cdb_effects=cdb_effects,
    )
    if not hint:
        return label
    if "—" in label or "--" in label:
        return label
    return f"{label} -- {hint}"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="YAPPING Hand Simulator — draw 5, list first N legal actions (raw engine data)."
    )
    parser.add_argument(
        "--deck",
        type=Path,
        required=True,
        help="Path to .ydk deck file (e.g. data/decks/MyDeck.ydk)",
    )
    parser.add_argument(
        "--num-draw",
        type=int,
        default=5,
        help="Number of cards to treat as hand (default: 5). Engine may fix this.",
    )
    parser.add_argument(
        "--max-actions",
        type=int,
        default=10,
        help="Show at most this many legal actions (default: 10).",
    )
    parser.add_argument(
        "--ygo-env",
        type=Path,
        default=os.environ.get("YGO_ENV_ROOT"),
        help="Root of the engine repo, e.g. vendor/yapcore (default: env YGO_ENV_ROOT).",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=None,
        help="RNG seed for reproducible hand.",
    )
    return parser.parse_args()


def run(
    deck: Path,
    num_draw: int = 5,
    max_actions: int = 10,
    ygo_env_root: Path | None = None,
    seed: int | None = None,
    take_action: int | None = None,
    interactive: bool = False,
    dfs: bool = False,
    activate_trace: bool = False,
    scored_trace: bool = False,
    engine_transcript: bool = False,
    engine_transcript_json: Path | None = None,
    engine_transcript_max_steps: int = 300,
    engine_verbose: bool = False,
    trace_max_steps: int = 200,
    lock_initial_player: bool = False,
    max_depth: int = 6,
    max_nodes: int = 500,
    first_turn: bool = True,
    target_code: int | None = None,
    fixed_hand: list[int] | None = None,
    dfs_json: Path | None = None,
    dfs_json_all: Path | None = None,
    fail_fast_drift: bool = False,
    goal_mzone: str = "",
    goal_szone: str = "",
    goal_grave: str = "",
    goal_banish: str = "",
    goal_hand: str = "",
    goal_hit_bonus: int = 40,
    meaningful_action_bonus: int = 5,
    action_goals_json: Path | None = None,
) -> None:
    """Run the Hand Simulator with the given options (no argparse)."""
    deck_path = Path(deck).resolve()
    if not deck_path.is_file():
        print(f"Deck file not found: {deck_path}", file=sys.stderr)
        sys.exit(1)

    ygo_root = Path(ygo_env_root).resolve() if ygo_env_root else None
    if not ygo_root or not ygo_root.is_dir():
        ygo_root = os.environ.get("YGO_ENV_ROOT")
        ygo_root = Path(ygo_root).resolve() if ygo_root else None
    if not ygo_root or not ygo_root.is_dir():
        print(
            "YGO_ENV_ROOT not set or not a directory. Clone and build yapcore (see docs/ENGINE_SETUP.md), then:\n"
            "  export YGO_ENV_ROOT=/path/to/yapcore\n"
            "  cd $YGO_ENV_ROOT   # so Lua scripts are found\n"
            "  python -m cli.hand_simulator --deck /path/to/data/decks/YourDeck.ydk\n"
            "See docs/ENGINE_SETUP.md",
            file=sys.stderr,
        )
        sys.exit(1)

    script_dir = Path(__file__).resolve().parent
    yapping_root = script_dir.parent
    if str(yapping_root) not in sys.path:
        sys.path.insert(0, str(yapping_root))

    # --- Step 1: imports ---
    t = _step("Importing modules")
    try:
        from engine.environment import create_env
        from engine.actions import action_index_to_label, decode_action_features
        from engine.idle import wait_until_main_phase_idle, complete_until_main_phase_idle
        from engine.state_delta import summarize_state_delta
    except ImportError as e:
        print(f"\nImport error: {e}", file=sys.stderr)
        print("Run from the yapping repo or set PYTHONPATH to the yapping root.", file=sys.stderr)
        sys.exit(1)
    _done(t)

    # --- Step 2: card name database ---
    t = _step("Loading card name database")
    code_to_name = _load_code_to_name(yapping_root, ygo_root)
    _done(t, f"{len(code_to_name):,} cards" if code_to_name else "not found — names will be omitted")

    # --- Step 3: code list (card_id → code) ---
    t = _step("Loading code list")
    card_id_to_code = _load_card_id_to_code(ygo_root)
    _done(t, f"{len(card_id_to_code):,} entries")

    # --- Step 4: create engine ---
    t = _step("Initialising yapcore engine")
    try:
        # UX: when fixed_hand is enabled, we intentionally brute-force a seed
        # that matches the exact desired opening hand. In that mode, the
        # caller-provided `--seed` is ignored.
        if fixed_hand is not None and seed is not None:
            print(
                f"\n[warning] --seed={int(seed)} is ignored because --fixed-hand is enabled; "
                "we will search for an engine seed that produces the exact fixed hand.",
                file=sys.stderr,
            )

        # When targeting a card/hand, we try many seeds so pass None and use reset(seed=...) in the loop
        env_seed = None if (target_code is not None or fixed_hand is not None) else seed
        env = create_env(
            deck_path=deck_path,
            ygo_env_root=ygo_root,
            seed=env_seed,
            engine_verbose=engine_verbose,
        )
    except RuntimeError as e:
        print(f"\n{e}", file=sys.stderr)
        sys.exit(1)
    actual_seed = env._seed
    _done(t, f"seed={actual_seed}" + ("  (pass --seed to reproduce)" if seed is None and target_code is None else ""))

    # --- Step 5: reset / draw opening hand (optionally until hand matches fixed hand / contains target card) ---
    if fixed_hand is not None:
        wanted = [int(c) for c in fixed_hand]
        wanted_counter = Counter(wanted)
        wanted_names = [code_to_name.get(str(c), str(c)) for c in wanted]
        t = _step(f"Drawing until hand exactly matches fixed hand: {', '.join(wanted_names)}")
        # Seed search can be expensive; default cap previously limited exploration.
        # We intentionally do not cap attempts here so that we can always find a
        # reproducible seed when the exact fixed-hand multiset exists.
        attempt = 0
        while True:
            attempt += 1
            # Deterministic, no-repeat-ish scan across seeds.
            # This is much more efficient than random sampling when trying
            # to locate a specific opening hand multiset.
            try_seed = attempt
            obs, hand, legal_actions = env.reset(seed=try_seed)
            hand_codes = [card_id_to_code.get(h, h) for h in hand]
            if Counter(hand_codes) == wanted_counter:
                actual_seed = try_seed
                _done(t, f"seed={actual_seed} (attempt {attempt})")
                break
            if attempt % 5000 == 0:
                print(f"    ... {attempt} attempts", flush=True)
    elif target_code is not None:
        target_name = code_to_name.get(str(target_code), f"code {target_code}")
        t = _step(f"Drawing until hand contains {target_name}")
        max_attempts = 500
        for attempt in range(max_attempts):
            try_seed = random.randint(1, 2**31 - 1)
            obs, hand, legal_actions = env.reset(seed=try_seed)
            hand_codes = [card_id_to_code.get(h, h) for h in hand]
            if target_code in hand_codes:
                actual_seed = try_seed
                _done(t, f"seed={actual_seed} (attempt {attempt + 1})")
                break
            if (attempt + 1) % 50 == 0:
                print(f"    ... {attempt + 1} attempts", flush=True)
        else:
            _done(t, "failed")
            print(f"  Could not draw target card ({target_code}) in {max_attempts} attempts.", file=sys.stderr)
            sys.exit(1)
    else:
        t = _step("Drawing opening hand")
        obs, hand, legal_actions = env.reset(seed=seed)
        _done(t, f"{len(hand)} cards, {len(legal_actions)} legal actions")

    # --- Step 6: wait until Main Phase idle (so we see Summon/Set/Activate menu) ---
    t = _step("Waiting for Main Phase idle")
    if wait_until_main_phase_idle(env, card_id_to_code, code_to_name, verbose=True):
        hand = env.get_hand()
        legal_actions = env.get_legal_actions()
        _done(t, f"{len(legal_actions)} legal actions")
    else:
        _done(t, "unchanged (staying in current state)")

    # --- Results ---
    print()
    hand_display = _format_hand_with_names(hand[:num_draw], code_to_name, card_id_to_code)
    effect_hint_cache: dict[int, dict[int, str]] = {}
    effect_label_overrides = _load_effect_label_overrides(yapping_root)
    cdb_effect_texts = _load_code_to_effect_texts(ygo_root)
    initial_to_play = env.get_to_play() if hasattr(env, "get_to_play") else None

    def _render_legal_actions(actions_now: list[int], limit: int | None = None) -> None:
        show_n = len(actions_now) if limit is None or limit <= 0 else min(limit, len(actions_now))
        for i, idx in enumerate(actions_now[:show_n], 1):
            feat = env.action_features(idx)
            label = decode_action_features(feat, card_id_to_code, code_to_name) if feat else action_index_to_label(idx)
            label = _label_with_effect_hint(
                label, feat, card_id_to_code, ygo_root, effect_hint_cache, effect_overrides=effect_label_overrides, cdb_effects=cdb_effect_texts
            )
            msg_id = int(feat[3]) if feat is not None and len(feat) >= 4 else None
            act_id = int(feat[4]) if feat is not None and len(feat) >= 5 else None
            finish = int(feat[5]) if feat is not None and len(feat) >= 6 else None
            phase_id = int(feat[7]) if feat is not None and len(feat) >= 8 else None
            print(f"  {i}. [{idx}] msg={msg_id} act={act_id} finish={finish} phase={phase_id}  {label}")
        if len(actions_now) > show_n:
            print(f"  ... and {len(actions_now) - show_n} more.")

    def _print_state_summary() -> None:
        hand_now = env.get_hand()
        hand_display_now = _format_hand_with_names(hand_now[:num_draw], code_to_name, card_id_to_code)
        to_play_now = env.get_to_play() if hasattr(env, "get_to_play") else None
        turn_now = env.get_turn_count() if hasattr(env, "get_turn_count") else None
        phase_now = env.get_current_phase() if hasattr(env, "get_current_phase") else None
        print(f"To play: {to_play_now}  Turn: {turn_now}  Phase: {phase_now}")
        print(f"Hand: {hand_display_now}")
        if hasattr(env, "get_state_snapshot"):
            obs_now = env.get_obs() if hasattr(env, "get_obs") else None
            st = env.get_state_snapshot(obs_now) or {}
            if st:
                print(f"MZONE : {_format_hand_with_names(st.get('field_mzone', []), code_to_name, card_id_to_code)}")
                print(f"SZONE : {_format_hand_with_names(st.get('field_szone', []), code_to_name, card_id_to_code)}")
                print(f"GY    : {_format_hand_with_names(st.get('grave', []), code_to_name, card_id_to_code)}")
                print(f"Banish: {_format_hand_with_names(st.get('banish', []), code_to_name, card_id_to_code)}")

    print("--- YAPPING Hand Simulator (raw data) ---")
    print(f"Deck: {deck_path}")
    print(f"Hand (first {num_draw}): {hand_display}")
    if not code_to_name and hand and any(h != 0 for h in hand):
        print("(Run: python -m cli.cli export-card-names  for card code -> name lookup)")
    print()

    n = min(max_actions, len(legal_actions))
    print(f"First {n} legal actions (of {len(legal_actions)} total):")
    _render_legal_actions(legal_actions, limit=max_actions)
    print()

    # Optional: take one action and show next state (proceed forward)
    if take_action is not None and legal_actions:
        # take_action = index into legal_actions (0 = first action)
        idx_in_list = max(0, min(take_action, len(legal_actions) - 1))
        action_index = legal_actions[idx_in_list]
        feat = env.action_features(action_index)
        action_label = decode_action_features(feat, card_id_to_code, code_to_name) if feat else action_index_to_label(action_index)
        action_label = _label_with_effect_hint(
            action_label, feat, card_id_to_code, ygo_root, effect_hint_cache, effect_overrides=effect_label_overrides, cdb_effects=cdb_effect_texts
        )
        print(f"--- Taking action {action_index}: {action_label} ---")
        obs, term, trunc, _ = env.step(action_index)
        if term or trunc:
            print("  (game ended)")
        else:
            if not complete_until_main_phase_idle(env, card_id_to_code, code_to_name):
                print("  (could not complete sub-steps)")
            hand = env.get_hand()
            legal_actions = env.get_legal_actions()
            hand_display = _format_hand_with_names(hand[:num_draw], code_to_name, card_id_to_code)
            print(f"Hand now: {hand_display}")
            print(f"Legal actions: {len(legal_actions)}")
            for i, idx in enumerate(legal_actions[:max_actions], 1):
                feat = env.action_features(idx)
                label = decode_action_features(feat, card_id_to_code, code_to_name) if feat else action_index_to_label(idx)
                label = _label_with_effect_hint(
                    label, feat, card_id_to_code, ygo_root, effect_hint_cache, effect_overrides=effect_label_overrides, cdb_effects=cdb_effect_texts
                )
                print(f"  {i}. [{idx}] {label}")
            if len(legal_actions) > max_actions:
                print(f"  ... and {len(legal_actions) - max_actions} more.")
        print()

    if interactive:
        print("--- Interactive prompt loop ---")
        print("Commands: number = choose displayed action, raw <id> = choose raw engine action, ls = relist, state = show state, q = quit")
        step_no = 1
        while True:
            legal_actions = env.get_legal_actions()
            if not legal_actions:
                print("No legal actions left.")
                break
            print()
            print(f"Prompt step {step_no}")
            _print_state_summary()
            print(f"Legal actions ({len(legal_actions)} total):")
            _render_legal_actions(legal_actions)

            to_play_now = env.get_to_play() if hasattr(env, "get_to_play") else None
            if lock_initial_player and initial_to_play in (0, 1) and to_play_now in (0, 1) and to_play_now != initial_to_play:
                auto_idx = None
                for idx in legal_actions:
                    feat = env.action_features(idx)
                    msg_id = int(feat[3]) if feat is not None and len(feat) >= 4 else None
                    act_id = int(feat[4]) if feat is not None and len(feat) >= 5 else None
                    finish = int(feat[5]) if feat is not None and len(feat) >= 6 else None
                    if act_id == 9:
                        auto_idx = idx
                        break
                    if msg_id in (6, 7) and act_id == 9:
                        auto_idx = idx
                        break
                    if finish == 1:
                        auto_idx = idx
                        break
                if auto_idx is not None:
                    feat = env.action_features(auto_idx)
                    auto_label = decode_action_features(feat, card_id_to_code, code_to_name) if feat else action_index_to_label(auto_idx)
                    auto_label = _label_with_effect_hint(
                        auto_label, feat, card_id_to_code, ygo_root, effect_hint_cache, effect_overrides=effect_label_overrides, cdb_effects=cdb_effect_texts
                    )
                    print(f"[auto-pass opponent] Stepping [{auto_idx}] {auto_label}")
                    before_manual = env.get_state_snapshot(env.get_obs()) if hasattr(env, "get_state_snapshot") else None
                    _obs, term, trunc, _ = env.step(auto_idx)
                    if hasattr(env, "get_state_snapshot"):
                        after_manual = env.get_state_snapshot(env.get_obs()) or {}
                        delta_manual = summarize_state_delta(before_manual, after_manual)
                        moved = delta_manual.get("moved") or []
                        tags = delta_manual.get("derived_tags") or []
                        if moved:
                            print("State delta:")
                            for row in moved:
                                print(f"  {row['card']}: {row['from']} -> {row['to']}")
                        if tags:
                            print("Derived tags:", ", ".join(tags))
                    step_no += 1
                    if term or trunc:
                        print("Game ended.")
                        break
                    continue

            raw = input("> ").strip()

            if raw.lower() in {"q", "quit", "exit"}:
                break
            if raw.lower() in {"ls", "l", "list", "state", "s"}:
                continue

            chosen_idx: int | None = None
            if raw.lower().startswith("raw "):
                try:
                    chosen_idx = int(raw.split(None, 1)[1].strip())
                except Exception:
                    print("Invalid raw action id.")
                    continue
                if chosen_idx not in legal_actions:
                    print(f"Action id {chosen_idx} is not in the current legal action list.")
                    continue
            else:
                try:
                    selected = int(raw)
                except ValueError:
                    print("Enter a displayed action number, 'raw <id>', 'ls', 'state', or 'q'.")
                    continue
                if selected < 1 or selected > len(legal_actions):
                    print(f"Choose a number from 1 to {len(legal_actions)}.")
                    continue
                chosen_idx = legal_actions[selected - 1]

            feat = env.action_features(chosen_idx)
            chosen_label = decode_action_features(feat, card_id_to_code, code_to_name) if feat else action_index_to_label(chosen_idx)
            chosen_label = _label_with_effect_hint(
                chosen_label, feat, card_id_to_code, ygo_root, effect_hint_cache, effect_overrides=effect_label_overrides, cdb_effects=cdb_effect_texts
            )
            print(f"Stepping [{chosen_idx}] {chosen_label}")
            before_manual = None
            if hasattr(env, "get_state_snapshot"):
                before_manual = env.get_state_snapshot(env.get_obs()) or {}
            _obs, term, trunc, _ = env.step(chosen_idx)
            if hasattr(env, "get_state_snapshot"):
                after_manual = env.get_state_snapshot(env.get_obs()) or {}
                delta_manual = summarize_state_delta(before_manual, after_manual)
                moved = delta_manual.get("moved") or []
                tags = delta_manual.get("derived_tags") or []
                if moved:
                    print("State delta:")
                    for row in moved:
                        print(f"  {row['card']}: {row['from']} -> {row['to']}")
                if tags:
                    print("Derived tags:", ", ".join(tags))
            step_no += 1
            if term or trunc:
                print("Game ended.")
                break
        print()

    action_goal_cfg = None
    if action_goals_json:
        cfg_path = Path(action_goals_json).resolve()
        action_goal_cfg = json.loads(cfg_path.read_text(encoding="utf-8"))

    # Optional: run one linear activate-first trace (no DFS), record every prompt node/state.
    if engine_transcript:
        print("--- Engine Transcript (no DFS) ---")
        nodes: list[dict] = []
        initial_to_play = env.get_to_play() if hasattr(env, "get_to_play") else None
        initial_turn = env.get_turn_count() if hasattr(env, "get_turn_count") else None

        def _state_named_tx() -> dict:
            obs_now = env.get_obs() if hasattr(env, "get_obs") else None
            st = env.get_state_snapshot(obs_now) if hasattr(env, "get_state_snapshot") else {}
            st = st or {}
            to_play = env.get_to_play() if hasattr(env, "get_to_play") else None

            def _card_obj(cid: int) -> dict:
                code = card_id_to_code.get(cid, cid)
                return {"card_id": cid, "code": int(code), "name": code_to_name.get(str(code), str(code))}

            def _zone_from_ids(ids: list[int]) -> list[dict]:
                return [_card_obj(int(cid)) for cid in (ids or [])]

            primary_rel = {
                "hand": _zone_from_ids(st.get("hand", [])),
                "mzone": _zone_from_ids(st.get("field_mzone", [])),
                "szone": _zone_from_ids(st.get("field_szone", [])),
                "grave": _zone_from_ids(st.get("grave", [])),
                "banish": _zone_from_ids(st.get("banish", [])),
            }

            by_controller: dict[str, dict] = {"0": {"hand": [], "mzone": [], "szone": [], "grave": [], "banish": []},
                                              "1": {"hand": [], "mzone": [], "szone": [], "grave": [], "banish": []}}
            by_absolute: dict[str, dict] = {"0": {"hand": [], "mzone": [], "szone": [], "grave": [], "banish": []},
                                            "1": {"hand": [], "mzone": [], "szone": [], "grave": [], "banish": []}}
            try:
                cards = None
                if obs_now is not None and hasattr(obs_now, "get"):
                    cards = obs_now.get("obs:cards_")
                    if cards is None:
                        cards = obs_now.get("cards_")
                    if cards is None:
                        cards = obs_now.get("cards")
                if cards is not None:
                    import numpy as _np
                    arr = _np.asarray(cards, dtype=_np.uint8)
                    if arr.ndim == 3:
                        arr = arr[0]
                    if arr.ndim >= 2 and arr.shape[1] >= 5:
                        for row in range(arr.shape[0]):
                            ctrl = int(arr[row, 4])
                            if ctrl not in (0, 1):
                                continue
                            cid = int(arr[row, 0]) * 256 + int(arr[row, 1])
                            if cid <= 0:
                                continue
                            loc = int(arr[row, 2])
                            zone = None
                            if loc == 2:
                                zone = "hand"
                            elif loc == 3:
                                zone = "mzone"
                            elif loc == 4:
                                zone = "szone"
                            elif loc in (5, 16):
                                zone = "grave"
                            elif loc == 6:
                                zone = "banish"
                            if zone is not None:
                                by_controller[str(ctrl)][zone].append(_card_obj(cid))
                                if to_play in (0, 1):
                                    abs_player = int(to_play) if ctrl == 0 else (1 - int(to_play))
                                    by_absolute[str(abs_player)][zone].append(_card_obj(cid))
            except Exception:
                pass

            primary = by_absolute["0"] if to_play in (0, 1) else primary_rel
            return {
                "to_play": int(to_play) if to_play in (0, 1) else None,
                "turn_count": int(env.get_turn_count()) if hasattr(env, "get_turn_count") and env.get_turn_count() is not None else None,
                "phase": env.get_current_phase() if hasattr(env, "get_current_phase") else None,
                "primary": primary,
                "primary_rel": primary_rel,
                "by_controller": by_controller,
                "by_absolute": by_absolute,
            }

        def _encode_opt(idx: int) -> dict:
            feat = env.action_features(idx)
            label = decode_action_features(feat, card_id_to_code, code_to_name) if feat else action_index_to_label(idx)
            msg_id = int(feat[3]) if feat is not None and len(feat) >= 4 else None
            act_id = int(feat[4]) if feat is not None and len(feat) >= 5 else None
            finish_id = int(feat[5]) if feat is not None and len(feat) >= 6 else None
            phase_id = int(feat[7]) if feat is not None and len(feat) >= 8 else None
            cid = (int(feat[0]) * 256 + int(feat[1])) if feat is not None and len(feat) >= 2 else None
            code = card_id_to_code.get(int(cid), int(cid)) if cid is not None else None
            return {
                "action_index": int(idx),
                "label": label,
                "msg_id": msg_id,
                "act_id": act_id,
                "finish": finish_id,
                "phase_id": phase_id,
                "feature_card_id": int(cid) if cid is not None else None,
                "feature_card_code": int(code) if code is not None else None,
                "feature_card_name": code_to_name.get(str(code), str(code)) if code is not None else None,
                "raw": [int(x) for x in feat] if feat is not None else [],
            }

        def _pick_action_tx(actions: list[int]) -> int | None:
            if not actions:
                return None
            rows = []
            for idx in actions:
                feat = env.action_features(idx)
                msg = int(feat[3]) if feat is not None and len(feat) >= 4 else 0
                act = int(feat[4]) if feat is not None and len(feat) >= 5 else -1
                finish = int(feat[5]) if feat is not None and len(feat) >= 6 else 0
                phase = int(feat[7]) if feat is not None and len(feat) >= 8 else 0
                rows.append((idx, msg, act, finish, phase))
            to_play_now = env.get_to_play() if hasattr(env, "get_to_play") else None
            phase_now = env.get_current_phase() if hasattr(env, "get_current_phase") else None

            def _passive_choice() -> int | None:
                for idx, _msg, act, _finish, _phase in rows:
                    if act == 9:
                        return idx
                for idx, msg, act, _finish, _phase in rows:
                    if msg in (6, 7) and act == 9:
                        return idx
                for idx, _msg, _act, finish, _phase in rows:
                    if finish == 1:
                        return idx
                return None

            if lock_initial_player and initial_to_play in (0, 1) and to_play_now in (0, 1) and to_play_now != initial_to_play:
                p = _passive_choice()
                if p is not None:
                    return p

            if first_turn and to_play_now == initial_to_play and phase_now in ("end", "end_phase"):
                p = _passive_choice()
                if p is not None:
                    return p

            msg_now = rows[0][1]
            if msg_now in (2, 6, 7):
                if msg_now == 2:
                    for idx, _msg, act, _finish, _phase in rows:
                        if act != 9:
                            return idx
                else:
                    for idx, _msg, act, _finish, _phase in rows:
                        if act != 9:
                            return idx
                for idx, _msg, act, _finish, _phase in rows:
                    if act == 9:
                        return idx

            for want in (8, 3, 4, 1, 5, 2, 6, 7):
                for idx, _msg, act, _finish, _phase in rows:
                    if act == want:
                        return idx
            for idx, _msg, act, _finish, phase in rows:
                if act == 9 and phase == 3:
                    return idx
            for idx, _msg, act, _finish, _phase in rows:
                if act == 9:
                    return idx
            return rows[0][0]

        ended = False
        for step in range(1, max(1, engine_transcript_max_steps) + 1):
            turn_now = env.get_turn_count() if hasattr(env, "get_turn_count") else None
            if initial_turn is not None and turn_now is not None and int(turn_now) != int(initial_turn):
                break
            legal = env.get_legal_actions()
            if not legal:
                break
            before = _state_named_tx()
            opts = [_encode_opt(i) for i in legal]
            msg_id = next((o.get("msg_id") for o in opts if o.get("msg_id") is not None), None)
            prompt_key = f"tp={before.get('to_play')}|tc={before.get('turn_count')}|ph={opts[0].get('phase_id') if opts else None}|msg={msg_id}"
            chosen_idx = _pick_action_tx(legal)
            if chosen_idx is None:
                break
            chosen = _encode_opt(chosen_idx)
            _obs, term, trunc, _ = env.step(chosen_idx)
            after = _state_named_tx()
            delta = summarize_state_delta(before, after)
            nodes.append(
                {
                    "step": int(step),
                    "prompt_key": prompt_key,
                    "before": before,
                    "legal_options": opts,
                    "chosen": chosen,
                    "after": after,
                    "state_delta": delta,
                }
            )
            print(
                f"  {step:>3}. [p={before.get('to_play')} t={before.get('turn_count')} msg={chosen.get('msg_id')} act={chosen.get('act_id')} phase={before.get('phase')}] {chosen.get('label')}"
            )
            if term or trunc:
                ended = True
                break

        out = Path(engine_transcript_json or "rep_engine_transcript.json").resolve()
        out.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "mode": "engine_transcript",
            "deck": str(deck_path),
            "seed": int(actual_seed),
            "initial_state": nodes[0]["before"] if nodes else _state_named_tx(),
            "nodes": nodes,
            "ended": bool(ended),
        }
        out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"  Transcript steps: {len(nodes)}" + (" (ended)" if ended else ""))
        print(f"  JSON transcript: {out}")
        print()

    # Optional: run one linear activate-first trace (no DFS), record every prompt node/state.
    if activate_trace:
        print("--- Activate-Trace from current state (no DFS) ---")
        trace_nodes: list[dict] = []
        initial_to_play = env.get_to_play() if hasattr(env, "get_to_play") else None
        initial_turn = env.get_turn_count() if hasattr(env, "get_turn_count") else None

        def _state_named() -> dict:
            obs_now = env.get_obs() if hasattr(env, "get_obs") else None
            st = env.get_state_snapshot(obs_now) if hasattr(env, "get_state_snapshot") else {}
            st = st or {}
            to_play = env.get_to_play() if hasattr(env, "get_to_play") else None

            def _card_obj(cid: int) -> dict:
                code = card_id_to_code.get(cid, cid)
                return {"card_id": cid, "code": int(code), "name": code_to_name.get(str(code), str(code))}

            def _zone_from_ids(ids: list[int]) -> list[dict]:
                out: list[dict] = []
                for cid in ids or []:
                    out.append(_card_obj(int(cid)))
                return out

            # Relative single-perspective view (controller==0 in current obs perspective).
            primary_rel = {
                "hand": _zone_from_ids(st.get("hand", [])),
                "mzone": _zone_from_ids(st.get("field_mzone", [])),
                "szone": _zone_from_ids(st.get("field_szone", [])),
                "grave": _zone_from_ids(st.get("grave", [])),
                "banish": _zone_from_ids(st.get("banish", [])),
            }

            # Debug: extract both raw controllers from obs:cards_ so we can detect perspective flips.
            by_controller: dict[str, dict] = {"0": {"hand": [], "mzone": [], "szone": [], "grave": [], "banish": []},
                                              "1": {"hand": [], "mzone": [], "szone": [], "grave": [], "banish": []}}
            by_absolute: dict[str, dict] = {"0": {"hand": [], "mzone": [], "szone": [], "grave": [], "banish": []},
                                            "1": {"hand": [], "mzone": [], "szone": [], "grave": [], "banish": []}}
            try:
                cards = None
                if obs_now is not None and hasattr(obs_now, "get"):
                    cards = obs_now.get("obs:cards_")
                    if cards is None:
                        cards = obs_now.get("cards_")
                    if cards is None:
                        cards = obs_now.get("cards")
                if cards is not None:
                    import numpy as _np
                    arr = _np.asarray(cards, dtype=_np.uint8)
                    if arr.ndim == 3:
                        arr = arr[0]
                    if arr.ndim >= 2 and arr.shape[1] >= 5:
                        for row in range(arr.shape[0]):
                            ctrl = int(arr[row, 4])
                            if ctrl not in (0, 1):
                                continue
                            cid = int(arr[row, 0]) * 256 + int(arr[row, 1])
                            if cid <= 0:
                                continue
                            loc = int(arr[row, 2])
                            zone = None
                            if loc == 2:
                                zone = "hand"
                            elif loc == 3:
                                zone = "mzone"
                            elif loc == 4:
                                zone = "szone"
                            elif loc in (5, 16):
                                zone = "grave"
                            elif loc == 6:
                                zone = "banish"
                            if zone is not None:
                                by_controller[str(ctrl)][zone].append(_card_obj(cid))
                                if to_play in (0, 1):
                                    abs_player = int(to_play) if ctrl == 0 else (1 - int(to_play))
                                    by_absolute[str(abs_player)][zone].append(_card_obj(cid))
            except Exception:
                pass

            # Stable primary: absolute player 0 when to_play is known; else fallback relative.
            primary = by_absolute["0"] if to_play in (0, 1) else primary_rel
            return {
                "to_play": int(to_play) if to_play in (0, 1) else None,
                "turn_count": int(env.get_turn_count()) if hasattr(env, "get_turn_count") and env.get_turn_count() is not None else None,
                "primary": primary,
                "primary_rel": primary_rel,
                "by_controller": by_controller,
                "by_absolute": by_absolute,
            }

        def _pick_action(actions: list[int]) -> int | None:
            if not actions:
                return None
            rows = []
            for idx in actions:
                feat = env.action_features(idx)
                label = decode_action_features(feat, card_id_to_code, code_to_name) if feat else action_index_to_label(idx)
                label = _label_with_effect_hint(
                    label, feat, card_id_to_code, ygo_root, effect_hint_cache, effect_overrides=effect_label_overrides, cdb_effects=cdb_effect_texts
                )
                msg = int(feat[3]) if feat is not None and len(feat) >= 4 else 0
                act = int(feat[4]) if feat is not None and len(feat) >= 5 else -1
                finish = int(feat[5]) if feat is not None and len(feat) >= 6 else 0
                phase = int(feat[7]) if feat is not None and len(feat) >= 8 else 0
                rows.append((idx, feat, label, msg, act, finish, phase))
            to_play_now = env.get_to_play() if hasattr(env, "get_to_play") else None
            phase_now = env.get_current_phase() if hasattr(env, "get_current_phase") else None

            def _passive_choice() -> int | None:
                # Prefer non-committal responses when we're not the initial player.
                # Cancel/Pass action is act_id=9 across prompts.
                for idx, _feat, _label, _msg, act, _finish, _phase in rows:
                    if act == 9:
                        return idx
                # For yes/no prompts, No/Cancel is act_id=9 in this wrapper.
                for idx, _feat, _label, msg, act, _finish, _phase in rows:
                    if msg in (6, 7) and act == 9:
                        return idx
                # Multi-select style finish.
                for idx, _feat, _label, _msg, _act, finish, _phase in rows:
                    if finish == 1:
                        return idx
                return None

            if lock_initial_player and initial_to_play in (0, 1) and to_play_now in (0, 1) and to_play_now != initial_to_play:
                p = _passive_choice()
                if p is not None:
                    return p

            # If we are back to our turn and already in End Phase, prefer to pass quickly.
            if first_turn and to_play_now == initial_to_play and phase_now in ("end", "end_phase"):
                p = _passive_choice()
                if p is not None:
                    return p

            # Main idle: allow explicit phase transition to End when no activation picked.
            # In idle menu, act_id=9 with phase_id=3 means move to End Phase.
            idle_rows = [r for r in rows if r[3] == 1]

            # Optional prompts: prefer activate/yes, keep pass/no as fallback.
            msg = rows[0][3]
            if msg in (2, 6, 7):
                if msg == 2:  # select_chain: prefer non-cancel chain
                    for idx, _feat, _label, _msg, act, _finish, _phase in rows:
                        if act != 9:
                            return idx
                else:  # select_effectyn / select_yesno: prefer affirmative, not cancel/no
                    for idx, _feat, _label, _msg, act, _finish, _phase in rows:
                        if act != 9:
                            return idx
                for idx, _feat, _label, _msg, act, _finish, _phase in rows:
                    if act == 9:
                        return idx

            # Main/other prompts: greedy "activate everything".
            # ActionAct IDs: Activate(8) > SpSummon(3) > Summon(4) > Set(1) > MSet(5) > Repo(2) > Attack(6/7)
            for want in (8, 3, 4, 1, 5, 2, 6, 7):
                for idx, _feat, _label, _msg, act, _finish, _phase in rows:
                    if act == want:
                        return idx
            if idle_rows:
                for idx, _feat, _label, _msg, act, _finish, phase in idle_rows:
                    if act == 9 and phase == 3:
                        return idx
            for idx, _feat, _label, _msg, act, _finish, _phase in rows:
                if act == 9:
                    return idx
            return rows[0][0]

        ended = False
        for step in range(1, max(1, trace_max_steps) + 1):
            turn_now = env.get_turn_count() if hasattr(env, "get_turn_count") else None
            if initial_turn is not None and turn_now is not None and int(turn_now) != int(initial_turn):
                break
            actions_now = env.get_legal_actions()
            idx = _pick_action(actions_now)
            if idx is None:
                break
            feat = env.action_features(idx)
            label = decode_action_features(feat, card_id_to_code, code_to_name) if feat else action_index_to_label(idx)
            label = _label_with_effect_hint(
                label, feat, card_id_to_code, ygo_root, effect_hint_cache, effect_overrides=effect_label_overrides, cdb_effects=cdb_effect_texts
            )
            msg_id = int(feat[3]) if feat is not None and len(feat) >= 4 else None
            act_id = int(feat[4]) if feat is not None and len(feat) >= 5 else None
            finish_id = int(feat[5]) if feat is not None and len(feat) >= 6 else None
            phase_id = int(feat[7]) if feat is not None and len(feat) >= 8 else None
            before = _state_named()
            p_now = before.get("to_play")
            t_now = before.get("turn_count")
            current_phase = env.get_current_phase() if hasattr(env, "get_current_phase") else None
            msg_name = _MSG_ID_TO_NAME.get(int(msg_id), f"msg_{msg_id}") if msg_id is not None else "unknown"
            obs, term, trunc, _ = env.step(idx)
            after = _state_named()
            trace_nodes.append(
                {
                    "step": step,
                    "action_index": int(idx),
                    "label": label,
                    "action_feature_ids": {
                        "msg_id": msg_id,
                        "act_id": act_id,
                        "finish": finish_id,
                        "phase_id": phase_id,
                        "raw": [int(x) for x in feat] if feat is not None else [],
                    },
                    "timing": {
                        "current_phase": current_phase,
                        "prompt_msg": msg_name,
                        "is_chain_window": bool(msg_id == 2),
                        "is_open_game_state": bool(msg_id == 1),
                    },
                    "before": before,
                    "after": after,
                }
            )
            print(f"  {step:>3}. [p={p_now} t={t_now} a={idx} {msg_name} phase={current_phase}] {label}")
            if term or trunc:
                ended = True
                break

        print(f"  Trace steps: {len(trace_nodes)}" + (" (ended)" if ended else ""))
        if dfs_json:
            payload = {
                "mode": "activate_trace",
                "deck": str(deck_path),
                "seed": int(actual_seed),
                "initial_state": trace_nodes[0]["before"] if trace_nodes else _state_named(),
                "nodes": trace_nodes,
            }
            out = Path(dfs_json).resolve()
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            print(f"  JSON trace: {out}")
        print()

    if scored_trace:
        from brain.search import _action_sig, _find_action_index_by_sig_or_label, _prompt_key, _step_hash

        print("--- Scored-Trace from current state (no DFS) ---")
        trace_nodes: list[dict] = []
        trace_rows: list[tuple[str, Optional[tuple[int, ...]], str, str, str]] = []
        history_labels: list[str] = []
        initial_to_play = env.get_to_play() if hasattr(env, "get_to_play") else None
        initial_turn = env.get_turn_count() if hasattr(env, "get_turn_count") else None
        delta_tag_weights: dict[str, int] = {
            "develops_monster": 12,
            "develops_spell_trap": 10,
            "sends_to_grave": 8,
            "adds_to_hand": 10,
            "banishes": 4,
            "commits_from_hand": 6,
            "discards_or_sends_from_hand": 4,
            "trades_board_for_grave": 2,
        }

        def _state_named_scored() -> dict:
            obs_now = env.get_obs() if hasattr(env, "get_obs") else None
            st = env.get_state_snapshot(obs_now) if hasattr(env, "get_state_snapshot") else {}
            st = st or {}
            to_play = env.get_to_play() if hasattr(env, "get_to_play") else None

            def _card_obj(cid: int) -> dict:
                code = card_id_to_code.get(cid, cid)
                return {"card_id": cid, "code": int(code), "name": code_to_name.get(str(code), str(code))}

            def _zone_from_ids(ids: list[int]) -> list[dict]:
                return [_card_obj(int(cid)) for cid in (ids or [])]

            primary_rel = {
                "hand": _zone_from_ids(st.get("hand", [])),
                "mzone": _zone_from_ids(st.get("field_mzone", [])),
                "szone": _zone_from_ids(st.get("field_szone", [])),
                "grave": _zone_from_ids(st.get("grave", [])),
                "banish": _zone_from_ids(st.get("banish", [])),
            }
            by_absolute: dict[str, dict] = {
                "0": {"hand": [], "mzone": [], "szone": [], "grave": [], "banish": []},
                "1": {"hand": [], "mzone": [], "szone": [], "grave": [], "banish": []},
            }
            try:
                cards = None
                if obs_now is not None and hasattr(obs_now, "get"):
                    cards = obs_now.get("obs:cards_")
                    if cards is None:
                        cards = obs_now.get("cards_")
                    if cards is None:
                        cards = obs_now.get("cards")
                if cards is not None:
                    import numpy as _np

                    arr = _np.asarray(cards, dtype=_np.uint8)
                    if arr.ndim == 3:
                        arr = arr[0]
                    if arr.ndim >= 2 and arr.shape[1] >= 5:
                        for row in range(arr.shape[0]):
                            ctrl = int(arr[row, 4])
                            if ctrl not in (0, 1):
                                continue
                            cid = int(arr[row, 0]) * 256 + int(arr[row, 1])
                            if cid <= 0:
                                continue
                            loc = int(arr[row, 2])
                            zone = None
                            if loc == 2:
                                zone = "hand"
                            elif loc == 3:
                                zone = "mzone"
                            elif loc == 4:
                                zone = "szone"
                            elif loc in (5, 16):
                                zone = "grave"
                            elif loc == 6:
                                zone = "banish"
                            if zone is None:
                                continue
                            if to_play in (0, 1):
                                abs_player = int(to_play) if ctrl == 0 else (1 - int(to_play))
                            else:
                                abs_player = ctrl
                            by_absolute[str(abs_player)][zone].append(_card_obj(cid))
            except Exception:
                pass

            primary = by_absolute["0"] if to_play in (0, 1) else primary_rel
            return {
                "to_play": int(to_play) if to_play in (0, 1) else None,
                "turn_count": int(env.get_turn_count()) if hasattr(env, "get_turn_count") and env.get_turn_count() is not None else None,
                "primary": primary,
                "primary_rel": primary_rel,
                "by_absolute": by_absolute,
            }

        def _action_goal_score_labels(labels: list[str]) -> tuple[int, int, int]:
            cfg = action_goal_cfg or {}
            score = 0
            contains_hits = 0
            order_hits = 0
            labels = list(labels or [])
            for rule in (cfg.get("rules") or []):
                if not isinstance(rule, dict):
                    continue
                token = str(rule.get("contains", "")).strip()
                if not token:
                    continue
                bonus = int(rule.get("bonus", 0))
                max_count = int(rule.get("max_count", 1))
                cnt = sum(1 for lbl in labels if token in (lbl or ""))
                if cnt <= 0:
                    continue
                used = min(cnt, max_count if max_count > 0 else cnt)
                score += int(used) * bonus
                contains_hits += int(used)
            for rule in (cfg.get("order_bonus") or []):
                if not isinstance(rule, dict):
                    continue
                seq = [str(x).strip() for x in (rule.get("sequence") or []) if str(x).strip()]
                if not seq:
                    continue
                pos = 0
                ok = True
                for token in seq:
                    found = False
                    while pos < len(labels):
                        if token in (labels[pos] or ""):
                            found = True
                            pos += 1
                            break
                        pos += 1
                    if not found:
                        ok = False
                        break
                if ok:
                    score += int(rule.get("bonus", 0))
                    order_hits += 1
            return int(score), int(contains_hits), int(order_hits)

        def _prompt_bias_bonus(
            current_msg: int,
            candidate_label: str,
            candidate_code: int | None,
            candidate_act_id: int | None,
            current_state: dict,
            prior_labels: list[str],
        ) -> tuple[int, list[str]]:
            score = 0
            reasons: list[str] = []
            cfg = action_goal_cfg or {}
            rules = cfg.get("prompt_bias_rules") or []
            history = list(prior_labels or [])
            history_joined = " | ".join(history[-16:])
            primary = current_state.get("primary", {}) if isinstance(current_state, dict) else {}

            def _zone_codes(zone_name: str) -> set[int]:
                vals = primary.get(zone_name, []) or []
                out: set[int] = set()
                for row in vals:
                    if isinstance(row, dict):
                        try:
                            out.add(int(row.get("code")))
                        except (TypeError, ValueError):
                            continue
                return out

            hand_codes = _zone_codes("hand")
            mzone_codes = _zone_codes("mzone")
            grave_codes = _zone_codes("grave")
            banish_codes = _zone_codes("banish")

            for i, rule in enumerate(rules):
                if not isinstance(rule, dict):
                    continue

                when_msg_id = rule.get("when_msg_id")
                if when_msg_id is not None and int(when_msg_id) != int(current_msg):
                    continue

                when_phase_in = rule.get("when_phase_in") or []
                if isinstance(when_phase_in, str):
                    when_phase_in = [when_phase_in]
                if when_phase_in:
                    cur_phase = str(env.get_current_phase() if hasattr(env, "get_current_phase") else "").strip().lower()
                    phases = {str(x).strip().lower() for x in when_phase_in if str(x).strip()}
                    if cur_phase not in phases:
                        continue

                when_label_contains = str(rule.get("when_label_contains", "")).strip()
                if when_label_contains and when_label_contains not in history_joined and when_label_contains not in candidate_label:
                    continue

                when_history_contains = rule.get("when_history_contains") or []
                if isinstance(when_history_contains, str):
                    when_history_contains = [when_history_contains]
                ok_history = True
                for token in when_history_contains:
                    tok = str(token).strip()
                    if tok and tok not in history_joined:
                        ok_history = False
                        break
                if not ok_history:
                    continue

                def _required_codes(field: str) -> set[int]:
                    reqs = set()
                    for raw in (rule.get(field) or []):
                        try:
                            reqs.add(int(raw))
                        except (TypeError, ValueError):
                            continue
                    return reqs

                requires_hand = _required_codes("requires_hand_codes")
                if requires_hand and not requires_hand.issubset(hand_codes):
                    continue

                requires_mzone = _required_codes("requires_mzone_codes")
                if requires_mzone and not requires_mzone.issubset(mzone_codes):
                    continue

                requires_grave = _required_codes("requires_grave_codes")
                if requires_grave and not requires_grave.issubset(grave_codes):
                    continue

                requires_banish = _required_codes("requires_banish_codes")
                if requires_banish and not requires_banish.issubset(banish_codes):
                    continue

                matched = False
                prefer_codes = []
                for raw in (rule.get("prefer_codes") or []):
                    try:
                        prefer_codes.append(int(raw))
                    except (TypeError, ValueError):
                        continue
                if prefer_codes:
                    matched = candidate_code is not None and int(candidate_code) in prefer_codes
                else:
                    matched = True

                prefer_act_ids = []
                for raw in (rule.get("prefer_act_ids") or []):
                    try:
                        prefer_act_ids.append(int(raw))
                    except (TypeError, ValueError):
                        continue
                if prefer_act_ids:
                    matched = matched and candidate_act_id is not None and int(candidate_act_id) in prefer_act_ids

                if not matched:
                    prefer_label_equals = rule.get("prefer_label_equals") or []
                    if isinstance(prefer_label_equals, str):
                        prefer_label_equals = [prefer_label_equals]
                    candidate_norm = str(candidate_label or "").strip()
                    for token in prefer_label_equals:
                        tok = str(token).strip()
                        if tok and candidate_norm == tok:
                            matched = True
                            break

                if not matched:
                    prefer_contains = rule.get("prefer_contains") or []
                    if isinstance(prefer_contains, str):
                        prefer_contains = [prefer_contains]
                    for token in prefer_contains:
                        tok = str(token).strip()
                        if tok and tok in candidate_label:
                            matched = True
                            break

                if not matched:
                    continue

                bonus = int(rule.get("bonus", 0))
                if bonus:
                    score += bonus
                    reasons.append(str(rule.get("reason") or f"prompt_bias_rule_{i+1}"))

            return score, reasons

        def _delta_score(before: dict, after: dict) -> tuple[int, dict[str, int]]:
            delta = summarize_state_delta(before, after)
            score = 0
            used: dict[str, int] = {}
            for tag in list(delta.get("derived_tags") or []):
                weight = int(delta_tag_weights.get(tag, 0))
                if weight:
                    score += weight
                    used[tag] = used.get(tag, 0) + weight
            return int(score), used

        def _passive_choice(rows: list[tuple[int, list | None, str, int, int, int, int]]) -> int | None:
            for idx, _feat, _label, _msg, act, _finish, _phase in rows:
                if act == 9:
                    return idx
            for idx, _feat, _label, msg, act, _finish, _phase in rows:
                if msg in (6, 7) and act == 9:
                    return idx
            for idx, _feat, _label, _msg, _act, finish, _phase in rows:
                if finish == 1:
                    return idx
            return None

        def _starter_wait_from_hand_codes(hand_codes: set[int]) -> bool:
            """Return True if opener rules indicate we should passively wait into main phase."""
            if not hand_codes:
                return False
            cfg = action_goal_cfg or {}
            for rule in (cfg.get("prompt_bias_rules") or []):
                if not isinstance(rule, dict):
                    continue
                if not bool(rule.get("wait_for_main_phase", False)):
                    continue
                req = set()
                for raw in (rule.get("requires_hand_codes") or []):
                    try:
                        req.add(int(raw))
                    except (TypeError, ValueError):
                        continue
                if req and req.issubset(hand_codes):
                    return True
            return False

        def _should_wait_for_main_phase(current_state: dict) -> bool:
            """If current phase is not main and hand matches a preferred main-phase starter rule, wait."""
            phase_now = str(env.get_current_phase() if hasattr(env, "get_current_phase") else "").strip().lower()
            if phase_now in ("main1", "main2", "main"):
                return False
            primary = current_state.get("primary", {}) if isinstance(current_state, dict) else {}
            hand_codes: set[int] = set()
            for row in (primary.get("hand", []) or []):
                if isinstance(row, dict):
                    try:
                        hand_codes.add(int(row.get("code")))
                    except (TypeError, ValueError):
                        continue
            return _starter_wait_from_hand_codes(hand_codes)

        initial_named = _state_named_scored()
        initial_primary = initial_named.get("primary", {}) if isinstance(initial_named, dict) else {}
        initial_hand_codes: set[int] = set()
        for row in (initial_primary.get("hand", []) or []):
            if isinstance(row, dict):
                try:
                    initial_hand_codes.add(int(row.get("code")))
                except (TypeError, ValueError):
                    continue
        should_wait_initial_main = _starter_wait_from_hand_codes(initial_hand_codes)

        def _restore_scored_trace() -> bool:
            obs0, _, _ = env.reset()
            for fp_before, sig, label, post_hash, post_prompt in trace_rows:
                actions_here = env.get_legal_actions()
                if _prompt_key(env, actions_here) != fp_before:
                    return False
                idx_here = _find_action_index_by_sig_or_label(
                    env, actions_here, sig, label, card_id_to_code, code_to_name
                )
                if idx_here is None:
                    return False
                obs1, term1, trunc1, _ = env.step(idx_here)
                if term1 or trunc1:
                    return False
                if _step_hash(env) != post_hash:
                    return False
                if _prompt_key(env, env.get_legal_actions()) != post_prompt:
                    return False
            return True

        def _rows_for_actions(actions: list[int]) -> list[tuple[int, list | None, str, int, int, int, int]]:
            rows: list[tuple[int, list | None, str, int, int, int, int]] = []
            for idx in actions:
                feat = env.action_features(idx)
                label = decode_action_features(feat, card_id_to_code, code_to_name) if feat else action_index_to_label(idx)
                label = _label_with_effect_hint(
                    label, feat, card_id_to_code, ygo_root, effect_hint_cache, effect_overrides=effect_label_overrides, cdb_effects=cdb_effect_texts
                )
                msg = int(feat[3]) if feat is not None and len(feat) >= 4 else 0
                act = int(feat[4]) if feat is not None and len(feat) >= 5 else -1
                finish = int(feat[5]) if feat is not None and len(feat) >= 6 else 0
                phase = int(feat[7]) if feat is not None and len(feat) >= 8 else 0
                if msg == 0:
                    continue
                rows.append((idx, feat, label, msg, act, finish, phase))
            return rows

        def _is_opaque_select_pool(rows: list[tuple[int, list | None, str, int, int, int, int]]) -> bool:
            if not rows:
                return False
            if any(msg != 3 or act != 0 for _idx, _feat, _label, msg, act, _finish, _phase in rows):
                return False
            specs: list[int] = []
            nonzero_codes = 0
            for _idx, feat, _label, _msg, _act, _finish, _phase in rows:
                if feat is None or len(feat) < 1:
                    return False
                try:
                    specs.append(int(feat[0]))
                except (TypeError, ValueError):
                    return False
                if feat is not None and len(feat) >= 3:
                    try:
                        card_id = int(feat[1]) * 256 + int(feat[2])
                        if card_id > 0:
                            nonzero_codes += 1
                    except (TypeError, ValueError):
                        pass
            specs_sorted = sorted(specs)
            if specs_sorted != list(range(1, len(specs_sorted) + 1)):
                return False
            # If the engine supplied concrete per-option card ids, trust those labels.
            return nonzero_codes == 0

        def _opaque_select_label(feat: list | None) -> str:
            spec = None
            if feat is not None and len(feat) >= 1:
                try:
                    spec = int(feat[0])
                except (TypeError, ValueError):
                    spec = None
            return f"Select option {spec}" if spec is not None else "Select option"

        def _pick_scored_action(actions: list[int]) -> tuple[int | None, dict]:
            if not actions:
                return None, {}
            rows = _rows_for_actions(actions)
            if not rows:
                return None, {}
            opaque_select_pool = _is_opaque_select_pool(rows)

            to_play_now = env.get_to_play() if hasattr(env, "get_to_play") else None
            before_named = _state_named_scored()
            if lock_initial_player and initial_to_play in (0, 1) and to_play_now in (0, 1) and to_play_now != initial_to_play:
                passive_idx = _passive_choice(rows)
                if passive_idx is not None:
                    return passive_idx, {"reason": "forced_passive", "total_score": 0}
            phase_now = str(env.get_current_phase() if hasattr(env, "get_current_phase") else "").strip().lower()
            if (
                to_play_now in (0, 1)
                and initial_to_play in (0, 1)
                and int(to_play_now) == int(initial_to_play)
                and should_wait_initial_main
                and phase_now not in ("main1", "main2", "main")
            ):
                passive_idx = _passive_choice(rows)
                if passive_idx is not None:
                    return passive_idx, {
                        "reason": "wait_for_main_phase",
                        "total_score": 0,
                        "initial_hand_codes": sorted(int(x) for x in initial_hand_codes),
                    }
            prompt_before = _prompt_key(env, actions)
            current_msg = rows[0][3]
            best_idx = rows[0][0]
            best_info: dict = {"reason": "fallback_first", "total_score": -10**9}

            for idx, feat, label, msg, act, finish, phase in rows:
                if opaque_select_pool:
                    label = _opaque_select_label(feat)
                base = 0
                reasons: list[str] = []
                candidate_code = None
                if feat is not None and len(feat) >= 3:
                    candidate_card_id = int(feat[1]) * 256 + int(feat[2])
                    if candidate_card_id > 0:
                        candidate_code = int(card_id_to_code.get(candidate_card_id, candidate_card_id))
                if msg == 2 and act != 9:
                    base += 16
                    reasons.append("optional_chain")
                if msg in (6, 7) and act != 9:
                    base += 22
                    reasons.append("optional_yes")
                if act == 8:
                    base += 8
                    reasons.append("activate")
                elif act == 3:
                    base += 7
                    reasons.append("spsummon")
                elif act == 4:
                    base += 6
                    reasons.append("summon")

                action_goal_score, contains_hits, order_hits = _action_goal_score_labels(history_labels + [label])
                card_bonus, card_reasons = _prompt_bias_bonus(
                    current_msg,
                    label,
                    candidate_code,
                    act,
                    before_named,
                    history_labels,
                )
                # Forward-only scored trace: score only the currently visible live options.
                # Do not simulate sibling candidates here; that was mixing prompt contexts.
                delta_score = 0
                delta_breakdown: dict[str, int] = {}
                total = int(base + action_goal_score + card_bonus + delta_score)
                info = {
                    "total_score": int(total),
                    "base_score": int(base),
                    "action_goal_score": int(action_goal_score),
                    "action_goal_contains_hits": int(contains_hits),
                    "action_goal_order_hits": int(order_hits),
                    "card_specific_bonus": int(card_bonus),
                    "delta_score": int(delta_score),
                    "delta_breakdown": dict(delta_breakdown),
                    "reasons": list(reasons) + list(card_reasons),
                }
                if total > int(best_info.get("total_score", -10**9)):
                    best_idx = idx
                    best_info = info

            return best_idx, best_info

        trace_meta = {
            "initial_hand_codes": sorted(int(x) for x in initial_hand_codes),
            "should_wait_initial_main": bool(should_wait_initial_main),
        }

        ended = False
        for step in range(1, max(1, trace_max_steps) + 1):
            turn_now = env.get_turn_count() if hasattr(env, "get_turn_count") else None
            if initial_turn is not None and turn_now is not None and int(turn_now) != int(initial_turn):
                break
            actions_now = env.get_legal_actions()
            pre_rows = _rows_for_actions(actions_now)
            to_play_now = env.get_to_play() if hasattr(env, "get_to_play") else None
            phase_now = str(env.get_current_phase() if hasattr(env, "get_current_phase") else "").strip().lower()
            wait_debug = {
                "to_play_now": int(to_play_now) if to_play_now in (0, 1) else None,
                "initial_to_play": int(initial_to_play) if initial_to_play in (0, 1) else None,
                "phase_now": phase_now,
                "should_wait_initial_main": bool(should_wait_initial_main),
                "initial_hand_codes": sorted(int(x) for x in initial_hand_codes),
                "passive_idx": None,
                "pre_rows_count": len(pre_rows),
            }
            if (
                pre_rows
                and to_play_now in (0, 1)
                and initial_to_play in (0, 1)
                and int(to_play_now) == int(initial_to_play)
                and should_wait_initial_main
                and phase_now not in ("main1", "main2", "main")
            ):
                passive_idx = _passive_choice(pre_rows)
                wait_debug["passive_idx"] = int(passive_idx) if passive_idx is not None else None
                if passive_idx is not None:
                    idx, score_info = passive_idx, {
                        "reason": "wait_for_main_phase",
                        "total_score": 0,
                        "initial_hand_codes": sorted(int(x) for x in initial_hand_codes),
                    }
                else:
                    idx, score_info = _pick_scored_action(actions_now)
            else:
                idx, score_info = _pick_scored_action(actions_now)
            if idx is None:
                break
            feat = env.action_features(idx)
            label = decode_action_features(feat, card_id_to_code, code_to_name) if feat else action_index_to_label(idx)
            label = _label_with_effect_hint(
                label, feat, card_id_to_code, ygo_root, effect_hint_cache, effect_overrides=effect_label_overrides, cdb_effects=cdb_effect_texts
            )
            opaque_select_pool = _is_opaque_select_pool(pre_rows)
            if opaque_select_pool:
                label = _opaque_select_label(feat)
            legal_options: list[dict] = []
            for opt_idx in actions_now:
                opt_feat = env.action_features(opt_idx)
                opt_label = decode_action_features(opt_feat, card_id_to_code, code_to_name) if opt_feat else action_index_to_label(opt_idx)
                opt_label = _label_with_effect_hint(
                    opt_label,
                    opt_feat,
                    card_id_to_code,
                    ygo_root,
                    effect_hint_cache,
                    effect_overrides=effect_label_overrides,
                    cdb_effects=cdb_effect_texts,
                )
                opt_msg = int(opt_feat[3]) if opt_feat is not None and len(opt_feat) >= 4 else None
                if opt_msg in (None, 0):
                    continue
                if opaque_select_pool:
                    opt_label = _opaque_select_label(opt_feat)
                opt_spec = int(opt_feat[0]) if opt_feat is not None and len(opt_feat) >= 1 else None
                opt_card_id = None
                opt_code = None
                if opt_feat is not None and len(opt_feat) >= 3:
                    try:
                        opt_card_id = int(opt_feat[1]) * 256 + int(opt_feat[2])
                    except (TypeError, ValueError):
                        opt_card_id = None
                    if opt_card_id and int(opt_card_id) > 0:
                        try:
                            opt_code = int(card_id_to_code.get(int(opt_card_id), int(opt_card_id)))
                        except (TypeError, ValueError):
                            opt_code = None
                legal_options.append(
                    {
                        "action_index": int(opt_idx),
                        "label": opt_label,
                        "raw_label": decode_action_features(opt_feat, card_id_to_code, code_to_name) if opt_feat else action_index_to_label(opt_idx),
                        "spec": opt_spec,
                        "card_id": opt_card_id,
                        "code": opt_code,
                        "msg_id": opt_msg,
                        "act_id": int(opt_feat[4]) if opt_feat is not None and len(opt_feat) >= 5 else None,
                        "finish": int(opt_feat[5]) if opt_feat is not None and len(opt_feat) >= 6 else None,
                        "phase_id": int(opt_feat[7]) if opt_feat is not None and len(opt_feat) >= 8 else None,
                        "raw": [int(x) for x in opt_feat] if opt_feat is not None else [],
                    }
                )
            msg_id = int(feat[3]) if feat is not None and len(feat) >= 4 else None
            act_id = int(feat[4]) if feat is not None and len(feat) >= 5 else None
            finish_id = int(feat[5]) if feat is not None and len(feat) >= 6 else None
            phase_id = int(feat[7]) if feat is not None and len(feat) >= 8 else None
            before = _state_named_scored()
            p_now = before.get("to_play")
            t_now = before.get("turn_count")
            current_phase = env.get_current_phase() if hasattr(env, "get_current_phase") else None
            msg_name = _MSG_ID_TO_NAME.get(int(msg_id), f"msg_{msg_id}") if msg_id is not None else "unknown"
            prompt_before = _prompt_key(env, actions_now)
            pre_timing = {
                "current_phase": current_phase,
                "prompt_msg": msg_name,
                "is_chain_window": bool(msg_id == 2),
                "is_open_game_state": bool(msg_id == 1),
                "prompt_key": prompt_before,
            }
            obs, term, trunc, info = env.step(idx)
            after = _state_named_scored()
            post_actions = env.get_legal_actions()
            post_prompt = _prompt_key(env, post_actions)
            post_phase = env.get_current_phase() if hasattr(env, "get_current_phase") else None
            post_msg_id = None
            try:
                if post_actions:
                    post_feat0 = env.action_features(int(post_actions[0]))
                    if post_feat0 is not None and len(post_feat0) >= 4:
                        post_msg_id = int(post_feat0[3])
            except Exception:
                post_msg_id = None
            post_msg_name = _MSG_ID_TO_NAME.get(int(post_msg_id), f"msg_{post_msg_id}") if post_msg_id is not None else "unknown"
            post_timing = {
                "current_phase": post_phase,
                "prompt_msg": post_msg_name,
                "is_chain_window": bool(post_msg_id == 2),
                "is_open_game_state": bool(post_msg_id == 1),
                "prompt_key": post_prompt,
            }
            trace_rows.append((prompt_before, _action_sig(feat), label, _step_hash(env), post_prompt))
            history_labels.append(label)
            post_legal_actions_str = None
            if isinstance(info, dict):
                raw_legal_actions_str = info.get("legal_actions_str")
                if raw_legal_actions_str is not None:
                    try:
                        if isinstance(raw_legal_actions_str, (bytes, bytearray)):
                            post_legal_actions_str = bytes(raw_legal_actions_str).split(b"\x00", 1)[0].decode("utf-8", errors="replace")
                        elif hasattr(raw_legal_actions_str, "tobytes"):
                            post_legal_actions_str = raw_legal_actions_str.tobytes().split(b"\x00", 1)[0].decode("utf-8", errors="replace")
                        elif isinstance(raw_legal_actions_str, (list, tuple)) and raw_legal_actions_str and all(isinstance(x, int) for x in raw_legal_actions_str):
                            post_legal_actions_str = bytes(raw_legal_actions_str).split(b"\x00", 1)[0].decode("utf-8", errors="replace")
                        else:
                            post_legal_actions_str = str(raw_legal_actions_str).split("\x00", 1)[0]
                    except Exception:
                        post_legal_actions_str = str(raw_legal_actions_str)
            trace_nodes.append(
                {
                    "step": step,
                    "action_index": int(idx),
                    "label": label,
                    "score_info": dict(score_info or {}),
                    "pre_legal_options": legal_options,
                    "legal_options": legal_options,
                    "action_feature_ids": {
                        "msg_id": msg_id,
                        "act_id": act_id,
                        "finish": finish_id,
                        "phase_id": phase_id,
                        "raw": [int(x) for x in feat] if feat is not None else [],
                    },
                    "timing": dict(pre_timing),
                    "pre_timing": dict(pre_timing),
                    "post_timing": dict(post_timing),
                    "pre_engine_legal_actions_str": None,
                    "post_engine_legal_actions_str": post_legal_actions_str,
                    "engine_legal_actions_str": post_legal_actions_str,
                    "wait_debug": dict(wait_debug),
                    "before": before,
                    "after": after,
                    "state_delta": summarize_state_delta(before.get("primary", {}), after.get("primary", {})),
                }
            )
            print(
                f"  {step:>3}. [p={p_now} t={t_now} a={idx} {msg_name} phase={current_phase}] "
                f"score={score_info.get('total_score', 0)} {label}"
            )
            if term or trunc:
                ended = True
                break

        print(f"  Scored trace steps: {len(trace_nodes)}" + (" (ended)" if ended else ""))
        if dfs_json:
            payload = {
                "mode": "scored_trace",
                "deck": str(deck_path),
                "seed": int(actual_seed),
                "meta": dict(trace_meta),
                "initial_state": trace_nodes[0]["before"] if trace_nodes else _state_named_scored(),
                "nodes": trace_nodes,
            }
            out = Path(dfs_json).resolve()
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            print(f"  JSON trace: {out}")
        print()

    # Optional: run full DFS from current state (explore each action until threshold or no actions)
    if dfs:
        from brain.search import run_combo_dfs
        print("--- DFS from current state ---")
        print(f"  max_depth={max_depth}  max_nodes={max_nodes}")
        try:
            def _parse_codes(raw: str) -> list[int]:
                vals: list[int] = []
                if not raw:
                    return vals
                for tok in str(raw).split(","):
                    t = tok.strip()
                    if not t:
                        continue
                    vals.append(int(t))
                return vals

            run_combo_dfs(
                env, card_id_to_code, code_to_name,
                max_depth=max_depth,
                max_nodes=max_nodes,
                verbose=True,
                first_turn=first_turn,
                lock_initial_player=lock_initial_player,
                json_out=dfs_json,
                json_all_out=dfs_json_all,
                fail_fast_drift=fail_fast_drift,
                goal_mzone_codes=_parse_codes(goal_mzone),
                goal_szone_codes=_parse_codes(goal_szone),
                goal_grave_codes=_parse_codes(goal_grave),
                goal_banish_codes=_parse_codes(goal_banish),
                goal_hand_codes=_parse_codes(goal_hand),
                goal_hit_bonus=goal_hit_bonus,
                meaningful_action_bonus=meaningful_action_bonus,
                action_goal_config=action_goal_cfg,
            )
        except ValueError as e:
            print(f"  DFS aborted: invalid goal code list ({e})", file=sys.stderr)
            raise SystemExit(2)
        except json.JSONDecodeError as e:
            print(f"  DFS aborted: invalid --action-goals-json ({e})", file=sys.stderr)
            raise SystemExit(2)
        except RuntimeError as e:
            print(f"  DFS aborted: {e}", file=sys.stderr)
            raise SystemExit(2)
        print()

    print("Use this run to validate legality/timing/state consistency first; then run full combo-map (Path B) or best-path (Path A).")


def run_sample_hands(
    deck: Path,
    num_hands: int = 10,
    num_draw: int = 5,
    ygo_env_root: Path | None = None,
    seed: int | None = None,
    out_path: Path | None = None,
    format: str = "text",
) -> None:
    """Generate a set of hands from the deck and output card names (text or JSON)."""
    deck_path = Path(deck).resolve()
    if not deck_path.is_file():
        print(f"Deck file not found: {deck_path}", file=sys.stderr)
        sys.exit(1)

    script_dir = Path(__file__).resolve().parent
    yapping_root = script_dir.parent

    ygo_root = Path(ygo_env_root).resolve() if ygo_env_root else None
    if not ygo_root or not ygo_root.is_dir():
        ygo_root = os.environ.get("YGO_ENV_ROOT")
        ygo_root = Path(ygo_root).resolve() if ygo_root else None
    if not ygo_root or not ygo_root.is_dir():
        ygo_root = _default_adapter_root(yapping_root)
    if not ygo_root.is_dir():
        print(
            "Engine repo not found. Set YGO_ENV_ROOT or use --ygo-env, or ensure vendor/yapcore exists. See docs/ENGINE_SETUP.md.",
            file=sys.stderr,
        )
        sys.exit(1)
    if str(yapping_root) not in sys.path:
        sys.path.insert(0, str(yapping_root))

    try:
        from engine.environment import create_env
    except ImportError as e:
        print(f"Import error: {e}", file=sys.stderr)
        sys.exit(1)

    code_to_name = _load_code_to_name(yapping_root, ygo_root)
    card_id_to_code = _load_card_id_to_code(ygo_root)

    try:
        env = create_env(deck_path=deck_path, ygo_env_root=ygo_root, seed=None)
    except RuntimeError as e:
        print(f"{e}", file=sys.stderr)
        sys.exit(1)

    hands_names: list[list[str]] = []
    for i in range(num_hands):
        # Use a different seed each time so we get different hands. With --seed use seed+i; else use i.
        reset_seed = (seed + i) if seed is not None else i
        _obs, hand, _ = env.reset(seed=reset_seed)
        names = _hand_to_names(hand[:num_draw], code_to_name, card_id_to_code)
        hands_names.append(names)

    out_file = open(out_path, "w", encoding="utf-8") if out_path else None
    try:
        if format == "json":
            data = {"deck": str(deck_path), "num_hands": num_hands, "hands": hands_names}
            s = json.dumps(data, indent=2, ensure_ascii=False)
            (out_file or sys.stdout).write(s)
            if out_file:
                out_file.write("\n")
        else:
            for names in hands_names:
                line = ", ".join(names)
                (out_file or sys.stdout).write(line + "\n")
    finally:
        if out_file:
            out_file.close()


def main() -> None:
    args = _parse_args()

    run(
        deck=args.deck,
        num_draw=args.num_draw,
        max_actions=args.max_actions,
        ygo_env_root=args.ygo_env,
        seed=args.seed,
    )


if __name__ == "__main__":
    main()
