"""
voice_input.py — Capture microphone audio and transcribe via Groq Whisper (free).

Supports two modes:
  • push-to-talk  : record while a key is held (default: Space)
  • continuous    : record until silence is detected (VAD-based)
"""

from __future__ import annotations

import os
import sys
import time
import wave
import tempfile
import threading
import argparse
from pathlib import Path
from typing import Optional

import numpy as np

# ── optional imports (graceful degradation) ──────────────────────────────────
try:
    import sounddevice as sd
    SOUNDDEVICE_OK = True
except ImportError:
    SOUNDDEVICE_OK = False
    print("[voice_input] WARNING: sounddevice not installed – audio capture disabled.", file=sys.stderr)

try:
    from groq import Groq
    GROQ_OK = True
except ImportError:
    GROQ_OK = False
    print("[voice_input] WARNING: groq not installed – run: pip install groq", file=sys.stderr)

try:
    from pynput import keyboard as pynput_keyboard
    PYNPUT_OK = True
except ImportError:
    PYNPUT_OK = False

# ── constants ─────────────────────────────────────────────────────────────────
SAMPLE_RATE       = 16_000
CHANNELS          = 1
DTYPE             = "int16"
SILENCE_THRESHOLD = 500
SILENCE_DURATION  = 1.5
MAX_RECORD_SECS   = 60


class AudioRecorder:
    """Thread-safe audio recorder wrapping sounddevice."""

    def __init__(self, sample_rate: int = SAMPLE_RATE, channels: int = CHANNELS):
        if not SOUNDDEVICE_OK:
            raise RuntimeError("sounddevice is required for audio capture.")
        self.sample_rate = sample_rate
        self.channels    = channels
        self._frames: list[np.ndarray] = []
        self._recording  = False
        self._stream: Optional[sd.InputStream] = None

    def _callback(self, indata, frames, time_info, status):
        if self._recording:
            self._frames.append(indata.copy())

    def _rms(self, chunk: np.ndarray) -> float:
        return float(np.sqrt(np.mean(chunk.astype(np.float64) ** 2)))

    def start(self):
        self._frames = []
        self._recording = True
        self._stream = sd.InputStream(
            samplerate=self.sample_rate,
            channels=self.channels,
            dtype=DTYPE,
            callback=self._callback,
        )
        self._stream.start()

    def stop(self) -> np.ndarray:
        self._recording = False
        if self._stream:
            self._stream.stop()
            self._stream.close()
            self._stream = None
        if not self._frames:
            return np.array([], dtype=DTYPE)
        return np.concatenate(self._frames, axis=0)

    def record_push_to_talk(self, key: str = "space") -> np.ndarray:
        if not PYNPUT_OK:
            print(f"\n[PTT] Press ENTER to start recording...", flush=True)
            input()
            print("[PTT] Recording… press ENTER to stop.", flush=True)
            self.start()
            input()
            return self.stop()

        _key_map = {
            "space": pynput_keyboard.Key.space,
            "ctrl":  pynput_keyboard.Key.ctrl,
            "alt":   pynput_keyboard.Key.alt,
        }
        target  = _key_map.get(key.lower(), pynput_keyboard.Key.space)
        pressed  = threading.Event()
        released = threading.Event()

        def on_press(k):
            if k == target and not pressed.is_set():
                pressed.set()
                self.start()
                print("\n[PTT] 🔴 Recording…", flush=True)

        def on_release(k):
            if k == target and pressed.is_set():
                released.set()
                return False

        print(f"\n[PTT] Hold [{key.upper()}] to speak, release to send.", flush=True)
        with pynput_keyboard.Listener(on_press=on_press, on_release=on_release) as listener:
            listener.join()

        audio = self.stop()
        print("[PTT] ⏹  Stopped.", flush=True)
        return audio

    def record_continuous(self) -> np.ndarray:
        print("\n[VAD] Speak now (auto-stops on silence)…", flush=True)
        self.start()
        silence_start: Optional[float] = None
        start_time = time.time()

        while True:
            time.sleep(0.1)
            if time.time() - start_time > MAX_RECORD_SECS:
                print("[VAD] Max duration reached.", flush=True)
                break
            if self._frames:
                rms = self._rms(self._frames[-1])
                if rms < SILENCE_THRESHOLD:
                    if silence_start is None:
                        silence_start = time.time()
                    elif time.time() - silence_start >= SILENCE_DURATION:
                        print("[VAD] Silence detected — stopping.", flush=True)
                        break
                else:
                    silence_start = None

        return self.stop()


def save_wav(audio: np.ndarray, sample_rate: int = SAMPLE_RATE) -> str:
    """Save numpy audio array to a temp WAV file; return path."""
    tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    with wave.open(tmp.name, "wb") as wf:
        wf.setnchannels(CHANNELS)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(audio.tobytes())
    return tmp.name


def transcribe_whisper(wav_path: str, language: Optional[str] = None) -> str:
    """Send WAV to Groq Whisper API (free) and return transcript text."""
    if not GROQ_OK:
        raise RuntimeError("groq package not installed. Run: pip install groq")

    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise EnvironmentError("GROQ_API_KEY environment variable not set.")

    client = Groq(api_key=api_key)
    with open(wav_path, "rb") as f:
        kwargs = {
            "model": "whisper-large-v3",
            "file": ("audio.wav", f, "audio/wav"),
            "response_format": "text",
        }
        if language:
            kwargs["language"] = language
        result = client.audio.transcriptions.create(**kwargs)

    return result.strip() if isinstance(result, str) else result.text.strip()


def record_and_transcribe(
    mode: str = "ptt",
    ptt_key: str = "space",
    language: Optional[str] = None,
) -> str:
    recorder = AudioRecorder()

    if mode == "continuous":
        audio = recorder.record_continuous()
    else:
        audio = recorder.record_push_to_talk(key=ptt_key)

    if audio.size == 0:
        return ""

    wav_path = save_wav(audio)
    try:
        print("[Whisper] Transcribing…", flush=True)
        text = transcribe_whisper(wav_path, language=language)
        print(f"[Whisper] ✅ '{text}'", flush=True)
        return text
    finally:
        Path(wav_path).unlink(missing_ok=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Voice capture + Groq Whisper transcription test")
    parser.add_argument("--mode", choices=["ptt", "continuous"], default="ptt")
    parser.add_argument("--key",  default="space")
    parser.add_argument("--lang", default=None)
    args = parser.parse_args()

    text = record_and_transcribe(mode=args.mode, ptt_key=args.key, language=args.lang)
    print(f"\nTranscript: {text}")
