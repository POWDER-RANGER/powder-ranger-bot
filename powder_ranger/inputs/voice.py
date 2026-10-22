"""Voice: local speech -> commands -> Governor. Nothing leaves the machine.

VoiceDispatcher  maps parsed commands to Governor messages (testable, no audio)
Speaker          text-to-speech on ONE dedicated thread (pyttsx3 breaks when
                 called from several threads, which the original prototype did)
VoiceListener    microphone -> energy-gated utterances -> faster-whisper -> text

Commands the companion cannot carry out yet (movement, squad orders: they
need the planners) are logged as player intents and answered honestly:
"I can't do that yet."
"""

from __future__ import annotations

import queue
import threading
import time
import uuid
from typing import Callable

from ..intent import Delegation, GamepadFrame
from .commands import Command, parse


class Speaker:
    def __init__(self, enabled: bool = True, rate: int = 180):
        self._q: queue.Queue[str | None] = queue.Queue()
        self.enabled = enabled
        self.spoken: list[str] = []
        self._rate = rate
        self._t = threading.Thread(target=self._run, name="tts", daemon=True)
        self._t.start()

    def _run(self) -> None:
        engine = None
        if self.enabled:
            try:
                import pyttsx3
                engine = pyttsx3.init()
                engine.setProperty("rate", self._rate)
            except Exception:
                engine = None
        while True:
            text = self._q.get()
            if text is None:
                return
            self.spoken.append(text)
            if engine is not None:
                engine.say(text)
                engine.runAndWait()
            else:
                print(f"[say] {text}")

    def say(self, text: str) -> None:
        self._q.put(text)

    def close(self) -> None:
        self._q.put(None)
        self._t.join(timeout=5)


class VoiceDispatcher:
    """send(msg_type, body) delivers to the Governor; player_tap sends PLAYER frames in one packet."""

    def __init__(self, send: Callable[[str, dict], None], player_tap: Callable[[list[GamepadFrame]], None],
                 say: Callable[[str], None], clock: Callable[[], float] = time.monotonic):
        self.send, self.player_tap, self.say, self.clock = send, player_tap, say, clock
        self.active_delegation: str | None = None

    def handle_text(self, text: str) -> Command | None:
        cmd = parse(text)
        self.send("presence", {"how": "voice"})
        if cmd is None:
            return None
        intent_id = uuid.uuid4().hex[:12]
        self.send("command", {"id": intent_id, "verb": cmd.verb, "target": cmd.target, "manner": cmd.manner,
                              "scope": cmd.scope, "text": cmd.text, "via": "voice"})
        v = cmd.verb
        if v == "stop":
            self.send("halt", {"reason": "voice: stop"})
            self.active_delegation = None
            self.say("Stopped.")
        elif v == "resume":
            self.send("resume", {})
            self.say("Resumed. Say 'you play' to hand me control.")
        elif v == "delegate":
            self.active_delegation = f"voice-{intent_id}"
            self.send("grant", Delegation(id=self.active_delegation, scope=cmd.scope, granted_at=self.clock(),
                                          note=f"voice: {cmd.text}").to_dict())
            self.say({"full_autopilot": "I've got it.", "driving": "I'll drive.",
                      "routine": "I'll handle the small stuff."}.get(cmd.scope, "Okay."))
        elif v == "revoke":
            self.send("revoke", {"id": None})
            self.active_delegation = None
            self.say("It's yours.")
        elif v == "press" and cmd.button:
            # one packet: press, then release one frame later (two packets in one tick would
            # replace each other before the press ever reached the pad)
            self.player_tap([GamepadFrame(buttons=frozenset({cmd.button})), GamepadFrame()])
        elif v == "status":
            self.say("I'm playing for you." if self.active_delegation else "You're in control.")
        elif v == "help":
            self.say("Say: you play, my turn, stop, or jump.")
        else:
            self.say("I heard you, but I can't do that yet.")
        return cmd


class VoiceListener:
    """Microphone -> utterances -> text. Requires sounddevice + faster-whisper.

    Energy gate: an utterance starts when RMS rises above start_rms and ends
    after silence_s of quiet. Short and simple; replace with a trained VAD later.
    """

    def __init__(self, on_text: Callable[[str], None], model: str = "base.en", device: str = "auto",
                 start_rms: float = 0.015, silence_s: float = 0.6, max_utt_s: float = 6.0,
                 sample_rate: int = 16000):
        from faster_whisper import WhisperModel
        self.model = WhisperModel(model, device=device, compute_type="int8")
        self.on_text = on_text
        self.sr, self.start_rms, self.silence_s, self.max_utt_s = sample_rate, start_rms, silence_s, max_utt_s
        self._stop = threading.Event()

    def stop(self) -> None:
        self._stop.set()

    def run(self) -> None:
        import numpy as np
        import sounddevice as sd

        block = int(self.sr * 0.03)
        buf: list = []
        speaking, quiet_t, start_t = False, 0.0, 0.0
        with sd.InputStream(samplerate=self.sr, channels=1, dtype="float32", blocksize=block) as stream:
            while not self._stop.is_set():
                chunk, _ = stream.read(block)
                rms = float(np.sqrt(np.mean(chunk ** 2)))
                now = time.monotonic()
                if not speaking and rms > self.start_rms:
                    speaking, start_t, quiet_t, buf = True, now, now, [chunk]
                elif speaking:
                    buf.append(chunk)
                    if rms > self.start_rms:
                        quiet_t = now
                    if now - quiet_t > self.silence_s or now - start_t > self.max_utt_s:
                        speaking = False
                        audio = np.concatenate(buf)[:, 0]
                        segments, _ = self.model.transcribe(audio, language="en", beam_size=1,
                                                            vad_filter=False, without_timestamps=True)
                        text = " ".join(s.text for s in segments).strip()
                        if text:
                            self.on_text(text)
