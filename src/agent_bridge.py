"""
agent_bridge.py — Pipe transcribed text into a running aider session.

Architecture
------------
aider is launched as a subprocess with its stdin connected to a pipe.
The bridge writes each transcribed utterance followed by a newline
into that pipe, exactly as if the user had typed it at the keyboard.

aider's stdout/stderr are forwarded to the terminal so the user still
sees all responses on screen (no TTS required).
"""

from __future__ import annotations

import os
import sys
import subprocess
import threading
import signal
import shutil
import time
from pathlib import Path
from typing import Optional, List


# ── helpers ───────────────────────────────────────────────────────────────────

def _find_aider() -> Optional[str]:
    """Return path to aider binary, or None if not found."""
    return shutil.which("aider")


def _stream_output(stream, prefix: str = ""):
    """Forward a stream to stdout in a daemon thread."""
    def _run():
        for line in iter(stream.readline, b""):
            decoded = line.decode("utf-8", errors="replace")
            sys.stdout.write(prefix + decoded)
            sys.stdout.flush()
    t = threading.Thread(target=_run, daemon=True)
    t.start()
    return t


# ── main class ────────────────────────────────────────────────────────────────

class AiderBridge:
    """
    Manages a long-running aider subprocess and exposes `send(text)`.

    Parameters
    ----------
    model       : LLM model passed to aider (e.g. 'gpt-4o', 'claude-3-5-sonnet-20241022')
    files       : extra files to open in aider on start
    extra_args  : any additional CLI flags forwarded verbatim to aider
    no_auto_commits : pass --no-auto-commits to aider
    """

    def __init__(
        self,
        model: str = "gpt-4o",
        files: Optional[List[str]] = None,
        extra_args: Optional[List[str]] = None,
        no_auto_commits: bool = False,
    ):
        self.model           = model
        self.files           = files or []
        self.extra_args      = extra_args or []
        self.no_auto_commits = no_auto_commits
        self._proc: Optional[subprocess.Popen] = None

    # ── lifecycle ─────────────────────────────────────────────────────────────

    def start(self):
        """Launch aider subprocess."""
        aider_bin = _find_aider()
        if not aider_bin:
            raise FileNotFoundError(
                "aider not found on PATH. Install with:  pip install aider-chat"
            )

        cmd = [aider_bin, "--model", self.model]
        if self.no_auto_commits:
            cmd.append("--no-auto-commits")
        cmd += self.extra_args
        cmd += self.files

        print(f"[bridge] Starting aider: {' '.join(cmd)}", flush=True)

        self._proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,   # merge stderr into stdout
            bufsize=0,
        )

        # stream aider output to terminal
        _stream_output(self._proc.stdout)

        # give aider a moment to print its banner
        time.sleep(2)
        print("[bridge] aider is ready.", flush=True)

    def send(self, text: str):
        """Write a line of text to aider's stdin."""
        if not self._proc or self._proc.poll() is not None:
            raise RuntimeError("aider process is not running.")
        line = text.strip() + "\n"
        self._proc.stdin.write(line.encode("utf-8"))
        self._proc.stdin.flush()
        print(f"[bridge] → sent: {text!r}", flush=True)

    def stop(self):
        """Gracefully terminate aider."""
        if self._proc and self._proc.poll() is None:
            try:
                self._proc.stdin.write(b"/exit\n")
                self._proc.stdin.flush()
                self._proc.wait(timeout=5)
            except Exception:
                self._proc.terminate()
        print("[bridge] aider stopped.", flush=True)

    def is_alive(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    # ── context manager ───────────────────────────────────────────────────────

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, *_):
        self.stop()


# ── CLI smoke-test ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Send a test message to aider via bridge")
    parser.add_argument("--model", default="gpt-4o")
    parser.add_argument("message", nargs="?", default="What files are in this directory?")
    args = parser.parse_args()

    with AiderBridge(model=args.model) as bridge:
        bridge.send(args.message)
        time.sleep(8)   # wait for response
