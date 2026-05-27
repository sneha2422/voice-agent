#!/usr/bin/env python3
"""
voice_agent.py — Main entry point for the Voice Input Interface.

Usage
-----
  python voice_agent.py [options]

The loop:
  1. Wait for voice input (push-to-talk or VAD)
  2. Transcribe via Whisper
  3. Apply optional command substitutions
  4. Send to aider via stdin pipe
  5. aider prints its response to screen
  6. Goto 1

Voice commands (spoken) → aider slash commands
-----------------------------------------------
  "exit" / "quit" / "goodbye"   → /exit
  "undo"                         → /undo
  "add file <name>"              → /add <name>
  "drop file <name>"             → /drop <name>
  "clear"                        → /clear
  "help"                         → /help
  "run"                          → /run
"""

from __future__ import annotations

import os
import re
import sys
import time
import signal
import argparse
import textwrap
from typing import Optional

# ── project imports ───────────────────────────────────────────────────────────
sys.path.insert(0, str(__file__ + "/../"))
from voice_input  import record_and_transcribe
from agent_bridge import AiderBridge

# ── voice command substitutions ───────────────────────────────────────────────

VOICE_COMMANDS: list[tuple[re.Pattern, str]] = [
    # exit synonyms
    (re.compile(r"^\s*(exit|quit|goodbye|bye)\s*$", re.I), "/exit"),
    # undo
    (re.compile(r"^\s*undo\s*$", re.I),                    "/undo"),
    # clear
    (re.compile(r"^\s*clear\s*$", re.I),                   "/clear"),
    # help
    (re.compile(r"^\s*help\s*$", re.I),                    "/help"),
    # run
    (re.compile(r"^\s*run\s*$", re.I),                     "/run"),
    # add file <name>
    (re.compile(r"^\s*add\s+file\s+(\S+)\s*$", re.I),     r"/add \1"),
    # drop file <name>
    (re.compile(r"^\s*drop\s+file\s+(\S+)\s*$", re.I),    r"/drop \1"),
    # show diff
    (re.compile(r"^\s*show\s+diff\s*$", re.I),             "/diff"),
]


def apply_voice_commands(text: str) -> str:
    """Map spoken phrases to aider slash commands."""
    for pattern, replacement in VOICE_COMMANDS:
        m = pattern.match(text)
        if m:
            # handle back-references like r"/add \1"
            return m.expand(replacement)
    return text


# ── banner ────────────────────────────────────────────────────────────────────

BANNER = textwrap.dedent("""
╔══════════════════════════════════════════════════════╗
║        🎙  Voice Input Interface for aider          ║
╠══════════════════════════════════════════════════════╣
║  PTT mode  : Hold SPACE to speak, release to send   ║
║  VAD mode  : Speak; auto-stops on silence           ║
║                                                      ║
║  Say "exit" or "quit" to leave                      ║
╚══════════════════════════════════════════════════════╝
""")


# ── main loop ─────────────────────────────────────────────────────────────────

def run(
    model: str        = "gpt-4o",
    mode: str         = "ptt",
    ptt_key: str      = "space",
    language: Optional[str] = None,
    files: list[str]  = (),
    extra_args: list[str] = (),
    no_auto_commits: bool = False,
    dry_run: bool     = False,
):
    """
    Main voice-agent loop.

    Parameters
    ----------
    model           : aider --model value
    mode            : 'ptt' or 'continuous'
    ptt_key         : push-to-talk key ('space', 'ctrl', 'alt')
    language        : Whisper language hint
    files           : files to open in aider
    extra_args      : extra aider CLI flags
    no_auto_commits : pass --no-auto-commits to aider
    dry_run         : if True, print transcripts without sending to aider
    """
    print(BANNER)

    if dry_run:
        print("[dry-run] aider will NOT be started — transcripts printed only.\n")

    bridge: Optional[AiderBridge] = None

    def _shutdown(*_):
        print("\n[voice_agent] Shutting down…", flush=True)
        if bridge:
            bridge.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT,  _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    if not dry_run:
        bridge = AiderBridge(
            model=model,
            files=list(files),
            extra_args=list(extra_args),
            no_auto_commits=no_auto_commits,
        )
        bridge.start()

    iteration = 0
    while True:
        iteration += 1
        print(f"\n{'─'*54}", flush=True)
        print(f"[Turn {iteration}] Waiting for voice input…", flush=True)

        try:
            raw_text = record_and_transcribe(
                mode=mode,
                ptt_key=ptt_key,
                language=language,
            )
        except KeyboardInterrupt:
            _shutdown()
        except Exception as exc:
            print(f"[voice_agent] ⚠ Capture error: {exc}", flush=True)
            continue

        if not raw_text.strip():
            print("[voice_agent] (empty transcript — skipped)", flush=True)
            continue

        # apply voice-command substitutions
        text = apply_voice_commands(raw_text)
        if text != raw_text:
            print(f"[voice_agent] Command substitution: {raw_text!r} → {text!r}")

        # check for exit
        if text.strip() == "/exit":
            _shutdown()

        if dry_run:
            print(f"[dry-run] Would send: {text!r}")
        else:
            if not bridge or not bridge.is_alive():
                print("[voice_agent] ⚠ aider process died — restarting…", flush=True)
                bridge = AiderBridge(
                    model=model,
                    files=list(files),
                    extra_args=list(extra_args),
                    no_auto_commits=no_auto_commits,
                )
                bridge.start()

            try:
                bridge.send(text)
            except Exception as exc:
                print(f"[voice_agent] ⚠ Send error: {exc}", flush=True)

        # small pause so the user can see the response begin
        time.sleep(0.5)


# ── CLI ───────────────────────────────────────────────────────────────────────

def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="voice_agent",
        description="Voice Input Interface for the aider coding agent",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent("""
        Examples
        --------
          # PTT with default GPT-4o:
          python voice_agent.py

          # VAD mode with Claude Sonnet:
          python voice_agent.py --mode continuous --model claude-3-5-sonnet-20241022

          # Open specific files, no auto-commits:
          python voice_agent.py --files app.py utils.py --no-auto-commits

          # Dry-run (no aider, just test transcription):
          python voice_agent.py --dry-run
        """),
    )
    p.add_argument("--model",   default="gpt-4o",
                   help="LLM model for aider (default: gpt-4o)")
    p.add_argument("--mode",    choices=["ptt", "continuous"], default="ptt",
                   help="Input mode: push-to-talk or VAD (default: ptt)")
    p.add_argument("--key",     dest="ptt_key", default="space",
                   choices=["space", "ctrl", "alt"],
                   help="Push-to-talk key (default: space)")
    p.add_argument("--lang",    dest="language", default=None,
                   help="Whisper language hint, e.g. 'en' (default: auto-detect)")
    p.add_argument("--files",   nargs="*", default=[],
                   help="Files to open in aider")
    p.add_argument("--aider-args", nargs=argparse.REMAINDER, default=[],
                   dest="extra_args",
                   help="Extra arguments forwarded verbatim to aider")
    p.add_argument("--no-auto-commits", action="store_true",
                   help="Pass --no-auto-commits to aider")
    p.add_argument("--dry-run", action="store_true",
                   help="Transcribe only — do not launch or send to aider")
    return p


if __name__ == "__main__":
    args = _build_parser().parse_args()
    run(
        model           = args.model,
        mode            = args.mode,
        ptt_key         = args.ptt_key,
        language        = args.language,
        files           = args.files,
        extra_args      = args.extra_args,
        no_auto_commits = args.no_auto_commits,
        dry_run         = args.dry_run,
    )
