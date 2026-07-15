"""Compare seed replay with the safe forward-descent replay cursor."""

import gc
import multiprocessing as mp
import os
import time

from analyze_ash import ReplayCursor, replay
from trace_albaz_combo import ASH_BLOSSOM, ROOT, SCRIPTS
from yapping._ocgcore import Duel


_worker_adapter = None


def init_worker():
    global _worker_adapter
    _worker_adapter = Duel(str(ROOT / "assets/cards.cdb"), str(SCRIPTS))


def parallel_replay(path):
    node = replay(path, ASH_BLOSSOM, None, 1, _worker_adapter)
    return node.key


def fork_suffix(adapter, prefix, suffix):
    """Run a suffix in a COW child while leaving the parent at prefix."""
    decision = replay(prefix, ASH_BLOSSOM, None, 1, adapter).decision
    read_fd, write_fd = os.pipe()
    child = os.fork()
    if child == 0:
        try:
            for index in suffix:
                decision = adapter.step(index)
            os.write(write_fd, adapter.state_key().hex().encode())
        finally:
            os.close(write_fd)
            os._exit(0)
    os.close(write_fd)
    result = os.read(read_fd, 1 << 20).decode()
    os.close(read_fd)
    _, status = os.waitpid(child, 0)
    if status != 0:
        raise RuntimeError(f"fork worker exited with status {status}")
    return bytes.fromhex(result)


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
    oracle = []
    oracle_state_keys = []
    for path in paths:
        oracle.append(replay(path, ASH_BLOSSOM, None, 1, oracle_adapter))
        oracle_state_keys.append(oracle_adapter.state_key())
    oracle_seconds = time.perf_counter() - started
    del oracle_adapter
    gc.collect()

    cursor_adapter = Duel(str(ROOT / "assets/cards.cdb"), str(SCRIPTS))
    cursor = ReplayCursor(ASH_BLOSSOM, None, 1, cursor_adapter)
    started = time.perf_counter()
    optimized = [cursor(path) for path in paths]
    cursor_seconds = time.perf_counter() - started

    equivalent = all(left.key == right.key for left, right in zip(oracle, optimized))
    workers = min(4, mp.cpu_count())
    started = time.perf_counter()
    with mp.Pool(workers, initializer=init_worker) as pool:
        parallel_keys = pool.map(parallel_replay, paths)
    parallel_seconds = time.perf_counter() - started
    print(f"paths: {len(paths)}")
    print(f"oracle_seconds: {oracle_seconds:.3f}")
    print(f"cursor_seconds: {cursor_seconds:.3f}")
    print(f"speedup: {oracle_seconds / cursor_seconds:.2f}x")
    print(f"equivalent: {equivalent}")
    print(f"parallel_workers: {workers}")
    print(f"parallel_seconds: {parallel_seconds:.3f}")
    print(f"parallel_equivalent: {parallel_keys == [node.key for node in oracle]}")
    del cursor_adapter, cursor
    gc.collect()
    fork_adapter = Duel(str(ROOT / "assets/cards.cdb"), str(SCRIPTS))
    started = time.perf_counter()
    fork_keys = []
    for path in paths[:20]:
        split = len(path) // 2
        fork_keys.append(fork_suffix(fork_adapter, path[:split], path[split:]))
    fork_seconds = time.perf_counter() - started
    print(f"fork_paths: {len(fork_keys)}")
    print(f"fork_seconds: {fork_seconds:.3f}")
    print(f"fork_equivalent: {fork_keys == oracle_state_keys[:20]}")
    if not equivalent:
        raise SystemExit("cursor diverged from replay oracle")


if __name__ == "__main__":
    main()
