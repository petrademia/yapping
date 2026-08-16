"""Park one forked live duel per DFS prefix; replay from seed only on a miss."""

from __future__ import annotations

import os
import pickle
import signal
import socket
import struct
import sys
import tempfile

from analyze_ash import action_name, replay, snapshot_from_duel

DARWIN_FORK_ERROR = (
    "fork replay is not supported on macOS: OCGCore card reads go through "
    "libsqlite3, which calls os_log after fork and segfaults. Use "
    "--replay-mode cursor. Set YAPPING_FORK_ALLOW_DARWIN=1 only to reproduce."
)


def ocgcore_fork_allowed():
    if not hasattr(os, "fork"):
        return False
    if sys.platform == "darwin" and not os.environ.get("YAPPING_FORK_ALLOW_DARWIN"):
        return False
    return True


def _require_ocgcore_fork():
    if not hasattr(os, "fork"):
        raise RuntimeError("fork replay requires os.fork")
    if sys.platform == "darwin" and not os.environ.get("YAPPING_FORK_ALLOW_DARWIN"):
        raise RuntimeError(DARWIN_FORK_ERROR)


def _is_prefix(prefix, path):
    return len(path) >= len(prefix) and path[:len(prefix)] == prefix


def _readn(sock, n):
    chunks = []
    remaining = n
    while remaining:
        chunk = sock.recv(remaining)
        if not chunk:
            raise ConnectionError("fork replay worker closed the socket")
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


def _send(sock, obj):
    payload = pickle.dumps(obj, protocol=pickle.HIGHEST_PROTOCOL)
    sock.sendall(struct.pack("!I", len(payload)) + payload)


def _recv(sock):
    n = struct.unpack("!I", _readn(sock, 4))[0]
    return pickle.loads(_readn(sock, n))


def _worker_loop(adapter, conn, snapshot, controlled_player, sock_path):
    signal.signal(signal.SIGCHLD, signal.SIG_IGN)
    try:
        _send(conn, snapshot)
        while True:
            message = _recv(conn)
            command = message[0]
            if command == "snapshot":
                _send(conn, snapshot)
            elif command == "descend":
                suffix = message[1]
                pid = os.fork()
                if pid == 0:
                    conn.close()
                    try:
                        chosen = list(snapshot.actions)
                        decision = snapshot.decision
                        for index in suffix:
                            action = decision["actions"][index]
                            chosen.append(action_name(action))
                            decision = adapter.step(index)
                        child_snap = snapshot_from_duel(
                            adapter, decision, tuple(chosen), controlled_player)
                        child_conn = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                        child_conn.connect(sock_path)
                        _worker_loop(adapter, child_conn, child_snap,
                                     controlled_player, sock_path)
                    except Exception as error:
                        sys.stderr.write(f"fork replay child failed: {error!r}\n")
                        sys.stderr.flush()
                    os._exit(1)
                _send(conn, pid)
            elif command == "exit":
                os._exit(0)
            else:
                os._exit(1)
    except Exception as error:
        sys.stderr.write(f"fork replay worker failed: {error!r}\n")
        sys.stderr.flush()
        os._exit(1)


class _Worker:
    def __init__(self, path, pid, conn, snapshot):
        self.path = path
        self.pid = pid
        self.conn = conn
        self.snapshot = snapshot

    def close(self):
        try:
            _send(self.conn, ("exit",))
        except OSError:
            pass
        try:
            self.conn.close()
        except OSError:
            pass
        try:
            os.waitpid(self.pid, 0)
        except ChildProcessError:
            pass


class ForkReplayCursor:
    """Reuse parked prefixes via fork(); reconstruct from seed only on a miss."""

    def __init__(self, opponent_card=None, opening_hand=None,
                 ecclesia_copies=1, adapter=None, matchup=None,
                 controlled_player=0):
        _require_ocgcore_fork()
        snapshot = replay((), opponent_card, opening_hand, ecclesia_copies,
                          adapter, matchup, controlled_player)
        self._start(adapter, snapshot, controlled_player)

    @classmethod
    def from_snapshot(cls, adapter, snapshot, controlled_player=0):
        if not hasattr(os, "fork"):
            raise RuntimeError("fork replay requires os.fork")
        cursor = object.__new__(cls)
        cursor._start(adapter, snapshot, controlled_player)
        return cursor

    def _start(self, adapter, snapshot, controlled_player):
        self.adapter = adapter
        self.controlled_player = controlled_player
        self._sock_path = tempfile.mktemp(prefix="yapping-fork-", suffix=".sock")
        self._listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self._workers = []
        self._prev_sigchld = signal.signal(signal.SIGCHLD, signal.SIG_IGN)
        try:
            self._listener.bind(self._sock_path)
            self._listener.listen(16)
            self._listener.settimeout(10)
            pid = os.fork()
            if pid == 0:
                self._listener.close()
                conn = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                conn.connect(self._sock_path)
                _worker_loop(adapter, conn, snapshot, controlled_player,
                             self._sock_path)
                os._exit(0)
            conn, _ = self._listener.accept()
            announced = _recv(conn)
            self._workers = [_Worker((), pid, conn, announced)]
            self.path = ()
            self.snapshot = announced
        except Exception:
            self.close()
            raise

    def __call__(self, path):
        path = tuple(path)
        while self._workers and not _is_prefix(self._workers[-1].path, path):
            self._workers[-1].close()
            self._workers.pop()
        if not self._workers:
            raise RuntimeError("fork replay pool miss: seed worker died")
        worker = self._workers[-1]
        if worker.path == path:
            self.path = path
            self.snapshot = worker.snapshot
            return worker.snapshot
        suffix = path[len(worker.path):]
        _send(worker.conn, ("descend", suffix))
        pid = _recv(worker.conn)
        try:
            conn, _ = self._listener.accept()
        except TimeoutError as error:
            raise RuntimeError(
                f"fork replay child {pid} did not connect"
            ) from error
        child_snap = _recv(conn)
        child = _Worker(path, pid, conn, child_snap)
        self._workers.append(child)
        self.path = path
        self.snapshot = child_snap
        return child_snap

    def close(self):
        while self._workers:
            self._workers[-1].close()
            self._workers.pop()
        listener = getattr(self, "_listener", None)
        if listener is not None:
            try:
                listener.close()
            except OSError:
                pass
            self._listener = None
        path = getattr(self, "_sock_path", None)
        if path:
            try:
                os.unlink(path)
            except OSError:
                pass
            self._sock_path = None
        prev = getattr(self, "_prev_sigchld", None)
        if prev is not None:
            signal.signal(signal.SIGCHLD, prev)
            self._prev_sigchld = None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
        return False
