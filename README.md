# YAPPING
### **Y**et **A**nother **P**ath **P**rocessor & **I**nference **N**ode **G**enerator

---

**YAPPING** is an exhaustive state-space combo analyzer for Yu-Gi-Oh!. It is designed to bridge high-level Python search algorithms with the low-level Lua logic of the **OCGCore**. Unlike traditional simulators, YAPPING doesn't just play the game—it explores every possible legal permutation of a given hand to identify the mathematically optimal end-board.

---

## ### Core Architecture

YAPPING operates across three distinct layers:

1.  **The Rules (Lua):** Utilizes existing `.lua` scripts from the OCGCore to ensure 100% accuracy with card effects, costs, and timing.
2.  **The Bridge (C++/Python):** Powered by **[petrademia/ygo-env](https://github.com/petrademia/ygo-env)** (fork of izzak98/ygo-env), providing a high-performance interface to the simulation engine.
3.  **The Brain (Python):** A recursive Breadth-First Search (BFS) engine with **Heuristic Pruning** and **State Hashing** to prevent infinite loops.

---

## ### Key Features

* **Exhaustive Branching:** Explores every "if-then" scenario based on your starting hand.
* **Heuristic Scoring:** Ranks end-boards based on interrupts (negates), resource count (follow-up), and floodgate presence.
* **Transposition Detection:** Identifies when different move sequences lead to the same board state and prunes redundant paths to save memory.
* **Headless Simulation:** Runs thousands of simulations per second without the overhead of a GUI.

---

## ### Project structure

```
yapping/
├── brain/                  # Intelligence: BFS/MCTS, heuristics, state hashing
├── vocal_chords/           # Bridge: ygo-env wrapper, actions, env setup
├── mouth/                  # Interface: simulator, exporter, CLI
├── scripture/              # Data: cards.cdb, scripts/, decks/
├── logs/                   # Saved combo paths and error logs
├── requirements.txt
├── README.md
└── main.py                 # Entry point (delegates to mouth.cli)
```

---

## ### Getting Started

### Prerequisites
* Python 3.10+
* An engine that uses OCGCore: **[petrademia/ygo-env](https://github.com/petrademia/ygo-env)** (recommended for YAPPING) or upstream [izzak98/ygo-env](https://github.com/izzak98/ygo-env) / [sbl1996/ygo-agent](https://github.com/sbl1996/ygo-agent) — see **[docs/ENGINE_SETUP.md](docs/ENGINE_SETUP.md)** for setup
* A `cards.cdb` SQLite database (standard for EDOPro/YGOPRO)

**On Windows:** The C++ engine builds only on Linux. Use **WSL** and follow **[docs/WSL_SETUP.md](docs/WSL_SETUP.md)**.

### Installation
```bash
git clone [https://github.com/yourusername/yapping.git](https://github.com/yourusername/yapping.git)
cd yapping
pip install -r requirements.txt
```

Build **ygo-env** (OCGCore bridge) on Linux/WSL; see **[docs/ENGINE_SETUP.md](docs/ENGINE_SETUP.md)**. After pulling engine changes, rebuild the native module: `cd vendor/ygo-env && xmake f -c -m release -y && xmake b ygopro_ygoenv` (or `make build_ext`). Short version: **[vendor/README.md](vendor/README.md)**.