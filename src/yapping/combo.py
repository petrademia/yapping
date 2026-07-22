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
    catalog = {str(card["name"]): int(card["id"]) for card in cards}
    if not catalog:
        raise ValueError(f"{source} has no numeric cards catalog")
    if database:
        connection = sqlite3.connect(database)
        try:
            for name, card_id in catalog.items():
                row = connection.execute("SELECT name FROM texts WHERE id = ?", (card_id,)).fetchone()
                if row is None:
                    raise ValueError(f"unknown card id {card_id} for {name}")
                if row[0] != name:
                    raise ValueError(f"card id {card_id} resolves to {row[0]!r}, not {name!r}")
        finally:
            connection.close()
    return data
