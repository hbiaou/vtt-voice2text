"""
transcriber.py - Whisper model loading and speech-to-text inference.

This module manages the faster-whisper model. The model is loaded once
at startup and kept in RAM for fast repeated transcriptions.
"""

import numpy as np
from faster_whisper import WhisperModel
from typing import Optional, Tuple, List

from config import config, APP_NAME


class Transcriber:
    """
    Handles speech-to-text transcription using faster-whisper.
    
    The model is loaded once during initialization and reused for all
    transcription requests. This avoids the overhead of loading the
    model for each transcription.
    
    Attributes:
        model: The loaded WhisperModel instance.
        is_ready: Flag indicating if the model is loaded and ready.
    """
    
    def __init__(self):
        """
        Initialize the Transcriber.
        Model loading is deferred to load_model() for better control.
        """
        self.model: Optional[WhisperModel] = None
        self.is_ready: bool = False
        self._device = config.device
        self._compute_type = config.compute_type
        self._model_size = config.model_size
    
    def load_model(self) -> bool:
        """
        Load the Whisper model into memory.
        
        This should be called once at application startup.
        The model stays in RAM until the application exits.
        
        Returns:
            True if model loaded successfully, False otherwise.
        """
        try:
            print(f"[{APP_NAME}] Loading Whisper model: {self._model_size}")
            print(f"[{APP_NAME}] Device: {self._device}, Compute: {self._compute_type}")
            
            # Load the faster-whisper model.
            # - device: 'cuda' for GPU, 'cpu' for CPU.
            # - compute_type: 'float16' for GPU speed, 'int8' for CPU efficiency.
            self.model = WhisperModel(
                self._model_size,
                device=self._device,
                compute_type=self._compute_type
            )
            
            self.is_ready = True
            print(f"[{APP_NAME}] Model loaded successfully!")
            return True
            
        except Exception as e:
            print(f"[{APP_NAME}] ERROR loading model: {e}")
            self.is_ready = False
            return False
    
    def transcribe(self, audio: np.ndarray) -> str:
        """
        Transcribe audio data to text.
        
        Args:
            audio: NumPy array of audio samples (float32, 16kHz, mono).
                   Values should be in range [-1.0, 1.0].
        
        Returns:
            Transcribed text string. Empty string if transcription fails.
        """
        # Check if model is loaded.
        if not self.is_ready or self.model is None:
            print(f"[{APP_NAME}] ERROR: Model not loaded!")
            return ""
        
        # Validate audio input.
        if audio is None or len(audio) == 0:
            return ""
        
        try:
            # Ensure audio is float32 (required by faster-whisper).
            if audio.dtype != np.float32:
                audio = audio.astype(np.float32)
            
            # Run transcription.
            # - beam_size=5: Balance between speed and accuracy.
            # - vad_filter=True: Filter out non-speech segments.
            # - language: Only set for .en models, otherwise auto-detect.
            transcribe_kwargs = {
                "beam_size": 5,
                "vad_filter": True,
            }
            
            # Only force English for English-only models (.en suffix).
            if self._model_size.endswith(".en"):
                transcribe_kwargs["language"] = "en"
            
            segments, info = self.model.transcribe(audio, **transcribe_kwargs)
            
            # Collect all segment texts.
            text_parts: List[str] = []
            for segment in segments:
                text_parts.append(segment.text.strip())
            
            # Join segments with spaces.
            result = " ".join(text_parts)
            
            # Log transcription result.
            if result:
                print(f"[{APP_NAME}] Transcribed: \"{result}\"")
            
            return result
            
        except Exception as e:
            print(f"[{APP_NAME}] Transcription error: {e}")
            return ""
    
    def get_model_info(self) -> dict:
        """
        Get information about the loaded model.
        
        Returns:
            Dictionary with model details.
        """
        return {
            "model_size": self._model_size,
            "device": self._device,
            "compute_type": self._compute_type,
            "is_ready": self.is_ready
        }
    
    def unload_model(self):
        """
        Unload the model from memory.
        Call this during application shutdown for clean cleanup.
        """
        if self.model is not None:
            # Delete model reference to free GPU/RAM memory.
            del self.model
            self.model = None
            self.is_ready = False
            print(f"[{APP_NAME}] Model unloaded.")


# Singleton instance for global access.
# Other modules can import this directly.
transcriber = Transcriber()


if __name__ == "__main__":
    # Test the transcriber module.
    print("Testing Transcriber module...")
    
    # Load model.
    if transcriber.load_model():
        print("Model info:", transcriber.get_model_info())
        
        # Create a silent test audio (1 second of silence).
        test_audio = np.zeros(16000, dtype=np.float32)
        result = transcriber.transcribe(test_audio)
        print(f"Test transcription result: '{result}'")
        
        # Cleanup.
        transcriber.unload_model()
    else:
        print("Failed to load model!")

