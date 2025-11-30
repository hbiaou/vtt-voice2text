"""
config.py - Application settings and configuration.

This module contains all configurable settings for the VTT-voice2text app.
Settings are stored in a dataclass for easy access and modification.

To change the model, edit MODEL_SIZE below or use command line:
    python main.py --model small.en

Available models (English-only, faster):
    tiny.en, base.en, small.en, medium.en

Available models (Multilingual, better for names):
    tiny, base, small, medium, large-v2, large-v3
"""

from dataclasses import dataclass, field
from typing import Literal
import sys
import torch


def detect_device() -> Literal["cuda", "cpu"]:
    """
    Auto-detect the best available compute device.
    Returns 'cuda' if NVIDIA GPU with CUDA is available, otherwise 'cpu'.
    """
    if torch.cuda.is_available():
        return "cuda"
    return "cpu"


def get_compute_type(device: str) -> str:
    """
    Get the optimal compute type based on device.
    - GPU (cuda): Use float16 for faster inference.
    - CPU: Use int8 quantization for speed on CPU.
    """
    if device == "cuda":
        return "float16"
    return "int8"


def parse_model_from_args() -> str:
    """
    Parse --model argument from command line.
    Returns the model name or default 'small' for better accuracy.
    
    Usage: python main.py --model medium
    """
    default_model = "small"  # Multilingual, good balance of speed/accuracy.
    
    for i, arg in enumerate(sys.argv):
        if arg == "--model" and i + 1 < len(sys.argv):
            return sys.argv[i + 1]
    
    return default_model


@dataclass
class AppConfig:
    """
    Main configuration class for VTT-voice2text.
    
    Attributes:
        hotkey_toggle: Key to start/stop listening (default: F8).
        hotkey_panic: Emergency stop key (default: F9).
        model_size: Whisper model size (default: small for multilingual).
        silence_threshold_sec: Seconds of silence before cutting audio chunk.
        sample_rate: Audio sample rate in Hz (16000 required by Whisper).
        device: Compute device ('cuda' or 'cpu').
        compute_type: Model precision ('float16' for GPU, 'int8' for CPU).
        vad_threshold: Voice activity detection sensitivity (0.0 to 1.0).
        min_speech_duration_ms: Minimum speech duration to consider valid.
        typing_delay_ms: Delay between keystrokes when injecting text.
        overlay_size: Size of the floating overlay window in pixels.
        overlay_margin: Distance from screen edge in pixels.
    """
    
    # Hotkey settings
    hotkey_toggle: str = "f8"
    hotkey_panic: str = "f9"
    
    # Whisper model settings (parsed from command line or default).
    # Use multilingual 'small' by default for better name recognition.
    model_size: str = field(default_factory=parse_model_from_args)
    
    # Audio settings
    silence_threshold_sec: float = 1.0
    sample_rate: int = 16000
    
    # Device settings (auto-detected by default)
    device: str = field(default_factory=detect_device)
    compute_type: str = field(default="")
    
    # VAD settings
    vad_threshold: float = 0.5
    min_speech_duration_ms: int = 250
    
    # Text injection settings
    typing_delay_ms: int = 10
    
    # UI settings
    overlay_size: int = 80
    overlay_margin: int = 50
    
    def __post_init__(self):
        """
        Post-initialization to set compute_type based on device.
        Called automatically after dataclass __init__.
        """
        if not self.compute_type:
            self.compute_type = get_compute_type(self.device)


# Global configuration instance.
# Import this in other modules to access settings.
config = AppConfig()


# Application metadata
APP_NAME = "VTT-voice2text"
APP_VERSION = "1.0.0"


if __name__ == "__main__":
    # Debug: Print current configuration when run directly.
    print(f"=== {APP_NAME} v{APP_VERSION} Configuration ===")
    print(f"Device: {config.device}")
    print(f"Compute Type: {config.compute_type}")
    print(f"Model: {config.model_size}")
    print(f"Toggle Hotkey: {config.hotkey_toggle.upper()}")
    print(f"Panic Hotkey: {config.hotkey_panic.upper()}")
    print(f"Silence Threshold: {config.silence_threshold_sec}s")
    print(f"VAD Threshold: {config.vad_threshold}")

