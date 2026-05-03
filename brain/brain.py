# ============================================================
# brain/brain.py — Ollama-backed Decision Brain
# Converts detections + game state → action JSON via local LLM.
# ============================================================

from __future__ import annotations

import json
import time
from typing import Dict, List, Any

import requests

from utils.logger import setup_logger
from state.game_state import GameState
from vision.vision import Detection

log = setup_logger(__name__)

WAIT_ACTION = {"action": "wait", "duration": 0.5}


class Brain:
    """
    Sends structured game context to Ollama (dolphin-llama3:8b)
    and parses the returned action JSON.

    dolphin-llama3:8b is used specifically because it does not refuse
    game-combat instructions (shoot, attack, eliminate). Censored models
    will stall the bot mid-combat.
    """

    def __init__(
        self,
        system_prompt: str,
        ollama_host:   str   = "http://localhost:11434",
        model:         str   = "dolphin-llama3:8b",
        timeout:       float = 8.0,
        temperature:   float = 0.2,
        max_tokens:    int   = 256,
    ):
        self.system_prompt = system_prompt
        self.ollama_host   = ollama_host.rstrip("/")
        self.model         = model
        self.timeout       = timeout
        self.temperature   = temperature
        self.max_tokens    = max_tokens
        self._endpoint     = f"{self.ollama_host}/api/generate"

        self._last_action:      Dict = WAIT_ACTION.copy()
        self._last_latency_ms:  float = 0.0
        self._error_count:      int   = 0

        self._verify_ollama()

    def _verify_ollama(self) -> None:
        try:
            r      = requests.get(f"{self.ollama_host}/api/tags", timeout=3)
            models = [m["name"] for m in r.json().get("models", [])]
            if self.model not in models and not any(self.model.split(":")[0] in m for m in models):
                log.warning(f"Model '{self.model}' not found. Pull with: ollama pull {self.model}")
            else:
                log.info(f"Brain connected to Ollama | model='{self.model}'")
        except Exception as e:
            log.error(f"Ollama not reachable at '{self.ollama_host}': {e}")

    def _build_user_prompt(self, detections: List[Detection], state: GameState) -> str:
        det_list = [d.to_dict() for d in detections]
        return (
            f"DETECTIONS:\n{json.dumps(det_list, indent=2)}\n\n"
            f"GAME_STATE:\n{json.dumps(state.to_summary_dict(), indent=2)}\n\n"
            "Output your action JSON now:"
        )

    def decide(self, detections: List[Detection], state: GameState) -> Dict[str, Any]:
        user_prompt = self._build_user_prompt(detections, state)
        payload = {
            "model":  self.model,
            "prompt": user_prompt,
            "system": self.system_prompt,
            "stream": False,
            "options": {
                "temperature": self.temperature,
                "num_predict": self.max_tokens,
                "stop": ["\n\n", "```"],
            },
        }
        t0 = time.perf_counter()
        try:
            resp     = requests.post(self._endpoint, json=payload, timeout=self.timeout)
            resp.raise_for_status()
            raw_text = resp.json().get("response", "").strip()
            self._last_latency_ms = (time.perf_counter() - t0) * 1000
            action = self._parse_action(raw_text)
            self._last_action  = action
            self._error_count  = 0
            log.debug(f"Brain decision: {action} | latency={self._last_latency_ms:.0f}ms")
            return action
        except requests.Timeout:
            self._last_latency_ms = self.timeout * 1000
            self._error_count    += 1
            log.warning(f"Ollama timeout after {self.timeout}s — WAIT fallback.")
            return WAIT_ACTION.copy()
        except Exception as e:
            self._error_count += 1
            log.error(f"Brain.decide() error: {e}")
            return WAIT_ACTION.copy()

    def _parse_action(self, raw: str) -> Dict[str, Any]:
        clean = raw.strip().strip("`").strip()
        if clean.startswith("json"):
            clean = clean[4:].strip()
        start, end = clean.find("{"), clean.rfind("}")
        if start != -1 and end != -1:
            clean = clean[start: end + 1]
        try:
            parsed = json.loads(clean)
            if "action" not in parsed:
                raise ValueError("Missing 'action' key")
            return parsed
        except (json.JSONDecodeError, ValueError) as e:
            log.warning(f"Brain JSON parse failed: {e} | raw='{raw[:120]}'")
            return WAIT_ACTION.copy()

    @property
    def last_action(self) -> Dict:
        return self._last_action

    @property
    def last_latency_ms(self) -> float:
        return self._last_latency_ms

    @property
    def error_count(self) -> int:
        return self._error_count
