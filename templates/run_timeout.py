#!/usr/bin/env python3
"""Run a command with a wall-clock timeout, killing its whole process group (macOS has no `timeout`).

Usage: run_timeout.py <seconds> -- <command> [args...]
Exit code: the command's own, 124 when the timeout fired (same as GNU timeout), 143 when this script was
terminated (SIGTERM/SIGINT/SIGHUP are forwarded to the command's group), 127 when the command cannot start.
"""
import os
import signal
import subprocess
import sys

GRACE_SECONDS = 5


def kill_group(proc: subprocess.Popen):
    """TERM the command's process group, give it a moment, then KILL whatever is left (even if the leader already exited)."""
    for sig in (signal.SIGTERM, signal.SIGKILL):
        try:
            os.killpg(proc.pid, sig)
        except ProcessLookupError:
            return
        if sig == signal.SIGTERM:
            try:
                proc.wait(timeout=GRACE_SECONDS)
            except subprocess.TimeoutExpired:
                pass


def main() -> int:
    """Start the command in its own session; on timeout or on a signal to this script, stop its whole group."""
    if len(sys.argv) < 4 or sys.argv[2] != "--":
        print("usage: run_timeout.py <seconds> -- <command> [args...]", file=sys.stderr)
        return 2
    seconds, command = float(sys.argv[1]), sys.argv[3:]
    try:
        proc = subprocess.Popen(command, start_new_session=True)
    except OSError as err:
        print(f"cannot start {command[0]}: {err}", file=sys.stderr)
        return 127

    def forward(signum, _frame):
        kill_group(proc)
        sys.exit(143)

    for sig in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
        signal.signal(sig, forward)
    try:
        return proc.wait(timeout=seconds if seconds > 0 else None)
    except subprocess.TimeoutExpired:
        kill_group(proc)
        print(f"TIMEOUT: killed after {seconds:.0f}s: {' '.join(command)[:200]}", file=sys.stderr)
        return 124


if __name__ == "__main__":
    sys.exit(main())
