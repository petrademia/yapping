"""
Recursive BFS / MCTS branching logic.

Explores every legal permutation of a given game state: for each state,
enumerates legal actions, applies them, and recurses. Uses heuristics
and state hashing (see state_hasher, heuristics) to prune and avoid
revisiting equivalent boards.
"""

# TODO: implement BFS/MCTS over env states
# - get legal actions from vocal_chords
# - step env, get new state
# - hash state, skip if seen (state_hasher)
# - score board (heuristics), prune weak branches
# - recurse / queue until terminal or depth limit
