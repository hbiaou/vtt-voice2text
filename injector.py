"""
injector.py - Text injection via simulated keyboard input.

This module types transcribed text into the currently active window
using pynput to simulate keyboard events. Works with any application
(Notepad, Chrome, VS Code, etc.).
"""

import time
import threading
from typing import Optional
from pynput.keyboard import Controller, Key

from config import config, APP_NAME


class TextInjector:
    """
    Handles typing text into the active window via keyboard simulation.
    
    Uses pynput to simulate keypresses. Includes an abort mechanism
    to stop mid-injection (panic button functionality).
    
    Attributes:
        is_typing: Flag indicating if currently injecting text.
        abort_flag: Flag to signal immediate stop of injection.
    """
    
    def __init__(self):
        """
        Initialize the TextInjector.
        """
        # Keyboard controller for simulating key presses.
        self._keyboard = Controller()
        
        # State flags.
        self.is_typing = False
        self.abort_flag = False
        
        # Typing delay from config (milliseconds).
        self._delay_sec = config.typing_delay_ms / 1000.0
        
        # Thread safety.
        self._lock = threading.Lock()
    
    def inject(self, text: str, add_trailing_space: bool = True) -> bool:
        """
        Type text into the currently active window.
        
        Characters are typed one at a time with a small delay to avoid
        dropped keystrokes. Automatically adds a trailing space.
        
        Args:
            text: The text to type.
            add_trailing_space: If True, add a space after the text.
        
        Returns:
            True if injection completed, False if aborted.
        """
        if not text:
            return True
        
        # Check if already typing (prevent concurrent injections).
        with self._lock:
            if self.is_typing:
                print(f"[{APP_NAME}] Already typing, skipping injection.")
                return False
            self.is_typing = True
            self.abort_flag = False
        
        try:
            # Clean up text - remove extra whitespace.
            text = text.strip()
            
            if not text:
                return True
            
            # Add trailing space if requested.
            if add_trailing_space:
                text = text + " "
            
            print(f"[{APP_NAME}] Injecting text: \"{text.strip()}\"")
            
            # Type each character with a small delay.
            for char in text:
                # Check abort flag before each character.
                if self.abort_flag:
                    print(f"[{APP_NAME}] Injection aborted!")
                    return False
                
                # Handle special characters.
                if char == '\n':
                    self._keyboard.press(Key.enter)
                    self._keyboard.release(Key.enter)
                elif char == '\t':
                    self._keyboard.press(Key.tab)
                    self._keyboard.release(Key.tab)
                else:
                    # Type regular character.
                    self._keyboard.type(char)
                
                # Small delay to avoid dropped keystrokes.
                if self._delay_sec > 0:
                    time.sleep(self._delay_sec)
            
            return True
            
        except Exception as e:
            print(f"[{APP_NAME}] Injection error: {e}")
            return False
            
        finally:
            # Always reset typing flag.
            with self._lock:
                self.is_typing = False
    
    def abort(self):
        """
        Abort any ongoing text injection immediately.
        
        This is the panic button functionality. Call this to stop
        mid-injection if something goes wrong.
        """
        self.abort_flag = True
        print(f"[{APP_NAME}] Abort signal sent!")
    
    def inject_fast(self, text: str, add_trailing_space: bool = True) -> bool:
        """
        Type text quickly using pynput's type() method.
        
        Faster than character-by-character, but may drop characters
        in some applications. Use for short text snippets.
        
        Args:
            text: The text to type.
            add_trailing_space: If True, add a space after the text.
        
        Returns:
            True if injection completed, False otherwise.
        """
        if not text:
            return True
        
        with self._lock:
            if self.is_typing:
                return False
            self.is_typing = True
            self.abort_flag = False
        
        try:
            text = text.strip()
            if add_trailing_space:
                text = text + " "
            
            # Use pynput's bulk type method.
            self._keyboard.type(text)
            return True
            
        except Exception as e:
            print(f"[{APP_NAME}] Fast injection error: {e}")
            return False
            
        finally:
            with self._lock:
                self.is_typing = False
    
    def type_special_key(self, key: Key):
        """
        Press a special key (Enter, Tab, Escape, etc.).
        
        Args:
            key: The pynput Key to press.
        """
        try:
            self._keyboard.press(key)
            self._keyboard.release(key)
        except Exception as e:
            print(f"[{APP_NAME}] Special key error: {e}")
    
    def clear_current_line(self):
        """
        Clear the current line by selecting all and deleting.
        Useful for correcting mistakes.
        """
        try:
            # Ctrl+A to select all in current field.
            with self._keyboard.pressed(Key.ctrl):
                self._keyboard.press('a')
                self._keyboard.release('a')
            
            # Small delay.
            time.sleep(0.05)
            
            # Delete selection.
            self._keyboard.press(Key.delete)
            self._keyboard.release(Key.delete)
            
        except Exception as e:
            print(f"[{APP_NAME}] Clear line error: {e}")


# Singleton instance for global access.
injector = TextInjector()


if __name__ == "__main__":
    # Test the injector module.
    print("Testing TextInjector module...")
    print("You have 3 seconds to click on a text field...")
    time.sleep(3)
    
    # Test basic injection.
    print("Injecting test text...")
    injector.inject("Hello, this is a test of VTT-voice2text!")
    
    print("\nTest complete!")

