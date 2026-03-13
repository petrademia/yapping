# When do "Activate" actions appear?

The engine (ygo-env/OCGCore) emits **legal actions** that we decode into labels like "Summon X", "Set Y", "Activate Z". Two things are easy to get wrong:

1. **Activate from hand**  
   - The engine **does** offer "Activate" (act_id=8) for some cards in hand in the idle command—e.g. "Activate The Bystial Lubellion", "Activate Gold Sarcophagus" (see `tmp_audit_actions.py` output). So the core *does* fill `idle_activate_` for some effects.  
   - For **Fallen of the White Dragon** specifically we don’t see "Activate" in the idle menu even when it’s in hand (use `python tmp_audit_actions.py --target-code 73819701` and ensure the run lands in **Main Phase idle**, not a chain window). The Lua script correctly registers `EFFECT_TYPE_IGNITION` + `LOCATION_HAND` with cost: send 1 monster from Extra Deck that is CodeListed(68468459), TYPE_MONSTER, AbleToGraveAsCost. So the gap is likely **card-specific**. Plausible causes:
  - **Extra Deck not considered when building idle_activate_** — the core might not check the Extra Deck for valid cost targets when deciding whether to add an effect to the idle “activatable” list, so the effect is skipped even when valid targets exist.
  - Cost/condition fails for some other reason (e.g. the core’s CodeList or Extra Deck state isn’t what the script expects).
- In **chain** states we do see Activate (e.g. "Chain Mulcharmy Fuwalos (Activate)", "Chain Maxx \"C\" (Activate)").

2. **Quick-Play Spells from hand** (e.g. Branded Opening)  
   - Can be activated from hand during our Main Phase.  
   - The engine might offer "Set Branded Opening" and/or "Activate Branded Opening" in the same idle menu; if only "Set" appears, the core may treat "activate from hand" differently (e.g. only in chain window) or not expose it.

## Investigate: what actions does the engine offer? (tmp_audit_actions.py)

To see **exactly which actions the agent can choose from** (by type and when), run from the **repo root** (so the script is found). The script will `chdir` to `vendor/ygo-env` so the engine finds `./script/`:

```bash
cd /mnt/c/Users/petrus/Projects/yapping
source .venv/bin/activate
python tmp_audit_actions.py
```

Options:

- `--seeds N` — sample N different initial states (default 3).
- `--steps N` — after each initial state, take N steps and audit again (default 1).

The script prints, for each state:

- **Total** legal actions.
- **By act_id:** counts for Summon, MSet, Set, Activate, Place, Cancel, etc.
- **By label prefix:** same grouped by the first word of the decoded label.
- **Activate labels:** if any act_id=8, lists them (so you see if “Activate from hand” ever appears).
- **Sample labels:** first 15 full labels.

At the end it summarizes whether Activate was seen in any state and which action types and prefixes appeared. Use this before designing heuristics or RL so you know what the engine actually returns.

## Diagnostic: one card and ignition (tmp_diagnose_effects.py)

To force a hand containing a specific card (e.g. Fallen of the White Dragon) and inspect when Activate appears:

```bash
cd vendor/ygo-env
python ../tmp_diagnose_effects.py
```

The script now:

- **Initial state:** Lists all actions with `act_id=8` (Activate) and all actions mentioning "Branded Opening", so you can see whether "Activate Branded Opening" is ever offered.
- **After Summon Fallen of the White Dragon:** Takes that action, then re-lists legal actions so you can confirm "Activate Fallen of the White Dragon" (ignition) appears only once the monster is on field.

Interpretation:

- If "Activate Fallen of the White Dragon" appears only after the summon → ignition behaviour is as expected.
- If "Activate Branded Opening" never appears at initial state → the engine may not offer quick-play-from-hand in the idle menu, or we need to look under a different message (e.g. chain).

## Same message (IDLECMD): Summon, Set, and Activate are together

There is **no separate message** for “activate effect”. In the engine (ygopro.h), **MSG_SELECT_IDLECMD** is handled by reading six lists from the core’s buffer in order:

1. `summonable_` → Summon  
2. `spsummon_` → SpSummon  
3. `repos_` → Repo  
4. `idle_mset_` → MSet  
5. `idle_set_` → Set  
6. **`idle_activate_`** → **Activate** (act_id=8)

So “Activate” options (ignition from hand, ignition on field, etc.) are **part of the same idle command** as Normal Summon and Set. The ygo-env C++ already iterates `idle_activate_` and appends `LegalAction::activate_spec(...)` to `legal_actions_` (around lines 6024–6053). So the **binding is correct**: if the core sends activatable effects in the idle packet, they show up as legal actions.

The reason we don’t see “Activate Fallen of the White Dragon” is that **the core** (ygopro-core / OCGCore, the C library that runs the duel and builds the message buffer) is sending an **empty** `idle_activate_` list. So either:

- The core’s logic that builds the “activatable” list for the idle command doesn’t include this effect (e.g. only includes certain effect types or locations), or  
- The effect is filtered out by the core’s cost/condition check (e.g. no valid Extra Deck target for the cost), or  
- There is a bug or limitation in the core when building that list.

So the missing step is in the **core** that fills the idle-command buffer, not in ygo-env (which already exposes whatever the core puts in `idle_activate_`). The Lua script is correct; the core is what decides which effects appear in that list.

Other message types (e.g. **MSG_SELECT_CHAIN**, **MSG_SELECT_PLACE**, **MSG_SELECT_CARD**) are different **states**: e.g. after you pick “Summon” the core sends SELECT_PLACE to choose the zone, then later might send SELECT_CHAIN if a chain is built. So “normal/set” vs “activate” are not different message types for the main-phase choice—they are different **categories inside the same IDLECMD**. Right now the core is only filling the summon/set categories and leaving the activate category empty.

## Phase: Draw vs Main

Some cards can be activated in **Draw Phase**, others only in **Main Phase**. When we “pass to reach idle” we may pass through Draw Phase first (different legal actions) before reaching Main Phase. The audit script treats “idle” as a state where we see Summon / MSet / Set in the menu, which implies **Main Phase**; Draw Phase idle typically doesn’t offer those. So for “what can I activate in Main Phase?” we keep passing until that menu appears. **Reliable Main Phase detection:** The engine does not expose current phase in obs/info. We use `msg_to_id == 1` (select_idle) plus at least one of **Summon, MSet, Set, Activate** in the legal labels, so hands with only Activate + Pass still count as Main Phase; we do not use "total ≥ 4". The wrapper has `get_current_phase()` for when the engine adds phase.

## Waiting for full resolution before the next action

We **do** wait for an effect to fully resolve before doing another main action. After we step a main-phase choice (e.g. "Activate Branded Fusion"), we run **completion** until we're back at **Main Phase idle**: that steps through every sub-prompt the engine sends (select materials, select zone, confirm, chain resolution, etc.). We only consider the "next" main action when we're at idle again. So Branded Fusion (and any activation/summon) is fully resolved before we take the next step; the engine’s restrictions (e.g. lock) apply for that turn as intended.

## What "Activate X" means (especially for monsters)

In our labels, **Activate** comes from the engine’s **ActionAct** value 8: “activate a card/effect”. So:

- **"Activate Branded Fusion"** = activate the spell (use the card).
- **"Activate Bystial Dis Pater"** = **activate that monster’s effect** (e.g. quick effect), **not** Special Summon it. Dis Pater is already on the field (e.g. Synchro Summoned earlier); the action is “use his effect”.

So “Activate [monster name]” never means “Special Summon this monster”. It means the monster is on field and you’re choosing to activate one of its effects. If a monster “cannot be Special Summoned except by Synchro Summon”, that restriction applies to **how it gets on the field**; once it’s there, “Activate Bystial Dis Pater” is just using his effect.

## Branded Fusion lock (and who enforces it)

**Real rule (exact card text):** “You cannot Special Summon from the Extra Deck, except Fusion Monsters, **the turn you activate this card**.” So the restriction applies for that entire turn (no Synchro, Xyz, or Link from the Extra Deck that turn).

**In our stack:** We do **not** enforce this in Python. The DFS only takes whatever **legal actions** the engine (ygo-env / OCGCore) returns. So:

- If the engine **does** enforce the lock, Synchro/SpSummon from ED after Branded Fusion would not appear in `get_legal_actions()`, and the path would be legal.
- If the engine **does not** enforce it, you can see a “best path” that includes e.g. “Summon The Golden Swordsoul” (Synchro) or “SpSummon …” after “Activate Branded Fusion”. That would be **illegal in real play**; the bug is in the **engine** (core or Lua scripts that build the legal action list), not in our labeling or DFS.

So: **lock after Branded Fusion** = engine’s job. Our labels only reflect what the engine offers. To confirm, after a step that corresponds to “Activate Branded Fusion”, inspect `get_legal_actions()` (e.g. with `tmp_audit_actions.py` or hand-sim) and see whether SpSummon/Synchro from Extra Deck still appears; if yes, the core is not applying the restriction.

**Replay and state drift:** The DFS used to record only "main" actions (e.g. "Activate Branded Fusion") and re-run completion (zone/card selection) with a generic "first non-Pass" choice on replay. That could lead to a **different** game state (e.g. different fusion materials) and then the next action index referred to a different option—so the path could look impossible (e.g. both Branded Fusion and Synchro in one line). We now **record every step** (including Select/Place during completion) and **replay that exact sequence** with no separate completion. So the state after replay matches the state we had when we expanded; the engine's lock (if implemented) is reflected correctly in the path.

**Verbose path labels:** The DFS result (and Ctrl+C) shows **enriched** main steps. Wording is driven by **scripture/card_display_hints.json** (card name → hint): e.g. `fusion_materials` → " (sent A, B to GY)", `cost_send_ed` → " (cost: sent X from Extra Deck to GY)". Add entries there instead of hardcoding; other Activate → " (target/selected: ...)", other Summon/SpSummon → " (materials: A, B)". Sub-prompts like **"Set position: face-up ATK"** and **"Place → m1"** are filtered out so the path lists only main-phase decisions.

**Effect index:** When the engine provides an effect id (e.g. for multi-effect cards), labels show **"Activate CardName (effect N)"** so the step is the specific effect activated, not just the card. Hint lookup strips "(effect N)" so hints still match by card name.

**Target/selected specificity:** For Activate, we show the **actual** cards chosen in completion (from Select/Confirm steps), not all possibilities. Hints `target_1`, `target_2`, `target_3` limit display to the first N selected (e.g. single-target effects). With no hint, we cap at 3 names then "and N others" so we don't list every option.

**Optional restriction on path (Branded Fusion lock):** If `code_to_type` (from cards.cdb) is passed to `run_combo_dfs`, we apply a **Python-side** filter: once "Activate Branded Fusion" is in the path, we skip any SpSummon of a Synchro/Xyz/Link (Extra Deck non-Fusion). So even if the engine offered that action, we don't push it. Hand-sim and tmp_discover load `code_to_type` from the env's cards.cdb when available and pass it in.

## Targets and costs (e.g. “Activate Bystial Saronir” — target in GY?)

We **do not** check in Python whether an activation has a valid target or cost. The engine decides what is legal and only offers an action when it has a valid target. So if you see **"Activate Bystial Saronir"** in a path, the engine did have a valid target at that state—**our code was not showing it**.

We now **always** show that a selection was made when the completion steps after an Activate (or Summon/SpSummon) include a Select or Confirm:

- If we can resolve the card name from the action (e.g. “Select Fallen of Albaz”), we show **"(target/selected: Fallen of Albaz)"**.
- If the engine sent a selection step without a card name in our decoder (e.g. “Select slot1” when card_id isn’t in our map or the action row doesn’t carry the card identity), we show **"(target/selected: 1 card)"** (or “2 cards” etc.). So you see that a target *was* selected; we just don’t have the name to display.

So the path will no longer show “Activate Bystial Saronir” with nothing after it when a target was required and chosen—you’ll get either the card name or “(target/selected: N card(s))”. Targets and costs are still enforced by the engine; we only fix the **display** so it’s clear the engine had a valid target.

**Illegal targets:** If the path shows a card that cannot legally be chosen (e.g. Albion can only send 1 "Fallen of Albaz" or 1 "Branded" Spell/Trap; if we show another card, the engine allowed it or our grouping is wrong). We don't validate legality in Python. **Turn 1:** Use `first_turn=True` so the path skips Attack/Battle. **"Then" effects:** We show cost/sent; a hint for "then Summon X" can be added in card_display_hints if needed.

## Hand traps and reactive timing

Cards like **Droll & Lock Bird** are best used in response to the opponent (e.g. when they add a card from deck to hand). That’s **reactive timing** — the right moment depends on opponent actions and chain order. Modelling that is more complex for combo building (you’d need to consider opponent moves and when to chain). For an initial combo/line builder it’s reasonable to **defer** hand-trap timing and focus on your own Main Phase sequence (summons, activations, set). Hand traps can be added later as a separate layer (e.g. “when to chain Droll”) once the core combo graph is stable.

## Approach: weighting vs RL

- **Investigate first:** Run `tmp_audit_actions.py` to see exactly which actions the engine offers and when (by act_id and label). That tells you what the agent can choose from (e.g. no point weighting "Activate from hand" if the engine never returns it in this state).
- **Heuristic weighting:** Once you know the action set, you can rank actions (e.g. prefer "Activate X" over "Set X" when both are legal, or prefer summons that enable follow-up). Good for a rule-based or greedy policy.
- **RL-style:** Learn a value/policy from outcomes (e.g. "did we end on a strong board?"). Makes sense once the action space and state representation are clear; the investigation step keeps the MDP well-defined.

So: run the diagnostic, confirm when Activate options appear, then decide whether to add simple weights or move toward RL.
