"""
Combo search: DFS over game states.

From a given state (env already at Main Phase idle), explore each legal action,
complete sub-prompts (zone, card, etc.), observe the next state, and recurse
until max_depth, max_nodes, or no legal actions. Returns best score and path.
"""

from __future__ import annotations

import json
import signal
import sqlite3
import sys
import time
import hashlib
from pathlib import Path
from collections import Counter, deque
from typing import Any, Optional

import numpy as np

from engine.actions import decode_action_features
from engine.state_delta import summarize_state_delta

from brain.heuristics import evaluate_line

# Prefixes we treat as main-phase decisions (idle menu: Summon/Set/Activate/Pass), not sub-prompts.
_MAIN_PREFIXES = frozenset({"Summon", "MSet", "Set", "Activate", "SpSummon", "Repo", "Attack", "DirectAttack"})
_OPTIONAL_PROMPT_MSG_IDS = frozenset({2, 6, 7})  # select_chain, select_effectyn, select_yesno

# Card display hints: loaded from data/card_display_hints.json (card name -> fusion_materials | cost_send_ed | etc.)
_display_hints_cache: Optional[dict[str, str]] = None


def _load_display_hints() -> dict[str, str]:
    """Load card name -> hint from data/card_display_hints.json. Keys starting with _ are ignored."""
    global _display_hints_cache
    if _display_hints_cache is not None:
        return _display_hints_cache
    root = Path(__file__).resolve().parent.parent
    path = root / "data" / "card_display_hints.json"
    out: dict[str, str] = {}
    if path.is_file():
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            for k, v in data.items():
                if isinstance(k, str) and not k.startswith("_") and isinstance(v, str):
                    out[k] = v
        except Exception:
            pass
    _display_hints_cache = out
    return out


def _card_name_from_label(base: str) -> Optional[str]:
    """Extract card name from a main label: 'Activate X' / 'Activate X (effect N)' / 'Summon X' -> X."""
    base = (base or "").strip()
    for prefix in ("Activate ", "Summon ", "SpSummon "):
        if base.startswith(prefix):
            name = base[len(prefix) :].strip()
            if " (effect " in name:
                name = name.split(" (effect ")[0].strip()
            return name or None
    return None


def _get_display_hint(card_name: Optional[str], hints: dict[str, str]) -> Optional[str]:
    """Return hint for this card: exact match, then longest key that appears in card_name."""
    if not card_name:
        return None
    if card_name in hints:
        return hints[card_name]
    # Substring match: longest hint key that is a substring of card_name
    best: Optional[tuple[int, str]] = None
    for key, value in hints.items():
        if key in card_name and (best is None or len(key) > best[0]):
            best = (len(key), value)
    return best[1] if best else None


def _parse_hint_draw(hint: Optional[str]) -> Optional[str]:
    """If hint contains |draw_N, return '; draw N' for display, else None. E.g. 'sent_to_gy_1|draw_1' -> '; draw 1'."""
    if not hint or "|" not in hint:
        return None
    for part in hint.split("|")[1:]:
        part = part.strip()
        if part.startswith("draw_") and part[5:].isdigit():
            return f"; draw {part[5:]}"
    return None


def _parse_hint_target_max(hint: Optional[str]) -> Optional[int]:
    """If hint is target_N or contains target_N (e.g. target_1), return N; else None. Effect-specific: show only first N selected."""
    if not hint:
        return None
    for part in hint.split("|"):
        part = part.strip()
        if part.startswith("target_") and part[7:].isdigit():
            return int(part[7:])
    return None


def _parse_hint_banish_max(hint: Optional[str]) -> Optional[int]:
    """If hint is banish_N or contains banish_N, return N; else None."""
    if not hint:
        return None
    for part in hint.split("|"):
        part = part.strip()
        if part.startswith("banish_") and part[7:].isdigit():
            return int(part[7:])
    return None


def _format_materials(names: list[str]) -> str:
    """Format material names with dedupe: same card twice -> 'CardName (x2)'."""
    if not names:
        return ""
    counts = Counter(names)
    parts = []
    for name, n in counts.items():
        if n > 1:
            parts.append(f"{name} (x{n})")
        else:
            parts.append(name)
    return ", ".join(parts)


def _is_main_label(s: str) -> bool:
    """True if this label is a main-phase choice (Summon/Set/Activate/SpSummon/Pass/etc.), not a sub-prompt."""
    s = (s or "").strip()
    if not s:
        return False
    # Sub-prompts: position choice after Summon, Place, etc. — not main idle choices
    if s.startswith("Set position") or s.startswith("Place →") or s.startswith("Confirm selection"):
        return False
    low = s.lower()
    # Chain-window pass ("Pass / don't chain") is not a main idle action.
    if "don't chain" in low:
        return False
    if s.startswith("→ ") or s.startswith("Pass"):
        return True
    first = s.split()[0] if s else ""
    return first in _MAIN_PREFIXES


def _is_chain_label(s: str) -> bool:
    """True if this label is a chain decision (optional/trigger window)."""
    s = (s or "").strip()
    return s.startswith("Chain ")


def _main_phase_labels_only(labels: list[str]) -> list[str]:
    """Filter to labels that are main-phase choices (not Select/Place/Confirm/option)."""
    return [L for L in labels if _is_main_label(L)]


def _current_msg_id(env: Any, actions: list[int]) -> int:
    """Best-effort current message id from legal actions (0 if unavailable)."""
    for idx in actions:
        feat = env.action_features(idx)
        if feat is not None and len(feat) >= 4 and int(feat[3]) != 0:
            return int(feat[3])
    return 0


def _preferred_optional_actions(
    env: Any,
    actions: list[int],
    cid_map: dict,
    name_map: dict,
    enforce_optional_activation: bool = True,
) -> list[int]:
    """
    From current optional-prompt actions, return actions ordered by preference.

    Policy:
    - select_chain: prefer real chain actions over "don't chain".
    - select_yesno/select_effectyn: prefer Yes over No.
    If enforce_optional_activation=False or no preferred choices exist, returns original actions.
    When enabled, preferred options are ordered first but non-preferred options are still kept.
    """
    if not actions:
        return actions
    msg_id = _current_msg_id(env, actions)
    if msg_id not in _OPTIONAL_PROMPT_MSG_IDS or not enforce_optional_activation:
        return actions

    preferred: list[int] = []
    if msg_id == 2:  # select_chain
        for idx in actions:
            feat = env.action_features(idx)
            label = decode_action_features(feat, cid_map, name_map) if feat else ""
            low = (label or "").lower()
            if "don't chain" in low or "pass" in low:
                continue
            preferred.append(idx)
    else:  # select_effectyn / select_yesno
        for idx in actions:
            feat = env.action_features(idx)
            if feat is not None and len(feat) >= 5 and int(feat[4]) != 9:
                preferred.append(idx)

    if not preferred:
        return actions
    preferred_set = set(preferred)
    rest = [a for a in actions if a not in preferred_set]
    return preferred + rest


def _passive_actions(
    env: Any,
    actions: list[int],
    cid_map: dict,
    name_map: dict,
) -> list[int]:
    """
    Return passive/non-committal actions from current prompt when available:
    Cancel/Pass (act_id=9), No on yes/no prompts, or finish-selection.
    """
    out: list[int] = []
    for idx in actions:
        feat = env.action_features(idx)
        if feat is None or len(feat) < 6:
            label = decode_action_features(feat, cid_map, name_map) if feat else ""
            low = (label or "").lower()
            if "pass" in low or "don't chain" in low or low.startswith("no") or "cancel" in low:
                out.append(idx)
            continue
        msg_id = int(feat[3])
        act_id = int(feat[4])
        finish = int(feat[5])
        if act_id == 9:
            out.append(idx)
            continue
        if msg_id in (6, 7) and act_id == 9:  # effectyn/yesno -> No/Cancel
            out.append(idx)
            continue
        if finish == 1:
            out.append(idx)
            continue
    return out


def _action_sig(feat: list | None) -> Optional[tuple[int, ...]]:
    """Stable action signature from action feature bytes; None if unavailable."""
    if not feat or len(feat) < 12:
        return None
    # Use the full 12-byte action feature row as semantic identity.
    return tuple(int(x) for x in feat[:12])


def _sig_msg_act(sig: Optional[tuple[int, ...]]) -> tuple[Optional[int], Optional[int], Optional[int]]:
    """Extract (msg_id, act_id, finish) from 12-byte action signature."""
    if not sig or len(sig) < 6:
        return None, None, None
    return int(sig[3]), int(sig[4]), int(sig[5])


def _obs_hash(obs: Any) -> str:
    """Deterministic hash of observation dict/arrays for replay validation."""
    h = hashlib.sha256()
    if obs is None:
        h.update(b"none")
        return h.hexdigest()
    if hasattr(obs, "keys"):
        keys = sorted(obs.keys())
        for k in keys:
            h.update(str(k).encode("utf-8", errors="replace"))
            v = obs[k]
            if v is None:
                h.update(b"<none>")
                continue
            try:
                arr = np.asarray(v)
                h.update(str(arr.shape).encode("utf-8", errors="replace"))
                h.update(str(arr.dtype).encode("utf-8", errors="replace"))
                h.update(arr.tobytes())
            except Exception:
                h.update(str(v).encode("utf-8", errors="replace"))
    else:
        h.update(str(obs).encode("utf-8", errors="replace"))
    return h.hexdigest()


def _stable_state_hash(env: Any) -> str:
    """Hash stable public snapshot zones for replay validation; empty string if unavailable."""
    st = _snapshot_state(env)
    if not st:
        return ""
    h = hashlib.sha256()
    for key in ("hand", "field_mzone", "field_szone", "grave", "banish"):
        vals = st.get(key, []) or []
        h.update(key.encode("utf-8"))
        h.update(b":")
        h.update(",".join(str(int(v)) for v in vals).encode("utf-8"))
        h.update(b";")
    return h.hexdigest()


def _step_hash(env: Any) -> str:
    """Deterministic post-step hash: prefer stable zone snapshot, fallback to full obs hash."""
    sh = _stable_state_hash(env)
    base = f"state:{sh}" if sh else f"obs:{_obs_hash(env.get_obs())}"
    tp = env.get_to_play() if hasattr(env, "get_to_play") else None
    tc = env.get_turn_count() if hasattr(env, "get_turn_count") else None
    ph = _phase_id(env)
    return f"{base}|tp={tp}|tc={tc}|ph={ph}"


def _phase_id(env: Any) -> Optional[int]:
    """Phase id from obs:global_[5] when available."""
    try:
        obs = env.get_obs() if hasattr(env, "get_obs") else None
        if obs is None or not hasattr(obs, "get"):
            return None
        g = obs.get("obs:global_")
        if g is None:
            g = obs.get("global_")
        if g is None:
            g = obs.get("global")
        if g is None:
            return None
        arr = np.asarray(g, dtype=np.uint8)
        if arr.ndim == 2:
            arr = arr[0]
        if arr.ndim >= 1 and arr.shape[0] > 5:
            return int(arr[5])
    except Exception:
        return None
    return None


def _prompt_key(env: Any, actions: list[int]) -> str:
    """
    Deterministic prompt context key from engine invariants:
    to_play, turn_count, phase_id, msg_id.
    """
    tp = env.get_to_play() if hasattr(env, "get_to_play") else None
    tc = env.get_turn_count() if hasattr(env, "get_turn_count") else None
    ph = _phase_id(env)
    msg = _current_msg_id(env, actions)
    return f"tp={tp}|tc={tc}|ph={ph}|msg={msg}"


def _prompt_fingerprint(env: Any, actions: list[int], cid_map: dict, name_map: dict) -> str:
    """Hash current prompt shape (msg + legal action signatures/labels) for strict replay validation."""
    msg_id = _current_msg_id(env, actions)
    chunks: list[str] = [f"msg={msg_id}", f"n={len(actions)}"]
    for idx in actions:
        feat = env.action_features(idx)
        label = decode_action_features(feat, cid_map, name_map) if feat is not None else f"action_{idx}"
        sig = _action_sig(feat)
        chunks.append(f"{sig}|{label}")
    raw = "\n".join(chunks).encode("utf-8", errors="replace")
    return hashlib.sha256(raw).hexdigest()


def _state_identity_key(state: Optional[dict]) -> tuple[tuple[int, ...], ...]:
    """Canonical absolute-public-state key from snapshot zones."""
    if not state:
        return tuple()
    zones = []
    for key in ("hand", "field_mzone", "field_szone", "grave", "banish"):
        vals = tuple(sorted(int(v) for v in (state.get(key, []) or [])))
        zones.append(vals)
    return tuple(zones)


def _legal_action_signature_key(env: Any, actions: list[int]) -> tuple[tuple[int, ...], ...]:
    """
    Canonical legal-action signature multiset for the current prompt.

    We sort the full 12-byte action signatures so node identity distinguishes prompts that
    share board state but expose different pending targets/options/finish states.
    """
    sigs: list[tuple[int, ...]] = []
    for idx in actions:
        feat = env.action_features(idx)
        sig = _action_sig(feat)
        if sig is None:
            sigs.append((-1, int(idx)))
        else:
            sigs.append(sig)
    return tuple(sorted(sigs))


def _node_key(env: Any, actions: list[int], state: Optional[dict]) -> tuple[Any, ...]:
    """
    Stable DFS node identity.

    Includes absolute public state plus prompt/decision context so two visually similar boards
    are not merged when the engine is waiting on different prompts or legal option sets.
    """
    return (
        _state_identity_key(state),
        int(env.get_to_play()) if hasattr(env, "get_to_play") and env.get_to_play() in (0, 1) else None,
        int(env.get_turn_count()) if hasattr(env, "get_turn_count") and env.get_turn_count() is not None else None,
        env.get_current_phase() if hasattr(env, "get_current_phase") else None,
        _current_msg_id(env, actions),
        _legal_action_signature_key(env, actions),
    )


def _find_action_index_by_sig_or_label(
    env: Any,
    actions: list[int],
    expected_sig: Optional[tuple[int, ...]],
    expected_label: str,
    cid_map: dict,
    name_map: dict,
) -> Optional[int]:
    """Resolve action in current legal list using signature first, then exact label fallback."""
    if expected_sig is not None:
        for idx in actions:
            feat = env.action_features(idx)
            if _action_sig(feat) == expected_sig:
                return idx
    if expected_label:
        for idx in actions:
            feat = env.action_features(idx)
            label = decode_action_features(feat, cid_map, name_map) if feat is not None else f"action_{idx}"
            if _labels_match(expected_label, label):
                return idx
    return None


def _reset_to_main_phase_idle(env: Any, cid_map: dict, name_map: dict, max_steps: int = 32) -> bool:
    """
    Reset env and auto-pass/cancel until Main Phase idle baseline is reached.
    Returns False if no pass/cancel action exists before reaching idle.
    """
    # Important: this helper is used for trace logging/replay.
    # If we call env.reset() without the original seed, the opening hand changes,
    # and the replay-based prompt node extraction will fail (returning empty logs).
    seed = getattr(env, "_seed", None)
    try:
        if seed is not None:
            _obs, _hand, _legal = env.reset(seed=int(seed))
        else:
            _obs, _hand, _legal = env.reset()
    except TypeError:
        # Some wrappers expose reset(seed=...) differently; fall back to plain reset.
        _obs, _hand, _legal = env.reset()
    for _ in range(max_steps):
        actions = env.get_legal_actions()
        if not actions:
            return False
        if _is_main_phase_idle_now(env, actions, cid_map, name_map):
            return True
        idx = _pass_or_cancel_index(env, actions, cid_map, name_map)
        if idx is None:
            return False
        _obs, term, trunc, _ = env.step(idx)
        if term or trunc:
            return False
    return False


def _replay_trace(
    env: Any,
    trace: list[tuple[str, Optional[tuple[int, ...]], str, str]],
    cid_map: dict,
    name_map: dict,
) -> bool:
    """Replay transcript from root with strict prompt/action/hash checks."""
    ok, _reason, _step = _replay_trace_reasoned(env, trace, cid_map, name_map)
    return ok


def _replay_trace_reasoned(
    env: Any,
    trace: list[tuple[str, Optional[tuple[int, ...]], str, str]],
    cid_map: dict,
    name_map: dict,
) -> tuple[bool, str, int]:
    """Replay transcript and return (ok, reason, step_idx_1_based_or_0)."""
    if not _reset_to_main_phase_idle(env, cid_map, name_map):
        return False, "reset_to_main_phase_idle_failed", 0
    for i, (fp_before, sig, label, post_hash) in enumerate(trace, start=1):
        actions = env.get_legal_actions()
        if _prompt_key(env, actions) != fp_before:
            return False, "prompt_context_mismatch", i
        idx = _find_action_index_by_sig_or_label(env, actions, sig, label, cid_map, name_map)
        if idx is None:
            return False, "action_not_found", i
        feat = env.action_features(idx)
        actual = decode_action_features(feat, cid_map, name_map) if feat is not None else f"action_{idx}"
        if label and not _labels_match(label, actual):
            return False, "label_mismatch", i
        _obs, term, trunc, _ = env.step(idx)
        if term or trunc:
            return False, "terminated_or_truncated", i
        if _step_hash(env) != post_hash:
            return False, "post_hash_mismatch", i
    return True, "ok", 0


def _is_main_phase_idle_now(env: Any, actions: list[int], cid_map: dict, name_map: dict) -> bool:
    """True if current menu is Main Phase idle (Summon/Set/Activate...), not a sub-prompt."""
    phase = env.get_current_phase() if hasattr(env, "get_current_phase") else None
    msg_id = _current_msg_id(env, actions)
    if phase is not None and phase not in ("main1", "main2", "main"):
        return False
    if msg_id == 1:  # select_idle
        return True
    # Chain/yes-no/effect-yn are never main idle menus.
    if msg_id in _OPTIONAL_PROMPT_MSG_IDS:
        return False
    # Fallback for wrappers that do not expose reliable msg_id/phase:
    # infer idle from legal action labels that look like idle menu commands.
    has_idle_cmd = False
    has_subprompt = False
    prefixes: set[str] = set()
    idle_prefixes = {"Summon", "MSet", "Set", "Activate", "SpSummon", "Repo", "Attack", "DirectAttack"}
    for idx in actions:
        feat = env.action_features(idx)
        label = decode_action_features(feat, cid_map, name_map) if feat else ""
        if not label:
            continue
        s = label.strip()
        if s.startswith("Select ") or s.startswith("Place ") or s.startswith("Set position"):
            has_subprompt = True
            continue
        first = s.split()[0]
        prefixes.add(first)
        if first in idle_prefixes:
            has_idle_cmd = True
    if has_idle_cmd and not has_subprompt:
        return True
    return bool(prefixes & idle_prefixes) and not has_subprompt


def _pass_or_cancel_index(env: Any, actions: list[int], cid_map: dict, name_map: dict) -> Optional[int]:
    """Return pass/cancel index if present, else None."""
    for idx in actions:
        feat = env.action_features(idx)
        if feat is not None and len(feat) >= 5 and int(feat[4]) == 9:
            return idx
        label = decode_action_features(feat, cid_map, name_map) if feat else ""
        if "Pass" in label or "don't chain" in label.lower():
            return idx
    return None


def _first_non_pass_index(env: Any, actions: list[int], cid_map: dict, name_map: dict) -> Optional[int]:
    """Return first non-pass index if present, else None."""
    for idx in actions:
        feat = env.action_features(idx)
        if feat is not None and len(feat) >= 5 and int(feat[4]) == 9:
            continue
        label = decode_action_features(feat, cid_map, name_map) if feat else ""
        if "Pass" in label or "don't chain" in label.lower():
            continue
        return idx
    return None


def _expand_completion_variants(
    env: Any,
    trace_prefix: list[tuple[str, Optional[tuple[int, ...]], str, str]],
    cid_map: dict,
    name_map: dict,
    first_turn: bool = False,
    enforce_optional_activation: bool = True,
    lock_initial_player: bool = False,
    initial_to_play: Optional[int] = None,
    max_steps: int = 20,
    max_variants: int = 12,
) -> list[tuple[list[tuple[str, Optional[tuple[int, ...]], str, str]], Optional[dict]]]:
    """
    Expand completion paths back to Main Phase idle.

    Branches only on optional trigger windows (CHAIN / EFFECTYN / YESNO), while keeping
    deterministic behavior for normal placement/selection prompts to control branching.
    Returns a list of (completion_steps, state_snapshot_at_idle).
    """
    variants: list[tuple[list[tuple[str, Optional[tuple[int, ...]], str, str]], Optional[dict]]] = []
    stack: deque[list[tuple[str, Optional[tuple[int, ...]], str, str]]] = deque([[]])

    while stack and len(variants) < max_variants:
        taken = stack.pop()

        # Rebuild exact node state: root -> trace_prefix -> taken
        if not _replay_trace(env, trace_prefix + taken, cid_map, name_map):
            continue

        seq = list(taken)
        for _ in range(max_steps):
            actions = env.get_legal_actions()
            if not actions:
                break
            if _is_main_phase_idle_now(env, actions, cid_map, name_map):
                state = env.get_state_snapshot(env.get_obs()) if hasattr(env, "get_state_snapshot") else None
                variants.append((seq, state))
                break

            msg_id = _current_msg_id(env, actions)
            if msg_id in _OPTIONAL_PROMPT_MSG_IDS and len(actions) > 1:
                to_play_now = env.get_to_play() if hasattr(env, "get_to_play") else None
                if (
                    lock_initial_player
                    and initial_to_play in (0, 1)
                    and to_play_now in (0, 1)
                    and int(to_play_now) != int(initial_to_play)
                ):
                    candidate_actions = _passive_actions(env, actions, cid_map, name_map)
                    if not candidate_actions:
                        candidate_actions = actions
                else:
                    candidate_actions = _preferred_optional_actions(
                        env, actions, cid_map, name_map, enforce_optional_activation=enforce_optional_activation
                    )
                # Branch candidate options in optional trigger windows (policy may remove don't-chain/No).
                for idx in reversed(candidate_actions):
                    fp_before = _prompt_key(env, actions)
                    feat = env.action_features(idx)
                    label = decode_action_features(feat, cid_map, name_map) if feat else f"action_{idx}"
                    sig = _action_sig(feat)
                    _obs, _term, _trunc, _ = env.step(idx)
                    if _term or _trunc:
                        continue
                    post_hash = _step_hash(env)
                    stack.append(seq + [(fp_before, sig, label, post_hash)])
                    # restore then continue trying sibling optional choices
                    _replay_trace(env, trace_prefix + seq, cid_map, name_map)
                break

            candidate_actions = _preferred_optional_actions(
                env, actions, cid_map, name_map, enforce_optional_activation=enforce_optional_activation
            )
            idx: Optional[int] = None
            if first_turn:
                # Avoid selecting pass/cancel when non-pass actions exist.
                # pass/cancel is identified by action feature `act_id == 9`.
                for cand in candidate_actions:
                    feat = env.action_features(cand)
                    if feat is not None and len(feat) >= 5 and int(feat[4]) != 9:
                        idx = cand
                        break
                if idx is None:
                    # Only pass/cancel options remain; fall back to the first candidate.
                    idx = candidate_actions[0] if candidate_actions else None
            else:
                # Conservative completion: prefer pass/cancel when legal to avoid consuming
                # unrelated optional branches; fall back to first non-pass for mandatory prompts.
                idx = _pass_or_cancel_index(env, candidate_actions, cid_map, name_map)
                if idx is None:
                    idx = _first_non_pass_index(env, candidate_actions, cid_map, name_map)
            if idx is None:
                break
            fp_before = _prompt_key(env, actions)
            feat = env.action_features(idx)
            label = decode_action_features(feat, cid_map, name_map) if feat else f"action_{idx}"
            sig = _action_sig(feat)
            turn_before = env.get_turn_count() if first_turn and hasattr(env, "get_turn_count") and env.get_turn_count() is not None else None
            _obs, _term, _trunc, _ = env.step(idx)
            if _term or _trunc:
                break
            if (
                first_turn
                and turn_before is not None
                and hasattr(env, "get_turn_count")
                and env.get_turn_count() is not None
                and int(env.get_turn_count()) != int(turn_before)
            ):
                # Turn advanced due to completion step; discard this variant.
                break
            post_hash = _step_hash(env)
            seq.append((fp_before, sig, label, post_hash))

    return variants


def _snapshot_state(env: Any) -> Optional[dict]:
    """
    Best-effort absolute snapshot for player 0 (hand/field/grave/banish).

    Important: wrapper.get_state_snapshot() is controller-relative (controller==0 in current
    observation perspective). During prompts where to_play flips, that can make logs look like
    cards "teleport". Here we remap controller -> absolute player using to_play so DFS logs/hashes
    are stable for absolute player 0.
    """
    if not hasattr(env, "get_obs"):
        return None
    try:
        obs = env.get_obs()
        if obs is None or not hasattr(obs, "get"):
            return None
        cards = obs.get("obs:cards_")
        if cards is None:
            cards = obs.get("cards_")
        if cards is None:
            cards = obs.get("cards")
        if cards is None:
            # Fallback to wrapper snapshot if card tensor not exposed.
            if hasattr(env, "get_state_snapshot"):
                return env.get_state_snapshot(obs)
            return None

        arr = np.asarray(cards, dtype=np.uint8)
        if arr.ndim == 3:
            arr = arr[0]
        if arr.ndim < 2 or arr.shape[1] < 5:
            return None

        to_play = env.get_to_play() if hasattr(env, "get_to_play") else None
        out = {"hand": [], "field_mzone": [], "field_szone": [], "grave": [], "banish": []}

        # Location ids (col 2): 2=hand, 3=mzone, 4=szone, 5 or 16=grave, 6=banish
        for row in range(arr.shape[0]):
            ctrl = int(arr[row, 4])
            if ctrl not in (0, 1):
                continue
            cid = int(arr[row, 0]) * 256 + int(arr[row, 1])
            if cid <= 0:
                continue
            loc = int(arr[row, 2])

            # Convert relative controller to absolute player when possible.
            if to_play in (0, 1):
                abs_player = int(to_play) if ctrl == 0 else (1 - int(to_play))
            else:
                abs_player = ctrl
            if abs_player != 0:
                continue

            if loc == 2:
                out["hand"].append(cid)
            elif loc == 3:
                out["field_mzone"].append(cid)
            elif loc == 4:
                out["field_szone"].append(cid)
            elif loc in (5, 16):
                out["grave"].append(cid)
            elif loc == 6:
                out["banish"].append(cid)
        return out
    except Exception:
        return None


def _cid_to_name(cid: int, cid_map: dict, name_map: dict) -> str:
    """card_id (code_list index) -> readable name, fallback to code/id string."""
    code = cid_map.get(int(cid), int(cid))
    return name_map.get(str(code), str(code))


def _format_state_for_log(state: Optional[dict], cid_map: dict, name_map: dict) -> str:
    """Compact single-line state formatter for DFS logs."""
    if not state:
        return "state=unavailable"

    def _fmt_zone(key: str) -> str:
        vals = state.get(key, []) or []
        names = [_cid_to_name(int(v), cid_map, name_map) for v in vals]
        return "[" + ", ".join(names) + "]"

    return (
        f"hand={_fmt_zone('hand')} "
        f"mzone={_fmt_zone('field_mzone')} "
        f"szone={_fmt_zone('field_szone')} "
        f"grave={_fmt_zone('grave')} "
        f"banish={_fmt_zone('banish')}"
    )


def _state_to_named_dict(state: Optional[dict], cid_map: dict, name_map: dict) -> dict:
    """State as JSON-friendly dict containing both ids and names."""
    if not state:
        return {"hand": [], "mzone": [], "szone": [], "grave": [], "banish": []}

    def _zone(ids: list) -> list[dict]:
        out: list[dict] = []
        for v in (ids or []):
            cid = int(v)
            out.append({"card_id": cid, "name": _cid_to_name(cid, cid_map, name_map)})
        return out

    return {
        "hand": _zone(state.get("hand", [])),
        "mzone": _zone(state.get("field_mzone", [])),
        "szone": _zone(state.get("field_szone", [])),
        "grave": _zone(state.get("grave", [])),
        "banish": _zone(state.get("banish", [])),
    }


def _write_dfs_json_report(
    out_path: Any,
    best_score: int,
    best_labels: list[str],
    best_prompt_labels: Optional[list[str]],
    visited: int,
    initial_state: Optional[dict],
    best_state: Optional[dict],
    prompt_nodes: list[tuple[str, Optional[dict]]],
    main_steps: Optional[list[dict]],
    cid_map: dict,
    name_map: dict,
) -> None:
    """Write DFS report JSON to disk."""
    if not out_path:
        return
    out = Path(out_path).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    report = {
        "best_score": int(best_score),
        "visited": int(visited),
        "best_path_labels": list(best_labels),
        "best_path_labels_full": list(best_prompt_labels or []),
        "initial_state": _state_to_named_dict(initial_state, cid_map, name_map),
        "best_state": _state_to_named_dict(best_state, cid_map, name_map),
        "main_steps": list(main_steps or []),
        "prompt_nodes": [
            {
                "step": i + 1,
                "label": lbl,
                "state": _state_to_named_dict(st, cid_map, name_map),
            }
            for i, (lbl, st) in enumerate(prompt_nodes)
        ],
    }
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _write_dfs_json_all_report(
    out_path: Any,
    meta: dict,
    visited_nodes: list[dict],
    skip_events: list[dict],
    cid_map: dict,
    name_map: dict,
) -> None:
    """Write full DFS traversal debug JSON."""
    if not out_path:
        return
    out = Path(out_path).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "meta": meta,
        "visited_nodes": visited_nodes,
        "skip_events": skip_events,
    }
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _labels_match(expected: str, actual: str) -> bool:
    """Strict replay consistency check to detect path/index drift."""
    return (expected or "").strip() == (actual or "").strip()


def _collect_best_main_step_details(
    env: Any,
    best_path: list[int],
    best_labels: list[str],
    cid_map: dict,
    name_map: dict,
) -> list[tuple[str, list[str], Optional[dict]]]:
    """
    Replay best path and collect completion labels + resulting state per main step.
    Returns list of (main_label, completion_labels, state_snapshot_after_step_resolution).
    """
    out: list[tuple[str, list[str], Optional[dict]]] = []
    if not best_path or not best_labels:
        return out

    n = min(len(best_path), len(best_labels))
    _obs, _, _ = env.reset()
    i = 0
    while i < n:
        idx = best_path[i]
        expected = best_labels[i]
        feat = env.action_features(idx)
        actual = decode_action_features(feat, cid_map, name_map) if feat else f"action_{idx}"
        if expected and not _labels_match(expected, actual):
            return []
        _obs, term, trunc, _ = env.step(idx)
        if term or trunc:
            return out

        label = best_labels[i]
        if not _is_main_label(label):
            i += 1
            continue

        j = i + 1
        completion_labels: list[str] = []
        while j < n and not _is_main_label(best_labels[j]):
            cidx = best_path[j]
            cexp = best_labels[j]
            cfeat = env.action_features(cidx)
            cact = decode_action_features(cfeat, cid_map, name_map) if cfeat else f"action_{cidx}"
            if cexp and not _labels_match(cexp, cact):
                return []
            _obs, term, trunc, _ = env.step(cidx)
            if term or trunc:
                break
            completion_labels.append(cexp)
            j += 1

        out.append((label, completion_labels, _snapshot_state(env)))
        i = j

    return out


def _collect_best_main_step_details_from_trace(
    env: Any,
    best_trace: list[tuple[str, Optional[tuple[int, ...]], str, str]],
    cid_map: dict,
    name_map: dict,
) -> list[tuple[str, list[str], Optional[dict], Optional[dict]]]:
    """
    Replay best transcript and collect completion labels + resulting state per main step.
    Returns list of (main_label, completion_labels, state_snapshot_after_step_resolution).
    """
    out: list[tuple[str, list[str], Optional[dict], Optional[dict]]] = []
    if not best_trace:
        return out
    if not _replay_trace(env, [], cid_map, name_map):
        return out

    i = 0
    n = len(best_trace)
    while i < n:
        fp, sig, label, post_hash = best_trace[i]
        actions = env.get_legal_actions()
        if _prompt_key(env, actions) != fp:
            return []
        idx = _find_action_index_by_sig_or_label(env, actions, sig, label, cid_map, name_map)
        if idx is None:
            return []
        before_state = _snapshot_state(env)
        _obs, term, trunc, _ = env.step(idx)
        if term or trunc:
            return out
        if _step_hash(env) != post_hash:
            return []

        if not _is_main_label(label):
            i += 1
            continue

        completion_labels: list[str] = []
        j = i + 1
        while j < n and not _is_main_label(best_trace[j][2]):
            fp2, sig2, label2, post_hash2 = best_trace[j]
            actions2 = env.get_legal_actions()
            if _prompt_key(env, actions2) != fp2:
                return []
            idx2 = _find_action_index_by_sig_or_label(env, actions2, sig2, label2, cid_map, name_map)
            if idx2 is None:
                return []
            _obs, term, trunc, _ = env.step(idx2)
            if term or trunc:
                break
            if _step_hash(env) != post_hash2:
                return []
            completion_labels.append(label2)
            j += 1

        out.append((label, completion_labels, before_state, _snapshot_state(env)))
        i = j
    return out


def _collect_logged_step_details_from_trace(
    env: Any,
    trace: list[tuple[str, Optional[tuple[int, ...]], str, str]],
    cid_map: dict,
    name_map: dict,
    include_chain_nodes: bool = True,
    include_all: bool = False,
) -> list[tuple[str, Optional[dict]]]:
    """
    Replay transcript and collect per-step state snapshots for log-worthy steps.
    Log-worthy = all prompt steps (when include_all), else main steps and optionally chain steps.
    """
    out: list[tuple[str, Optional[dict]]] = []
    if not trace:
        return out
    if not _reset_to_main_phase_idle(env, cid_map, name_map):
        return out
    for fp_before, sig, label, post_hash in trace:
        actions = env.get_legal_actions()
        if _prompt_key(env, actions) != fp_before:
            return []
        idx = _find_action_index_by_sig_or_label(env, actions, sig, label, cid_map, name_map)
        if idx is None:
            return []
        _obs, term, trunc, _ = env.step(idx)
        if term or trunc:
            return out
        if _step_hash(env) != post_hash:
            return []
        if include_all or _is_main_label(label) or (include_chain_nodes and _is_chain_label(label)):
            out.append((label, _snapshot_state(env)))
    return out


def _first_main_pass_index(labels: list[str]) -> Optional[int]:
    """Index of first main-phase label that is Pass / end-of-turn, or None."""
    for i, L in enumerate(labels):
        if not _is_main_label(L):
            continue
        s = (L or "").strip()
        if "Pass" in s or s.startswith("Pass") or "End" in s and "phase" in s:
            return i
    return None


def _truncate_at_turn_end(
    path: list[int], labels: list[str]
) -> tuple[list[int], list[str]]:
    """Truncate path and labels at first Pass (inclusive). Path and labels must be same length."""
    idx = _first_main_pass_index(labels)
    if idx is None:
        return path, labels
    return path[: idx + 1], labels[: idx + 1]


def _select_card_names_from_completion(completion_labels: list[str]) -> list[str]:
    """From completion step labels (Select X, Confirm, Place...), collect card names from 'Select CardName'."""
    names: list[str] = []
    for L in completion_labels:
        s = (L or "").strip()
        if s.startswith("Select ") and len(s) > 7:
            name = s[7:].strip()  # after "Select "
            if name and name != "slot" and not name.startswith("slot"):
                names.append(name)
    return names


def _completion_has_selection(completion_labels: list[str]) -> bool:
    """True if completion included a Select or Confirm step (target/material was chosen, even if we have no name)."""
    for L in completion_labels:
        s = (L or "").strip()
        if s.startswith("Select ") or s == "Confirm selection":
            return True
    return False


def _count_selection_steps(completion_labels: list[str]) -> int:
    """Number of Select steps (cards chosen); excludes Confirm so we show card count not confirm count."""
    n = 0
    for L in completion_labels:
        s = (L or "").strip()
        if s.startswith("Select "):
            n += 1
    return n


def _enrich_main_labels_with_completion(labels: list[str]) -> list[str]:
    """Enrich main labels using data/card_display_hints.json (fusion_materials, cost_send_ed, etc.)."""
    hints = _load_display_hints()
    out: list[str] = []
    i = 0
    while i < len(labels):
        L = labels[i]
        if not _is_main_label(L):
            i += 1
            continue
        completion: list[str] = []
        j = i + 1
        while j < len(labels) and not _is_main_label(labels[j]):
            completion.append(labels[j])
            j += 1
        names = _select_card_names_from_completion(completion)
        has_selection = _completion_has_selection(completion)
        n_sel = _count_selection_steps(completion)
        base = (L or "").strip()
        card_name = _card_name_from_label(base)
        hint = _get_display_hint(card_name, hints)

        if base.startswith("Activate "):
            if hint == "fusion_materials":
                if names and len(names) >= 2:
                    out.append(f"{base} (sent {', '.join(names[:2])} to GY)")
                elif names:
                    out.append(f"{base} (sent {', '.join(names)} to GY)")
                elif has_selection and n_sel >= 2:
                    out.append(f"{base} (sent {n_sel} materials to GY)")
                elif has_selection and n_sel > 0:
                    out.append(f"{base} (sent {n_sel} card{'s' if n_sel != 1 else ''} to GY)")
                else:
                    out.append(L)
            elif hint == "cost_send_ed":
                if names and len(names) >= 1:
                    out.append(f"{base} (cost: sent {names[0]} from Extra Deck to GY)")
                elif has_selection and n_sel > 0:
                    out.append(f"{base} (cost: sent 1 from Extra Deck to GY)")
                else:
                    out.append(L)
            elif hint == "sent_to_gy" or hint and hint.startswith("sent_to_gy_1"):
                # sent_to_gy_1 = send 1 card only (e.g. Albion the Shrouded Dragon)
                draw_suffix = _parse_hint_draw(hint) or ""
                if hint and hint.startswith("sent_to_gy_1"):
                    uniq = list(dict.fromkeys(names))
                    if len(uniq) == 1:
                        out.append(f"{base} (sent {uniq[0]} to GY{draw_suffix})")
                    elif has_selection and n_sel > 0:
                        out.append(f"{base} (sent 1 card to GY{draw_suffix})")
                    else:
                        out.append(L)
                else:
                    if names:
                        out.append(f"{base} (sent {', '.join(names)} to GY{draw_suffix})")
                    elif has_selection and n_sel > 0:
                        out.append(f"{base} (sent {n_sel} card{'s' if n_sel != 1 else ''} to GY{draw_suffix})")
                    else:
                        out.append(L)
            elif hint == "add_1_to_hand" or hint == "add_1_branded_st":
                if names and len(names) >= 1:
                    out.append(f"{base} (add {names[0]} to hand)")
                else:
                    suffix = " (add 1 Branded S/T to hand)" if hint == "add_1_branded_st" else " (add 1 card to hand)"
                    out.append(f"{base}{suffix}")
            elif hint == "no_target":
                out.append(L)
            else:
                target_max = _parse_hint_target_max(hint)
                banish_max = _parse_hint_banish_max(hint)
                if banish_max is not None and names:
                    show = names[:banish_max]
                    out.append(f"{base} (banish: {', '.join(show)})")
                elif banish_max is not None and has_selection and n_sel > 0:
                    n_show = min(n_sel, banish_max)
                    out.append(f"{base} (banish: {n_show} card{'s' if n_show != 1 else ''})")
                elif target_max is not None and names:
                    show = names[:target_max]
                    out.append(f"{base} (target/selected: {', '.join(show)})")
                elif target_max is not None and has_selection and n_sel > 0:
                    out.append(f"{base} (target/selected: {min(n_sel, target_max)} card{'s' if min(n_sel, target_max) != 1 else ''})")
                else:
                    # Conservative fallback: avoid guessing targets/materials for unknown effects.
                    out.append(L)
        elif base.startswith("SpSummon "):
            # Special Summon (Synchro/Fusion/Xyz/Link): materials or cost_send_ed
            if hint == "cost_send_ed":
                if names and len(names) >= 1:
                    out.append(f"{base} (cost: sent {names[0]} from Extra Deck to GY)")
                elif has_selection and n_sel > 0:
                    out.append(f"{base} (cost: sent 1 from Extra Deck to GY)")
                else:
                    out.append(L)
            elif names:
                out.append(f"{base} (materials: {_format_materials(names)})")
            elif has_selection and n_sel > 0:
                out.append(f"{base} (materials: {n_sel} card{'s' if n_sel != 1 else ''})")
            else:
                out.append(L)
        elif base.startswith("Summon "):
            # Normal Summon: no materials (we don't append completion as "materials")
            out.append(L)
        else:
            out.append(L)
        i = j
    return out


def _build_structured_main_steps(
    details: list[tuple[str, list[str], Optional[dict], Optional[dict]]],
    cid_map: dict,
    name_map: dict,
) -> list[dict]:
    """
    Build structured per-main-step info from completion labels.
    Adds selected_cards/target_cards/cost_cards for easier debugging.
    """
    hints = _load_display_hints()
    out: list[dict] = []
    for i, (main_label, completion_labels, before_state, state) in enumerate(details, 1):
        base = (main_label or "").strip()
        card_name = _card_name_from_label(base)
        hint = _get_display_hint(card_name, hints)
        selected = _select_card_names_from_completion(completion_labels)
        target_cards: list[str] = []
        cost_cards: list[str] = []
        material_cards: list[str] = []
        banish_cards: list[str] = []

        if base.startswith("SpSummon "):
            material_cards = list(selected)
        elif base.startswith("Activate "):
            if hint == "cost_send_ed":
                if selected:
                    cost_cards = [selected[0]]
            elif hint == "fusion_materials":
                material_cards = list(selected)
            else:
                bmax = _parse_hint_banish_max(hint)
                tmax = _parse_hint_target_max(hint)
                if bmax is not None:
                    banish_cards = selected[:bmax] if selected else []
                elif tmax is not None:
                    target_cards = selected[:tmax] if selected else []
                elif hint == "no_target":
                    target_cards = []
                else:
                    # Conservative fallback: if effect had selections, expose them as targets.
                    target_cards = list(selected)

        delta = summarize_state_delta(
            _state_to_named_dict(before_state, cid_map, name_map),
            _state_to_named_dict(state, cid_map, name_map),
        )

        out.append(
            {
                "step": int(i),
                "label": base,
                "selected_cards": list(selected),
                "target_cards": list(target_cards),
                "cost_cards": list(cost_cards),
                "material_cards": list(material_cards),
                "banish_cards": list(banish_cards),
                "completion": list(completion_labels),
                "state_delta": delta,
                "state": _state_to_named_dict(state, cid_map, name_map),
            }
        )
    return out


def load_code_to_type(cdb_path: Path) -> dict[str, int]:
    """Load card code -> type bitmask from cards.cdb (datas table). Returns {} if unavailable."""
    out: dict[str, int] = {}
    try:
        conn = sqlite3.connect(cdb_path)
        cur = conn.execute("SELECT id, type FROM datas")
        for row in cur.fetchall():
            out[str(row[0])] = int(row[1])
        conn.close()
    except Exception:
        pass
    return out


def run_combo_dfs(
    env: Any,
    cid_map: dict,
    name_map: dict,
    max_depth: int = 6,
    max_nodes: int = 500,
    verbose: bool = True,
    first_turn: bool = False,
    enforce_optional_activation: bool = True,
    lock_initial_player: bool = False,
    json_out: Any = None,
    json_all_out: Any = None,
    fail_fast_drift: bool = False,
    goal_mzone_codes: Optional[list[int]] = None,
    goal_szone_codes: Optional[list[int]] = None,
    goal_grave_codes: Optional[list[int]] = None,
    goal_banish_codes: Optional[list[int]] = None,
    goal_hand_codes: Optional[list[int]] = None,
    goal_hit_bonus: int = 40,
    meaningful_action_bonus: int = 5,
    action_goal_config: Optional[dict] = None,
) -> tuple[int, list[str], int]:
    """
    Run DFS from current state. Caller must have env reset and at Main Phase idle.

    Search is prompt-level: each DFS edge is one exact engine response (idle, chain, yes/no, place, select, etc.).
    This avoids drift from inferred completion policies.

    When first_turn=True, Pass in Main Phase 1 is treated as end of turn for search depth.

    If enforce_optional_activation=True, optional trigger windows are engine-driven but
    activation-preferring: Chain over don't-chain, Yes over No (when available).

    Returns (best_score, best_labels, visited_count, state_at_best). best_labels are enriched.
    state_at_best is a dict with keys hand, field_mzone, field_szone, grave, banish (lists of card_ids)
    at the end of the best path, or None if no path or replay failed.
    """
    best_score = -1
    best_labels: list[str] = []
    best_trace: list[tuple[str, Optional[tuple[int, ...]], str, str]] = []
    best_state: Optional[dict] = None  # state at best node (avoids final replay for state)
    best_so_far: dict = {"score": best_score, "labels": best_labels}
    # Root snapshot captured once; use for "Initial state" display (avoid reset during signal/summary).
    root_state: Optional[dict] = _snapshot_state(env)
    initial_to_play = env.get_to_play() if hasattr(env, "get_to_play") else None
    initial_turn_count = env.get_turn_count() if hasattr(env, "get_turn_count") else None
    # Stack: (labels, state, trace, parent_idx).
    # trace is strict transcript from root and should always end at a stable main-phase idle state.
    # parent_idx helps reconstruct the DFS tree shape in json_all debug output.
    stack: deque[
        tuple[list[str], Optional[dict], list[tuple[str, Optional[tuple[int, ...]], str, str]], Optional[int]]
    ] = deque([([], None, [], None)])
    # Persist node state by full engine-facing node identity for debugging/recovery.
    node_states: dict[tuple[Any, ...], dict] = {}
    # Transposition detection: canonical (hand, mzone, szone, grave, banish) multisets already scored.
    visited_board_states: set[tuple[tuple[int, ...], ...]] = set()
    visited = 0
    t0 = time.time()
    visited_nodes: list[dict] = []
    skip_events: list[dict] = []
    flush_every_states = 50
    flush_every_seconds = 30.0
    last_flush_visited = 0
    last_flush_time = time.time()
    goal_mzone = set(int(x) for x in (goal_mzone_codes or []))
    goal_szone = set(int(x) for x in (goal_szone_codes or []))
    goal_grave = set(int(x) for x in (goal_grave_codes or []))
    goal_banish = set(int(x) for x in (goal_banish_codes or []))
    goal_hand = set(int(x) for x in (goal_hand_codes or []))
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

    def _goal_hits_from_state(st: Optional[dict]) -> int:
        if not st:
            return 0
        hits = 0

        def _zone_hits(zone_key: str, goals: set[int]) -> int:
            if not goals:
                return 0
            n = 0
            for cid in (st.get(zone_key, []) or []):
                code = cid_map.get(int(cid), int(cid))
                if int(code) in goals:
                    n += 1
            return n

        hits += _zone_hits("field_mzone", goal_mzone)
        hits += _zone_hits("field_szone", goal_szone)
        hits += _zone_hits("grave", goal_grave)
        hits += _zone_hits("banish", goal_banish)
        hits += _zone_hits("hand", goal_hand)
        return hits

    def _count_meaningful_actions(trace_rows: list[tuple[str, Optional[tuple[int, ...]], str, str]]) -> int:
        """
        Count meaningful actions using engine signature IDs (msg_id/act_id), not label parsing.
        Meaningful:
          - select_idle actions: Set(1), MSet(5), Summon(4), SpSummon(3), Activate(8)
          - select_chain actions: any chain action except cancel/pass (act_id != 9)
        """
        n = 0
        for _fp, sig, _label, _post in (trace_rows or []):
            msg_id, act_id, _finish = _sig_msg_act(sig)
            if msg_id is None or act_id is None:
                continue
            if msg_id == 1 and act_id in (1, 5, 4, 3, 8):
                n += 1
                continue
            if msg_id == 2 and act_id != 9:
                n += 1
                continue
        return n

    def _optional_prompt_bonus(trace_rows: list[tuple[str, Optional[tuple[int, ...]], str, str]]) -> int:
        """
        Reward our-side affirmative optional prompts:
          - select_chain with act_id != 9
          - select_effectyn/select_yesno with act_id != 9
        Only count prompts taken by the initial player; opponent prompts stay neutral/passive.
        """
        bonus = 0
        for fp, sig, _label, _post in (trace_rows or []):
            msg_id, act_id, _finish = _sig_msg_act(sig)
            if msg_id is None or act_id is None:
                continue
            tp = None
            try:
                for part in str(fp).split("|"):
                    if part.startswith("tp="):
                        tp = int(part[3:])
                        break
            except Exception:
                tp = None
            if tp not in (0, 1) or initial_to_play not in (0, 1) or int(tp) != int(initial_to_play):
                continue
            if msg_id == 2 and act_id != 9:
                bonus += 14
            elif msg_id in (6, 7) and act_id != 9:
                bonus += 18
        return int(bonus)

    def _delta_tag_score(st: Optional[dict]) -> tuple[int, dict[str, int]]:
        named = _state_to_named_dict(st, cid_map, name_map)
        root_named = _state_to_named_dict(root_state, cid_map, name_map)
        delta = summarize_state_delta(root_named, named)
        tags = list(delta.get("derived_tags") or [])
        score = 0
        used: dict[str, int] = {}
        for tag in tags:
            w = int(delta_tag_weights.get(tag, 0))
            if w == 0:
                continue
            score += w
            used[tag] = w
        return int(score), used

    def _action_goal_score(all_labels: list[str]) -> tuple[int, int, int]:
        """
        Score label sequence against optional action-goal config.
        Returns (score, contains_matches, order_matches).

        Config schema:
          {
            "rules": [{"contains":"...", "bonus":80, "max_count":1}, ...],
            "order_bonus": [{"sequence":["...", "..."], "bonus":120}, ...]
          }
        """
        cfg = action_goal_config or {}
        score = 0
        contains_hits = 0
        order_hits = 0
        labels = list(all_labels or [])

        for rule in (cfg.get("rules") or []):
            if not isinstance(rule, dict):
                continue
            token = str(rule.get("contains", "")).strip()
            if not token:
                continue
            bonus = int(rule.get("bonus", 0))
            max_count = int(rule.get("max_count", 1))
            cnt = sum(1 for L in labels if token in (L or ""))
            if cnt <= 0:
                continue
            used = min(cnt, max_count if max_count > 0 else cnt)
            score += int(used) * bonus
            contains_hits += int(used)

        for rule in (cfg.get("order_bonus") or []):
            if not isinstance(rule, dict):
                continue
            seq = rule.get("sequence") or []
            if not isinstance(seq, list) or not seq:
                continue
            seq = [str(x).strip() for x in seq if str(x).strip()]
            if not seq:
                continue
            bonus = int(rule.get("bonus", 0))
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
                score += bonus
                order_hits += 1

        return int(score), int(contains_hits), int(order_hits)

    def _skip_reason_counts() -> dict[str, int]:
        out: dict[str, int] = {}
        for ev in skip_events:
            r = str(ev.get("reason", ev.get("type", "unknown")))
            out[r] = out.get(r, 0) + 1
        return out

    def _flush_progress(periodic: bool = False) -> None:
        _write_dfs_json_report(
            out_path=json_out,
            best_score=best_so_far["score"],
            best_labels=_main_phase_labels_only(list(best_so_far.get("labels", []))),
            best_prompt_labels=best_so_far.get("labels", []),
            visited=visited,
            initial_state=root_state,
            best_state=best_state,
            prompt_nodes=[],
            main_steps=[],
            cid_map=cid_map,
            name_map=name_map,
        )
        meta = {
            "best_score": int(best_so_far["score"]),
            "visited": int(visited),
            "max_depth": int(max_depth),
            "max_nodes": int(max_nodes),
            "first_turn": bool(first_turn),
            "lock_initial_player": bool(lock_initial_player),
            "goal_mzone_codes": sorted(goal_mzone),
            "goal_szone_codes": sorted(goal_szone),
            "goal_grave_codes": sorted(goal_grave),
            "goal_banish_codes": sorted(goal_banish),
            "goal_hand_codes": sorted(goal_hand),
            "goal_hit_bonus": int(goal_hit_bonus),
            "meaningful_action_bonus": int(meaningful_action_bonus),
            "has_action_goal_config": bool(action_goal_config),
            "skip_reason_counts": _skip_reason_counts(),
        }
        if periodic:
            meta["periodic_flush"] = True
        _write_dfs_json_all_report(
            out_path=json_all_out,
            meta=meta,
            visited_nodes=visited_nodes,
            skip_events=skip_events,
            cid_map=cid_map,
            name_map=name_map,
        )

    def _on_interrupt(sig: int, frame: Any) -> None:
        print("\n  [Ctrl+C] Interrupted. Best combo so far:", flush=True)
        print(f"  Score : {best_so_far['score']}", flush=True)
        main = _main_phase_labels_only(list(best_so_far["labels"]))
        _dummy_path = list(range(len(main)))
        _, main = _truncate_at_turn_end(_dummy_path, main)
        if main:
            print(f"  Path  ({len(main)} steps):", flush=True)
            for i, label in enumerate(main, 1):
                print(f"    {i}. {label}", flush=True)
            if root_state:
                print("  Initial state:", flush=True)
                print(f"    {_format_state_for_log(root_state, cid_map, name_map)}", flush=True)
            chain_details = _collect_logged_step_details_from_trace(
                env, best_trace, cid_map, name_map, include_chain_nodes=True, include_all=True
            )
            if chain_details:
                print("  Prompt nodes (all):", flush=True)
                for i, (lbl, st) in enumerate(chain_details, 1):
                    print(f"    {i}. {lbl}", flush=True)
                    print(f"       {_format_state_for_log(st, cid_map, name_map)}", flush=True)
            _write_dfs_json_report(
                out_path=json_out,
                best_score=best_so_far["score"],
                best_labels=best_so_far["labels"],
                best_prompt_labels=best_so_far.get("labels", []),
                visited=visited,
                initial_state=root_state,
                best_state=best_state,
                prompt_nodes=chain_details or [],
                main_steps=[],
                cid_map=cid_map,
                name_map=name_map,
            )
            if json_out:
                print(f"  JSON report: {Path(json_out).resolve()}", flush=True)
            _write_dfs_json_all_report(
                out_path=json_all_out,
                meta={
                    "best_score": int(best_so_far["score"]),
                    "visited": int(visited),
                    "max_depth": int(max_depth),
                    "max_nodes": int(max_nodes),
                    "first_turn": bool(first_turn),
                    "lock_initial_player": bool(lock_initial_player),
                    "goal_mzone_codes": sorted(goal_mzone),
                    "goal_szone_codes": sorted(goal_szone),
                    "goal_grave_codes": sorted(goal_grave),
                    "goal_banish_codes": sorted(goal_banish),
                    "goal_hand_codes": sorted(goal_hand),
                    "goal_hit_bonus": int(goal_hit_bonus),
                    "meaningful_action_bonus": int(meaningful_action_bonus),
                    "has_action_goal_config": bool(action_goal_config),
                    "interrupted": True,
                },
                visited_nodes=visited_nodes,
                skip_events=skip_events,
                cid_map=cid_map,
                name_map=name_map,
            )
            if json_all_out:
                print(f"  JSON all report: {Path(json_all_out).resolve()}", flush=True)
        else:
            print("  Path  : (none yet)", flush=True)
        sys.exit(0)

    try:
        signal.signal(signal.SIGINT, _on_interrupt)
    except (ValueError, OSError):
        pass  # not in main thread or signal not available

    if verbose:
        mode = " (first turn: Pass = end of turn)" if first_turn else ""
        print(f"  Starting DFS (max_depth={max_depth}, max_nodes={max_nodes}){mode}...", flush=True)
        print(f"  (Ctrl+C to stop and print best combo so far)", flush=True)

    while stack and visited < max_nodes:
        labels, state, trace, parent_idx = stack.pop()
        main_labels = _main_phase_labels_only(labels)

        if len(main_labels) > max_depth:
            skip_events.append(
                {
                    "type": "pruned_depth_limit",
                    "reason": "main_depth_gt_max_depth",
                    "max_depth": int(max_depth),
                    "main_depth": int(len(main_labels)),
                    "path_len": int(len(trace)),
                    "labels_tail": labels[-10:],
                }
            )
            continue

        # Transposition detection: skip replay entirely if this board state was already scored.
        if state is not None:
            board_key = _state_identity_key(state)
            if board_key in visited_board_states:
                skip_events.append(
                    {
                        "type": "transposition",
                        "reason": "board_state_already_visited",
                        "path_len": len(trace),
                        "labels_tail": labels[-10:],
                    }
                )
                continue

        # Replay exact sequence so env is at this node (we still need env for get_legal_actions/step)
        if verbose:
            path_str = " → ".join(labels[-5:]) if labels else "(start)"
            print(f"  [{visited+1}] pdepth={len(labels)} mdepth={len(main_labels)}  {path_str}", flush=True)

        obs, _, _ = env.reset()
        terminated = False
        replay_drift = False
        expected_trace = trace
        ok_replay, replay_reason, replay_step = _replay_trace_reasoned(env, expected_trace, cid_map, name_map)
        if not ok_replay:
            replay_drift = True
            if verbose:
                print(f"      [skip drift] transcript replay failed ({replay_reason} at step {replay_step})", flush=True)
            skip_events.append(
                {
                    "type": "replay_drift",
                    "reason": replay_reason,
                    "replay_step": int(replay_step),
                    "path_len": len(trace),
                    "labels_tail": labels[-10:],
                }
            )
            if fail_fast_drift:
                if verbose:
                    print(
                        f"  FATAL: replay drift at pdepth={len(labels)} mdepth={len(main_labels)} "
                        f"({replay_reason} at step {replay_step}). Exiting due to --fail-fast-drift.",
                        flush=True,
                    )
                _write_dfs_json_report(
                    out_path=json_out,
                    best_score=best_so_far["score"],
                    best_labels=best_so_far["labels"],
                    best_prompt_labels=best_so_far.get("labels", []),
                    visited=visited,
                    initial_state=root_state,
                    best_state=best_state,
                    prompt_nodes=[],
                    main_steps=[],
                    cid_map=cid_map,
                    name_map=name_map,
                )
                _write_dfs_json_all_report(
                    out_path=json_all_out,
                    meta={
                        "best_score": int(best_so_far["score"]),
                        "visited": int(visited),
                        "max_depth": int(max_depth),
                        "max_nodes": int(max_nodes),
                        "first_turn": bool(first_turn),
                        "lock_initial_player": bool(lock_initial_player),
                        "goal_mzone_codes": sorted(goal_mzone),
                        "goal_szone_codes": sorted(goal_szone),
                        "goal_grave_codes": sorted(goal_grave),
                        "goal_banish_codes": sorted(goal_banish),
                        "goal_hand_codes": sorted(goal_hand),
                        "goal_hit_bonus": int(goal_hit_bonus),
                        "meaningful_action_bonus": int(meaningful_action_bonus),
                        "has_action_goal_config": bool(action_goal_config),
                        "fail_fast_drift": True,
                        "fatal_drift": {
                            "reason": replay_reason,
                            "replay_step": int(replay_step),
                            "path_len": len(trace),
                            "labels_tail": labels[-10:],
                        },
                    },
                    visited_nodes=visited_nodes,
                    skip_events=skip_events,
                    cid_map=cid_map,
                    name_map=name_map,
                )
                raise RuntimeError(
                    f"DFS replay drift: {replay_reason} at step {replay_step} (pdepth={len(labels)} mdepth={len(main_labels)})"
                )
        if replay_drift:
            continue

        # State at this node: prefer stack payload, then fresh snapshot. Node-state lookup uses the
        # stronger node key built after replay, not just labels.
        if state is None:
            state = _snapshot_state(env)
        # Hard turn boundary for turn-1 DFS: do not score/expand states outside initial turn.
        if first_turn and initial_turn_count is not None and hasattr(env, "get_turn_count"):
            turn_now = env.get_turn_count()
            if turn_now is not None and int(turn_now) != int(initial_turn_count):
                skip_events.append(
                    {
                        "type": "turn_boundary",
                        "reason": "turn_count_changed",
                        "initial_turn_count": int(initial_turn_count),
                        "turn_count": int(turn_now),
                        "path_len": len(trace),
                        "labels_tail": labels[-10:],
                    }
                )
                continue
        actions = env.get_legal_actions()
        node_key = _node_key(env, actions, state)
        if state is None:
            state = node_states.get(node_key)
        if state is not None:
            node_states[node_key] = state
        if verbose:
            print(f"      {_format_state_for_log(state, cid_map, name_map)}", flush=True)

        visited += 1
        # Mark this board state as scored so duplicate routes are skipped.
        if state is not None:
            visited_board_states.add(_state_identity_key(state))
        obs = env.get_obs()
        board_score = evaluate_line(obs, labels)
        goal_hits = _goal_hits_from_state(state)
        meaningful_actions = _count_meaningful_actions(expected_trace)
        action_goal_score, action_goal_contains_hits, action_goal_order_hits = _action_goal_score(labels)
        optional_prompt_score = _optional_prompt_bonus(expected_trace)
        delta_tag_score, delta_tag_breakdown = _delta_tag_score(state)
        base_score = int(
            int(goal_hit_bonus) * int(goal_hits)
            + int(meaningful_action_bonus) * int(meaningful_actions)
            + int(action_goal_score)
            + int(optional_prompt_score)
            + int(delta_tag_score)
        )
        score = int(base_score)
        trace_meta: list[dict[str, Any]] = []
        if json_all_out:
            for fp_before, sig, tlabel, post_hash in (trace or []):
                msg_id, act_id, finish = _sig_msg_act(sig)
                trace_meta.append(
                    {
                        "fp": fp_before,
                        "msg_id": msg_id,
                        "act_id": act_id,
                        "finish": finish,
                        "label": tlabel,
                        "post_hash": post_hash,
                    }
                )
        visited_nodes.append(
            {
                "idx": visited,
                "parent_idx": parent_idx,
                "prompt_depth": len(labels),
                "main_depth": len(main_labels),
                "score": int(score),
                "base_score": int(base_score),
                "board_score_ignored": int(board_score),
                "goal_hits": int(goal_hits),
                "meaningful_actions": int(meaningful_actions),
                "action_goal_score": int(action_goal_score),
                "action_goal_contains_hits": int(action_goal_contains_hits),
                "action_goal_order_hits": int(action_goal_order_hits),
                "optional_prompt_score": int(optional_prompt_score),
                "delta_tag_score": int(delta_tag_score),
                "delta_tag_breakdown": dict(delta_tag_breakdown),
                "labels": list(labels),
                "state": _state_to_named_dict(state, cid_map, name_map),
                "node_key": {
                    "state": [list(zone) for zone in _state_identity_key(state)],
                    "to_play": int(env.get_to_play()) if hasattr(env, "get_to_play") and env.get_to_play() in (0, 1) else None,
                    "turn_count": int(env.get_turn_count()) if hasattr(env, "get_turn_count") and env.get_turn_count() is not None else None,
                    "phase": env.get_current_phase() if hasattr(env, "get_current_phase") else None,
                    "msg_id": _current_msg_id(env, actions),
                    "legal_action_signatures": [list(sig) for sig in _legal_action_signature_key(env, actions)],
                },
                "to_play": int(env.get_to_play()) if hasattr(env, "get_to_play") and env.get_to_play() in (0, 1) else None,
                "turn_count": int(env.get_turn_count()) if hasattr(env, "get_turn_count") and env.get_turn_count() is not None else None,
                "phase": env.get_current_phase() if hasattr(env, "get_current_phase") else None,
                "stop_reason": None,
                "trace_meta": trace_meta,
            }
        )
        now = time.time()
        if (
            visited - last_flush_visited >= flush_every_states
            or (now - last_flush_time) >= flush_every_seconds
        ):
            _flush_progress(periodic=True)
            last_flush_visited = visited
            last_flush_time = now
        if score > best_score:
            best_score = score
            best_labels = list(labels)
            best_trace = list(expected_trace)
            best_state = state  # keep state at best node so we don't need to replay at end
            best_so_far["score"] = score
            best_so_far["labels"] = list(labels)
            if verbose:
                path_str = " → ".join(labels[-5:]) if labels else "(initial state)"
                print(
                    f"  ★ NEW BEST  pdepth={len(labels)} mdepth={len(main_labels)}  score={score}  {path_str}",
                    flush=True,
                )

        if lock_initial_player and initial_to_play in (0, 1) and hasattr(env, "get_to_play"):
            cur_to_play = env.get_to_play()
            if cur_to_play in (0, 1) and int(cur_to_play) != int(initial_to_play):
                passive = _passive_actions(env, actions, cid_map, name_map)
                if passive:
                    actions = passive
        actions = _preferred_optional_actions(
            env, actions, cid_map, name_map, enforce_optional_activation=enforce_optional_activation
        )
        at_leaf = terminated or len(main_labels) >= max_depth or not actions

        if at_leaf:
            # Keep leaf stop reasons inside visited nodes so json_all can explain "why we stopped"
            # without requiring replay-based inference.
            if len(main_labels) >= max_depth:
                visited_nodes[-1]["stop_reason"] = "depth_limit"
            elif not actions:
                visited_nodes[-1]["stop_reason"] = "no_legal_actions"
            elif terminated:
                visited_nodes[-1]["stop_reason"] = "terminated_or_truncated"
            else:
                visited_nodes[-1]["stop_reason"] = "leaf"
            continue

        # Expand by main-phase action, then auto-resolve engine prompts until the next
        # stable main-phase idle state. Optional trigger windows may still branch.
        main_actions: list[tuple[int, str, Optional[tuple[int, ...]], str]] = []
        fp_before_main = _prompt_key(env, actions)
        for a in actions:
            feat = env.action_features(a)
            label = decode_action_features(feat, cid_map, name_map) if feat else f"action_{a}"
            if not _is_main_label(label):
                continue
            main_actions.append((a, label, _action_sig(feat), fp_before_main))

        if not main_actions:
            visited_nodes[-1]["stop_reason"] = "no_main_actions"
            continue

        for a, label, main_sig, fp_before_main in reversed(main_actions):
            turn_before = (
                int(env.get_turn_count())
                if first_turn
                and hasattr(env, "get_turn_count")
                and env.get_turn_count() is not None
                else None
            )
            obs, term, trunc, _ = env.step(a)
            # In first-turn mode we want setup-only behavior:
            # if a main action advances the engine to the next turn, do not
            # record/expand that node. This prevents the post-`Pass` draw
            # from showing up in the best path state snapshot.
            if (
                first_turn
                and turn_before is not None
                and hasattr(env, "get_turn_count")
                and env.get_turn_count() is not None
                and int(env.get_turn_count()) != int(turn_before)
            ):
                env.reset()
                _replay_trace(env, expected_trace, cid_map, name_map)
                continue
            if term or trunc:
                env.reset()
                _replay_trace(env, expected_trace, cid_map, name_map)
                continue

            main_post_hash = _step_hash(env)
            main_step = (fp_before_main, main_sig, label, main_post_hash)
            trace_after_main = expected_trace + [main_step]

            completion_variants = _expand_completion_variants(
                env,
                trace_after_main,
                cid_map,
                name_map,
                first_turn=first_turn,
                enforce_optional_activation=enforce_optional_activation,
                lock_initial_player=lock_initial_player,
                initial_to_play=initial_to_play,
            )
            if not completion_variants:
                completion_variants = [([], _snapshot_state(env))]

            for completion_steps, state_child in reversed(completion_variants):
                child_trace = trace_after_main + list(completion_steps)
                child_labels = labels + [label] + [step_label for _fp, _sig, step_label, _post in completion_steps]
                if state_child is not None:
                    replay_ok = _replay_trace(env, child_trace, cid_map, name_map)
                    if replay_ok:
                        child_actions = env.get_legal_actions()
                        child_node_key = _node_key(env, child_actions, state_child)
                        node_states[child_node_key] = state_child
                stack.append((child_labels, state_child, child_trace, visited))

            # Restore state for next sibling
            obs, _, _ = env.reset()
            _replay_trace(env, expected_trace, cid_map, name_map)

    elapsed = time.time() - t0
    best_prompt = list(best_labels)
    main_best = _main_phase_labels_only(best_prompt)
    # Don't show or return main actions after first main pass/end.
    _dummy_path = list(range(len(main_best)))
    _, main_best = _truncate_at_turn_end(_dummy_path, main_best)
    # State at best node was stored when we updated best (no replay needed)
    state_at_best = best_state
    if verbose:
        print(flush=True)
        print(f"  ── DFS result ─────────────────────────────────", flush=True)
        transposition_skips = sum(1 for e in skip_events if e.get("type") == "transposition")
        print(f"  Explored : {visited} states in {elapsed:.2f}s", flush=True)
        print(f"  Tracked node states : {len(node_states)}", flush=True)
        if transposition_skips:
            print(f"  Transposition skips : {transposition_skips}", flush=True)
        print(f"  Best score : {best_score}", flush=True)
        if main_best:
            print(f"  Best path  ({len(main_best)} steps):", flush=True)
            for i, label in enumerate(main_best, 1):
                print(f"    {i}. {label}", flush=True)
        else:
            print("  Best path  : (no actions)", flush=True)
        if root_state:
            print("  Initial state:", flush=True)
            print(f"    {_format_state_for_log(root_state, cid_map, name_map)}", flush=True)
        chain_details = _collect_logged_step_details_from_trace(
            env, best_trace, cid_map, name_map, include_chain_nodes=True, include_all=True
        )
        if chain_details:
            print("  Prompt nodes (all):", flush=True)
            for i, (lbl, st) in enumerate(chain_details, 1):
                print(f"    {i}. {lbl}", flush=True)
                print(f"       {_format_state_for_log(st, cid_map, name_map)}", flush=True)
        _write_dfs_json_report(
            out_path=json_out,
            best_score=best_score,
            best_labels=main_best,
            best_prompt_labels=best_prompt,
            visited=visited,
            initial_state=root_state,
            best_state=state_at_best,
            prompt_nodes=chain_details or [],
            main_steps=_build_structured_main_steps(
                _collect_best_main_step_details_from_trace(env, best_trace, cid_map, name_map),
                cid_map,
                name_map,
            ),
            cid_map=cid_map,
            name_map=name_map,
        )
        if json_out:
            print(f"  JSON report: {Path(json_out).resolve()}", flush=True)

        skip_reason_counts: dict[str, int] = {}
        for ev in skip_events:
            r = str(ev.get("reason", ev.get("type", "unknown")))
            skip_reason_counts[r] = skip_reason_counts.get(r, 0) + 1
        _write_dfs_json_all_report(
            out_path=json_all_out,
            meta={
                "best_score": int(best_score),
                "visited": int(visited),
                "max_depth": int(max_depth),
                "max_nodes": int(max_nodes),
                "first_turn": bool(first_turn),
                "lock_initial_player": bool(lock_initial_player),
                "goal_mzone_codes": sorted(goal_mzone),
                "goal_szone_codes": sorted(goal_szone),
                "goal_grave_codes": sorted(goal_grave),
                "goal_banish_codes": sorted(goal_banish),
                "goal_hand_codes": sorted(goal_hand),
                "goal_hit_bonus": int(goal_hit_bonus),
                "meaningful_action_bonus": int(meaningful_action_bonus),
                "has_action_goal_config": bool(action_goal_config),
                "skip_reason_counts": skip_reason_counts,
            },
            visited_nodes=visited_nodes,
            skip_events=skip_events,
            cid_map=cid_map,
            name_map=name_map,
        )
        if json_all_out:
            print(f"  JSON all report: {Path(json_all_out).resolve()}", flush=True)
        if state_at_best:
            print("  State at best:", flush=True)
            print(f"    {_format_state_for_log(state_at_best, cid_map, name_map)}", flush=True)
            print(
                f"    hand_count={len(state_at_best.get('hand', []))} "
                f"field_m_count={len(state_at_best.get('field_mzone', []))} "
                f"field_s_count={len(state_at_best.get('field_szone', []))} "
                f"grave_count={len(state_at_best.get('grave', []))} "
                f"banish_count={len(state_at_best.get('banish', []))}",
                flush=True,
            )

    return best_score, main_best, visited, state_at_best

