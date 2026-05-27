# 🎙 Voice Input Interface for aider

A hands-free voice interface that wraps **[aider](https://aider.chat)** — the open-source terminal AI coding agent — and lets you drive it entirely through spoken commands. Every utterance is captured from your microphone, transcribed via **OpenAI Whisper**, and sent to aider's stdin as if you had typed it.

---

## Architecture

```
┌─────────────────────────────────────────────────────┐
│                  voice_agent.py                     │
│  (main loop + voice-command substitution table)     │
└────────────┬───────────────────────┬────────────────┘
             │                       │
     ┌───────▼──────┐      ┌─────────▼────────┐
     │ voice_input  │      │  agent_bridge    │
     │  .py         │      │  .py             │
     │              │      │                  │
     │ sounddevice  │      │ subprocess.Popen │
     │ (mic capture)│      │ (aider --stdin)  │
     │     +        │      └──────────────────┘
     │ Whisper API  │
     └──────────────┘
```

| Component | File | Responsibility |
|---|---|---|
| `voice_input.py`  | `src/` | Mic capture (PTT & VAD), WAV export, Whisper API call |
| `agent_bridge.py` | `src/` | Launch aider as a subprocess, pipe text to its stdin |
| `voice_agent.py`  | `src/` | Orchestration loop, voice-command substitution, CLI |

---

## Prerequisites

| Requirement | Notes |
|---|---|
| Python 3.9 + | Tested on 3.9, 3.10, 3.11 |
| PortAudio | Required by `sounddevice` (see below) |
| OpenAI API key | For Whisper transcription **and** aider's LLM |
| Git repository | aider must be run inside a git repo |

### Install PortAudio

```bash
# macOS
brew install portaudio

# Ubuntu / Debian
sudo apt-get install portaudio19-dev

# Windows
# PortAudio is bundled in the sounddevice wheel — no extra step needed.
```

---

## Installation

```bash
# 1. Clone / unzip this project
cd voice-agent

# 2. Create and activate a virtual environment
python -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate

# 3. Install Python dependencies
pip install -r requirements.txt
```

> **Cost note:** Whisper API pricing is **$0.006 / minute** of audio. A typical coding session of 30 short utterances (~10 s each) costs ~$0.03. aider itself uses the LLM you configure (GPT-4o by default); costs depend on your usage.

---

## Configuration

Export your API key before running:

```bash
export OPENAI_API_KEY="sk-..."        # macOS / Linux
set OPENAI_API_KEY=sk-...             # Windows cmd
$env:OPENAI_API_KEY="sk-..."          # Windows PowerShell
```

aider also reads `ANTHROPIC_API_KEY` if you want to use a Claude model.

---

## Usage

### Quick start (inside a git repo)

```bash
cd /path/to/your/project
python /path/to/voice-agent/src/voice_agent.py
```

Hold **Space** to speak, release to send. aider's response appears on screen.

### Full CLI reference

```
python src/voice_agent.py [options]

Options:
  --model MODEL        aider LLM (default: gpt-4o)
  --mode {ptt,continuous}
                       ptt = push-to-talk (hold SPACE)
                       continuous = auto-stop on silence
  --key {space,ctrl,alt}
                       PTT key (default: space)
  --lang LANG          Whisper language hint, e.g. en (default: auto)
  --files FILE ...     Files to open in aider at startup
  --no-auto-commits    Pass --no-auto-commits to aider
  --dry-run            Transcribe only, do not launch aider
  --aider-args ...     Extra flags forwarded verbatim to aider
```

### Examples

```bash
# Default PTT, GPT-4o:
python src/voice_agent.py

# VAD mode (hands-free), Claude Sonnet:
python src/voice_agent.py --mode continuous \
    --model claude-3-5-sonnet-20241022

# Open files, no git commits:
python src/voice_agent.py --files app.py utils.py --no-auto-commits

# Test microphone + Whisper without aider:
python src/voice_agent.py --dry-run

# Test Whisper module standalone:
python src/voice_input.py --mode ptt
```

---

## Voice commands

These spoken phrases are mapped to aider slash commands before sending:

| You say | aider receives |
|---|---|
| "exit" / "quit" / "goodbye" | `/exit` |
| "undo" | `/undo` |
| "clear" | `/clear` |
| "help" | `/help` |
| "run" | `/run` |
| "show diff" | `/diff` |
| "add file app.py" | `/add app.py` |
| "drop file utils.py" | `/drop utils.py` |
| anything else | forwarded as-is |

---

## Running the tests

```bash
# From the project root
pytest tests/ -v
```

No API key is required; all network calls are mocked.

---

## Demo setup time

**~2 minutes** from a clean environment with dependencies already installed.

Steps:
1. `export OPENAI_API_KEY=...` (30 s)
2. `cd` into any git repo (5 s)
3. `python src/voice_agent.py` (30 s to start aider)
4. Hold Space → speak → release (live demo)

---

## Limitations & known issues

- **Linux Wayland:** `pynput` global key listener may require `xdotool` or running as root. The Enter-fallback mode activates automatically.
- **Background noise:** The VAD silence threshold (`SILENCE_THRESHOLD = 500` RMS) may need tuning in noisy environments. Adjust in `voice_input.py`.
- **aider version compatibility:** Tested with `aider-chat >= 0.50`. The bridge writes to aider's stdin; if a future aider version changes its input protocol this may need updating.
- **No audio output:** Responses are text-only on screen. TTS was intentionally excluded per the problem spec.
- **Single session:** The bridge manages one aider process. Parallel sessions are not supported.

---

## License

MIT License — see `LICENSE`.

Dependencies and their licenses:
| Package | License |
|---|---|
| aider-chat | Apache 2.0 |
| openai | MIT |
| sounddevice | MIT |
| numpy | BSD-3 |
| pynput | LGPL-3.0 |
| pytest | MIT |

All dependency licenses are permissive and compatible with MIT.
