# VTT-voice2text

A production-ready, local desktop voice dictation application for Windows. Press a hotkey, speak, and have your words automatically typed into any active window.

## Features

- **Global Hotkey Control**: Toggle recording with F8 from any application
- **Smart Voice Detection**: Uses silero-vad to detect speech automatically
- **Local Processing**: All transcription happens on your machine using faster-whisper
- **Universal Injection**: Types text into any active window (Notepad, Chrome, VS Code, etc.)
- **Visual Feedback**: Floating overlay shows recording status without stealing focus
- **GPU Acceleration**: Supports NVIDIA CUDA for faster transcription

## Quick Start

### 1. Install Dependencies

```bash
# Create a virtual environment (recommended)
python -m venv venv
venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### 2. Run the Application

```bash
python main.py
```

### 3. Start Dictating

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

## Configuration

Edit `config.py` to customize settings:

```python
@dataclass
class AppConfig:
    hotkey_toggle: str = "f8"        # Recording toggle key
    hotkey_panic: str = "f9"         # Emergency stop key
    model_size: str = "base.en"      # Whisper model size
    silence_threshold_sec: float = 1.0  # Silence before cutting
    vad_threshold: float = 0.5       # Voice detection sensitivity
```

### Available Whisper Models

| Model | Size | Speed | Accuracy |
|-------|------|-------|----------|
| `tiny.en` | 39MB | Fastest | Basic |
| `base.en` | 74MB | Fast | Good (default) |
| `small.en` | 244MB | Medium | Better |
| `medium.en` | 769MB | Slow | Best |

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
- Use a smaller model (`tiny.en`)
- Reduce `silence_threshold_sec` in config

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

