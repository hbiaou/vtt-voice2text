"""
settings_dialog.py - Settings GUI for VTT-voice2text.

Provides a dialog to configure:
- Hotkeys (toggle, panic)
- Model selection
- Output mode (type vs clipboard)
- Custom vocabulary management
- Audio settings (silence threshold, VAD)
"""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTabWidget, QWidget,
    QLabel, QLineEdit, QComboBox, QSlider, QCheckBox, QPushButton,
    QGroupBox, QFormLayout, QTableWidget, QTableWidgetItem,
    QHeaderView, QMessageBox, QSpinBox, QDoubleSpinBox,
    QRadioButton, QButtonGroup
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont, QKeySequence

from config import config, custom_vocab, AVAILABLE_MODELS, APP_NAME


class HotkeyEdit(QLineEdit):
    """
    Custom line edit for capturing hotkey input.
    """
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setReadOnly(True)
        self.setPlaceholderText("Press a key...")
    
    def keyPressEvent(self, event):
        """
        Capture key press and set as hotkey.
        """
        key = event.key()
        
        # Ignore modifier-only keys.
        if key in (Qt.Key_Control, Qt.Key_Shift, Qt.Key_Alt, Qt.Key_Meta):
            return
        
        # Convert key to string.
        key_name = QKeySequence(key).toString().lower()
        
        if key_name:
            self.setText(key_name)


class SettingsDialog(QDialog):
    """
    Settings dialog with tabbed interface.
    
    Tabs:
    - General: Hotkeys, output mode
    - Model: Whisper model selection
    - Vocabulary: Custom word corrections
    - Advanced: Audio settings
    """
    
    # Signal emitted when settings are saved and require restart.
    settings_changed = Signal(bool)  # True if model changed (needs restart).
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        self.setWindowTitle(f"{APP_NAME} Settings")
        self.setMinimumSize(500, 450)
        
        # Track if model was changed (requires restart).
        self._original_model = config.model_size
        
        self._setup_ui()
        self._load_current_settings()
    
    def _setup_ui(self):
        """
        Setup the dialog UI with tabs.
        """
        layout = QVBoxLayout(self)
        
        # Tab widget.
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)
        
        # Create tabs.
        self.tabs.addTab(self._create_general_tab(), "General")
        self.tabs.addTab(self._create_model_tab(), "Model")
        self.tabs.addTab(self._create_vocab_tab(), "Vocabulary")
        self.tabs.addTab(self._create_advanced_tab(), "Advanced")
        
        # Buttons.
        button_layout = QHBoxLayout()
        
        self.save_btn = QPushButton("Save")
        self.save_btn.clicked.connect(self._save_settings)
        
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.clicked.connect(self.reject)
        
        button_layout.addStretch()
        button_layout.addWidget(self.save_btn)
        button_layout.addWidget(self.cancel_btn)
        
        layout.addLayout(button_layout)
    
    def _create_general_tab(self) -> QWidget:
        """
        Create the General settings tab.
        """
        tab = QWidget()
        layout = QVBoxLayout(tab)
        
        # Hotkeys group.
        hotkeys_group = QGroupBox("Hotkeys")
        hotkeys_layout = QFormLayout(hotkeys_group)
        
        self.toggle_hotkey = HotkeyEdit()
        hotkeys_layout.addRow("Toggle Recording:", self.toggle_hotkey)
        
        self.panic_hotkey = HotkeyEdit()
        hotkeys_layout.addRow("Panic Stop:", self.panic_hotkey)
        
        layout.addWidget(hotkeys_group)
        
        # Output mode group.
        output_group = QGroupBox("Output Mode")
        output_layout = QVBoxLayout(output_group)
        
        self.output_type_radio = QRadioButton("Type text (simulate keyboard)")
        self.output_clipboard_radio = QRadioButton("Copy to clipboard")
        
        output_layout.addWidget(self.output_type_radio)
        output_layout.addWidget(self.output_clipboard_radio)
        
        # Description labels.
        type_desc = QLabel("Text is typed character by character into the active window.")
        type_desc.setStyleSheet("color: gray; font-size: 11px; margin-left: 20px;")
        output_layout.addWidget(type_desc)
        
        clipboard_desc = QLabel("Text is copied to clipboard. Paste with Ctrl+V.")
        clipboard_desc.setStyleSheet("color: gray; font-size: 11px; margin-left: 20px;")
        output_layout.addWidget(clipboard_desc)
        
        layout.addWidget(output_group)
        
        layout.addStretch()
        return tab
    
    def _create_model_tab(self) -> QWidget:
        """
        Create the Model settings tab.
        """
        tab = QWidget()
        layout = QVBoxLayout(tab)
        
        # Model selection group.
        model_group = QGroupBox("Whisper Model")
        model_layout = QVBoxLayout(model_group)
        
        model_label = QLabel("Select the speech recognition model:")
        model_layout.addWidget(model_label)
        
        self.model_combo = QComboBox()
        for model_id, model_name in AVAILABLE_MODELS:
            self.model_combo.addItem(model_name, model_id)
        
        model_layout.addWidget(self.model_combo)
        
        # Model info.
        info_label = QLabel(
            "<b>Tips:</b><br>"
            "• <b>Multilingual</b> models handle names and accents better<br>"
            "• <b>Larger</b> models are more accurate but slower<br>"
            "• <b>English-only</b> models are faster for English text<br>"
            "• Changing the model requires restarting the app"
        )
        info_label.setStyleSheet("color: gray; font-size: 11px;")
        info_label.setWordWrap(True)
        model_layout.addWidget(info_label)
        
        layout.addWidget(model_group)
        
        # Device info.
        device_group = QGroupBox("Device")
        device_layout = QFormLayout(device_group)
        
        device_label = QLabel(config.device.upper())
        device_label.setStyleSheet("font-weight: bold;")
        device_layout.addRow("Current:", device_label)
        
        compute_label = QLabel(config.compute_type)
        device_layout.addRow("Compute Type:", compute_label)
        
        layout.addWidget(device_group)
        
        layout.addStretch()
        return tab
    
    def _create_vocab_tab(self) -> QWidget:
        """
        Create the Custom Vocabulary tab.
        """
        tab = QWidget()
        layout = QVBoxLayout(tab)
        
        # Enable/disable checkbox.
        self.vocab_enabled = QCheckBox("Enable custom vocabulary corrections")
        layout.addWidget(self.vocab_enabled)
        
        # Description.
        desc = QLabel(
            "Add word corrections for commonly misrecognized words.\n"
            "Example: If 'Noref' is transcribed instead of 'Honoré', add it below."
        )
        desc.setStyleSheet("color: gray; font-size: 11px;")
        desc.setWordWrap(True)
        layout.addWidget(desc)
        
        # Vocabulary table.
        self.vocab_table = QTableWidget()
        self.vocab_table.setColumnCount(2)
        self.vocab_table.setHorizontalHeaderLabels(["Misheard", "Correct"])
        self.vocab_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.vocab_table.setSelectionBehavior(QTableWidget.SelectRows)
        layout.addWidget(self.vocab_table)
        
        # Add/Remove buttons.
        btn_layout = QHBoxLayout()
        
        self.add_vocab_btn = QPushButton("Add")
        self.add_vocab_btn.clicked.connect(self._add_vocab_row)
        btn_layout.addWidget(self.add_vocab_btn)
        
        self.remove_vocab_btn = QPushButton("Remove Selected")
        self.remove_vocab_btn.clicked.connect(self._remove_vocab_row)
        btn_layout.addWidget(self.remove_vocab_btn)
        
        btn_layout.addStretch()
        layout.addLayout(btn_layout)
        
        return tab
    
    def _create_advanced_tab(self) -> QWidget:
        """
        Create the Advanced settings tab.
        """
        tab = QWidget()
        layout = QVBoxLayout(tab)
        
        # Audio settings group.
        audio_group = QGroupBox("Audio Settings")
        audio_layout = QFormLayout(audio_group)
        
        # Silence threshold.
        self.silence_spin = QDoubleSpinBox()
        self.silence_spin.setRange(0.3, 3.0)
        self.silence_spin.setSingleStep(0.1)
        self.silence_spin.setSuffix(" seconds")
        audio_layout.addRow("Silence Threshold:", self.silence_spin)
        
        silence_desc = QLabel("Pause duration before audio is sent for transcription.")
        silence_desc.setStyleSheet("color: gray; font-size: 10px;")
        audio_layout.addRow("", silence_desc)
        
        # VAD threshold.
        self.vad_spin = QDoubleSpinBox()
        self.vad_spin.setRange(0.1, 0.9)
        self.vad_spin.setSingleStep(0.05)
        audio_layout.addRow("VAD Sensitivity:", self.vad_spin)
        
        vad_desc = QLabel("Voice Activity Detection threshold. Lower = more sensitive.")
        vad_desc.setStyleSheet("color: gray; font-size: 10px;")
        audio_layout.addRow("", vad_desc)
        
        layout.addWidget(audio_group)
        
        # Typing settings group.
        typing_group = QGroupBox("Typing Settings")
        typing_layout = QFormLayout(typing_group)
        
        self.typing_delay_spin = QSpinBox()
        self.typing_delay_spin.setRange(0, 50)
        self.typing_delay_spin.setSuffix(" ms")
        typing_layout.addRow("Keystroke Delay:", self.typing_delay_spin)
        
        typing_desc = QLabel("Delay between keystrokes. Increase if characters are dropped.")
        typing_desc.setStyleSheet("color: gray; font-size: 10px;")
        typing_layout.addRow("", typing_desc)
        
        layout.addWidget(typing_group)
        
        layout.addStretch()
        return tab
    
    def _load_current_settings(self):
        """
        Load current settings into the UI.
        """
        # General tab.
        self.toggle_hotkey.setText(config.hotkey_toggle)
        self.panic_hotkey.setText(config.hotkey_panic)
        
        if config.output_mode == "clipboard":
            self.output_clipboard_radio.setChecked(True)
        else:
            self.output_type_radio.setChecked(True)
        
        # Model tab.
        for i in range(self.model_combo.count()):
            if self.model_combo.itemData(i) == config.model_size:
                self.model_combo.setCurrentIndex(i)
                break
        
        # Vocabulary tab.
        self.vocab_enabled.setChecked(config.use_custom_vocab)
        self._load_vocab_table()
        
        # Advanced tab.
        self.silence_spin.setValue(config.silence_threshold_sec)
        self.vad_spin.setValue(config.vad_threshold)
        self.typing_delay_spin.setValue(config.typing_delay_ms)
    
    def _load_vocab_table(self):
        """
        Load vocabulary corrections into the table.
        """
        self.vocab_table.setRowCount(0)
        
        for wrong, correct in custom_vocab.get_all().items():
            row = self.vocab_table.rowCount()
            self.vocab_table.insertRow(row)
            self.vocab_table.setItem(row, 0, QTableWidgetItem(wrong))
            self.vocab_table.setItem(row, 1, QTableWidgetItem(correct))
    
    def _add_vocab_row(self):
        """
        Add a new empty row to the vocabulary table.
        """
        row = self.vocab_table.rowCount()
        self.vocab_table.insertRow(row)
        self.vocab_table.setItem(row, 0, QTableWidgetItem(""))
        self.vocab_table.setItem(row, 1, QTableWidgetItem(""))
        self.vocab_table.setCurrentCell(row, 0)
        self.vocab_table.editItem(self.vocab_table.item(row, 0))
    
    def _remove_vocab_row(self):
        """
        Remove selected rows from the vocabulary table.
        """
        selected_rows = set()
        for item in self.vocab_table.selectedItems():
            selected_rows.add(item.row())
        
        for row in sorted(selected_rows, reverse=True):
            self.vocab_table.removeRow(row)
    
    def _save_settings(self):
        """
        Save all settings and close dialog.
        """
        # Check if model changed (requires restart).
        new_model = self.model_combo.currentData()
        model_changed = new_model != self._original_model
        
        # Save to config.
        config.hotkey_toggle = self.toggle_hotkey.text() or "f8"
        config.hotkey_panic = self.panic_hotkey.text() or "f9"
        config.model_size = new_model
        config.output_mode = "clipboard" if self.output_clipboard_radio.isChecked() else "type"
        config.use_custom_vocab = self.vocab_enabled.isChecked()
        config.silence_threshold_sec = self.silence_spin.value()
        config.vad_threshold = self.vad_spin.value()
        config.typing_delay_ms = self.typing_delay_spin.value()
        
        # Save config to file.
        config.save()
        
        # Save vocabulary.
        self._save_vocabulary()
        
        # Notify about model change.
        if model_changed:
            QMessageBox.information(
                self,
                "Restart Required",
                "The model has been changed. Please restart the application "
                "for the new model to take effect."
            )
        
        # Emit signal and close.
        self.settings_changed.emit(model_changed)
        self.accept()
    
    def _save_vocabulary(self):
        """
        Save vocabulary table to custom_vocab.
        """
        # Clear existing and rebuild from table.
        custom_vocab.corrections.clear()
        
        for row in range(self.vocab_table.rowCount()):
            wrong_item = self.vocab_table.item(row, 0)
            correct_item = self.vocab_table.item(row, 1)
            
            if wrong_item and correct_item:
                wrong = wrong_item.text().strip()
                correct = correct_item.text().strip()
                
                if wrong and correct:
                    custom_vocab.corrections[wrong.lower()] = correct
        
        custom_vocab.save()

