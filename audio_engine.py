"""
audio_engine.py - Microphone capture and Voice Activity Detection (VAD).

This module handles:
1. Continuous audio streaming from the microphone using sounddevice.
2. Voice Activity Detection using silero-vad to detect speech.
3. Smart audio chunking - cuts audio when silence is detected after speech.
"""

import numpy as np
import sounddevice as sd
import torch
import threading
import time
from typing import Callable, Optional
from collections import deque

from config import config, APP_NAME


class AudioEngine:
    """
    Manages microphone audio capture with Voice Activity Detection.
    
    Uses silero-vad to detect speech segments. When the user speaks,
    audio is accumulated. After a configurable silence period, the
    audio chunk is emitted via callback for transcription.
    
    Attributes:
        is_listening: Flag indicating if currently capturing audio.
        on_audio_chunk: Callback function called when audio chunk is ready.
    """
    
    def __init__(self, on_audio_chunk: Optional[Callable[[np.ndarray], None]] = None):
        """
        Initialize the AudioEngine.
        
        Args:
            on_audio_chunk: Callback function that receives audio chunks.
                           Called with numpy array (float32, 16kHz) when
                           speech segment is complete.
        """
        self.on_audio_chunk = on_audio_chunk
        self.is_listening = False
        
        # Audio settings from config.
        self._sample_rate = config.sample_rate
        self._silence_threshold = config.silence_threshold_sec
        self._vad_threshold = config.vad_threshold
        
        # VAD model (loaded lazily).
        self._vad_model = None
        self._vad_ready = False
        
        # Audio stream.
        self._stream: Optional[sd.InputStream] = None
        
        # Audio buffer for accumulating speech.
        self._audio_buffer: deque = deque()
        self._is_speaking = False
        self._silence_start_time: Optional[float] = None
        
        # Thread safety.
        self._lock = threading.Lock()
        
        # VAD requires specific chunk size (512 samples at 16kHz).
        self._vad_chunk_size = 512
        self._pending_samples: np.ndarray = np.array([], dtype=np.float32)
    
    def load_vad_model(self) -> bool:
        """
        Load the silero-vad model.
        
        Should be called once at application startup.
        
        Returns:
            True if model loaded successfully, False otherwise.
        """
        try:
            print(f"[{APP_NAME}] Loading silero-vad model...")
            
            # Load silero-vad from torch hub.
            # This downloads the model on first run (~2MB).
            self._vad_model, utils = torch.hub.load(
                repo_or_dir='snakers4/silero-vad',
                model='silero_vad',
                force_reload=False,
                trust_repo=True
            )
            
            self._vad_ready = True
            print(f"[{APP_NAME}] VAD model loaded successfully!")
            return True
            
        except Exception as e:
            print(f"[{APP_NAME}] ERROR loading VAD model: {e}")
            self._vad_ready = False
            return False
    
    def _check_voice_activity(self, audio_chunk: np.ndarray) -> bool:
        """
        Check if audio chunk contains speech using VAD.
        
        Args:
            audio_chunk: Audio samples (float32, 16kHz).
        
        Returns:
            True if speech detected, False otherwise.
        """
        if not self._vad_ready or self._vad_model is None:
            # Fallback: simple energy-based detection.
            energy = np.sqrt(np.mean(audio_chunk ** 2))
            return energy > 0.01
        
        try:
            # Convert to torch tensor.
            audio_tensor = torch.from_numpy(audio_chunk)
            
            # Get speech probability from VAD model.
            speech_prob = self._vad_model(audio_tensor, self._sample_rate).item()
            
            return speech_prob > self._vad_threshold
            
        except Exception as e:
            print(f"[{APP_NAME}] VAD error: {e}")
            return False
    
    def _audio_callback(self, indata: np.ndarray, frames: int, 
                        time_info: dict, status: sd.CallbackFlags):
        """
        Callback function called by sounddevice for each audio block.
        
        This runs in a separate audio thread. Processes audio in real-time
        to detect speech and accumulate audio chunks.
        
        Args:
            indata: Input audio data from microphone.
            frames: Number of frames in this block.
            time_info: Timing information.
            status: Status flags (overflow, underflow, etc.).
        """
        if status:
            print(f"[{APP_NAME}] Audio status: {status}")
        
        if not self.is_listening:
            return
        
        # Convert to mono float32 if needed.
        audio = indata[:, 0].copy().astype(np.float32)
        
        # Append to pending samples for VAD processing.
        self._pending_samples = np.concatenate([self._pending_samples, audio])
        
        # Process in VAD-compatible chunks (512 samples).
        while len(self._pending_samples) >= self._vad_chunk_size:
            # Extract chunk for VAD.
            vad_chunk = self._pending_samples[:self._vad_chunk_size]
            self._pending_samples = self._pending_samples[self._vad_chunk_size:]
            
            # Check for voice activity.
            is_speech = self._check_voice_activity(vad_chunk)
            
            with self._lock:
                if is_speech:
                    # Speech detected - add to buffer.
                    self._audio_buffer.append(vad_chunk)
                    self._is_speaking = True
                    self._silence_start_time = None
                    
                elif self._is_speaking:
                    # Was speaking, now silence.
                    # Still add to buffer (captures trailing audio).
                    self._audio_buffer.append(vad_chunk)
                    
                    if self._silence_start_time is None:
                        # Start counting silence.
                        self._silence_start_time = time.time()
                    else:
                        # Check if silence exceeded threshold.
                        silence_duration = time.time() - self._silence_start_time
                        
                        if silence_duration >= self._silence_threshold:
                            # Silence threshold reached - emit chunk.
                            self._emit_audio_chunk()
    
    def _emit_audio_chunk(self):
        """
        Emit accumulated audio buffer to callback.
        Called when silence is detected after speech.
        """
        if len(self._audio_buffer) == 0:
            return
        
        # Concatenate all buffered audio.
        audio_chunk = np.concatenate(list(self._audio_buffer))
        
        # Clear buffer and reset state.
        self._audio_buffer.clear()
        self._is_speaking = False
        self._silence_start_time = None
        
        # Check minimum duration (avoid very short clips).
        min_samples = int(config.min_speech_duration_ms * self._sample_rate / 1000)
        if len(audio_chunk) < min_samples:
            return
        
        # Call the callback if set.
        if self.on_audio_chunk is not None:
            try:
                self.on_audio_chunk(audio_chunk)
            except Exception as e:
                print(f"[{APP_NAME}] Error in audio chunk callback: {e}")
    
    def start(self) -> bool:
        """
        Start listening to the microphone.
        
        Returns:
            True if started successfully, False otherwise.
        """
        if self.is_listening:
            return True
        
        try:
            # Clear any previous state.
            with self._lock:
                self._audio_buffer.clear()
                self._is_speaking = False
                self._silence_start_time = None
                self._pending_samples = np.array([], dtype=np.float32)
            
            # Create and start audio stream.
            # - channels=1: Mono audio.
            # - samplerate=16000: Required by Whisper.
            # - blocksize=2048: Larger blocks reduce overflow on slower CPUs.
            # - latency='high': Prioritize stability over latency.
            self._stream = sd.InputStream(
                channels=1,
                samplerate=self._sample_rate,
                dtype=np.float32,
                blocksize=2048,
                latency='high',
                callback=self._audio_callback
            )
            self._stream.start()
            self.is_listening = True
            
            print(f"[{APP_NAME}] Audio capture started.")
            return True
            
        except Exception as e:
            print(f"[{APP_NAME}] ERROR starting audio capture: {e}")
            return False
    
    def stop(self):
        """
        Stop listening to the microphone.
        
        Emits any remaining audio in buffer before stopping.
        """
        if not self.is_listening:
            return
        
        self.is_listening = False
        
        # Emit any remaining audio.
        with self._lock:
            if len(self._audio_buffer) > 0 and self._is_speaking:
                self._emit_audio_chunk()
        
        # Stop and close the stream.
        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception as e:
                print(f"[{APP_NAME}] Error stopping stream: {e}")
            self._stream = None
        
        print(f"[{APP_NAME}] Audio capture stopped.")
    
    def get_input_devices(self) -> list:
        """
        Get list of available audio input devices.
        
        Returns:
            List of dictionaries with device info.
        """
        devices = []
        try:
            for i, device in enumerate(sd.query_devices()):
                if device['max_input_channels'] > 0:
                    devices.append({
                        'index': i,
                        'name': device['name'],
                        'channels': device['max_input_channels'],
                        'sample_rate': device['default_samplerate']
                    })
        except Exception as e:
            print(f"[{APP_NAME}] Error querying devices: {e}")
        
        return devices
    
    def cleanup(self):
        """
        Clean up resources.
        Call this during application shutdown.
        """
        self.stop()
        self._vad_model = None
        self._vad_ready = False


# Singleton instance for global access.
audio_engine = AudioEngine()


if __name__ == "__main__":
    # Test the audio engine.
    print("Testing AudioEngine module...")
    print("Available input devices:")
    for device in audio_engine.get_input_devices():
        print(f"  [{device['index']}] {device['name']}")
    
    # Test callback.
    def test_callback(audio: np.ndarray):
        duration = len(audio) / config.sample_rate
        print(f"Received audio chunk: {duration:.2f}s, {len(audio)} samples")
    
    audio_engine.on_audio_chunk = test_callback
    
    # Load VAD.
    if audio_engine.load_vad_model():
        print("\nStarting audio capture for 10 seconds...")
        print("Speak into your microphone!")
        
        audio_engine.start()
        time.sleep(10)
        audio_engine.stop()
        
        print("Test complete!")
    else:
        print("Failed to load VAD model!")
    
    audio_engine.cleanup()

