# ============================================================
# main.py — POWDER-RANGER Bot Entry Point
#
# F9  → Toggle pause / resume
# F10 → Graceful stop and exit
# F8  → Toggle debug overlay window
#
# Usage:
#   python main.py             (uses active_game in bot.yaml)
#   python main.py --game gtav
#   python main.py --game mgs5
#   python main.py --dry-run   (no inputs sent — vision+brain only)
# ============================================================

from __future__ import annotations

import argparse
import sys
import time
from enum import Enum, auto
from pathlib import Path
from typing import Dict, Any

import cv2
import keyboard
import yaml

from utils.logger import setup_logger
from capture.capture import ScreenCapture
from vision.vision import VisionEngine
from brain.brain import Brain
from brain.games import gtav as gtav_reflex, mgs5 as mgs5_reflex
from control.control import Controller
from state.game_state import GameState


class BotStatus(Enum):
    RUNNING = auto()
    PAUSED  = auto()
    STOPPED = auto()


def load_config(game_id: str) -> Dict[str, Any]:
    cfg_dir       = Path("config")
    bot_cfg_path  = cfg_dir / "bot.yaml"
    game_cfg_path = cfg_dir / f"{game_id}.yaml"

    if not bot_cfg_path.exists():
        raise FileNotFoundError("Missing config/bot.yaml")
    if not game_cfg_path.exists():
        raise FileNotFoundError(f"Missing config/{game_id}.yaml")

    with open(bot_cfg_path, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    with open(game_cfg_path, encoding="utf-8") as f:
        game_cfg = yaml.safe_load(f)

    for k, v in game_cfg.items():
        if isinstance(v, dict) and isinstance(cfg.get(k), dict):
            cfg[k] = {**cfg[k], **v}
        else:
            cfg[k] = v

    cfg["active_game"] = game_id
    return cfg


class PowderRangerBot:
    def __init__(self, cfg: Dict[str, Any], dry_run: bool = False):
        self.cfg     = cfg
        self.dry_run = dry_run
        self.status  = BotStatus.PAUSED
        self.game_id = cfg["active_game"]

        log_cfg  = cfg.get("logging", {})
        self.log = setup_logger(
            "main",
            level        = log_cfg.get("level", "INFO"),
            log_file     = log_cfg.get("log_file", "logs/bot.log"),
            max_bytes    = log_cfg.get("max_bytes", 5_242_880),
            backup_count = log_cfg.get("backup_count", 3),
        )
        self.log.info(f"POWDER-RANGER Bot v{cfg['bot']['version']} | game={self.game_id} | dry_run={dry_run}")

        self.state = GameState()

        cap_cfg       = cfg.get("capture", {})
        self.capture  = ScreenCapture(
            region      = cap_cfg.get("region", {"top": 0, "left": 0, "width": 1920, "height": 1080}),
            monitor_idx = cap_cfg.get("monitor", 1),
        )

        vis_cfg      = cfg.get("vision", {})
        self.vision  = VisionEngine(
            model_path  = vis_cfg.get("model_path", "models/placeholder.onnx"),
            class_map   = {int(k): v for k, v in vis_cfg.get("class_map", {}).items()},
            conf_thresh = vis_cfg.get("confidence", 0.40),
            iou_thresh  = vis_cfg.get("iou", 0.45),
            input_size  = vis_cfg.get("input_size", 640),
        )

        ollama_cfg  = cfg.get("ollama", {})
        brain_cfg   = cfg.get("brain", {})
        self.brain  = Brain(
            system_prompt = brain_cfg.get("system_prompt", "Output JSON action."),
            ollama_host   = ollama_cfg.get("host", "http://localhost:11434"),
            model         = ollama_cfg.get("model", "dolphin-llama3:8b"),
            timeout       = ollama_cfg.get("timeout", 8.0),
            temperature   = ollama_cfg.get("temperature", 0.2),
            max_tokens    = ollama_cfg.get("max_tokens", 256),
        )

        ctrl_cfg        = cfg.get("control", {})
        self.controller = Controller(
            bindings          = ctrl_cfg,
            mouse_sensitivity = ctrl_cfg.get("mouse_sensitivity", 0.45),
            max_duration      = ctrl_cfg.get("max_action_duration", 2.5),
            dry_run           = dry_run,
        )

        loop_cfg          = cfg.get("loop", {})
        self._target_fps  = loop_cfg.get("target_fps", 8)
        self._frame_skip  = loop_cfg.get("frame_skip", 1)
        self._tick_sleep  = 1.0 / max(self._target_fps, 1)
        self._frame_idx   = 0

        disp_cfg           = cfg.get("display", {})
        self._show_overlay = disp_cfg.get("show_overlay", True)
        self._overlay_scale= disp_cfg.get("overlay_scale", 0.6)
        self._debug_window = False

        vis_game_cfg         = cfg.get("vision", {})
        self._threat_labels  = vis_game_cfg.get("threat_classes", [])
        self._caution_labels = vis_game_cfg.get("caution_classes", [])

        self._register_hotkeys()
        self.log.info("Hotkeys ready. F9=pause/resume  F10=stop  F8=debug. Press F9 to START.")

    def _register_hotkeys(self) -> None:
        hk = self.cfg.get("hotkeys", {})
        keyboard.add_hotkey(hk.get("pause", "F9"),  self._toggle_pause)
        keyboard.add_hotkey(hk.get("stop",  "F10"), self._stop)
        keyboard.add_hotkey(hk.get("debug", "F8"),  self._toggle_debug)

    def _toggle_pause(self) -> None:
        if self.status == BotStatus.RUNNING:
            self.status = BotStatus.PAUSED
            self.log.info("⏸  PAUSED")
        elif self.status == BotStatus.PAUSED:
            self.status = BotStatus.RUNNING
            self.log.info("▶  RUNNING")

    def _stop(self) -> None:
        self.log.info("🛑 STOPPED")
        self.status = BotStatus.STOPPED

    def _toggle_debug(self) -> None:
        self._debug_window = not self._debug_window
        self.log.info(f"Debug overlay: {'ON' if self._debug_window else 'OFF'}")

    def _fast_reflex(self):
        if self.game_id == "gtav":
            return gtav_reflex.fast_reflex(self.state)
        elif self.game_id == "mgs5":
            return mgs5_reflex.fast_reflex(self.state, self.state.detections)
        return None

    def run(self) -> None:
        tick_times = []
        try:
            while self.status != BotStatus.STOPPED:
                tick_start = time.perf_counter()

                if self.status == BotStatus.PAUSED:
                    time.sleep(0.1)
                    continue

                frame = self.capture.grab()
                if frame is None:
                    time.sleep(0.1)
                    continue

                self._frame_idx += 1
                if self._frame_idx % self._frame_skip != 0:
                    time.sleep(0.01)
                    continue

                detections = self.vision.analyze(frame)

                self.state.update_from_detections(
                    detections    = detections,
                    threat_labels = self._threat_labels,
                    caution_labels= self._caution_labels,
                )

                action = self._fast_reflex()
                if action is None:
                    action = self.brain.decide(detections, self.state)

                self.state.last_action    = action.get("action", "wait")
                self.state.last_action_ts = time.time()

                self.controller.execute(action)

                if self._show_overlay:
                    annotated = self.vision.annotate(frame, detections)
                    h, w      = annotated.shape[:2]
                    disp      = cv2.resize(annotated,
                                           (int(w * self._overlay_scale),
                                            int(h * self._overlay_scale)))
                    status_text = (
                        f"{self.game_id.upper()} | "
                        f"FPS:{self.state.fps:.1f} | "
                        f"Action:{action.get('action','?')} | "
                        f"Brain:{self.brain.last_latency_ms:.0f}ms"
                    )
                    cv2.putText(disp, status_text, (10, 20),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 1)
                    cv2.imshow("POWDER-RANGER BOT", disp)
                    if cv2.waitKey(1) & 0xFF == ord("q"):
                        self._stop()

                elapsed = time.perf_counter() - tick_start
                time.sleep(max(0.0, self._tick_sleep - elapsed))

                tick_times.append(time.perf_counter() - tick_start)
                if len(tick_times) > 20:
                    tick_times.pop(0)
                self.state.fps = 1.0 / (sum(tick_times) / len(tick_times)) if tick_times else 0.0

        except KeyboardInterrupt:
            self.log.info("KeyboardInterrupt — shutting down.")
        finally:
            self._shutdown()

    def _shutdown(self) -> None:
        self.log.info("Shutting down POWDER-RANGER Bot...")
        self.capture.close()
        cv2.destroyAllWindows()
        self.log.info("Shutdown complete. Goodbye, Boss.")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="POWDER-RANGER Bot — GTA V / MGS5 autonomous agent")
    parser.add_argument("--game", choices=["gtav", "mgs5"], default=None)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    try:
        with open("config/bot.yaml") as f:
            bot_cfg_raw = yaml.safe_load(f)
        game_id = args.game or bot_cfg_raw.get("bot", {}).get("active_game", "gtav")
        cfg = load_config(game_id)
    except FileNotFoundError as e:
        print(f"[ERROR] {e}")
        sys.exit(1)

    bot = PowderRangerBot(cfg, dry_run=args.dry_run)
    bot.run()
