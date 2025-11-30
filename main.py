"""
main.py - Entry point and GUI orchestration for VTT-voice2text.

This is the main application file that creates:
1. System tray icon with menu (Toggle, Quit).
2. Floating overlay window showing recording state.
3. Global hotkey handling (F8 toggle, F9 panic).
4. Coordination between audio capture, transcription, and text injection.
"""

# Suppress deprecation warning from ctranslate2 (pkg_resources).
import warnings
warnings.filterwarnings("ignore", message=".*pkg_resources.*")

import sys
import signal
import threading
from enum import Enum
from typing import Optional

from PySide6.QtWidgets import (
    QApplication, QWidget, QSystemTrayIcon, QMenu, QLabel, QVBoxLayout
)
from PySide6.QtCore import (
    Qt, QTimer, Signal, QObject, QThread, QPropertyAnimation, 
    QEasingCurve, Property, QSize
)
from PySide6.QtGui import (
    QIcon, QPainter, QColor, QBrush, QPen, QPixmap, QFont, QAction
)

import keyboard
import numpy as np


# =============================================================================
# Global reference for signal handler
# =============================================================================
_app_instance = None

from config import config, APP_NAME, APP_VERSION
from audio_engine import audio_engine
from transcriber import transcriber
from injector import injector


# =============================================================================
# Application State Machine
# =============================================================================

class AppState(Enum):
    """
    Application states for the dictation workflow.
    
    STANDBY: Not listening, red indicator.
    LISTENING: Recording audio, green indicator.
    TRANSCRIBING: Processing audio, yellow indicator.
    """
    STANDBY = "standby"
    LISTENING = "listening"
    TRANSCRIBING = "transcribing"


# =============================================================================
# Signals for Thread Communication
# =============================================================================

class AppSignals(QObject):
    """
    Qt signals for cross-thread communication.
    
    PySide6 requires signals to update GUI from worker threads.
    """
    # Signal when audio chunk is ready for transcription.
    audio_chunk_ready = Signal(np.ndarray)
    
    # Signal when transcription is complete.
    transcription_complete = Signal(str)
    
    # Signal to update application state.
    state_changed = Signal(AppState)
    
    # Signal for status messages.
    status_message = Signal(str)
    
    # Signal when model is loaded.
    model_loaded = Signal(bool)


# Global signals instance.
signals = AppSignals()


# =============================================================================
# Transcription Worker Thread
# =============================================================================

class TranscriptionWorker(QThread):
    """
    Worker thread for running transcription without blocking GUI.
    """
    
    def __init__(self, audio_data: np.ndarray):
        super().__init__()
        self.audio_data = audio_data
    
    def run(self):
        """
        Run transcription in background thread.
        """
        # Transcribe the audio.
        text = transcriber.transcribe(self.audio_data)
        
        # Emit result via signal.
        signals.transcription_complete.emit(text)


# =============================================================================
# Model Loading Worker Thread
# =============================================================================

class ModelLoaderWorker(QThread):
    """
    Worker thread for loading models without blocking GUI.
    """
    
    def run(self):
        """
        Load both VAD and Whisper models.
        """
        # Load VAD model first (smaller, faster).
        vad_ok = audio_engine.load_vad_model()
        
        # Load Whisper model.
        whisper_ok = transcriber.load_model()
        
        # Emit result.
        signals.model_loaded.emit(vad_ok and whisper_ok)


# =============================================================================
# Floating Overlay Widget
# =============================================================================

class OverlayWidget(QWidget):
    """
    Small floating overlay window showing recording state.
    
    Displays a colored circle:
    - Red: Standby (not listening).
    - Green (pulsing): Listening for speech.
    - Yellow: Transcribing audio.
    """
    
    def __init__(self):
        super().__init__()
        
        # Window properties.
        self.setWindowTitle(APP_NAME)
        self.setFixedSize(config.overlay_size, config.overlay_size)
        
        # Frameless, always on top, tool window (no taskbar entry).
        self.setWindowFlags(
            Qt.WindowStaysOnTopHint |
            Qt.FramelessWindowHint |
            Qt.Tool
        )
        
        # Transparent background.
        self.setAttribute(Qt.WA_TranslucentBackground)
        
        # Current state.
        self._state = AppState.STANDBY
        
        # Animation properties.
        self._pulse_value = 1.0
        self._pulse_animation: Optional[QPropertyAnimation] = None
        
        # Position in bottom-right corner.
        self._position_overlay()
        
        # Setup pulse animation.
        self._setup_animation()
    
    def _position_overlay(self):
        """
        Position the overlay in the bottom-right corner of the screen.
        """
        screen = QApplication.primaryScreen().geometry()
        x = screen.width() - config.overlay_size - config.overlay_margin
        y = screen.height() - config.overlay_size - config.overlay_margin - 40  # Account for taskbar.
        self.move(x, y)
    
    def _setup_animation(self):
        """
        Setup the pulsing animation for the listening state.
        """
        self._pulse_animation = QPropertyAnimation(self, b"pulse_value")
        self._pulse_animation.setDuration(800)
        self._pulse_animation.setStartValue(0.6)
        self._pulse_animation.setEndValue(1.0)
        self._pulse_animation.setEasingCurve(QEasingCurve.InOutSine)
        self._pulse_animation.setLoopCount(-1)  # Infinite loop.
    
    def get_pulse_value(self) -> float:
        return self._pulse_value
    
    def set_pulse_value(self, value: float):
        self._pulse_value = value
        self.update()  # Trigger repaint.
    
    # Qt property for animation.
    pulse_value = Property(float, get_pulse_value, set_pulse_value)
    
    def set_state(self, state: AppState):
        """
        Update the overlay state and appearance.
        
        Args:
            state: New application state.
        """
        self._state = state
        
        # Start/stop pulse animation based on state.
        if state == AppState.LISTENING:
            if self._pulse_animation and self._pulse_animation.state() != QPropertyAnimation.State.Running:
                self._pulse_animation.start()
        else:
            if self._pulse_animation and self._pulse_animation.state() == QPropertyAnimation.State.Running:
                self._pulse_animation.stop()
            self._pulse_value = 1.0
        
        self.update()  # Trigger repaint.
    
    def cleanup(self):
        """
        Clean up resources before closing.
        """
        if self._pulse_animation:
            self._pulse_animation.stop()
            self._pulse_animation = None
    
    def paintEvent(self, event):
        """
        Custom paint event to draw the colored circle.
        """
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        # Determine color based on state.
        if self._state == AppState.STANDBY:
            color = QColor(220, 53, 69)  # Red.
            alpha = 200
        elif self._state == AppState.LISTENING:
            color = QColor(40, 167, 69)  # Green.
            alpha = int(200 * self._pulse_value)
        else:  # TRANSCRIBING
            color = QColor(255, 193, 7)  # Yellow.
            alpha = 200
        
        color.setAlpha(alpha)
        
        # Calculate circle dimensions.
        margin = 10
        size = min(self.width(), self.height()) - 2 * margin
        
        # Apply pulse scaling for listening state.
        if self._state == AppState.LISTENING:
            scale = 0.8 + 0.2 * self._pulse_value
            size = int(size * scale)
        
        x = (self.width() - size) // 2
        y = (self.height() - size) // 2
        
        # Draw outer glow/shadow.
        glow_color = QColor(color)
        glow_color.setAlpha(50)
        painter.setBrush(QBrush(glow_color))
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(x - 5, y - 5, size + 10, size + 10)
        
        # Draw main circle.
        painter.setBrush(QBrush(color))
        painter.setPen(QPen(color.darker(120), 2))
        painter.drawEllipse(x, y, size, size)
        
        # Draw inner highlight.
        highlight = QColor(255, 255, 255, 60)
        painter.setBrush(QBrush(highlight))
        painter.setPen(Qt.NoPen)
        highlight_size = size // 3
        painter.drawEllipse(x + size // 4, y + size // 6, highlight_size, highlight_size)
    
    def mousePressEvent(self, event):
        """
        Allow dragging the overlay by clicking on it.
        """
        if event.button() == Qt.LeftButton:
            self._drag_position = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()
    
    def mouseMoveEvent(self, event):
        """
        Handle overlay dragging.
        """
        if event.buttons() == Qt.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_position)
            event.accept()


# =============================================================================
# Main Application Controller
# =============================================================================

class VTTApplication:
    """
    Main application controller.
    
    Coordinates all components: GUI, audio capture, transcription, injection.
    """
    
    def __init__(self):
        """
        Initialize the application.
        """
        # Qt Application.
        self.app = QApplication(sys.argv)
        self.app.setQuitOnLastWindowClosed(False)  # Keep running in tray.
        
        # Application state.
        self._state = AppState.STANDBY
        self._models_loaded = False
        
        # Current transcription worker.
        self._transcription_worker: Optional[TranscriptionWorker] = None
        
        # Create UI components.
        self._create_overlay()
        self._create_system_tray()
        
        # Connect signals.
        self._connect_signals()
        
        # Setup global hotkeys.
        self._setup_hotkeys()
        
        # Set audio callback.
        audio_engine.on_audio_chunk = self._on_audio_chunk
    
    def _create_overlay(self):
        """
        Create the floating overlay widget.
        """
        self.overlay = OverlayWidget()
        self.overlay.show()
    
    def _create_system_tray(self):
        """
        Create the system tray icon and menu.
        """
        # Check if system tray is available.
        if not QSystemTrayIcon.isSystemTrayAvailable():
            print(f"[{APP_NAME}] WARNING: System tray not available!")
        
        # Create tray icon.
        self.tray_icon = QSystemTrayIcon(self.app)
        
        # Create a visible microphone-style icon.
        icon_pixmap = QPixmap(32, 32)
        icon_pixmap.fill(Qt.transparent)
        
        painter = QPainter(icon_pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        
        # Draw a red/orange circle (stands out in system tray).
        painter.setBrush(QBrush(QColor(220, 80, 60)))
        painter.setPen(QPen(QColor(180, 60, 40), 2))
        painter.drawEllipse(2, 2, 28, 28)
        
        # Draw "V" for VTT in white.
        painter.setPen(QPen(QColor(255, 255, 255), 3))
        painter.drawLine(8, 10, 16, 22)
        painter.drawLine(16, 22, 24, 10)
        
        painter.end()
        
        self.tray_icon.setIcon(QIcon(icon_pixmap))
        
        # Create context menu.
        tray_menu = QMenu()
        
        # Toggle action.
        self.toggle_action = QAction(f"Toggle ({config.hotkey_toggle.upper()})")
        self.toggle_action.triggered.connect(self._toggle_listening)
        tray_menu.addAction(self.toggle_action)
        
        # Status display.
        self.status_action = QAction("Status: Loading...")
        self.status_action.setEnabled(False)
        tray_menu.addAction(self.status_action)
        
        tray_menu.addSeparator()
        
        # Quit action.
        quit_action = QAction("Quit")
        quit_action.triggered.connect(self._quit)
        tray_menu.addAction(quit_action)
        
        self.tray_icon.setContextMenu(tray_menu)
        self.tray_icon.setToolTip(f"{APP_NAME} v{APP_VERSION}")
        self.tray_icon.show()
        
        # Handle tray icon click.
        self.tray_icon.activated.connect(self._on_tray_activated)
    
    def _connect_signals(self):
        """
        Connect Qt signals for thread communication.
        """
        signals.state_changed.connect(self._on_state_changed)
        signals.transcription_complete.connect(self._on_transcription_complete)
        signals.status_message.connect(self._update_status)
        signals.model_loaded.connect(self._on_models_loaded)
    
    def _setup_hotkeys(self):
        """
        Setup global hotkeys using the keyboard library.
        """
        try:
            # Toggle hotkey (F8).
            keyboard.add_hotkey(
                config.hotkey_toggle,
                self._toggle_listening,
                suppress=False
            )
            
            # Panic hotkey (F9).
            keyboard.add_hotkey(
                config.hotkey_panic,
                self._panic_stop,
                suppress=False
            )
            
            print(f"[{APP_NAME}] Hotkeys registered: {config.hotkey_toggle.upper()}, {config.hotkey_panic.upper()}")
            
        except Exception as e:
            print(f"[{APP_NAME}] Error setting up hotkeys: {e}")
    
    def _toggle_listening(self):
        """
        Toggle between listening and standby states.
        Called when user presses the toggle hotkey.
        """
        if not self._models_loaded:
            print(f"[{APP_NAME}] Models not loaded yet!")
            return
        
        if self._state == AppState.STANDBY:
            # Start listening.
            self._set_state(AppState.LISTENING)
            audio_engine.start()
            print(f"[{APP_NAME}] Started listening...")
            
        elif self._state == AppState.LISTENING:
            # Stop listening.
            audio_engine.stop()
            self._set_state(AppState.STANDBY)
            print(f"[{APP_NAME}] Stopped listening.")
            
        # If transcribing, don't interrupt - let it finish.
    
    def _panic_stop(self):
        """
        Emergency stop - abort everything immediately.
        Called when user presses the panic hotkey.
        """
        print(f"[{APP_NAME}] PANIC STOP!")
        
        # Abort any ongoing text injection.
        injector.abort()
        
        # Stop audio capture.
        audio_engine.stop()
        
        # Return to standby.
        self._set_state(AppState.STANDBY)
    
    def _on_audio_chunk(self, audio: np.ndarray):
        """
        Callback when audio chunk is ready from AudioEngine.
        Called from audio thread - use signal for thread safety.
        
        Args:
            audio: NumPy array of audio samples.
        """
        # Emit signal to handle in main thread.
        signals.audio_chunk_ready.emit(audio)
    
    def _process_audio_chunk(self, audio: np.ndarray):
        """
        Process an audio chunk - start transcription.
        
        Args:
            audio: NumPy array of audio samples.
        """
        if self._state != AppState.LISTENING:
            return
        
        print(f"[{APP_NAME}] Processing audio chunk: {len(audio)} samples")
        
        # Change state to transcribing.
        self._set_state(AppState.TRANSCRIBING)
        
        # Start transcription worker.
        self._transcription_worker = TranscriptionWorker(audio)
        self._transcription_worker.start()
    
    def _on_transcription_complete(self, text: str):
        """
        Handle transcription result.
        Called via signal when transcription worker finishes.
        
        Args:
            text: Transcribed text.
        """
        # Inject text into active window.
        if text:
            injector.inject(text, add_trailing_space=True)
        
        # Return to listening state (continuous dictation).
        if audio_engine.is_listening:
            self._set_state(AppState.LISTENING)
        else:
            self._set_state(AppState.STANDBY)
    
    def _set_state(self, state: AppState):
        """
        Update application state.
        
        Args:
            state: New state.
        """
        self._state = state
        signals.state_changed.emit(state)
    
    def _on_state_changed(self, state: AppState):
        """
        Handle state change - update UI.
        
        Args:
            state: New state.
        """
        # Update overlay.
        self.overlay.set_state(state)
        
        # Update status text.
        status_text = {
            AppState.STANDBY: "Standby",
            AppState.LISTENING: "Listening...",
            AppState.TRANSCRIBING: "Transcribing..."
        }.get(state, "Unknown")
        
        self._update_status(f"Status: {status_text}")
    
    def _update_status(self, message: str):
        """
        Update the status display in system tray menu.
        
        Args:
            message: Status message.
        """
        self.status_action.setText(message)
    
    def _on_tray_activated(self, reason):
        """
        Handle tray icon activation (click).
        
        Args:
            reason: Activation reason.
        """
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            # Single click - toggle listening.
            self._toggle_listening()
    
    def _on_models_loaded(self, success: bool):
        """
        Handle model loading completion.
        
        Args:
            success: True if models loaded successfully.
        """
        self._models_loaded = success
        
        if success:
            self._update_status("Status: Ready")
            print(f"[{APP_NAME}] All models loaded. Ready!")
            self.tray_icon.showMessage(
                APP_NAME,
                f"Ready! Press {config.hotkey_toggle.upper()} to start dictating.",
                QSystemTrayIcon.MessageIcon.Information,
                3000
            )
        else:
            self._update_status("Status: Model Error!")
            print(f"[{APP_NAME}] ERROR: Failed to load models!")
    
    def _quit(self):
        """
        Clean shutdown of the application.
        """
        print(f"[{APP_NAME}] Shutting down...")
        
        # Stop overlay animation first to avoid property errors.
        if hasattr(self, 'overlay'):
            self.overlay.cleanup()
        
        # Stop audio.
        audio_engine.cleanup()
        
        # Unload transcriber.
        transcriber.unload_model()
        
        # Remove hotkeys.
        try:
            keyboard.unhook_all()
        except:
            pass
        
        # Quit application.
        self.app.quit()
    
    def run(self):
        """
        Run the application.
        """
        print(f"=== {APP_NAME} v{APP_VERSION} ===")
        print(f"Toggle: {config.hotkey_toggle.upper()}")
        print(f"Panic: {config.hotkey_panic.upper()}")
        print(f"Device: {config.device}")
        print()
        
        # Connect audio chunk signal.
        signals.audio_chunk_ready.connect(self._process_audio_chunk)
        
        # Start model loading in background.
        self._update_status("Status: Loading models...")
        self.model_loader = ModelLoaderWorker()
        self.model_loader.start()
        
        # Run Qt event loop.
        return self.app.exec()


# =============================================================================
# Signal Handler for Ctrl+C
# =============================================================================

def signal_handler(signum, frame):
    """
    Handle Ctrl+C (SIGINT) for clean shutdown.
    """
    print(f"\n[{APP_NAME}] Ctrl+C received. Shutting down...")
    global _app_instance
    if _app_instance:
        _app_instance._quit()
    sys.exit(0)


# =============================================================================
# Entry Point
# =============================================================================

def main():
    """
    Application entry point.
    """
    global _app_instance
    
    # Register signal handler for Ctrl+C.
    signal.signal(signal.SIGINT, signal_handler)
    
    try:
        _app_instance = VTTApplication()
        
        # Timer to allow Python to process signals (Ctrl+C).
        # Qt event loop blocks Python signal handling otherwise.
        timer = QTimer()
        timer.timeout.connect(lambda: None)  # Dummy callback.
        timer.start(100)  # Check every 100ms.
        
        sys.exit(_app_instance.run())
    except Exception as e:
        print(f"[{APP_NAME}] Fatal error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()

