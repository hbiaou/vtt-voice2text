"""
config.py - Application settings and configuration.

This module contains all configurable settings for the VTT-voice2text app.
Settings are stored in a dataclass and persisted to a JSON file.

To change the model, edit MODEL_SIZE below or use command line:
    python main.py --model small.en

Available models (English-only, faster):
    tiny.en, base.en, small.en, medium.en

Available models (Multilingual, better for names):
    tiny, base, small, medium, large-v2, large-v3
"""

from dataclasses import dataclass, field, asdict
from typing import Literal, Dict, List
import sys
import json
import os
import torch


# Path to settings file in user's home directory.
SETTINGS_FILE = os.path.join(os.path.expanduser("~"), ".vtt-voice2text-settings.json")

# Path to custom vocabulary file.
VOCAB_FILE = os.path.join(os.path.expanduser("~"), ".vtt-voice2text-vocab.json")


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


# Available Whisper models for the settings UI.
AVAILABLE_MODELS = [
    ("tiny.en", "Tiny (English) - 39MB, ~1s"),
    ("tiny", "Tiny (Multilingual) - 39MB, ~1s"),
    ("base.en", "Base (English) - 74MB, ~2s"),
    ("base", "Base (Multilingual) - 74MB, ~2s"),
    ("small.en", "Small (English) - 244MB, ~4s"),
    ("small", "Small (Multilingual) - 244MB, ~4s"),
    ("medium.en", "Medium (English) - 769MB, ~8s"),
    ("medium", "Medium (Multilingual) - 769MB, ~8s"),
    ("large-v2", "Large v2 (Multilingual) - 1.5GB, ~15s"),
    ("large-v3", "Large v3 (Multilingual) - 1.5GB, ~15s"),
]


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
        output_mode: 'type' to simulate typing, 'clipboard' to copy to clipboard.
        use_custom_vocab: Whether to apply custom vocabulary corrections.
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
    
    # Output mode: 'type' or 'clipboard'
    output_mode: str = "type"
    
    # Custom vocabulary settings
    use_custom_vocab: bool = True
    
    def __post_init__(self):
        """
        Post-initialization to set compute_type based on device.
        Called automatically after dataclass __init__.
        """
        if not self.compute_type:
            self.compute_type = get_compute_type(self.device)
    
    def save(self):
        """
        Save current settings to JSON file.
        """
        # Only save user-configurable settings.
        settings = {
            "hotkey_toggle": self.hotkey_toggle,
            "hotkey_panic": self.hotkey_panic,
            "model_size": self.model_size,
            "silence_threshold_sec": self.silence_threshold_sec,
            "vad_threshold": self.vad_threshold,
            "typing_delay_ms": self.typing_delay_ms,
            "output_mode": self.output_mode,
            "use_custom_vocab": self.use_custom_vocab,
        }
        
        try:
            with open(SETTINGS_FILE, 'w') as f:
                json.dump(settings, f, indent=2)
            print(f"[VTT] Settings saved to {SETTINGS_FILE}")
        except Exception as e:
            print(f"[VTT] Error saving settings: {e}")
    
    def load(self):
        """
        Load settings from JSON file if it exists.
        """
        if not os.path.exists(SETTINGS_FILE):
            return
        
        try:
            with open(SETTINGS_FILE, 'r') as f:
                settings = json.load(f)
            
            # Apply loaded settings.
            for key, value in settings.items():
                if hasattr(self, key):
                    setattr(self, key, value)
            
            # Recalculate compute_type after loading device.
            self.compute_type = get_compute_type(self.device)
            
            print(f"[VTT] Settings loaded from {SETTINGS_FILE}")
        except Exception as e:
            print(f"[VTT] Error loading settings: {e}")


class CustomVocabulary:
    """
    Manages custom vocabulary for word corrections.
    
    Stores mappings from misrecognized words to correct spellings.
    Example: {"noref": "Honoré", "onori": "Honoré"}
    """
    
    def __init__(self):
        self.corrections: Dict[str, str] = {}
        self.load()
    
    def load(self):
        """
        Load custom vocabulary from JSON file.
        """
        if not os.path.exists(VOCAB_FILE):
            # Create default example vocabulary.
            self.corrections = {
                # Add example corrections (case-insensitive matching).
                # "misheard": "correct",
            }
            self.save()
            return
        
        try:
            with open(VOCAB_FILE, 'r', encoding='utf-8') as f:
                self.corrections = json.load(f)
            print(f"[VTT] Loaded {len(self.corrections)} custom vocabulary entries")
        except Exception as e:
            print(f"[VTT] Error loading vocabulary: {e}")
            self.corrections = {}
    
    def save(self):
        """
        Save custom vocabulary to JSON file.
        """
        try:
            with open(VOCAB_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.corrections, f, indent=2, ensure_ascii=False)
            print(f"[VTT] Vocabulary saved to {VOCAB_FILE}")
        except Exception as e:
            print(f"[VTT] Error saving vocabulary: {e}")
    
    def add_correction(self, wrong: str, correct: str):
        """
        Add a word correction mapping.
        
        Args:
            wrong: The misrecognized word (case-insensitive).
            correct: The correct spelling.
        """
        self.corrections[wrong.lower()] = correct
        self.save()
    
    def remove_correction(self, wrong: str):
        """
        Remove a word correction mapping.
        
        Args:
            wrong: The misrecognized word to remove.
        """
        key = wrong.lower()
        if key in self.corrections:
            del self.corrections[key]
            self.save()
    
    def apply(self, text: str) -> str:
        """
        Apply vocabulary corrections to transcribed text.
        
        Performs case-insensitive word replacement while preserving
        the original capitalization pattern.
        
        Args:
            text: The transcribed text.
        
        Returns:
            Text with corrections applied.
        """
        if not self.corrections:
            return text
        
        words = text.split()
        result = []
        
        for word in words:
            # Strip punctuation for matching.
            stripped = word.strip('.,!?;:"\'-')
            lower_stripped = stripped.lower()
            
            if lower_stripped in self.corrections:
                correct = self.corrections[lower_stripped]
                
                # Preserve punctuation.
                prefix = word[:len(word) - len(word.lstrip('.,!?;:"\'-'))]
                suffix = word[len(word.rstrip('.,!?;:"\'-')):]
                
                # Apply capitalization pattern.
                if stripped.isupper():
                    correct = correct.upper()
                elif stripped[0].isupper() if stripped else False:
                    correct = correct[0].upper() + correct[1:] if len(correct) > 1 else correct.upper()
                
                result.append(prefix + correct + suffix)
            else:
                result.append(word)
        
        return ' '.join(result)
    
    def get_all(self) -> Dict[str, str]:
        """
        Get all correction mappings.
        
        Returns:
            Dictionary of wrong -> correct mappings.
        """
        return self.corrections.copy()


# Global configuration instance.
# Import this in other modules to access settings.
config = AppConfig()

# Load saved settings on import.
config.load()

# Global custom vocabulary instance.
custom_vocab = CustomVocabulary()

# Application metadata
APP_NAME = "VTT-voice2text"
APP_VERSION = "1.1.0"


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
    print(f"Output Mode: {config.output_mode}")
    print(f"Use Custom Vocab: {config.use_custom_vocab}")
    print(f"\nCustom Vocabulary ({len(custom_vocab.corrections)} entries):")
    for wrong, correct in custom_vocab.get_all().items():
        print(f"  '{wrong}' -> '{correct}'")
