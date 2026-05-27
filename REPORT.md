# REPORT — Voice Input Interface for aider

## Motivation

Terminal coding agents remove friction from the development loop, but they still demand constant keyboard attention: typing a question, waiting, typing a follow-up, copying an error message from a test run and pasting it. The hands stay glued to the keyboard even when the brain is focused on a completely different problem. Voice input dissolves that friction. The ideal state is: a developer looks at their screen, thinks out loud, and the agent acts — no hands needed.

---

## Choice of target agent: aider

Several open-source terminal coding agents were evaluated:

| Agent | Notes |
|---|---|
| **aider** | Mature, actively maintained, stdin-driven, git-aware, multi-model |
| opencode | Newer, good TUI but stdin integration is less documented |
| Claude Code (`claude`) | Excellent, but tighter subprocess control is harder with its interactive TUI |
| Cursor CLI | Primarily IDE-centric; poor headless mode |

aider was chosen for three reasons:

1. **stdin is a first-class interface.** aider reads from stdin line-by-line in interactive mode, which means the bridge is a single `subprocess.Popen` with `stdin=PIPE` — no screen-scraping, no pseudo-terminal emulation.
2. **Rich slash-command vocabulary.** `/add`, `/drop`, `/undo`, `/diff`, etc. map cleanly to spoken phrases.
3. **Multi-model support.** The same bridge works with GPT-4o, Claude Sonnet, Gemini, and local models — the user just changes `--model`.

---

## Speech-to-text engine: OpenAI Whisper API

### Alternatives evaluated

| Option | Verdict |
|---|---|
| **OpenAI Whisper API** (cloud) | ✅ Chosen — best accuracy/cost ratio |
| Local `whisper` (PyTorch) | Good accuracy but 1–4 GB model download; adds latency on CPU |
| Google Cloud Speech-to-Text | Comparable accuracy, more complex auth, higher cost at scale |
| Azure Cognitive Services Speech | Good, but vendor lock-in and heavier SDK |
| Vosk | Offline, lightweight, but noticeably lower accuracy on technical vocabulary |
| DeepSpeech / Coqui | Discontinued or unmaintained |

**Why Whisper API:** At **$0.006 / minute**, a 30-utterance session costs under $0.03. The API handles language detection, punctuation, and technical vocabulary (function names, library names) far better than any free offline alternative. The 16 kHz mono WAV format it expects is trivially produced by `sounddevice`.

**Cost safeguard:** A `MAX_RECORD_SECS = 60` cap ensures no single utterance can blow past one minute of audio. With typical 5–15 second utterances the per-session cost stays in the low single-digit cents.

---

## Input modes

### Push-to-talk (PTT) — default

The user holds a key (Space by default) while speaking. `pynput` listens for the key press/release globally and triggers `sounddevice` recording. This mirrors the familiar walkie-talkie paradigm, feels deliberate, and avoids spurious triggers from background noise.

**Fallback without pynput:** If `pynput` cannot be imported (e.g. in a restricted environment), the bridge falls back to Enter-to-start / Enter-to-stop, which is still fully scriptable from the keyboard.

### Continuous / VAD mode (--mode continuous)

Records until a configurable period of silence (default 1.5 s). Useful for longer dictations and truly hands-free scenarios, at the cost of occasional false stops in a noisy room. The silence threshold (`SILENCE_THRESHOLD`) is a tunable constant in `voice_input.py`.

---

## Integration method: subprocess stdin pipe

Two integration strategies were considered:

| Strategy | Description | Verdict |
|---|---|---|
| **stdin pipe** | Launch aider via `subprocess.Popen(stdin=PIPE)`, write lines | ✅ Chosen |
| PTY / `ptyprocess` | Allocate a pseudo-terminal, drive it like a human | Rejected |

The stdin pipe approach is simpler, more portable, and easier to test (mocking `Popen` is trivial). The PTY approach would be needed if aider required a real terminal (e.g. used `curses` or raw mode input), but aider's interactive mode works fine with a pipe.

aider's stdout is merged with stderr and streamed back to the terminal via a daemon reader thread, preserving full visual fidelity of responses including diffs, syntax-highlighted code, and progress indicators.

---

## Voice command substitution

A lightweight pattern table maps unambiguous short spoken phrases to aider slash commands. The design is intentionally conservative: only phrases that are **unambiguous single-word or short fixed phrases** are intercepted. Longer natural-language requests are forwarded verbatim, so the user can say _"add a docstring to every function in utils.py"_ and aider receives the full sentence.

This avoids the brittleness of a full NLU layer while still making common operations (undo, clear, add file, exit) voice-accessible without needing to spell out the slash character.

---

## Trade-offs and limitations

| Limitation | Explanation |
|---|---|
| **Latency** | Each utterance incurs a Whisper API round-trip (typically 0.5–1.5 s). This is imperceptible for normal coding interaction but would feel slow for rapid-fire short commands. |
| **No audio output** | The spec explicitly excludes TTS; responses are text-only. Adding TTS (e.g. ElevenLabs or `pyttsx3`) would close the loop for fully eyes-free use. |
| **Wayland PTT** | `pynput` global key hooks require X11 or special permissions on Wayland. The Enter-fallback activates automatically. |
| **Single aider session** | The bridge manages one subprocess. Multi-agent / parallel sessions are not in scope. |
| **aider API surface** | The bridge relies on aider reading from stdin line-by-line. If aider moves to a socket/RPC API in a future version, the bridge would need updating. |
| **Noise sensitivity** | VAD threshold is a simple RMS check. A production system would benefit from a learned VAD model (e.g. Silero VAD). |

---

## What went well

- The stdin pipe integration turned out to be remarkably simple — fewer than 80 lines for the bridge — because aider already treats stdin as a first-class interface.
- Whisper's accuracy on developer vocabulary (library names, function signatures, CLI flags) was notably better than expected, making the "add file app.py" pattern practical in real use.
- The PTT approach eliminates the accidental-trigger problem entirely; developers already understand the hold-to-talk metaphor from voice chat tools.

---

## External services used

| Service | Purpose | Cost model | Why chosen |
|---|---|---|---|
| OpenAI Whisper API | Speech-to-text | $0.006 / min | Best accuracy/cost for technical vocabulary |
| OpenAI GPT-4o (via aider) | Code generation | ~$10 / 1M tokens | Default aider model; swappable |

No data is retained by either service beyond the standard API logging window. No credentials are included in the submission.
