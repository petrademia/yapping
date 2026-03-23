"""
Main Phase idle detection and wait.

Shared logic for "wait until we're in Main Phase" (select_idle with Summon/MSet/Set/Activate).
Used by hand simulator and BFS combo discover so both show the full Main Phase menu.
"""

from __future__ import annotations

from collections import defaultdict

from engine.actions import decode_action_features

# msg_to_id: 1 = select_idle (IDLECMD), 2 = select_chain, ...
MSG_SELECT_IDLE = 1


def _action_report(env, cid_map, name_map) -> dict:
    """Summary of current legal actions: by_prefix, total, msg_to_id (for idle detection)."""
    legal = env.get_legal_actions()
    by_prefix = defaultdict(int)
    msg_to_id = 0
    for idx in legal:
        feat = env.action_features(idx)
        if feat is not None and len(feat) >= 4 and int(feat[3]) != 0 and msg_to_id == 0:
            msg_to_id = int(feat[3])
        label = decode_action_features(feat, cid_map, name_map) if feat else f"action_{idx}"
        prefix = label.split()[0] if label else "?"
        by_prefix[prefix] += 1
    return {"by_prefix": dict(by_prefix), "total": len(legal), "msg_to_id": msg_to_id}


def _is_main_phase_idle(env, report: dict) -> bool:
    """True if we're in Main Phase idle (select_idle with Summon/MSet/Set/Activate), not Draw/chain.

    Prefers env.get_current_phase() if the engine exposes it. Otherwise uses msg_to_id=1
    plus at least one main-phase action (Summon, MSet, Set, Activate)."""
    phase = env.get_current_phase() if hasattr(env, "get_current_phase") else None
    if phase is not None:
        return phase in ("main1", "main2", "main")
    if report["msg_to_id"] != MSG_SELECT_IDLE:
        return False
    prefixes = set(report["by_prefix"].keys())
    return bool(prefixes & {"Summon", "MSet", "Set", "Activate"})


def _pass_or_cancel_index(env, cid_map, name_map) -> int | None:
    """Index of Pass/Cancel action (act_id 9 or label Pass), or last action."""
    legal = env.get_legal_actions()
    for idx in legal:
        feat = env.action_features(idx)
        if feat is not None and len(feat) >= 5 and int(feat[4]) == 9:
            return idx
        label = decode_action_features(feat, cid_map, name_map) if feat else ""
        if "Pass" in label or "don't chain" in label.lower():
            return idx
    if legal:
        return legal[-1]
    return None


def wait_until_main_phase_idle(
    env, cid_map, name_map, max_steps: int = 10, verbose: bool = False
) -> bool:
    """Step Pass/Cancel until Main Phase idle (Summon/Set/Activate menu) or max_steps. Returns True if reached.
    When verbose=True, print each step and current options (e.g. Pass only vs Main Phase menu)."""
    for step in range(1, max_steps + 1):
        report = _action_report(env, cid_map, name_map)
        opts = ", ".join(sorted(report["by_prefix"].keys())) or "—"
        if _is_main_phase_idle(env, report):
            if verbose:
                print(f"  [idle] step {step}: Main Phase idle  (options: {opts})")
            return True
        idx = _pass_or_cancel_index(env, cid_map, name_map)
        if idx is None:
            if verbose:
                print(f"  [idle] step {step}: no Pass action, stopping")
            return False
        if verbose:
            print(f"  [idle] step {step}: Pass  (options: {opts})")
        _obs, term, trunc, _ = env.step(idx)
        if term or trunc:
            if verbose:
                print(f"  [idle] step {step}: game ended")
            return False
    if verbose:
        print(f"  [idle] step {max_steps}: max steps reached, not in Main Phase")
    return False


def _first_non_pass_index(env, cid_map, name_map) -> int | None:
    """First legal action that is not Pass/Cancel (for completing place/card selection)."""
    legal = env.get_legal_actions()
    for idx in legal:
        feat = env.action_features(idx)
        if feat is not None and len(feat) >= 5 and int(feat[4]) == 9:
            continue
        label = decode_action_features(feat, cid_map, name_map) if feat else ""
        if "Pass" in label or "don't chain" in label.lower():
            continue
        return idx
    return None


def complete_until_main_phase_idle(
    env, cid_map, name_map, max_steps: int = 20
) -> bool:
    """After taking an action (e.g. Summon), we may be in SELECT_PLACE or similar.
    Step through by taking the first non-Pass choice (e.g. pick a zone) until we're
    back at Main Phase idle. Use this in BFS so 'next state' is actually reached."""
    for _ in range(max_steps):
        report = _action_report(env, cid_map, name_map)
        if _is_main_phase_idle(env, report):
            return True
        idx = _first_non_pass_index(env, cid_map, name_map)
        if idx is not None:
            _obs, term, trunc, _ = env.step(idx)
            if term or trunc:
                return False
            continue
        idx = _pass_or_cancel_index(env, cid_map, name_map)
        if idx is None:
            return False
        _obs, term, trunc, _ = env.step(idx)
        if term or trunc:
            return False
    return False


def complete_until_main_phase_idle_recorded(
    env, cid_map, name_map, max_steps: int = 20
) -> tuple[bool, list[tuple[int, str]]]:
    """Same as complete_until_main_phase_idle but returns the sequence of (action_index, label) taken.

    Use this in DFS so we can replay the exact same completion and avoid state drift
    (e.g. different Branded Fusion materials → different board → wrong action indices)."""
    recorded: list[tuple[int, str]] = []
    for _ in range(max_steps):
        report = _action_report(env, cid_map, name_map)
        if _is_main_phase_idle(env, report):
            return True, recorded
        idx = _first_non_pass_index(env, cid_map, name_map)
        if idx is not None:
            feat = env.action_features(idx) if hasattr(env, "action_features") else None
            label = decode_action_features(feat, cid_map, name_map) if feat else f"action_{idx}"
            recorded.append((idx, label))
            _obs, term, trunc, _ = env.step(idx)
            if term or trunc:
                return False, recorded
            continue
        idx = _pass_or_cancel_index(env, cid_map, name_map)
        if idx is None:
            return False, recorded
        feat = env.action_features(idx) if hasattr(env, "action_features") else None
        label = decode_action_features(feat, cid_map, name_map) if feat else f"action_{idx}"
        recorded.append((idx, label))
        _obs, term, trunc, _ = env.step(idx)
        if term or trunc:
            return False, recorded
    return False, recorded
