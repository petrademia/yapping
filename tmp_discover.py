import json
import random
from pathlib import Path

from vocal_chords.wrapper import YgoEnvWrapper
from vocal_chords.idle import wait_until_main_phase_idle
from brain.search import run_combo_dfs, load_code_to_type

_HERE = Path(__file__).resolve().parent
_YGO_ROOT = _HERE / "vendor" / "ygo-env"
_DECK = _YGO_ROOT / "assets" / "deck" / "Branded.ydk"


# ── helpers ────────────────────────────────────────────────────────────────

def load_card_id_to_code(ygo_root: Path) -> dict:
    """1-based code_list.txt line index → card code (matches engine card_id encoding)."""
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


def load_code_to_name(yapping_root: Path) -> dict:
    """str(card_code) → card name from scripture/card_code_to_name.json."""
    db_path = yapping_root / "scripture" / "card_code_to_name.json"
    if not db_path.exists():
        return {}
    with open(db_path, encoding="utf-8") as f:
        return json.load(f)


def hand_names(env: YgoEnvWrapper, cid_map: dict, name_map: dict) -> list[str]:
    """Return readable names for the current hand."""
    hand = env.get_hand()
    names = []
    for cid in hand:
        code = cid_map.get(cid, cid)
        names.append(name_map.get(str(code), f"#{code}"))
    return names


# ── search ─────────────────────────────────────────────────────────────────

def search_combo(
    env_root: Path,
    deck_path: Path,
    seed: int,
    max_depth: int = 5,
    max_nodes: int = 500,
    cid_map: dict | None = None,
    name_map: dict | None = None,
):
    cid_map = cid_map or load_card_id_to_code(env_root)
    name_map = name_map or load_code_to_name(_HERE)

    env = YgoEnvWrapper(deck_path=deck_path, ygo_env_root=env_root, seed=seed)

    obs, _, _ = env.reset()
    if not wait_until_main_phase_idle(env, cid_map, name_map):
        print("  (Could not reach Main Phase idle after reset; continuing with current state.)")
    hand_str = ", ".join(hand_names(env, cid_map, name_map))
    print(f"  Hand     : {hand_str}")
    print(f"  DFS      : max_depth={max_depth}  max_nodes={max_nodes} (from Main Phase)")
    print()

    cdb_path = env_root / "assets" / "locale" / "en" / "cards.cdb"
    code_to_type = load_code_to_type(cdb_path) if cdb_path.is_file() else None
    run_combo_dfs(
        env, cid_map, name_map,
        max_depth=max_depth, max_nodes=max_nodes, verbose=True, first_turn=True,
        code_to_type=code_to_type,
    )


# ── main ───────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    N_HANDS   = 3
    MAX_DEPTH = 6
    MAX_NODES = 500   # total DFS nodes per hand (increase for deeper search)

    print("Loading card data...", end="", flush=True)
    cid_map  = load_card_id_to_code(_YGO_ROOT)
    name_map = load_code_to_name(_HERE)
    print(f"  {len(cid_map):,} code_list entries, {len(name_map):,} card names\n")

    for i in range(N_HANDS):
        seed = random.randint(1000, 999_999)
        print("=" * 52)
        print(f"  Hand {i+1} / {N_HANDS}   seed={seed}")
        print("=" * 52)
        search_combo(
            env_root=_YGO_ROOT,
            deck_path=_DECK,
            seed=seed,
            max_depth=MAX_DEPTH,
            max_nodes=MAX_NODES,
            cid_map=cid_map,
            name_map=name_map,
        )
        print()
