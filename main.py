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
    
    LOADING: Models are loading, spinning indicator.
    STANDBY: Not listening, ready indicator.
    LISTENING: Recording audio, pulsing indicator.
    TRANSCRIBING: Processing audio, processing indicator.
    """
    LOADING = "loading"
    STANDBY = "standby"
    LISTENING = "listening"
    TRANSCRIBING = "transcribing"


# Status messages for loading phases.
LOADING_MESSAGES = {
    "init": "Initializing...",
    "vad": "Loading VAD...",
    "whisper": "Loading Whisper...",
    "ready": "Ready",
    "error": "Error!"
}


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
    
    # Signal for loading progress updates.
    loading_progress = Signal(str)  # "vad", "whisper", "ready", "error"


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
        Load both VAD and Whisper models with progress updates.
        """
        # Emit loading VAD status.
        signals.loading_progress.emit("vad")
        vad_ok = audio_engine.load_vad_model()
        
        if not vad_ok:
            signals.loading_progress.emit("error")
            signals.model_loaded.emit(False)
            return
        
        # Emit loading Whisper status.
        signals.loading_progress.emit("whisper")
        whisper_ok = transcriber.load_model()
        
        if not whisper_ok:
            signals.loading_progress.emit("error")
            signals.model_loaded.emit(False)
            return
        
        # All loaded successfully.
        signals.loading_progress.emit("ready")
        signals.model_loaded.emit(True)


# =============================================================================
# Floating Overlay Widget - Modern Design
# =============================================================================

class OverlayWidget(QWidget):
    """
    Modern floating overlay window showing recording state.
    
    Features:
    - Glassmorphic design with blur effect simulation
    - Animated states: spinning (loading), pulsing (listening)
    - Status text display
    - Smooth transitions between states
    """
    
    # Increased size for modern design with text.
    OVERLAY_WIDTH = 160
    OVERLAY_HEIGHT = 100
    
    def __init__(self):
        super().__init__()
        
        # Window properties.
        self.setWindowTitle(APP_NAME)
        self.setFixedSize(self.OVERLAY_WIDTH, self.OVERLAY_HEIGHT)
        
        # Frameless, always on top, tool window (no taskbar entry).
        self.setWindowFlags(
            Qt.WindowStaysOnTopHint |
            Qt.FramelessWindowHint |
            Qt.Tool
        )
        
        # Transparent background.
        self.setAttribute(Qt.WA_TranslucentBackground)
        
        # Current state.
        self._state = AppState.LOADING
        self._status_text = "Initializing..."
        
        # Animation properties.
        self._animation_value = 0.0
        self._animation: Optional[QPropertyAnimation] = None
        
        # Spin animation timer for loading state.
        self._spin_angle = 0
        self._spin_timer = QTimer(self)
        self._spin_timer.timeout.connect(self._update_spin)
        
        # Position in bottom-right corner.
        self._position_overlay()
        
        # Setup animations.
        self._setup_animation()
        
        # Start in loading state with spin animation.
        self._spin_timer.start(30)  # ~33 FPS for smooth spin.
    
    def _position_overlay(self):
        """
        Position the overlay in the bottom-right corner of the screen.
        """
        screen = QApplication.primaryScreen().geometry()
        x = screen.width() - self.OVERLAY_WIDTH - config.overlay_margin
        y = screen.height() - self.OVERLAY_HEIGHT - config.overlay_margin - 50
        self.move(x, y)
    
    def _setup_animation(self):
        """
        Setup the pulsing animation for the listening state.
        """
        self._animation = QPropertyAnimation(self, b"animation_value")
        self._animation.setDuration(1200)
        self._animation.setStartValue(0.0)
        self._animation.setEndValue(1.0)
        self._animation.setEasingCurve(QEasingCurve.InOutSine)
        self._animation.setLoopCount(-1)
    
    def _update_spin(self):
        """
        Update spin angle for loading animation.
        """
        if self._state == AppState.LOADING:
            self._spin_angle = (self._spin_angle + 8) % 360
            self.update()
        elif self._state == AppState.TRANSCRIBING:
            self._spin_angle = (self._spin_angle + 12) % 360
            self.update()
    
    def get_animation_value(self) -> float:
        return self._animation_value
    
    def set_animation_value(self, value: float):
        self._animation_value = value
        self.update()
    
    # Qt property for animation.
    animation_value = Property(float, get_animation_value, set_animation_value)
    
    def set_status_text(self, text: str):
        """
        Update the status text displayed on the overlay.
        """
        self._status_text = text
        self.update()
    
    def set_state(self, state: AppState):
        """
        Update the overlay state and appearance.
        """
        self._state = state
        
        # Manage animations based on state.
        if state == AppState.LISTENING:
            # Start pulse animation for listening.
            self._spin_timer.stop()
            if self._animation and self._animation.state() != QPropertyAnimation.State.Running:
                self._animation.start()
        elif state == AppState.LOADING or state == AppState.TRANSCRIBING:
            # Start spin animation for loading/transcribing.
            if self._animation and self._animation.state() == QPropertyAnimation.State.Running:
                self._animation.stop()
            self._spin_timer.start(30)
        else:
            # Standby - no animation.
            self._spin_timer.stop()
            if self._animation and self._animation.state() == QPropertyAnimation.State.Running:
                self._animation.stop()
            self._animation_value = 0.0
        
        self.update()
    
    def cleanup(self):
        """
        Clean up resources before closing.
        """
        self._spin_timer.stop()
        if self._animation:
            self._animation.stop()
            self._animation = None
    
    def paintEvent(self, event):
        """
        Custom paint event - modern glassmorphic design.
        """
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.TextAntialiasing)
        
        # === Background Panel (Glassmorphic) ===
        # Dark semi-transparent background with rounded corners.
        bg_rect = self.rect().adjusted(2, 2, -2, -2)
        
        # Background gradient.
        bg_color = QColor(20, 20, 30, 230)
        painter.setBrush(QBrush(bg_color))
        painter.setPen(QPen(QColor(60, 60, 80, 150), 1))
        painter.drawRoundedRect(bg_rect, 16, 16)
        
        # === State Indicator ===
        indicator_size = 40
        indicator_x = 20
        indicator_y = (self.height() - indicator_size) // 2
        
        # Determine colors based on state.
        if self._state == AppState.LOADING:
            primary_color = QColor(100, 149, 237)  # Cornflower blue.
            self._draw_spinner(painter, indicator_x, indicator_y, indicator_size)
        elif self._state == AppState.STANDBY:
            primary_color = QColor(76, 175, 80)  # Material green.
            self._draw_ready_icon(painter, indicator_x, indicator_y, indicator_size)
        elif self._state == AppState.LISTENING:
            primary_color = QColor(76, 175, 80)  # Green.
            self._draw_listening_icon(painter, indicator_x, indicator_y, indicator_size)
        elif self._state == AppState.TRANSCRIBING:
            primary_color = QColor(255, 183, 77)  # Amber.
            self._draw_processing_icon(painter, indicator_x, indicator_y, indicator_size)
        
        # === Status Text ===
        text_x = indicator_x + indicator_size + 12
        text_width = self.width() - text_x - 15
        
        # Status label.
        painter.setPen(QColor(255, 255, 255, 220))
        font = QFont("Segoe UI", 10, QFont.Weight.DemiBold)
        painter.setFont(font)
        
        # Draw status text.
        text_rect = painter.boundingRect(
            text_x, indicator_y, text_width, indicator_size,
            Qt.AlignLeft | Qt.AlignVCenter, self._status_text
        )
        painter.drawText(
            text_x, indicator_y, text_width, indicator_size,
            Qt.AlignLeft | Qt.AlignVCenter, self._status_text
        )
        
        # Hotkey hint (smaller, dimmer).
        if self._state == AppState.STANDBY:
            hint_font = QFont("Segoe UI", 8)
            painter.setFont(hint_font)
            painter.setPen(QColor(150, 150, 150, 180))
            painter.drawText(
                text_x, indicator_y + 22, text_width, 20,
                Qt.AlignLeft | Qt.AlignVCenter, f"Press {config.hotkey_toggle.upper()}"
            )
    
    def _draw_spinner(self, painter: QPainter, x: int, y: int, size: int):
        """
        Draw a spinning loader animation.
        """
        center_x = x + size // 2
        center_y = y + size // 2
        radius = size // 2 - 4
        
        # Draw spinning arc segments.
        pen = QPen(QColor(100, 149, 237), 3, Qt.SolidLine, Qt.RoundCap)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        
        # Main spinning arc.
        from PySide6.QtCore import QRectF
        arc_rect = QRectF(center_x - radius, center_y - radius, radius * 2, radius * 2)
        
        # Draw arc (angle in 1/16th of a degree).
        start_angle = self._spin_angle * 16
        span_angle = 270 * 16
        painter.drawArc(arc_rect, start_angle, span_angle)
        
        # Faded trail.
        fade_pen = QPen(QColor(100, 149, 237, 80), 3, Qt.SolidLine, Qt.RoundCap)
        painter.setPen(fade_pen)
        painter.drawArc(arc_rect, start_angle + span_angle, 90 * 16)
    
    def _draw_ready_icon(self, painter: QPainter, x: int, y: int, size: int):
        """
        Draw a checkmark/ready icon.
        """
        center_x = x + size // 2
        center_y = y + size // 2
        
        # Outer glow.
        glow = QColor(76, 175, 80, 60)
        painter.setBrush(QBrush(glow))
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(center_x - size//2 + 2, center_y - size//2 + 2, size - 4, size - 4)
        
        # Inner circle.
        painter.setBrush(QBrush(QColor(76, 175, 80)))
        painter.drawEllipse(center_x - 14, center_y - 14, 28, 28)
        
        # Checkmark.
        painter.setPen(QPen(QColor(255, 255, 255), 3, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        painter.drawLine(center_x - 7, center_y, center_x - 2, center_y + 5)
        painter.drawLine(center_x - 2, center_y + 5, center_x + 7, center_y - 5)
    
    def _draw_listening_icon(self, painter: QPainter, x: int, y: int, size: int):
        """
        Draw a pulsing microphone/listening icon.
        """
        center_x = x + size // 2
        center_y = y + size // 2
        
        # Pulse effect.
        pulse_scale = 0.85 + 0.15 * self._animation_value
        pulse_alpha = int(255 * (1.0 - self._animation_value * 0.5))
        
        # Outer pulse ring.
        ring_size = int(size * pulse_scale)
        ring_color = QColor(76, 175, 80, int(100 * (1.0 - self._animation_value)))
        painter.setBrush(Qt.NoBrush)
        painter.setPen(QPen(ring_color, 2))
        painter.drawEllipse(
            center_x - ring_size//2, center_y - ring_size//2,
            ring_size, ring_size
        )
        
        # Inner filled circle.
        inner_color = QColor(76, 175, 80, pulse_alpha)
        painter.setBrush(QBrush(inner_color))
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(center_x - 14, center_y - 14, 28, 28)
        
        # Microphone icon (simplified).
        painter.setPen(QPen(QColor(255, 255, 255), 2, Qt.SolidLine, Qt.RoundCap))
        # Mic body.
        painter.drawRoundedRect(center_x - 4, center_y - 10, 8, 14, 4, 4)
        # Mic stand.
        painter.drawArc(center_x - 8, center_y - 2, 16, 12, 0, -180 * 16)
        painter.drawLine(center_x, center_y + 7, center_x, center_y + 11)
    
    def _draw_processing_icon(self, painter: QPainter, x: int, y: int, size: int):
        """
        Draw a processing/transcribing icon with spinning dots.
        """
        center_x = x + size // 2
        center_y = y + size // 2
        
        # Background circle.
        painter.setBrush(QBrush(QColor(255, 183, 77, 60)))
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(center_x - 16, center_y - 16, 32, 32)
        
        # Spinning dots around center.
        import math
        num_dots = 8
        dot_radius = 3
        orbit_radius = 12
        
        for i in range(num_dots):
            angle = math.radians(self._spin_angle + i * (360 / num_dots))
            dot_x = center_x + orbit_radius * math.cos(angle)
            dot_y = center_y + orbit_radius * math.sin(angle)
            
            # Fade dots based on position in spin.
            alpha = int(255 * ((i + 1) / num_dots))
            dot_color = QColor(255, 183, 77, alpha)
            painter.setBrush(QBrush(dot_color))
            painter.drawEllipse(int(dot_x - dot_radius), int(dot_y - dot_radius), 
                               dot_radius * 2, dot_radius * 2)
    
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
        
        # Application state - start in LOADING.
        self._state = AppState.LOADING
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
        
        # Set initial loading state on overlay.
        self.overlay.set_state(AppState.LOADING)
        self.overlay.set_status_text("Initializing...")
    
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
        signals.loading_progress.connect(self._on_loading_progress)
    
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
        # Update overlay state.
        self.overlay.set_state(state)
        
        # Update status text on overlay and tray.
        status_text = {
            AppState.LOADING: "Loading...",
            AppState.STANDBY: "Ready",
            AppState.LISTENING: "Listening...",
            AppState.TRANSCRIBING: "Transcribing..."
        }.get(state, "Unknown")
        
        self.overlay.set_status_text(status_text)
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
    
    def _on_loading_progress(self, phase: str):
        """
        Handle loading progress updates from model loader.
        
        Args:
            phase: Current loading phase ("vad", "whisper", "ready", "error").
        """
        messages = {
            "vad": "Loading VAD...",
            "whisper": "Loading Whisper...",
            "ready": "Ready",
            "error": "Error!"
        }
        
        status_text = messages.get(phase, "Loading...")
        self.overlay.set_status_text(status_text)
        self._update_status(f"Status: {status_text}")
    
    def _on_models_loaded(self, success: bool):
        """
        Handle model loading completion.
        
        Args:
            success: True if models loaded successfully.
        """
        self._models_loaded = success
        
        if success:
            # Transition to STANDBY state.
            self._set_state(AppState.STANDBY)
            self.overlay.set_status_text("Ready")
            self._update_status("Status: Ready")
            print(f"[{APP_NAME}] All models loaded. Ready!")
            self.tray_icon.showMessage(
                APP_NAME,
                f"Ready! Press {config.hotkey_toggle.upper()} to start dictating.",
                QSystemTrayIcon.MessageIcon.Information,
                3000
            )
        else:
            self.overlay.set_status_text("Error!")
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
        print(f"Model: {config.model_size}")
        print()
        
        # Connect audio chunk signal.
        signals.audio_chunk_ready.connect(self._process_audio_chunk)
        
        # Set initial LOADING state.
        self._set_state(AppState.LOADING)
        self._update_status("Status: Loading models...")
        
        # Start model loading in background.
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

