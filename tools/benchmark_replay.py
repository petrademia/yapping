"""Compare seed replay with the safe forward-descent replay cursor."""

import gc
import sys
import time

from analyze_ash import ReplayCursor, replay
from trace_albaz_combo import ASH_BLOSSOM, ROOT, SCRIPTS
from yapping._ocgcore import Duel


def collect_paths(adapter, limit=200, path=(), result=None):
    result = result or []
    if len(result) >= limit:
        return result
    node = replay(path, ASH_BLOSSOM, None, 1, adapter)
    result.append(path)
    if len(path) < 12:
        for index in range(min(6, len(node.decision["actions"]))):
            if len(result) >= limit:
                break
            collect_paths(adapter, limit, path + (index,), result)
    return result


def main():
    paths_adapter = Duel(str(ROOT / "assets/cards.cdb"), str(SCRIPTS))
    paths = collect_paths(paths_adapter)
    del paths_adapter
    gc.collect()

    oracle_adapter = Duel(str(ROOT / "assets/cards.cdb"), str(SCRIPTS))
    started = time.perf_counter()
    oracle = [replay(path, ASH_BLOSSOM, None, 1, oracle_adapter) for path in paths]
    oracle_seconds = time.perf_counter() - started
    del oracle_adapter
    gc.collect()

    cursor_adapter = Duel(str(ROOT / "assets/cards.cdb"), str(SCRIPTS))
    cursor = ReplayCursor(ASH_BLOSSOM, None, 1, cursor_adapter)
    started = time.perf_counter()
    optimized = [cursor(path) for path in paths]
    cursor_seconds = time.perf_counter() - started

    equivalent = all(left.key == right.key for left, right in zip(oracle, optimized))
    print(f"paths: {len(paths)}")
    print(f"oracle_seconds: {oracle_seconds:.3f}")
    print(f"cursor_seconds: {cursor_seconds:.3f}")
    print(f"speedup: {oracle_seconds / cursor_seconds:.2f}x")
    print(f"equivalent: {equivalent}")
    if not equivalent:
        raise SystemExit("cursor diverged from replay oracle")


if __name__ == "__main__":
    main()
