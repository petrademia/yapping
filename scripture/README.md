# Scripture — The Rulebook (Data)

- **cards.cdb** — SQLite database of card names and info (EDOPro/YGOPRO standard). Place your copy here; YAPPING does not ship with card data.
- **scripts/** — Card scripts: `c<id>.lua` files (e.g. `c12345678.lua`) used by OCGCore. Point ygo-env to this folder.
- **decks/** — Your `.ydk` deck files for simulation.
- **card_display_hints.json** — Card name → display hint for DFS path enrichment. Values: `fusion_materials`, `cost_send_ed`, `sent_to_gy`, `sent_to_gy_1`. Append `|draw_1` for "; draw 1". **Do not** give a single hint to multi-effect cards (e.g. Aluber, Guiding Quem)—they need per-effect hints (e.g. by effect index from the engine) so the right wording is used for each effect. Keys starting with `_` are ignored. Only **SpSummon** gets materials; **Summon** (Normal Summon) never shows materials.
