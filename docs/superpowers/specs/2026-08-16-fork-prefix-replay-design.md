# Phase 1 — fork prefix-reuse replay

Status: approved 2026-08-16 (mechanism: `os.fork` copy-on-write).

## Goal

Keep a live duel parked at recent DFS prefixes so a backtrack does not
`reset()` and replay from seed. `minimax_replay` and
`hidden_minimax_replay` stay unchanged. The replay callable still maps
`path -> Snapshot`.

Exit (from DIRECTION.md): existing fixtures keep identical scores, action
lines, and `complete` flags; Ghost Ogre wall-clock improves by about 10×
versus today's `ReplayCursor`, or the measurement explains why not.

## Why fork

`DuelAdapter` holds one native duel and forbids a second adapter (global
script/card readers). OCGCore has no clone/serialize API. DIRECTION lists
core cloning as a non-goal until prefix reuse is exhausted.

`ReplayCursor` already steps forward on descent. On backtrack it rebuilds
from seed. A second live prefix is required to beat that. `os.fork()`
copies the native duel, Lua, and RNG; the parent/keeper stays at the
prefix; the child steps.

## Mechanism

New callable `ForkReplayCursor` with the same constructor and
`__call__(path)` as `ReplayCursor`.

- After the seed `replay(())`, the search process forks worker 0 and must
  not call `adapter.step` / `adapter.reset` again until workers are
  joined.
- Workers talk to the search process over a Unix-domain socket.
- The search process holds a stack of workers, one per prefix along the
  current DFS path.
- Descent: the deepest worker whose path is a prefix of `path` forks; the
  child steps the suffix, connects as a new worker, and returns a pickled
  `Snapshot`. The keeper does not step.
- Backtrack: pop and `exit` workers whose path is not a prefix of the
  request. Worker 0 (path `()`) is a prefix of every path, so seed replay
  happens only if worker 0 has died (pool miss).
- Workers finish with `os._exit` so adapter destructors do not run in the
  child.

## CLI

`--replay-mode` gains `fork`. Default stays `cursor` so CI does not
depend on fork-safety. Oracle mode stays the correctness baseline.

## Failure

If `os.fork` is missing, construction raises `RuntimeError`. On macOS,
`ForkReplayCursor(...)` (the OCGCore path) raises unless
`YAPPING_FORK_ALLOW_DARWIN=1`, because forked children segfault in
libsqlite3/`os_log` during `adapter.step`. `from_snapshot` stays available
for in-process fake adapters. If a worker dies or IPC fails, raise; do not
silently fall back to `ReplayCursor`.

## Non-goals

- Engine clone or serialization.
- Changing minimax.
- Making `fork` the default.
- Windows.
- Parking a worker per visited node (only the current DFS spine).

## Measurement

Ghost Ogre on Darwin (this machine, 2026-08-16):

- `cursor` at 200 nodes: 0.54 s, 2.72 ms/state, incomplete
- `cursor` at 2000 nodes: 3.44 s, 1.72 ms/state, incomplete
- `fork` matches `cursor` on bounded Ash (80 nodes) when forced with
  `YAPPING_FORK_ALLOW_DARWIN=1`, then segfaults at visit ~142 on Ghost Ogre
  (`card::is_set_card` → sqlite3_reset → os_log). No 10×. Default stays
  `cursor`.

