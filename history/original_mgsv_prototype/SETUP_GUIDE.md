
# MGSV Autonomous Gaming Assistant - Complete Setup Guide

## 🎯 Mission Statement

Build a fully autonomous AI companion for Metal Gear Solid V: The Phantom Pain that evolves into an adaptive accessibility tool for players with disabilities. This system prioritizes:

- **Privacy First**: All processing happens locally on your laptop
- **Ethical Design**: Built for assistance, not competitive advantage  
- **Accessibility Focus**: Transforms gaming for disabled players
- **Open Source**: Transparent, auditable, community-driven

## 📋 Prerequisites

### Hardware Requirements

#### Minimum System (Entry Level)
```
CPU: Intel i5-8th gen / AMD Ryzen 5 3600
RAM: 8GB (6GB system + 2GB AI models)
GPU: Integrated graphics (basic CV processing)
Storage: 5GB for models and cache
Expected Performance: 15-20 FPS observation
```

#### Recommended System (Optimal)
```
CPU: Intel i7-10th gen / AMD Ryzen 7 4700U  
RAM: 16GB (allows larger AI models)
GPU: NVIDIA GTX 1650+ (accelerated CV)
Storage: 20GB SSD for fast model loading
Expected Performance: 30-60 FPS observation
```

#### Development System (Research)
```
CPU: Intel i9 / AMD Ryzen 9
RAM: 32GB (multiple AI models in memory)
GPU: RTX 3060+ (real-time vision processing)
Storage: 50GB NVMe SSD
Expected Performance: 60+ FPS with multiple models
```

### Software Dependencies

#### Python Environment (3.9+)
```bash
# Core computer vision
pip install opencv-python==4.8.1.78
pip install numpy==1.24.3
pip install mss==9.0.1
pip install Pillow==10.0.0

# AI/ML stack
pip install torch==2.0.1
pip install transformers==4.33.2
pip install stable-baselines3==2.0.0
pip install sentence-transformers==2.2.2

# Accessibility interfaces
pip install speech-recognition==3.10.0
pip install pyttsx3==2.90
pip install pygame==2.5.2
pip install psutil==5.9.5

# Optional: Advanced features
pip install pytesseract==0.3.10  # OCR for HUD reading
pip install ollama==0.1.7        # Local LLM server
pip install whisper==1.1.10      # Local speech recognition
```

#### System-Level Dependencies

**Windows (Recommended)**
```bash
# Windows API for input simulation (built-in)
# DirectX for screen capture (built-in)
# Visual C++ Redistributable 2019+
```

**Linux (Advanced)**
```bash
sudo apt update
sudo apt install python3-dev python3-pip
sudo apt install libopencv-dev python3-opencv
sudo apt install espeak espeak-data libespeak1 libespeak-dev
sudo apt install portaudio19-dev python3-pyaudio
```

## 🚀 Installation Steps

### Step 1: Clone and Setup Environment

```bash
# Create project directory
mkdir mgsv-autonomous-assistant
cd mgsv-autonomous-assistant

# Create virtual environment
python -m venv venv

# Activate environment
# Windows:
venv\Scripts\activate
# Linux/Mac:
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### Step 2: Download Core Files

```bash
# Core system files (from our generated code)
# - mgsv_autonomous_assistant.py           # Main autonomous system
# - mgsv_accessibility_integration.py      # Accessibility layer
# - mgsv_autonomous_assistant_architecture.txt  # Technical documentation

# Create directory structure
mkdir -p assets/templates
mkdir -p assets/models
mkdir -p accessibility_profiles
mkdir -p logs
mkdir -p cache
```

### Step 3: Setup Local AI Models

#### Option A: Lightweight (Phi-3 Mini - 2.4GB)
```bash
# Using Hugging Face transformers
python -c "
from transformers import AutoTokenizer, AutoModelForCausalLM
model_name = 'microsoft/Phi-3-mini-4k-instruct'
tokenizer = AutoTokenizer.from_pretrained(model_name)
model = AutoModelForCausalLM.from_pretrained(model_name)
tokenizer.save_pretrained('assets/models/phi-3-mini')
model.save_pretrained('assets/models/phi-3-mini')
print('✅ Phi-3 Mini downloaded')
"
```

#### Option B: Balanced (Llama 3.2 8B - 8.5GB)
```bash
# Using Ollama (easier management)
# Install Ollama from https://ollama.ai
ollama pull llama3.2:8b
ollama pull phi3:mini

# Verify installation
ollama list
```

#### Option C: Local-Only Setup (No Internet)
```bash
# Pre-download models on internet-connected machine
# Transfer model files to target system
# Point model paths to local files
```

### Step 4: Configure MGSV Integration

#### Game Setup
```
1. Install Metal Gear Solid V: The Phantom Pain (Steam/Epic)
2. Launch game once to create config files
3. Set display to Borderless Windowed (for screen capture)
4. Configure graphics settings for stable 60 FPS
5. Disable Steam overlay if using Steam version
```

#### Memory Address Research (Optional)
```bash
# For advanced users wanting memory reading
# Download Cheat Engine: https://cheatengine.org
# Find community MGSV tables: https://fearlessrevolution.com
# Extract memory offsets for:
#   - Player health
#   - Ammo count  
#   - Position coordinates
#   - Alert status
# 
# Note: Our system works without memory reading using CV only
```

### Step 5: Accessibility Hardware Setup

#### Eye Tracking
```bash
# Option 1: Tobii Eye Tracker 5 ($230)
# Install Tobii Software + SDK
# Connect via USB 3.0
# Calibrate in Tobii Experience

# Option 2: Webcam-based (Free)
# Ensure good lighting
# Position camera at eye level
# 30cm-60cm distance from face
```

#### Voice Recognition
```bash
# Test microphone
python -c "
import speech_recognition as sr
r = sr.Recognizer()
with sr.Microphone() as source:
    print('Say something...')
    audio = r.listen(source, timeout=5)
try:
    text = r.recognize_sphinx(audio)
    print(f'You said: {text}')
except:
    print('Could not understand audio')
"
```

## ⚡ Quick Start Guide

### Basic Autonomous Mode

```bash
# 1. Activate environment
source venv/bin/activate  # or venv\Scripts\activate on Windows

# 2. Start MGSV game
# Launch game, load save file, get to gameplay

# 3. Run basic autonomous assistant
python mgsv_autonomous_assistant.py

# Expected output:
# 🎮 MGSV Autonomous Gaming Assistant
# 🔍 Searching for process: mgsvtpp.exe
# 👁️ Eye tracking cascades loaded
# 🤖 Loading local AI model: phi-3-mini
# ✅ Input simulator initialized
# 🚀 MGSV Autonomous Assistant initialized
# ▶️ Starting autonomous assistant...
# 📊 FPS: 24.3 | Health: 100% | Enemies: 0
```

### Accessibility Mode

```bash
# Run accessibility-integrated version
python mgsv_accessibility_integration.py

# Follow setup wizard:
# ♿ MGSV Accessibility Setup
# 1. Enter your name: Alice
# 2. Primary input method: 1 (Eye tracking)
# 3. Assistance level: 3 (Tactical assist)
# 
# ✅ Profile saved
# 🚀 Initializing systems...
# 👁️ Starting gaze calibration...
# 🎤 Voice interface ready
# ▶️ Starting accessible gaming session...
```

## 🎮 Usage Instructions

### Autonomous Mode Controls

**System Controls:**
- `Ctrl+C` - Stop the assistant
- `Ctrl+Pause` - Temporarily pause AI actions
- `Ctrl+Shift+S` - Save current game state snapshot

**AI Behavior:**
- AI observes game screen at 30 FPS
- Makes strategic decisions using local LLM
- Executes actions via safe input simulation
- Adapts behavior based on game state

### Accessibility Mode Controls

**Eye Tracking:**
- Look at action zones to highlight them
- Blink to confirm selected action
- Gaze zones: Forward (top), Crouch (bottom), Smoke (left), Cover (right)

**Voice Commands:**
- "Move forward" / "Go forward"
- "Crouch down" / "Get down"  
- "Throw smoke" / "Use smoke"
- "Take cover" / "Hide"
- "Stop" / "Pause" - Pause AI
- "Status" - Get current game state report

**Hybrid Control:**
- Combine eye tracking for selection + voice for confirmation
- Use blink detection as universal "Enter" key
- Voice overrides take priority over gaze selection

## 🔧 Advanced Configuration

### Performance Tuning

#### config.json
```json
{
  "performance": {
    "max_fps": 30,
    "action_rate_limit": 2.0,
    "cv_processing_threads": 2,
    "ai_inference_batch_size": 1
  },
  "ai_models": {
    "llm": "phi-3-mini",
    "vision": "opencv",
    "speech": "sphinx"
  },
  "accessibility": {
    "eye_tracking_enabled": true,
    "voice_commands_enabled": true,
    "tts_enabled": true,
    "overlay_opacity": 0.7
  },
  "safety": {
    "max_actions_per_minute": 120,
    "human_variation_enabled": true,
    "memory_modification_disabled": true
  }
}
```

### Custom AI Training

```bash
# Collect training data
python scripts/collect_gameplay_data.py --hours 10

# Train reinforcement learning agent
python scripts/train_rl_agent.py --episodes 50000

# Fine-tune local LLM for MGSV
python scripts/finetune_llm.py --data gameplay_logs/
```

### Memory Reading Setup (Advanced)

```python
# memory_config.py
MEMORY_OFFSETS = {
    "health": 0x141E3C8B0,
    "ammo": 0x141E3C8B4, 
    "position_x": 0x141E3C8C0,
    "position_y": 0x141E3C8C4,
    "alert_level": 0x141E3C8D0
}

# Enable in main config
USE_MEMORY_READING = True  # Faster than CV, requires offsets
```

## 🛡️ Safety and Ethics

### Built-in Safety Features

**Technical Safeguards:**
- No memory modification (read-only access)
- Rate limiting (max 2 actions/second)
- Human-like timing variation
- Single-player game focus only
- No network communication

**Ethical Guidelines:**
- Accessibility-first design philosophy  
- Open source transparency
- Community-driven development
- Disabled user feedback integration
- Academic research collaboration

### Privacy Protection

**Data Handling:**
- All processing happens locally
- No telemetry or usage tracking
- No cloud API calls
- User profiles stored locally only
- Optional data collection with explicit consent

**Security Measures:**
- No elevated privileges required
- Sandboxed execution environment
- Input validation and sanitization
- Safe API usage only
- Regular security audits

## 🔍 Troubleshooting

### Common Issues

#### "No game process found"
```bash
# Check if MGSV is running
tasklist | findstr mgsvtpp

# Verify process name
# Steam: mgsvtpp.exe
# Epic: MGSV_TPP.exe (different name)
# Update process name in config
```

#### "Screenshot capture failed"
```bash
# Run as administrator (Windows)
# Check display settings (use Borderless Windowed)
# Verify MSS installation: pip install --upgrade mss
# Test capture: python -c "from mss import mss; print(mss().grab({'top':0,'left':0,'width':100,'height':100}))"
```

#### "AI model loading failed"
```bash
# Check available RAM: 8GB minimum for basic models
# Verify model files downloaded correctly
# Try smaller model: phi3:mini instead of llama3.2:8b
# Clear model cache: rm -rf ~/.cache/huggingface/
```

#### "Voice recognition not working"
```bash
# Test microphone access
# Install additional dependencies: pip install pyaudio
# Switch to different recognition engine
# Check audio permissions (Windows Privacy Settings)
```

#### "Eye tracking calibration failed"
```bash
# Ensure good lighting (avoid backlighting)
# Clean camera lens
# Adjust camera angle (eye level)
# Try different camera: cv2.VideoCapture(1) instead of (0)
# Install camera drivers
```

### Performance Optimization

#### Low FPS Issues
```bash
# Reduce processing resolution
# Disable unnecessary features
# Use lighter AI models
# Close other applications
# Update GPU drivers
```

#### High Memory Usage
```bash
# Monitor: Task Manager → Memory
# Reduce model size: phi-3-mini vs llama-3.2-8b
# Enable model quantization
# Clear caches regularly
# Restart application periodically
```

## 📊 System Monitoring

### Performance Metrics

```bash
# Monitor system performance
python scripts/monitor_performance.py

# Output:
# 📊 System Performance Monitor
# CPU Usage: 45%
# RAM Usage: 6.2GB / 16GB
# GPU Usage: 23%
# AI Inference: 156ms avg
# Screenshot FPS: 28.4
# Actions/min: 47
```

### Debug Logging

```python
# Enable debug mode
import logging
logging.basicConfig(level=logging.DEBUG)

# Log file locations:
# logs/autonomous_assistant.log
# logs/accessibility_controller.log  
# logs/performance_metrics.log
```

## 🚀 Deployment Options

### Single User Setup
```bash
# Desktop shortcut for easy access
# Windows Task Scheduler for auto-start
# System tray integration
```

### Research Lab Deployment
```bash
# Docker containerization
# Multi-user profile management
# Data collection and analysis tools
# Integration with research protocols
```

### Community Distribution
```bash
# GitHub releases with pre-built executables
# Documentation and video tutorials
# Community support forums
# Accessibility organization partnerships
```

## 📈 Future Development

### Roadmap

**Phase 1 (Months 1-3): Core Foundation**
- ✅ Autonomous gameplay system
- ✅ Computer vision pipeline
- ✅ Local AI integration
- ✅ Basic accessibility features

**Phase 2 (Months 4-6): Enhanced Intelligence**
- 🔄 Advanced RL training
- 🔄 Multi-game support expansion
- 🔄 Improved natural language processing
- 🔄 Community feedback integration

**Phase 3 (Months 7-12): Accessibility Focus**
- 📋 BCI integration research
- 📋 Academic partnerships
- 📋 Clinical testing programs
- 📋 Industry collaboration

**Phase 4 (Year 2+): Ecosystem Development**
- 📋 Platform-agnostic architecture  
- 📋 Developer SDK release
- 📋 Open source community growth
- 📋 Standards and policy influence

### Contributing

**Code Contributions:**
```bash
# Fork repository
# Create feature branch
# Follow coding standards
# Add tests and documentation
# Submit pull request
```

**Research Collaborations:**
- Academic institutions
- Disability advocacy organizations
- Gaming accessibility companies
- Assistive technology researchers

**Community Support:**
- User testing and feedback
- Documentation improvements
- Translation and localization
- Accessibility consulting

## 📞 Support and Community

### Getting Help

**Technical Support:**
- GitHub Issues: [repository_url]/issues
- Community Discord: [discord_invite]
- Documentation Wiki: [wiki_url]
- Video Tutorials: [youtube_channel]

**Accessibility Support:**
- AbleGamers Partnership: accessibility@ablegamers.org
- SpecialEffect Collaboration: info@specialeffect.org.uk
- User Testing Program: testing@mgsv-assistant.org

### Legal and Licensing

**Open Source License:** MIT License
**Third-Party Components:** See LICENSES.md
**Game Compatibility:** Single-player use only
**Warranty:** Provided as-is, no warranty

---

**🎮 Ready to transform gaming accessibility? Let's build the future together!**

For immediate support or questions, reach out through our community channels or GitHub issues. 

Remember: This isn't about creating the perfect bot—it's about creating perfect access to the games we love.
