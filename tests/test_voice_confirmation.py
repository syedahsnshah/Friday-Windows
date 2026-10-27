"""Ensure only the genuine input-transcription branch can approve by voice."""
import asyncio
import threading
import unittest
from types import SimpleNamespace

from core import confirm
from main import FridayLive


class VoiceInputTests(unittest.TestCase):
    def test_generated_output_cannot_approve_but_finished_input_can(self):
        completed = threading.Event()
        confirm.bind(lambda title, detail: None, lambda: None)
        confirm.request("input-test", "Specific action", "Details", lambda: completed.set())
        phrase = confirm.voice_instruction().split("Say ", 1)[1].split(" to approve", 1)[0]

        class Session:
            def __init__(self, input_text=None, output_text=None):
                self.input_text, self.output_text = input_text, output_text
            async def receive(self):
                sc = SimpleNamespace(
                    input_transcription=SimpleNamespace(text=self.input_text, finished=True) if self.input_text else None,
                    output_transcription=SimpleNamespace(text=self.output_text) if self.output_text else None,
                    turn_complete=False)
                yield SimpleNamespace(data=None, server_content=sc, tool_call=None)
                raise asyncio.CancelledError()

        def run(session):
            assistant = SimpleNamespace(session=session, _visemes=SimpleNamespace(feed_text=lambda text: None))
            with self.assertRaises(asyncio.CancelledError):
                asyncio.run(FridayLive._receive_audio(assistant))

        run(Session(output_text=phrase))
        self.assertFalse(completed.is_set())
        run(Session(input_text=phrase))
        self.assertTrue(completed.wait(2))
        confirm.bind(None, None)


if __name__ == "__main__":
    unittest.main()
