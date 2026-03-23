"""
Mappings for Selection / Activation logic.

Translates between high-level "do this with these cards" and the
low-level action codes expected by ygo-env (e.g. select card index,
activate, set, summon). Used by wrapper and search to enumerate
and apply legal moves.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Lookup tables derived from ygopro.h
# ---------------------------------------------------------------------------

# msg_to_id: 1-based index into the _msgs vector (make_ids with id_offset=1)
# _msgs = [IDLECMD, CHAIN, CARD, TRIBUTE, POSITION, EFFECTYN, YESNO,
#          BATTLECMD, UNSELECT_CARD, OPTION, PLACE, SUM, DISFIELD,
#          ANNOUNCE_ATTRIB, ANNOUNCE_NUMBER, ANNOUNCE_CARD]
_ID_TO_MSG: dict[int, str] = {
    0:  "none",
    1:  "select_idle",
    2:  "select_chain",
    3:  "select_card",
    4:  "select_tribute",
    5:  "select_position",
    6:  "select_effectyn",
    7:  "select_yesno",
    8:  "select_battle",
    9:  "select_unselect",
    10: "select_option",
    11: "select_place",
    12: "select_sum",
    13: "select_disfield",
    14: "announce_attrib",
    15: "announce_number",
    16: "announce_card",
}

# ActionAct enum (0-based, matches C++ enum class ActionAct)
_ACT_NAMES: list[str] = [
    "None",         # 0
    "Set",          # 1  — set spell/trap face-down
    "Repo",         # 2  — reposition monster
    "SpSummon",     # 3  — special summon
    "Summon",       # 4  — normal summon
    "MSet",         # 5  — set monster face-down
    "Attack",       # 6  — attack a target
    "DirectAttack", # 7  — direct attack
    "Activate",     # 8  — activate a card/effect
    "Cancel",       # 9  — end/cancel (phase transition)
]

# ActionPhase enum (0-based)
_PHASE_NAMES: list[str] = [
    "None",    # 0
    "Battle",  # 1
    "Main2",   # 2
    "End",     # 3
]

# ActionPlace enum (0-based, matches C++ enum class ActionPlace)
_PLACE_NAMES: list[str] = [
    "None",
    "m1", "m2", "m3", "m4", "m5", "m6", "m7",          # MZone 1-7
    "s1", "s2", "s3", "s4", "s5", "s6", "s7", "s8",    # SZone 1-8
    "om1","om2","om3","om4","om5","om6","om7",           # OpMZone 1-7
    "os1","os2","os3","os4","os5","os6","os7","os8",     # OpSZone 1-8
]


def _extract_enum_names(hdr: str, enum_name: str) -> list[str]:
    m = re.search(rf"enum\s+class\s+{re.escape(enum_name)}\s*\{{(.*?)\}};", hdr, flags=re.S)
    if not m:
        return []
    body = m.group(1)
    out: list[str] = []
    for raw in body.split(","):
        tok = raw.strip()
        if not tok:
            continue
        tok = tok.split("=")[0].strip()
        tok = tok.split("//")[0].strip()
        if tok:
            out.append(tok)
    return out


def _extract_msgs(hdr: str) -> list[str]:
    m = re.search(r"static\s+const\s+std::vector<int>\s+_msgs\s*=\s*\{(.*?)\};", hdr, flags=re.S)
    if not m:
        return []
    body = m.group(1)
    out: list[str] = []
    for raw in body.split(","):
        tok = raw.strip().split("//")[0].strip()
        if tok:
            out.append(tok)
    return out


def _msg_token_to_label(tok: str) -> str:
    lut = {
        "MSG_SELECT_IDLECMD": "select_idle",
        "MSG_SELECT_CHAIN": "select_chain",
        "MSG_SELECT_CARD": "select_card",
        "MSG_SELECT_TRIBUTE": "select_tribute",
        "MSG_SELECT_POSITION": "select_position",
        "MSG_SELECT_EFFECTYN": "select_effectyn",
        "MSG_SELECT_YESNO": "select_yesno",
        "MSG_SELECT_BATTLECMD": "select_battle",
        "MSG_SELECT_UNSELECT_CARD": "select_unselect",
        "MSG_SELECT_OPTION": "select_option",
        "MSG_SELECT_PLACE": "select_place",
        "MSG_SELECT_SUM": "select_sum",
        "MSG_SELECT_DISFIELD": "select_disfield",
        "MSG_ANNOUNCE_ATTRIB": "announce_attrib",
        "MSG_ANNOUNCE_NUMBER": "announce_number",
        "MSG_ANNOUNCE_CARD": "announce_card",
    }
    return lut.get(tok, tok.lower())


def _sync_from_engine_header() -> None:
    """
    Override local lookup tables with values parsed from engine header (ygopro.h).
    Falls back silently to baked defaults when unavailable.
    """
    global _ID_TO_MSG, _ACT_NAMES, _PHASE_NAMES
    try:
        root = Path(__file__).resolve().parent.parent
        hdr_path = root / "vendor" / "ygo-env" / "ygoenv" / "ygoenv" / "ygopro" / "ygopro.h"
        if not hdr_path.is_file():
            return
        hdr = hdr_path.read_text(encoding="utf-8", errors="ignore")

        msg_tokens = _extract_msgs(hdr)
        if msg_tokens:
            parsed: dict[int, str] = {0: "none"}
            for i, tok in enumerate(msg_tokens, start=1):
                parsed[i] = _msg_token_to_label(tok)
            _ID_TO_MSG = parsed

        acts = _extract_enum_names(hdr, "ActionAct")
        if acts:
            _ACT_NAMES = acts

        phases = _extract_enum_names(hdr, "ActionPhase")
        if phases:
            _PHASE_NAMES = phases
    except Exception:
        return


_sync_from_engine_header()

# ---------------------------------------------------------------------------
# Column layout of obs['actions_']  shape (max_options, 12)
# ---------------------------------------------------------------------------
# col 0  — spec_index (card slot within a selection group)
# col 1  — card_id high byte  (code_list 1-based index)
# col 2  — card_id low byte
# col 3  — msg_to_id  (see _ID_TO_MSG)
# col 4  — ActionAct  (see _ACT_NAMES)
# col 5  — finish flag (1 = confirm selection)
# col 6  — effect id
# col 7  — ActionPhase  (see _PHASE_NAMES)
# col 8  — position_to_id
# col 9  — number
# col 10 — ActionPlace  (see _PLACE_NAMES)
# col 11 — attribute id


def _card_name(card_id: int, card_id_to_code: dict, code_to_name: dict) -> str:
    """Resolve card_id (code_list index) → code → name."""
    if card_id == 0:
        return ""
    code = card_id_to_code.get(card_id, card_id)
    name = code_to_name.get(str(code), "")
    return name or f"card#{code}"


def decode_action_features(
    feat: list,
    card_id_to_code: Optional[dict] = None,
    code_to_name: Optional[dict] = None,
) -> str:
    """
    Turn the 12 feature bytes for one action slot into a human-readable label.

    feat      — list/array of 12 uint8 values (one row of obs['actions_'])
    card_id_to_code — {card_id: card_code} from code_list.txt (1-based index → code)
    code_to_name    — {str(code): name} from card_code_to_name.json
    """
    if not feat or len(feat) < 12:
        return "invalid"

    cid_map  = card_id_to_code or {}
    name_map = code_to_name or {}

    spec    = int(feat[0])
    cid_hi  = int(feat[1])
    cid_lo  = int(feat[2])
    msg_id  = int(feat[3])
    act_id  = int(feat[4])
    finish  = int(feat[5])
    effect_id = int(feat[6]) if len(feat) > 6 else 0
    phase_id = int(feat[7])
    # pos    = int(feat[8])
    number  = int(feat[9])
    place_id = int(feat[10])
    # attrib = int(feat[11])

    card_id = cid_hi * 256 + cid_lo
    msg     = _ID_TO_MSG.get(msg_id, f"msg{msg_id}")
    act     = _ACT_NAMES[act_id] if act_id < len(_ACT_NAMES) else f"act{act_id}"
    phase   = _PHASE_NAMES[phase_id] if phase_id < len(_PHASE_NAMES) else ""
    place   = _PLACE_NAMES[place_id] if place_id < len(_PLACE_NAMES) else ""
    name    = _card_name(card_id, cid_map, name_map)

    # --- MSG_SELECT_IDLECMD / MSG_SELECT_BATTLECMD ---
    if msg in ("select_idle", "select_battle"):
        if act == "Cancel":
            # phase transition: go to Battle / Main2 / End
            dest = phase if phase not in ("None", "") else "End"
            return f"→ {dest} phase"
        parts = []
        if act not in ("None", ""):
            parts.append(act)
        if name:
            parts.append(name)
        label = " ".join(parts) or "Pass"
        # For Activate, append effect index when card has multiple effects (so step label is specific)
        if act == "Activate" and effect_id > 0:
            label += f" (effect {effect_id})"
        return label

    # --- MSG_SELECT_CHAIN ---
    if msg == "select_chain":
        if act == "Cancel":
            return "Pass / don't chain"
        label = "Chain"
        if name:
            label += f" {name}"
        if act not in ("None", "Cancel", ""):
            label += f" ({act})"
        if effect_id > 0:
            label += f" effect {effect_id}"
        return label

    # --- SELECT_CARD / SELECT_TRIBUTE / SELECT_SUM / SELECT_UNSELECT ---
    if msg in ("select_card", "select_tribute", "select_sum", "select_unselect"):
        if finish:
            return "Confirm selection"
        label = "Select"
        if name:
            label += f" {name}"
        elif spec:
            label += f" slot{spec}"
        return label

    # --- SELECT_POSITION ---
    if msg == "select_position":
        pos_labels = {1: "face-up ATK", 2: "face-down ATK", 4: "face-up DEF", 8: "face-down DEF"}
        return f"Set position: {pos_labels.get(int(feat[8]), f'pos{feat[8]}')}"

    # --- SELECT_EFFECTYN / SELECT_YESNO ---
    if msg in ("select_effectyn", "select_yesno"):
        # In ygo-env optional prompts, act_id=9 is the cancel/no branch.
        # Other act_ids represent the effect-bearing affirmative choice.
        yn = "No" if act_id == 9 else "Yes"
        label = yn
        if name:
            label += f" ({name})"
        return label

    # --- SELECT_OPTION ---
    if msg == "select_option":
        label = f"Option {act_id}"
        if name:
            label += f": {name}"
        return label

    # --- SELECT_PLACE / SELECT_DISFIELD ---
    if msg in ("select_place", "select_disfield"):
        return f"Place → {place}" if place not in ("None", "") else "Place card"

    # --- ANNOUNCE_* ---
    if msg == "announce_attrib":
        attribs = {1: "Earth", 2: "Water", 4: "Fire", 8: "Wind", 16: "Light", 32: "Dark", 64: "Divine"}
        return f"Announce: {attribs.get(int(feat[11]), f'attrib{feat[11]}')}"
    if msg == "announce_number":
        return f"Announce: {number}"
    if msg == "announce_card":
        return f"Announce card: {name or f'card_id={card_id}'}"

    # --- fallback ---
    label = msg
    if name:
        label += f" {name}"
    if act not in ("None", ""):
        label += f" [{act}]"
    return label


def action_index_to_label(
    action_index: int,
    feat: Optional[list] = None,
    card_id_to_code: Optional[dict] = None,
    code_to_name: Optional[dict] = None,
) -> str:
    """
    Human-readable label for an action index.

    When called with only action_index (legacy), returns 'action_N'.
    When called with feat (12 feature bytes from obs['actions_']), returns
    a decoded label like 'Summon Aluber the Jester of Despia'.
    """
    if feat is not None:
        return decode_action_features(feat, card_id_to_code, code_to_name)
    return f"action_{action_index}"
