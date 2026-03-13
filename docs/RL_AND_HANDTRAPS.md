# RL, Expected Value, and Hand Traps

Long-term vision for making combo search **resilient** to hand traps (Ash, Nibiru, etc.) via expected value and opponent modeling. We are **not** pivoting the whole codebase to this yet; this doc captures the plan and phases.

---

## How we reach the best combo today

The DFS **does** get a reward at every state and **does** optimize: it keeps the path with the **maximum** score and returns it as "best path."

- **Reward** = `evaluate_line(obs, labels)` in `brain/heuristics.py`: board score (monsters/spells/hand) plus path penalty (too many summons).
- **Best combo** = the path that has the highest value of that reward over the whole run.

So "correct/best" is defined by the heuristic. To get combos that match what you want (e.g. prefer negates, follow-up), we need to **tune the reward**: change weights in `evaluate_board` (e.g. `WEIGHT_MONSTER`, `WEIGHT_SPELL_TRAP`) and/or add negate/board-quality terms when we have card data.

---

## What the DFS can and cannot do

| Thing | Can the DFS do it? | Notes |
|-------|--------------------|--------|
| **Synchro summon** | Yes, if the engine offers it | DFS takes every legal action the engine returns. When the board has tuner + non-tuner and the core puts "SpSummon" (or Synchro) in the list, we take it and complete sub-prompts (e.g. choose material). We don't filter by type. |
| **Activate spell (e.g. send deck → GY)** | Yes, if the engine offers it | "Activate Branded Fusion" (or similar) is a legal action when the engine says so. We step it and `complete_until_main_phase_idle` runs through any sub-prompts (select card from deck, etc.). So deck → GY and resolution are handled by the engine. |
| **Graveyard in the reward** | Yes (added) | We were not counting GY before. We now add `WEIGHT_GRAVE` in `evaluate_board` so cards in our graveyard (e.g. for Branded follow-up) increase the score. Location in obs is col 2; we treat `loc == 5` or `loc == 16` as GY depending on engine encoding. |
| **Turn 1 = setup only** | Yes | When `first_turn=True`, the DFS skips Attack, DirectAttack, and "→ Battle phase", so best paths are setup-only (no battle in the combo). |
| **State at best path** | Yes | DFS returns `state_at_best`: dict with **hand**, **field_mzone**, **field_szone**, **grave**, **banish** (lists of card_ids) at the end of the best combo. Use `env.get_state_snapshot(obs)` for any obs; DFS fills it after replaying the best path. |

So the only thing that was **missing** was **graveyard in the evaluation**. Synchro and spell activations were already possible as long as the engine lists them as legal actions; we don't block or special-case them.

---

## 1. Expected value instead of raw reward

**Idea:** Optimize **expected reward**, not just end-board reward.

- **Path A:** 5 negates, but loses to Ash 60% of the time → low EV if "interrupted" reward is bad.
- **Path B:** 2 negates, plays through Ash 95% of the time → higher EV.

$$EV = P_{success} \times Reward_{Endboard} + P_{fail} \times Reward_{Interrupted}$$

If we define "interrupted" as a very low reward (e.g. nothing on board), the agent learns to favor **safer** lines (Path B).

**Status:** Not implemented. Current DFS/rollout only maximizes end-board score.

---

## 2. How the model "sees" hand traps

We don't know the opponent's hand. The agent must **play around** the meta distribution.

| Method | Role in the RL model |
|--------|----------------------|
| **Opponent modeling** | During training, opponent has a deck with meta hand-trap ratios (e.g. 3 Ash, 3 Imperm). We sample "did they have it?" from that distribution. |
| **State augmentation** | Add e.g. "summon count" or "hand trap flag" to state. Model learns: by Summon #5 with no negate, Nibiru risk is high. |
| **MCTS** | Simulate many futures with random hand-trap timing; choose the move that survives most often (AlphaZero-style). |

**Status:** No opponent agent yet; no hand-trap injection in the env.

---

## 3. Choice point (failure state)

When a hand trap is played, the agent gets a **new state** it didn't choose:

- **Action:** Activate Branded Fusion.
- **External event:** Opponent chains Ash Blossom.
- **New state:** Branded Fusion negated, 0 monsters on field.

The RL response: from this **failure state**, recompute the best path with remaining resources. Over time the agent learns to **bait** (lead with a sub-optimal searcher, save the real starter for after the bait).

**Status:** Engine supports chains; we don't yet simulate "opponent chains Ash" during search.

---

## 4. Self-play

Two agents:

- **Player A (Combo):** Build the best board.
- **Player B (Hand Trap):** Choose when to use a hand trap to break Player A.

Because B is learning too, A is forced to find **resilient** combo paths. Output = **resilient policy**, not just one combo.

**Status:** Future phase.

---

## 5. Practical step: reward shaping now

Before full RL, we can align **valuation** with this vision:

- **Interrupted reward:** Low (e.g. 0 or negative) when the line is stopped with nothing on board. (We can define "interrupted" later when we have opponent; for now we can tag states in rollout.)
- **Summon-count penalty:** Slight negative reward (or lower score) when we reach Summon #5+ with no negate on board — encourages **early negate** (Baronne, Apollo) before going deep.
- **Early negate bonus:** In heuristics, boost score when we have a negate on board early in the combo.

Adding these to **brain/heuristics** (and using them in DFS/rollout) makes the current "best path" already prefer **safer** lines. When we add opponent and EV later, the reward shape is already right.

---

## Phased plan

| Phase | What | Status |
|-------|------|--------|
| **1** | DFS, rollout, simple board score (monsters/spells/hand) | Done |
| **2** | Reward shaping: summon-count penalty, early-negate bonus, interrupted = low | Next |
| **3** | Opponent model: inject hand traps (e.g. "Ash on this action" with probability), define success/fail and EV | Later |
| **4** | EV-based policy or MCTS over hand-trap uncertainty | Later |
| **5** | Self-play (combo vs hand-trap agent) | Later |

**Recommendation:** Do **Phase 2** next (heuristic tweaks) so DFS and rollout already favor resilient lines. Then document state representation for "summon count" and "negate on board" so Phase 3 can plug in cleanly.
