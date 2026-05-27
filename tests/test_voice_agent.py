"""
tests/test_voice_agent.py — Unit tests for voice_agent components.

Run with:
    pytest tests/
"""

import sys
import os
import re
import types
import importlib
import unittest
from unittest.mock import patch, MagicMock

# ── path setup ────────────────────────────────────────────────────────────────
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))


# ─────────────────────────────────────────────────────────────────────────────
# voice_agent command substitution tests
# ─────────────────────────────────────────────────────────────────────────────

# Import only the pure-logic parts (no side-effectful imports needed)
from voice_agent import apply_voice_commands, VOICE_COMMANDS  # noqa: E402


class TestVoiceCommandSubstitution(unittest.TestCase):

    def test_exit_synonyms(self):
        for phrase in ["exit", "Exit", "quit", "QUIT", "goodbye", "bye"]:
            with self.subTest(phrase=phrase):
                self.assertEqual(apply_voice_commands(phrase), "/exit")

    def test_undo(self):
        self.assertEqual(apply_voice_commands("undo"), "/undo")
        self.assertEqual(apply_voice_commands("  UNDO  "), "/undo")

    def test_clear(self):
        self.assertEqual(apply_voice_commands("clear"), "/clear")

    def test_help(self):
        self.assertEqual(apply_voice_commands("help"), "/help")

    def test_run(self):
        self.assertEqual(apply_voice_commands("run"), "/run")

    def test_add_file(self):
        result = apply_voice_commands("add file app.py")
        self.assertEqual(result, "/add app.py")

    def test_drop_file(self):
        result = apply_voice_commands("drop file utils.py")
        self.assertEqual(result, "/drop utils.py")

    def test_show_diff(self):
        self.assertEqual(apply_voice_commands("show diff"), "/diff")

    def test_plain_text_passthrough(self):
        msg = "Write a function that sorts a list"
        self.assertEqual(apply_voice_commands(msg), msg)

    def test_empty_passthrough(self):
        self.assertEqual(apply_voice_commands(""), "")

    def test_case_insensitivity(self):
        self.assertEqual(apply_voice_commands("ADD FILE main.c"), "/add main.c")
        self.assertEqual(apply_voice_commands("DROP FILE README.md"), "/drop README.md")

    def test_natural_sentences_not_matched(self):
        # "run" as part of a longer sentence should NOT be substituted
        msg = "run the tests and fix any failures"
        self.assertEqual(apply_voice_commands(msg), msg)

    def test_undo_with_trailing_whitespace(self):
        self.assertEqual(apply_voice_commands("undo   "), "/undo")


# ─────────────────────────────────────────────────────────────────────────────
# voice_input audio helpers (mock sounddevice + openai)
# ─────────────────────────────────────────────────────────────────────────────

class TestSaveWav(unittest.TestCase):

    def test_save_and_load(self):
        """save_wav should produce a valid WAV file."""
        import numpy as np
        import wave
        from voice_input import save_wav

        # 0.5 s of silence
        audio = np.zeros(8000, dtype="int16")
        path  = save_wav(audio)

        self.assertTrue(os.path.exists(path))
        with wave.open(path, "rb") as wf:
            self.assertEqual(wf.getnchannels(), 1)
            self.assertEqual(wf.getsampwidth(), 2)
            self.assertEqual(wf.getframerate(), 16_000)

        os.unlink(path)

    def test_empty_audio(self):
        """save_wav with empty array should still produce a valid (silent) WAV."""
        import numpy as np
        from voice_input import save_wav

        audio = np.array([], dtype="int16")
        path  = save_wav(audio)
        self.assertTrue(os.path.exists(path))
        os.unlink(path)


class TestTranscribeWhisper(unittest.TestCase):

    @patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test"})
    @patch("builtins.open", unittest.mock.mock_open(read_data=b"RIFF...."))
    @patch("voice_input.openai")
    def test_transcribe_returns_string(self, mock_openai):
        """transcribe_whisper should return stripped text from the API."""
        from voice_input import transcribe_whisper

        mock_client = MagicMock()
        mock_openai.OpenAI.return_value = mock_client
        mock_client.audio.transcriptions.create.return_value = "  hello world  "

        result = transcribe_whisper("/tmp/fake.wav", language="en")
        self.assertEqual(result, "hello world")

    @patch.dict(os.environ, {}, clear=True)
    def test_missing_api_key_raises(self):
        from voice_input import transcribe_whisper
        # Remove key if present
        os.environ.pop("OPENAI_API_KEY", None)
        with self.assertRaises(EnvironmentError):
            transcribe_whisper("/tmp/fake.wav")


# ─────────────────────────────────────────────────────────────────────────────
# agent_bridge smoke test (no real subprocess)
# ─────────────────────────────────────────────────────────────────────────────

class TestAiderBridgeSend(unittest.TestCase):

    @patch("agent_bridge.shutil.which", return_value="/usr/bin/aider")
    @patch("agent_bridge.subprocess.Popen")
    @patch("agent_bridge._stream_output")
    def test_send_writes_newline(self, mock_stream, mock_popen, mock_which):
        from agent_bridge import AiderBridge

        mock_proc            = MagicMock()
        mock_proc.poll.return_value = None
        mock_proc.stdout     = MagicMock()
        mock_popen.return_value = mock_proc

        bridge = AiderBridge(model="gpt-4o")
        bridge.start()
        bridge.send("refactor main.py")

        written = mock_proc.stdin.write.call_args[0][0]
        self.assertEqual(written, b"refactor main.py\n")

    @patch("agent_bridge.shutil.which", return_value=None)
    def test_missing_aider_raises(self, _):
        from agent_bridge import AiderBridge
        bridge = AiderBridge()
        with self.assertRaises(FileNotFoundError):
            bridge.start()


# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    unittest.main(verbosity=2)
