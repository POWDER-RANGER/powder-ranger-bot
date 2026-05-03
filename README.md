# POWDER-RANGER BOT ⚡
### Autonomous GTA V + MGS5 Agent — Vision × LLM × DirectInput

```
Screen → YOLOv8n ONNX → Game State → Fast Reflex / Ollama Brain → pydirectinput
```

CPU-only inference on Windows. GPU training via Google Colab (free T4).  
Local LLM brain via Ollama (`dolphin-llama3:8b` — used specifically because it does not refuse game-combat instructions).

---

## Hardware Requirements

| Component | Minimum | Recommended |
|-----------|---------|-------------|
| CPU | i5-8th gen | i7-10th gen+ |
| RAM | 16 GB | 32 GB |
| GPU (training only) | Colab T4 (free) | RTX 3060+ |
| Storage | 10 GB free | 50 GB (datasets) |
| OS | Windows 10 | Windows 11 |

---

## Quick Start

```bash
# 1. Clone
git clone https://github.com/POWDER-RANGER/powder-ranger-bot
cd powder-ranger-bot

# 2. Environment
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt

# 3. Ollama
winget install Ollama.Ollama
ollama pull dolphin-llama3:8b
# (in a separate terminal) ollama serve

# 4. Dry-run (no model needed — verifies loop)
python main.py --game gtav --dry-run

# 5. After training, run live
python main.py --game gtav
python main.py --game mgs5
```

---

## Hotkeys

| Key | Action |
|-----|--------|
| **F9** | Toggle pause / resume |
| **F10** | Stop bot and exit |
| **F8** | Toggle debug overlay |
| **Q** (overlay window) | Stop bot |

---

## Architecture

```
main.py
 ├── capture/capture.py        mss screen grab → BGR numpy frame
 ├── vision/vision.py          YOLOv8n ONNX → List[Detection] (with real NMS)
 ├── state/game_state.py       Threat flags, alert state, health
 ├── brain/brain.py            Ollama REST → action JSON
 │   └── games/
 │       ├── gtav.py           Rule-based fast reflex (GTA V)
 │       └── mgs5.py           Rule-based fast reflex (MGS5)
 └── control/control.py        pydirectinput keyboard executor + KEY_MAP
```

### Decision Flow (per tick)
```
1. Capture frame           (mss)
2. YOLOv8n ONNX inference  (~60–100ms CPU)
3. Update GameState
4. fast_reflex()           (<1ms — alert/health/cone rules)
5. Brain.decide()          (500–2000ms Ollama — only if reflex returns None)
6. Controller.execute()    (pydirectinput)
7. Overlay display         (optional)
```

### Why dolphin-llama3:8b?
Censored models refuse instructions like "shoot the enemy" or "take out the guard"  
and will stall the bot mid-combat. `dolphin-llama3:8b` is uncensored and purpose-fit.

---

## Training Pipeline

See `training/colab_train.md` for the full Colab notebook.

```
1. Gameplay frames  — Roboflow dataset OR yt-dlp + ffmpeg
2. Auto-label       — autodistill + GroundedSAM (zero manual annotation)
3. Train            — yolov8n.pt on Colab T4 (~30–60 min, 80 epochs)
4. Export           — best.onnx (opset=12, simplify=True)
5. Deploy           — drop into models/
```

---

## Extending to a New Game

1. `config/{game}.yaml` — class_map, capture region, system_prompt
2. `brain/games/{game}.py` — `fast_reflex()` + `enrich_prompt_context()`
3. Train ONNX model with game-specific ontology
4. `python main.py --game {game}`

---

## Phase 2 Roadmap

- [ ] `state/schema.py` — typed `Entity` + `WorldState` dataclasses
- [ ] `planner/behavior_tree.py` — composable BT node system for GTA
- [ ] `planner/goap.py` — GOAP action model + BFS planner for MGS5
- [ ] `perception/gta_perception.py` / `mgs5_perception.py` — structured world builders
- [ ] `agent.py` — threaded pipeline (capture / infer / plan-act workers)
- [ ] `control/mapping.py` — explicit action registry
- [ ] HUD pixel sampling for health and wanted level

---

## Known Limitations

- Screen-only — no direct game memory access
- OCR not implemented — health/wanted level are heuristic
- Ollama latency 500–2000ms — effective at 6–10 FPS
- **Single-player only** — do NOT use in online modes
- Bot runs without `.onnx` (empty detections) — train before going live

---

**Curtis Charles Farrar** | ORCID: 0009-0008-9273-2458  
https://github.com/POWDER-RANGER | https://powder-ranger.github.io
