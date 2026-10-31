#!/usr/bin/env python3
"""Run a command with a wall-clock timeout, killing its whole process group (macOS has no `timeout`).

Usage: run_timeout.py [--shield] <seconds> -- <command> [args...]
Exit code: the command's own, 124 when the timeout fired (same as GNU timeout), 143 when this script was
terminated (SIGTERM/SIGINT/SIGHUP are forwarded to the command's group), 127 when the command cannot start.
--shield: for a step that must finish (a restore during cleanup). This script ignores INT/TERM/HUP and the command runs
in its own session, so a terminal Ctrl-C never reaches it, even when the command re-enables SIGINT (Go programs such as
docker compose do); only the timeout stops it.
"""
import os
import signal
import subprocess
import sys

GRACE_SECONDS = 5
POLL_SECONDS = 0.5
SIGNALS = (signal.SIGTERM, signal.SIGINT, signal.SIGHUP)


def kill_group(proc: subprocess.Popen):
    """TERM the command's process group, give it a moment, then KILL whatever is left (even if the leader already exited)."""
    for sig in (signal.SIGTERM, signal.SIGKILL):
        try:
            os.killpg(proc.pid, sig)
        except OSError:  # gone, or (macOS: EPERM) a group that holds only a zombie
            return
        if sig == signal.SIGTERM:
            try:
                proc.wait(timeout=GRACE_SECONDS)
            except subprocess.TimeoutExpired:
                pass


def child_setup():
    """In the child before exec: unblock the signals blocked around the start and put INT, QUIT, TERM and HUP back to their
    default action (a background job inherits INT/QUIT ignored; --shield ignores the rest in this script), so the
    command still stops gracefully on the timeout's TERM."""
    signal.pthread_sigmask(signal.SIG_UNBLOCK, SIGNALS)
    for sig in (signal.SIGINT, signal.SIGQUIT, signal.SIGTERM, signal.SIGHUP):
        signal.signal(sig, signal.SIG_DFL)


def wait_with_deadline(proc: subprocess.Popen, seconds: float):
    """Wait in short polls, so a signal handler can reap the command too; returns its code or None on timeout."""
    remaining = seconds if seconds > 0 else None
    while True:
        step = POLL_SECONDS if remaining is None else min(POLL_SECONDS, remaining)
        try:
            return proc.wait(timeout=step)
        except subprocess.TimeoutExpired:
            if remaining is not None:
                remaining -= step
                if remaining <= 0:
                    return None


def main() -> int:
    """Start the command in its own session; on timeout or on a signal to this script, stop its whole group."""
    args = sys.argv[1:]
    shield = bool(args) and args[0] == "--shield"
    if shield:
        args = args[1:]
    if len(args) < 3 or args[1] != "--":
        print("usage: run_timeout.py [--shield] <seconds> -- <command> [args...]", file=sys.stderr)
        return 2
    seconds, command = float(args[0]), args[2:]
    started = []

    def forward(signum, _frame):
        kill_group(started[0])
        sys.exit(143)

    # Signals are blocked from before the start until the command is recorded, so one that arrives in between is
    # handled (forwarded) after the record instead of leaving an orphan.
    signal.pthread_sigmask(signal.SIG_BLOCK, SIGNALS)
    for sig in SIGNALS:
        signal.signal(sig, signal.SIG_IGN if shield else forward)
    try:
        proc = subprocess.Popen(command, start_new_session=True, preexec_fn=child_setup)
    except OSError as err:
        print(f"cannot start {command[0]}: {err}", file=sys.stderr)
        return 127
    started.append(proc)
    signal.pthread_sigmask(signal.SIG_UNBLOCK, SIGNALS)
    code = wait_with_deadline(proc, seconds)
    if code is not None:
        return code
    kill_group(proc)
    print(f"TIMEOUT: killed after {seconds:.0f}s: {' '.join(command)[:200]}", file=sys.stderr)
    return 124


if __name__ == "__main__":
    sys.exit(main())
