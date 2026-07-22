"""Machine-facing helpers for human-authored combo compendia."""

import json
import sqlite3
from pathlib import Path
from typing import Any


def load_combo(path: str | Path, database: str | Path | None = None) -> dict[str, Any]:
    """Load a combo compendium and validate its numeric card catalog."""
    source = Path(path)
    data = json.loads(source.read_text(encoding="utf-8"))
    cards = data.get("cards", [])
    card_ids = {
        int(card["id"] if isinstance(card, dict) else card)
        for card in cards
    }
    if not card_ids:
        raise ValueError(f"{source} has no numeric cards catalog")
    if database:
        connection = sqlite3.connect(database)
        try:
            for card_id in card_ids:
                row = connection.execute("SELECT id FROM texts WHERE id = ?", (card_id,)).fetchone()
                if row is None:
                    raise ValueError(f"unknown card id {card_id}")
        finally:
            connection.close()
    return data
