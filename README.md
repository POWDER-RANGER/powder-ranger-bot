<!-- ══════════════════════════════════════════ POWDER-RANGER BOT HEADER -->
<div align="center">

[![Header](https://capsule-render.vercel.app/api?type=waving&color=0:0D1117,35:001A00,70:00E676,100:76FF03&height=300&section=header&text=POWDER-RANGER+BOT&fontSize=70&fontColor=76FF03&animation=fadeIn&fontAlignY=40&desc=Autonomous+GTA+V+%E2%80%94+Vision+%C3%97+LLM+%C3%97+DirectInput&descColor=B2FF59&descSize=17&descAlignY=64)](https://github.com/POWDER-RANGER/powder-ranger-bot)

<br>

[![Typing SVG](https://readme-typing-svg.demolab.com?font=Press+Start+2P&weight=700&size=16&duration=2600&pause=700&color=76FF03&center=true&vCenter=true&width=900&lines=YOLOv8+Vision+%C3%97+Ollama+LLM+Brain+%C3%97+DirectInput;CPU-only+Inference+%E2%80%94+Single-Player+Only;Autonomous+GTA+V+%E2%80%94+Autonomous+MGS5;Fast+Reflexes+%E2%80%94+Strategic+Planning+%E2%80%94+Real-time+Overlay)](https://github.com/POWDER-RANGER/powder-ranger-bot)

<br>

![](https://img.shields.io/badge/STATUS-OPERATIONAL-00E676?style=for-the-badge&labelColor=0D1117)
![](https://img.shields.io/badge/GAME-GTA_V+MGS5-76FF03?style=for-the-badge&labelColor=0D1117)
![](https://img.shields.io/badge/INFERENCE-CPU_Only-00E676?style=for-the-badge&labelColor=0D1117)
![](https://img.shields.io/badge/LICENSE-MIT-76FF03?style=for-the-badge&labelColor=0D1117)

</div>

---

## 🎮 Overview

```
Screen → YOLOv8n ONNX → Game State → Fast Reflex / Ollama Brain → pydirectinput
```

CPU-only inference on Windows. GPU training via Google Colab (free T4).  
Local LLM brain via Ollama (`dolphin-llama3:8b` — uncensored for game-combat instructions).

> ⚠️ **Single-player only.** Do NOT use in online modes.

---

## 💻 Hardware Requirements

| Component | Minimum | Recommended |
|-----------|---------|-------------|
| CPU | i5-8th gen | i7-10th gen+ |
| RAM | 16 GB | 32 GB |
| GPU (training only) | Colab T4 (free) | RTX 3060+ |
| Storage | 10 GB free | 50 GB (datasets) |
| OS | Windows 10 | Windows 11 |

---

## 🚀 Quick Start

```bash
# 1. Clone
git clone https://github.com/POWDER-RANGER/powder-ranger-bot
cd powder-ranger-bot

# 2. Environment
python -m venv venv
venv\\Scripts\\activate
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

## 🎯 Architecture

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

---

## ⌨️ Hotkeys

| Key | Action |
|-----|--------|
| **F9** | Toggle pause / resume |
| **F10** | Stop bot and exit |
| **F8** | Toggle debug overlay |
| **Q** (overlay window) | Stop bot |

---

## 🧠 Why dolphin-llama3:8b?

Censored models refuse instructions like "shoot the enemy" or "take out the guard" and will stall the bot mid-combat. `dolphin-llama3:8b` is uncensored and purpose-fit.

---

## 🏋️ Training Pipeline

```
1. Gameplay frames  — Roboflow dataset OR yt-dlp + ffmpeg
2. Auto-label       — autodistill + GroundedSAM (zero manual annotation)
3. Train            — yolov8n.pt on Colab T4 (~30–60 min, 80 epochs)
4. Export           — best.onnx (opset=12, simplify=True)
5. Deploy           — drop into models/
```

See `training/colab_train.md` for the full Colab notebook.

---

## 🔮 Phase 2 Roadmap

- [ ] `state/schema.py` — typed `Entity` + `WorldState` dataclasses
- [ ] `planner/behavior_tree.py` — composable BT node system for GTA
- [ ] `planner/goap.py` — GOAP action model + BFS planner for MGS5
- [ ] `perception/gta_perception.py` / `mgs5_perception.py` — structured world builders
- [ ] `agent.py` — threaded pipeline (capture / infer / plan-act workers)
- [ ] `control/mapping.py` — explicit action registry
- [ ] HUD pixel sampling for health and wanted level

---

## 📈 GitHub Stats

<div align="center">

![Bot Stats](https://github-readme-stats.vercel.app/api?username=POWDER-RANGER&repo=powder-ranger-bot&show_icons=true&theme=merko&hide_border=true)

</div>

---

## 🔗 POWDER-RANGER Ecosystem

### 🌐 Live .io Pages
| Project | Link | Description |
|---------|------|-------------|
| **Main Portfolio** | [powder-ranger.github.io](https://powder-ranger.github.io) | Master portfolio with all 46 repos |
| **POWDER-RANGER Bot** | [powder-ranger.github.io/powder-ranger-bot](https://powder-ranger.github.io/powder-ranger-bot) | Bot demo and documentation |
| **CIVWATCH** | [powder-ranger.github.io/CIVWATCH](https://powder-ranger.github.io/CIVWATCH) | Civic transparency platform |
| **OBLISK** | [powder-ranger.github.io/OBLISK](https://powder-ranger.github.io/OBLISK) | Multi-agent AI orchestration |
| **AI Nexus** | [powder-ranger.github.io/ai-nexus](https://powder-ranger.github.io/ai-nexus) | Browser-based AI platform |
| **Dollar Gravity** | [powder-ranger.github.io/dollar-gravity-framework](https://powder-ranger.github.io/dollar-gravity-framework) | USD gravity visualization |

### 🔧 Core Repositories
| Repository | Language | Purpose |
|-----------|----------|---------|
| **[POWDER-RANGER Bot](https://github.com/POWDER-RANGER/powder-ranger-bot)** | Python | Autonomous GTA V + MGS5 agent (this repo) |
| **[CIVWATCH](https://github.com/POWDER-RANGER/CIVWATCH)** | TypeScript | Civic transparency platform |
| **[OBLISK](https://github.com/POWDER-RANGER/OBLISK)** | Python | Multi-agent AI with encrypted vaults |
| **[RED-AGENT-GOV](https://github.com/POWDER-RANGER/RED-AGENT-GOV)** | Python | Governance-enforced agent engine |
| **[CharlesAI](https://github.com/POWDER-RANGER/CharlesAI)** | PowerShell | COMET Agent with memory & orchestration |
| **[OBELISK-Enterprise](https://github.com/POWDER-RANGER/OBELISK-Enterprise)** | Python | $2.5M AI Governance Platform |
| **[NSO Kryptonite](https://github.com/POWDER-RANGER/nso-kryptonite-platform)** | TypeScript | Adversarial defense command center |
| **[AI Nexus](https://github.com/POWDER-RANGER/ai-nexus)** | JavaScript | Browser-based complete AI platform |
| **[Guiding Light AI](https://github.com/POWDER-RANGER/guiding-light-ai)** | Rust | Values-to-policies CLI tool |
| **[Dollar Gravity](https://github.com/POWDER-RANGER/dollar-gravity-framework)** | JavaScript | USD-centric finance-security dashboard |
| **[Dojin D](https://github.com/POWDER-RANGER/dojin-d)** | TypeScript | ECS combat simulation engine |
| **[Contextual Memory UI](https://github.com/POWDER-RANGER/contextual-memory-ui)** | JavaScript | AI memory infrastructure platform |
| **[OBELISK-Desktop-AI](https://github.com/POWDER-RANGER/OBELISK-Desktop-AI)** | PowerShell | Desktop AI orchestrator |
| **[CIVWATCH Cell Titan](https://github.com/POWDER-RANGER/civwatch-cell-titan)** | Shell | RF observability platform |
| **[CIVWATCH v3](https://github.com/POWDER-RANGER/civwatch-v3)** | HTML | Unified RF observability |

---

## 🤝 Connect

[![LinkedIn](https://img.shields.io/badge/LinkedIn-Curtis_Farrar-0077B5?style=flat&logo=linkedin)](https://www.linkedin.com/in/curtis-farrar-g6b)
[![GitHub](https://img.shields.io/badge/GitHub-POWDER--RANGER-181717?style=flat&logo=github)](https://github.com/POWDER-RANGER)
[![Portfolio](https://img.shields.io/badge/Portfolio-powder--ranger.github.io-76FF03?style=flat&logo=githubpages)](https://powder-ranger.github.io)
[![ORCID](https://img.shields.io/badge/ORCID-0009--0008--9273--2458-A6CE39?style=flat&logo=orcid)](https://orcid.org/0009-0008-9273-2458)

---

**Curtis Charles Farrar** | ORCID: 0009-0008-9273-2458

<div align="center">

[![Footer](https://capsule-render.vercel.app/api?type=waving&color=0:76FF03,35:00E676,70:001A00,100:0D1117&height=150&section=footer)](https://github.com/POWDER-RANGER/powder-ranger-bot)

</div>
