# Combo Map & the Three Paths

YAPPING is built to support three ways of using the same engine and search:

---

## The "Combo Map" (Visualizer / Teacher)

**Goal:** Don’t only find the *best* board — **map every possible path** like a flowchart.

**Who it’s for:** Players learning a complex deck who want to see **divergent paths** (e.g. “If they hand trap me here, I can pivot to this board instead”).

**Technical focus:** **Graph theory.** The important outputs are:
- **JSON export** — machine-readable tree of (state → legal actions → next states).
- **Visualization** — flowchart/diagram of how one card leads to multiple branches.

So the “combo map” is the full tree (or pruned DAG) of *all* reachable lines from a given hand, not a single path.

---

## The Three Paths (A, B, C)

| Path | Question | What YAPPING does |
|------|----------|--------------------|
| **A** | “Show me the **best** thing I can do with this hand.” | Single optimal path: run heuristics (Yap Score), prune, return the highest-scoring end-board and the sequence of actions to get there. |
| **B** | “Show me **everywhere** this hand can go.” | Full **combo map**: enumerate all legal branches (BFS/MCTS), hash states to merge transpositions, export the tree as JSON + flowchart. |
| **C** | “**Surprise me** with something I didn’t know was possible.” | Discovery mode: e.g. underused branches, rare end-boards, or paths that differ from the “obvious” line. Can be built on top of B (filter/rank the map) or with extra exploration. |

All three use the same **Hand Simulator** and **engine** (engine wrapper): same deck, same hand, same legal-action enumeration. The difference is how we **search** (brain) and **present** (cli: JSON, flowchart, “best only”, “all”, “surprise”).

---

## Implementation order

1. **Hand Simulator (done)** — Deck → draw 5 → list first N legal actions. Raw data to confirm the engine works. (`cli/hand_simulator.py`, `cli/cli.py hand-sim`.)
2. **Path A (best path)** — Brain search + heuristics; return one best path and its score.
3. **Path B (combo map)** — Same search, but keep full tree; state hashing to avoid duplicate nodes; export JSON + flowchart (e.g. Mermaid).
4. **Path C (surprise)** — Query the map (or re-run search) with filters / diversity / “non-obvious” ranking.

The **JSON export** and **flowchart** are the main deliverables for the Combo Map (Path B); Path A is a special case (single path); Path C is a view over the same graph.
