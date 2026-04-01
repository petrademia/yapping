"""
Scripted combo execution.

Each step in a recipe is a dict with two fields:
  "label" - human-readable action label (e.g. "Summon Fallen of Albaz")
  "sig"   - 12-int action signature from the engine feature row

Matching order (most to least specific):
  1. sig exact match         <- deterministic, seed/hand independent
  2. label exact match
  3. label case-insensitive exact
  4. label prefix  (e.g. "Summon Albaz" matches "Summon Fallen of Albaz")
  5. label contains

Plain strings are also accepted as steps (sig omitted, label-only).

Recipes are recorded by `cli combo-record` which captures both fields
automatically — users never need to write sigs by hand.

Usage
-----
    from brain.combo import run_combo_from_recipe, load_recipe

    recipe = load_recipe("data/combos/branded_fusion.json")
    result = run_combo_from_recipe(recipe, env, cid_map, name_map)
    print(result)
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional, Union

from engine.actions import decode_action_features
from brain.search import _reset_to_main_phase_idle, _snapshot_state, _action_sig, _prompt_key, _step_hash, _replay_trace_reasoned


# ---------------------------------------------------------------------------
# Step normalisation
# ---------------------------------------------------------------------------

# A step in a recipe: either a plain string label or {"label": ..., "sig": [...]}
RecipeStep = Union[str, dict]


def _parse_step(step: RecipeStep) -> tuple[Optional[tuple[int, ...]], str]:
    """Return (sig_or_None, label) from a recipe step."""
    if isinstance(step, str):
        return None, step
    sig_raw = step.get("sig")
    sig = tuple(int(x) for x in sig_raw) if sig_raw else None
    return sig, step.get("label", "")


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------

@dataclass
class StepResult:
    input_label: str        # label from recipe
    matched_label: str      # label the engine resolved to
    action_idx: int
    sig: Optional[tuple[int, ...]]  # signature of the matched action
    board: dict             # zone snapshot after this step resolves

    def __str__(self) -> str:
        if self.input_label == self.matched_label:
            return f"  [ok] {self.matched_label}"
        return f"  [ok] {self.input_label!r} -> {self.matched_label!r}"


@dataclass
class ComboResult:
    success: bool
    steps: list[StepResult] = field(default_factory=list)
    board: dict = field(default_factory=dict)
    failed_at: Optional[int] = None
    error: Optional[str] = None
    legal_at_failure: list[str] = field(default_factory=list)

    def __str__(self) -> str:
        lines = [str(s) for s in self.steps]
        if self.success:
            lines.append(f"  Result: OK  ({len(self.steps)} steps)")
        else:
            lines.append(f"  Result: FAILED at step {self.failed_at} ({self.error})")
            if self.legal_at_failure:
                lines.append("  Legal actions at failure:")
                for lbl in self.legal_at_failure:
                    lines.append(f"    - {lbl}")
        return "\n".join(lines)


@dataclass
class ComboReplayValidation:
    success: bool
    result: ComboResult
    trace: list[tuple[str, Optional[tuple[int, ...]], str, str]] = field(default_factory=list)
    replay_ok: bool = False
    replay_reason: str = ""
    replay_step: int = 0


# ---------------------------------------------------------------------------
# Action picking
# ---------------------------------------------------------------------------

def _label_priority(expected: str, actual: str) -> int:
    """Match priority 0-3 (lower=better), -1 if no match."""
    s, a = expected.strip(), actual.strip()
    if not s:
        return -1
    if s == a:
        return 0
    if s.lower() == a.lower():
        return 1
    if a.lower().startswith(s.lower()):
        return 2
    if s.lower() in a.lower():
        return 3
    return -1


def _pick_action(
    env: Any,
    actions: list[int],
    expected_sig: Optional[tuple[int, ...]],
    expected_label: str,
    cid_map: dict,
    name_map: dict,
) -> Optional[tuple[int, str, tuple[int, ...]]]:
    """
    Return (action_idx, matched_label, sig) for the best match, or None.
    Tries sig exact match first, then label fuzzy match.
    """
    # 1. Signature match (deterministic)
    if expected_sig is not None:
        for idx in actions:
            feat = env.action_features(idx)
            sig = _action_sig(feat)
            if sig == expected_sig:
                label = decode_action_features(feat, cid_map, name_map) if feat is not None else f"action_{idx}"
                return idx, label, sig

    # 2. Label fuzzy match
    candidates: list[tuple[int, str, tuple[int, ...], int]] = []
    for idx in actions:
        feat = env.action_features(idx)
        label = decode_action_features(feat, cid_map, name_map) if feat is not None else f"action_{idx}"
        sig = _action_sig(feat) or ()
        priority = _label_priority(expected_label, label)
        if priority >= 0:
            candidates.append((idx, label, sig, priority))

    if not candidates:
        return None
    candidates.sort(key=lambda x: (x[3], x[0]))
    idx, label, sig, _ = candidates[0]
    return idx, label, sig


def _legal_labels(env: Any, actions: list[int], cid_map: dict, name_map: dict) -> list[str]:
    out = []
    for idx in actions:
        feat = env.action_features(idx)
        out.append(decode_action_features(feat, cid_map, name_map) if feat is not None else f"action_{idx}")
    return out


# ---------------------------------------------------------------------------
# Core runner
# ---------------------------------------------------------------------------

def run_combo(
    env: Any,
    steps: list[RecipeStep],
    cid_map: dict,
    name_map: dict,
) -> ComboResult:
    """
    Execute a scripted combo sequence.  The env must already be at main-phase
    idle (call _reset_to_main_phase_idle first, or use run_combo_from_recipe).

    Each step may be a plain string label or {"label": ..., "sig": [...]}.
    Signature match is tried first; label fuzzy match is the fallback.
    """
    result_steps: list[StepResult] = []
    board: dict = _snapshot_state(env) or {}

    for i, raw_step in enumerate(steps):
        expected_sig, expected_label = _parse_step(raw_step)
        actions = env.get_legal_actions()

        if not actions:
            return ComboResult(
                success=False, steps=result_steps, board=board,
                failed_at=i, error="no_legal_actions",
            )

        match = _pick_action(env, actions, expected_sig, expected_label, cid_map, name_map)
        if match is None:
            return ComboResult(
                success=False, steps=result_steps, board=board,
                failed_at=i, error=f"no_match: {expected_label!r}",
                legal_at_failure=_legal_labels(env, actions, cid_map, name_map),
            )

        action_idx, matched_label, matched_sig = match
        _obs, terminated, truncated, _ = env.step(action_idx)
        board = _snapshot_state(env) or {}

        result_steps.append(StepResult(
            input_label=expected_label,
            matched_label=matched_label,
            action_idx=action_idx,
            sig=matched_sig,
            board=dict(board),
        ))

        if (terminated or truncated) and i < len(steps) - 1:
            return ComboResult(
                success=False, steps=result_steps, board=board,
                failed_at=i, error="game_ended_early",
            )

    return ComboResult(success=True, steps=result_steps, board=board)


def run_combo_with_trace(
    env: Any,
    steps: list[RecipeStep],
    cid_map: dict,
    name_map: dict,
) -> tuple[ComboResult, list[tuple[str, Optional[tuple[int, ...]], str, str]]]:
    """
    Execute a scripted combo sequence and also capture a strict replay transcript:
    (prompt_key_before, action_sig, matched_label, post_step_hash).
    """
    result_steps: list[StepResult] = []
    trace: list[tuple[str, Optional[tuple[int, ...]], str, str]] = []
    board: dict = _snapshot_state(env) or {}

    for i, raw_step in enumerate(steps):
        expected_sig, expected_label = _parse_step(raw_step)
        actions = env.get_legal_actions()

        if not actions:
            return ComboResult(
                success=False, steps=result_steps, board=board,
                failed_at=i, error="no_legal_actions",
            ), trace

        match = _pick_action(env, actions, expected_sig, expected_label, cid_map, name_map)
        if match is None:
            return ComboResult(
                success=False, steps=result_steps, board=board,
                failed_at=i, error=f"no_match: {expected_label!r}",
                legal_at_failure=_legal_labels(env, actions, cid_map, name_map),
            ), trace

        prompt_before = _prompt_key(env, actions)
        action_idx, matched_label, matched_sig = match
        _obs, terminated, truncated, _ = env.step(action_idx)
        post_hash = _step_hash(env)
        board = _snapshot_state(env) or {}

        trace.append((prompt_before, matched_sig, matched_label, post_hash))
        result_steps.append(StepResult(
            input_label=expected_label,
            matched_label=matched_label,
            action_idx=action_idx,
            sig=matched_sig,
            board=dict(board),
        ))

        if (terminated or truncated) and i < len(steps) - 1:
            return ComboResult(
                success=False, steps=result_steps, board=board,
                failed_at=i, error="game_ended_early",
            ), trace

    return ComboResult(success=True, steps=result_steps, board=board), trace


# ---------------------------------------------------------------------------
# Recipe helpers
# ---------------------------------------------------------------------------

def load_recipe(path: str | Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def run_combo_from_recipe(
    recipe: dict,
    env: Any,
    cid_map: dict,
    name_map: dict,
) -> ComboResult:
    """Reset env (using recipe seed if present) then execute all steps."""
    seed = recipe.get("seed")
    if seed is not None:
        env._seed = int(seed)
    if not _reset_to_main_phase_idle(env, cid_map, name_map):
        return ComboResult(success=False, error="failed_to_reach_main_phase_idle")
    return run_combo(env, recipe.get("steps", []), cid_map, name_map)


def validate_recipe_replay(
    recipe: dict,
    env: Any,
    cid_map: dict,
    name_map: dict,
) -> ComboReplayValidation:
    """
    Execute the recipe, capture a strict trace, then replay it from root with
    prompt/action/hash validation.
    """
    seed = recipe.get("seed")
    if seed is not None:
        env._seed = int(seed)
    if not _reset_to_main_phase_idle(env, cid_map, name_map):
        result = ComboResult(success=False, error="failed_to_reach_main_phase_idle")
        return ComboReplayValidation(success=False, result=result, replay_ok=False, replay_reason=result.error or "")

    result, trace = run_combo_with_trace(env, recipe.get("steps", []), cid_map, name_map)
    if not result.success:
        return ComboReplayValidation(
            success=False,
            result=result,
            trace=trace,
            replay_ok=False,
            replay_reason=result.error or "combo_failed",
            replay_step=(result.failed_at + 1) if result.failed_at is not None else 0,
        )

    replay_ok, replay_reason, replay_step = _replay_trace_reasoned(env, trace, cid_map, name_map)
    return ComboReplayValidation(
        success=result.success and replay_ok,
        result=result,
        trace=trace,
        replay_ok=replay_ok,
        replay_reason=replay_reason,
        replay_step=replay_step,
    )


def record_combo(
    env: Any,
    cid_map: dict,
    name_map: dict,
) -> list[dict]:
    """
    Interactive loop: show legal actions, let the user pick one, record
    {"label": ..., "sig": [...]} for each choice.  Returns the recorded steps.

    Type the action number to pick it, or 'done' / empty to finish.
    """
    recorded: list[dict] = []

    while True:
        actions = env.get_legal_actions()
        if not actions:
            print("  (no legal actions — stopping)")
            break

        print()
        for i, idx in enumerate(actions):
            feat = env.action_features(idx)
            label = decode_action_features(feat, cid_map, name_map) if feat is not None else f"action_{idx}"
            print(f"  {i:2d}. {label}")

        raw = input("\n  Pick action number (or 'done'): ").strip()
        if raw.lower() in ("done", "d", "q", ""):
            break

        try:
            choice = int(raw)
        except ValueError:
            print("  Invalid input — enter a number or 'done'.")
            continue

        if choice < 0 or choice >= len(actions):
            print(f"  Out of range (0-{len(actions)-1}).")
            continue

        idx = actions[choice]
        feat = env.action_features(idx)
        label = decode_action_features(feat, cid_map, name_map) if feat is not None else f"action_{idx}"
        sig = _action_sig(feat)

        env.step(idx)
        recorded.append({"label": label, "sig": list(sig) if sig else []})
        print(f"  Recorded: {label}")

    return recorded
