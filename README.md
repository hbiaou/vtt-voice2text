# VTT-voice2text

A production-ready, local desktop voice dictation application for Windows. Press a hotkey, speak, and have your words automatically typed into any active window.

## Features

### Completed Features

- [x] **Global Hotkey Control** - Toggle recording with F8, panic stop with F9
- [x] **Smart Voice Detection** - Uses silero-vad to detect speech automatically
- [x] **Local Processing** - All transcription on your machine using faster-whisper
- [x] **Universal Text Injection** - Types into any active window (Notepad, Chrome, VS Code, etc.)
- [x] **Visual Feedback** - Floating overlay with animated states and status text
- [x] **System Tray Integration** - Runs in background with tray icon and menu
- [x] **GPU Acceleration** - Supports NVIDIA CUDA for faster transcription
- [x] **Multilingual Support** - 99 languages with multilingual models
- [x] **Command-line Model Selection** - Switch models with `--model` flag
- [x] **Easy Setup** - One-click install and run batch scripts
- [x] **Draggable Overlay** - Reposition the status indicator anywhere
- [x] **Graceful Shutdown** - Ctrl+C and proper cleanup on exit
- [x] **Settings GUI** - In-app settings panel to change hotkeys, model, output mode
- [x] **Custom Vocabulary** - Add custom words/names for better recognition
- [x] **Clipboard Mode** - Option to copy to clipboard instead of typing

### Planned Features

- [ ] **Audio Device Selection** - Choose specific microphone from GUI
- [ ] **Punctuation Commands** - Voice commands for "period", "comma", "new line"
- [ ] **History Log** - View and copy previous transcriptions
- [ ] **Auto-start on Boot** - Option to launch with Windows
- [ ] **Noise Suppression** - Built-in background noise filtering
- [ ] **Multiple Language Profiles** - Quick switch between language settings

## Quick Start

### Option A: Easy Setup (Recommended)

1. Double-click **`install.bat`** (one-time setup)
2. Double-click **`run.bat`** to start the app

### Option B: Manual Setup

```bash
# One-time setup
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt

# Run the app (each time)
venv\Scripts\activate
python main.py

# Or with a specific model
python main.py --model medium
```

### Start Dictating

1. Press **F8** to start listening (green indicator)
2. Speak into your microphone
3. Pause for ~1 second when done
4. Text is automatically typed into your active window
5. Press **F8** again to stop listening

## Hotkeys

| Key | Action |
|-----|--------|
| **F8** | Toggle listening on/off |
| **F9** | Panic stop - immediately abort |

## Visual Indicators

The floating overlay in the corner shows the current state:

- 🔴 **Red**: Standby (not listening)
- 🟢 **Green (pulsing)**: Listening for speech
- 🟡 **Yellow**: Transcribing audio

You can drag the overlay to reposition it.

## GPU Acceleration (Optional)

For faster transcription with an NVIDIA GPU:

```bash
# Uninstall CPU-only PyTorch
pip uninstall torch

# Install CUDA-enabled PyTorch (CUDA 11.8)
pip install torch --index-url https://download.pytorch.org/whl/cu118

# Or for CUDA 12.1
pip install torch --index-url https://download.pytorch.org/whl/cu121
```

Verify CUDA is working:

```bash
python -c "import torch; print('CUDA:', torch.cuda.is_available())"
```

## Changing the Whisper Model

The default model is `small` (multilingual). You can change it for better accuracy or speed.

### Option 1: Command Line (Recommended)

```bash
python main.py --model medium
```

### Option 2: Edit config.py

Change the default in the `parse_model_from_args()` function:

```python
default_model = "medium"  # Change this line
```

### Available Whisper Models

| Model | Size | Speed | Languages | Best Use Case |
|-------|------|-------|-----------|---------------|
| `tiny.en` | 39MB | ~1s | English | Quick drafts, low-power devices |
| `tiny` | 39MB | ~1s | 99 languages | Fast multilingual, low accuracy |
| `base.en` | 74MB | ~2s | English | Everyday English dictation |
| `base` | 74MB | ~2s | 99 languages | Basic multilingual support |
| `small.en` | 244MB | ~4s | English | Accurate English transcription |
| **`small`** | 244MB | ~4s | 99 languages | **Default** - Good for names, accents |
| `medium.en` | 769MB | ~8s | English | Professional English transcription |
| `medium` | 769MB | ~8s | 99 languages | Best balance of speed/accuracy |
| `large-v2` | 1.5GB | ~15s | 99 languages | High accuracy, older version |
| `large-v3` | 1.5GB | ~15s | 99 languages | Highest accuracy available |

> **Speed**: Approximate time to transcribe 10 seconds of audio on CPU. GPU is 3-5x faster.

**Which model should I use?**

| Scenario | Recommended Model |
|----------|-------------------|
| Fast dictation, English only | `base.en` or `small.en` |
| Names, accents, mixed languages | `small` or `medium` |
| Non-English languages | `small` or `medium` |
| Maximum accuracy (slow) | `large-v3` |
| Low-power device / fastest | `tiny.en` or `tiny` |

## Settings GUI

Right-click the system tray icon and select **Settings** to open the settings panel.

### General Tab
- **Hotkeys**: Change the toggle (F8) and panic (F9) keys
- **Output Mode**: Choose between typing text or copying to clipboard

### Model Tab
- Select from 10 Whisper models (tiny to large-v3)
- View current device (CPU/GPU) and compute type

### Vocabulary Tab
- Enable/disable custom vocabulary corrections
- Add word mappings for commonly misrecognized words
- Example: Map "Noref" → "Honoré"

### Advanced Tab
- **Silence Threshold**: Adjust pause duration before transcription
- **VAD Sensitivity**: Tune voice detection sensitivity
- **Keystroke Delay**: Adjust typing speed (if characters are dropped)

## Custom Vocabulary

The app can automatically correct misrecognized words. This is useful for:
- Names (Honoré, François, etc.)
- Technical terms
- Brand names

**To add corrections:**
1. Open Settings → Vocabulary tab
2. Click "Add" to create a new row
3. Enter the misheard word and the correct spelling
4. Click "Save"

Vocabulary is saved to `~/.vtt-voice2text-vocab.json`.

## Clipboard Mode

Instead of typing text directly, you can copy it to the clipboard:

1. Open Settings → General tab
2. Select "Copy to clipboard"
3. Click "Save"

Now transcribed text will be copied to clipboard. Paste with **Ctrl+V**.

## Other Configuration

Settings are saved to `~/.vtt-voice2text-settings.json` and persist between sessions.

You can also edit `config.py` for advanced settings:

```python
@dataclass
class AppConfig:
    hotkey_toggle: str = "f8"           # Recording toggle key
    hotkey_panic: str = "f9"            # Emergency stop key
    silence_threshold_sec: float = 1.0  # Silence before cutting
    vad_threshold: float = 0.5          # Voice detection sensitivity (0.0-1.0)
    output_mode: str = "type"           # "type" or "clipboard"
    use_custom_vocab: bool = True       # Apply vocabulary corrections
```

## Troubleshooting

### Microphone Not Working

1. Check Windows privacy settings (Settings > Privacy > Microphone)
2. Ensure your mic is set as default recording device
3. Run `python audio_engine.py` to test audio capture

### Hotkeys Not Working

- Run the application as Administrator
- Check for conflicts with other hotkey software

### Slow Transcription

- Enable GPU acceleration (see above)
- Use a smaller model: `python main.py --model tiny`
- Reduce `silence_threshold_sec` in config

### Names or Accents Not Recognized Correctly

- Use a multilingual model: `python main.py --model medium`
- Multilingual models handle names like "Honoré", "François" better than `.en` models

### Text Not Typing

- Ensure the target window has focus
- Some applications may block simulated input
- Press F9 to abort if injection loops

## Architecture

```
main.py           # GUI, system tray, hotkeys, state machine
audio_engine.py   # Microphone capture, VAD, audio buffering
transcriber.py    # Whisper model loading and inference
injector.py       # Keyboard simulation for text injection
config.py         # Application settings
```

## Requirements

- Windows 10/11
- Python 3.9+
- Microphone
- (Optional) NVIDIA GPU with CUDA

## License

MIT License - Use freely for personal and commercial projects.

