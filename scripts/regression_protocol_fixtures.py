#!/usr/bin/env python3
from __future__ import annotations

import struct


def parse_confirm_cards(payload: bytes) -> dict:
    player, skip_panel, size = struct.unpack_from("<BBB", payload, 0)
    offset = 3
    cards = []
    for _ in range(size):
        code, controller, location, sequence = struct.unpack_from("<IBBB", payload, offset)
        offset += 7
        cards.append(
            {
                "code": code,
                "controller": controller,
                "location": location,
                "sequence": sequence,
            }
        )
    return {
        "player": player,
        "skip_panel": bool(skip_panel),
        "cards": cards,
        "remaining": payload[offset:],
    }


def parse_select_unselect_card(payload: bytes) -> dict:
    player, finishable, cancelable, min_count, max_count, select_size = struct.unpack_from(
        "<BBBBBB", payload, 0
    )
    offset = 6
    selectable = []
    for _ in range(select_size):
        code, controller, location, sequence, position = struct.unpack_from("<IBBBB", payload, offset)
        offset += 8
        selectable.append(
            {
                "code": code,
                "controller": controller,
                "location": location,
                "sequence": sequence,
                "position": position,
            }
        )
    (unselect_size,) = struct.unpack_from("<B", payload, offset)
    offset += 1
    return {
        "player": player,
        "finishable": bool(finishable),
        "cancelable": bool(cancelable),
        "min": min_count,
        "max": max_count,
        "selectable": selectable,
        "unselect_size": unselect_size,
        "remaining": payload[offset:],
    }


def parse_select_chain(payload: bytes) -> dict:
    player, size, spe_count = struct.unpack_from("<BBB", payload, 0)
    hint_timing, other_timing = struct.unpack_from("<II", payload, 3)
    offset = 11
    chains = []
    for _ in range(size):
        flag, forced, code, controller, location, sequence, position, desc = struct.unpack_from(
            "<BBIBBBBI", payload, offset
        )
        offset += 14
        chains.append(
            {
                "flag": flag,
                "forced": bool(forced),
                "code": code,
                "controller": controller,
                "location": location,
                "sequence": sequence,
                "position": position,
                "desc": desc,
            }
        )
    return {
        "player": player,
        "spe_count": spe_count,
        "hint_timing": hint_timing,
        "other_timing": other_timing,
        "chains": chains,
        "remaining": payload[offset:],
    }


def parse_select_card(payload: bytes) -> dict:
    player, cancelable, min_count, max_count, size = struct.unpack_from("<BBBBB", payload, 0)
    offset = 5
    cards = []
    for _ in range(size):
        code, controller, location, sequence, position = struct.unpack_from("<IBBBB", payload, offset)
        offset += 8
        cards.append(
            {
                "code": code,
                "controller": controller,
                "location": location,
                "sequence": sequence,
                "position": position,
            }
        )
    return {
        "player": player,
        "cancelable": bool(cancelable),
        "min": min_count,
        "max": max_count,
        "cards": cards,
        "remaining": payload[offset:],
    }


def parse_select_option(payload: bytes) -> dict:
    player, size = struct.unpack_from("<BB", payload, 0)
    offset = 2
    options = []
    for _ in range(size):
        (desc,) = struct.unpack_from("<I", payload, offset)
        offset += 4
        options.append({"desc": desc})
    return {
        "player": player,
        "options": options,
        "remaining": payload[offset:],
    }


def main() -> int:
    confirm_cards_payload = struct.pack(
        "<BBBIBBB",
        1,
        0,
        1,
        19096726,  # Tri-Brigade Mercourier
        1,
        2,
        3,
    )
    confirm_cards = parse_confirm_cards(confirm_cards_payload)
    assert confirm_cards["player"] == 1
    assert confirm_cards["skip_panel"] is False
    assert len(confirm_cards["cards"]) == 1
    assert confirm_cards["cards"][0]["code"] == 19096726
    assert confirm_cards["remaining"] == b""

    select_unselect_payload = struct.pack(
        "<BBBBBBIBBBBIBBBBB",
        0,  # player
        1,  # finishable
        0,  # cancelable
        1,  # min
        2,  # max
        2,  # select size
        95515789,
        0,
        0x01,
        0x00,
        0x00,
        73819701,
        0,
        0x01,
        0x01,
        0x01,
        1,  # unselect size
    )
    select_unselect = parse_select_unselect_card(select_unselect_payload)
    assert select_unselect["player"] == 0
    assert select_unselect["finishable"] is True
    assert select_unselect["min"] == 1
    assert select_unselect["max"] == 2
    assert len(select_unselect["selectable"]) == 2
    assert select_unselect["selectable"][1]["code"] == 73819701
    assert select_unselect["unselect_size"] == 1
    assert select_unselect["remaining"] == b""

    select_chain_payload = struct.pack(
        "<BBBIIBBIBBBBIBBIBBBBI",
        0,  # player
        2,  # size
        1,  # spe_count
        0x11223344,
        0x55667788,
        0x00,  # flag
        0x01,  # forced
        62962630,
        0,
        0x04,
        0x00,
        0x01,
        1001,
        0x08,  # flag
        0x00,  # forced
        81767888,
        1,
        0x10,
        0x02,
        0x00,
        3062202629,
    )
    select_chain = parse_select_chain(select_chain_payload)
    assert select_chain["player"] == 0
    assert select_chain["spe_count"] == 1
    assert select_chain["hint_timing"] == 0x11223344
    assert select_chain["other_timing"] == 0x55667788
    assert len(select_chain["chains"]) == 2
    assert select_chain["chains"][0]["forced"] is True
    assert select_chain["chains"][0]["code"] == 62962630
    assert select_chain["chains"][1]["flag"] == 0x08
    assert select_chain["chains"][1]["desc"] == 3062202629
    assert select_chain["remaining"] == b""

    select_card_payload = struct.pack(
        "<BBBBBIBBBBIBBBB",
        0,  # player
        1,  # cancelable
        1,  # min
        1,  # max
        2,  # size
        62962630,
        0,
        0x01,
        0x00,
        0x01,
        81767888,
        1,
        0x10,
        0x02,
        0x00,
    )
    select_card = parse_select_card(select_card_payload)
    assert select_card["player"] == 0
    assert select_card["cancelable"] is True
    assert select_card["min"] == 1
    assert select_card["max"] == 1
    assert len(select_card["cards"]) == 2
    assert select_card["cards"][0]["code"] == 62962630
    assert select_card["cards"][1]["controller"] == 1
    assert select_card["remaining"] == b""

    select_option_payload = struct.pack(
        "<BBII",
        0,  # player
        2,  # size
        1001,
        3062202629,
    )
    select_option = parse_select_option(select_option_payload)
    assert select_option["player"] == 0
    assert len(select_option["options"]) == 2
    assert select_option["options"][0]["desc"] == 1001
    assert select_option["options"][1]["desc"] == 3062202629
    assert select_option["remaining"] == b""

    print("Protocol fixture regression passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
