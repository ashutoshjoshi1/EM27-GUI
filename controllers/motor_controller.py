# controllers/motor_controller.py

import platform
import serial
import time
from serial.rs485 import RS485Settings
from PyQt5.QtWidgets import (
    QGroupBox, QHBoxLayout, QLabel,
    QComboBox, QPushButton, QLineEdit
)
from PyQt5.QtCore    import QObject, pyqtSignal
from PyQt5.QtGui     import QIntValidator, QValidator
from drivers.motor   import MotorDriver

class StrictIntValidator(QIntValidator):
    """Validator that rejects any integer outside the given range outright."""
    def __init__(self, minimum, maximum, parent=None):
        super().__init__(parent)
        self.setRange(minimum, maximum)

    def validate(self, input_str, pos):
        # allow empty or just “-” while typing
        if input_str in ("", "-"):
            return (QValidator.Intermediate, input_str, pos)
        # must parse as integer
        try:
            val = int(input_str)
        except ValueError:
            return (QValidator.Invalid, input_str, pos)
        # only accept in range
        if self.bottom() <= val <= self.top():
            return (QValidator.Acceptable, input_str, pos)
        else:
            return (QValidator.Invalid, input_str, pos)


class MotorController(QObject):
    status_signal = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        
        self.preferred_port = None
        
        self.groupbox = QGroupBox("Motor Control")
        self.groupbox.setStyleSheet("""
            QGroupBox   { color: white; }
            QLabel      { color: white; }
            QComboBox   { color: white; }
            QLineEdit   { color: white; }
            QPushButton { color: white; }
        """)
        layout = QHBoxLayout(self.groupbox)

        # Port selector
        layout.addWidget(QLabel("Port:"))
        self.port_combo = QComboBox()
        ports = serial.tools.list_ports.comports()
        self.port_combo.addItems([p.device for p in ports])
        layout.addWidget(self.port_combo)

        # Baud selector
        layout.addWidget(QLabel("Baud:"))
        self.baud_combo = QComboBox()
        self.baud_combo.addItems(["9600","19200","38400","57600","115200"])
        layout.addWidget(self.baud_combo)

        # Connect button
        self.connect_btn = QPushButton("Connect")
        self.connect_btn.clicked.connect(self._on_connect)
        layout.addWidget(self.connect_btn)

        # Angle input & Move button
        self.angle_input = QLineEdit()
        self.angle_input.setPlaceholderText("Angle ° (−2100 … -30)")
        self.angle_input.setValidator(StrictIntValidator(-2100, -30, self))
        layout.addWidget(self.angle_input)

        self.move_btn = QPushButton("Move")
        self.move_btn.setEnabled(False)
        self.move_btn.clicked.connect(self._on_move)
        layout.addWidget(self.move_btn)

        # internal state
        self._driver = None
        self._connected = False
        self._last_move_time = 0
        self._min_move_interval = 0.5  # Minimum seconds between moves

    @property
    def driver(self):
        return self._driver
    
    def _paced_move(self, angle: int):
        """
        Send a move with proper inter-command spacing and alarm clear retry.
        This prevents alarm issues during continuous operation.
        """
        if not self._driver:
            return False, "Motor not initialized"
        
        # Prevent moves too close together
        current_time = time.time()
        time_since_last_move = current_time - self._last_move_time
        if time_since_last_move < self._min_move_interval:
            wait_time = self._min_move_interval - time_since_last_move
            time.sleep(wait_time)
        
        # Add inter-command gap to prevent alarm issues
        time.sleep(0.12)  # INTER_CMD_GAP_SEC from motor_cont.py
        
        # Drain serial buffers
        try:
            self._driver.ser.reset_input_buffer()
            self._driver.ser.reset_output_buffer()
        except Exception:
            pass
        
        # Send move command
        ok, msg = self._driver.move_to(angle)
        
        # If move failed, try clearing alarm and retry
        if not ok:
            try:
                if hasattr(self._driver, 'clear_alarm'):
                    self._driver.clear_alarm()
                    time.sleep(0.25)
                    # Drain again after alarm clear
                    try:
                        self._driver.ser.reset_input_buffer()
                        self._driver.ser.reset_output_buffer()
                    except Exception:
                        pass
                    time.sleep(0.12)
                    # Retry move
                    ok, msg = self._driver.move_to(angle)
            except Exception as e:
                print(f"Retry after alarm clear failed: {e}")
        
        # Record move time
        self._last_move_time = time.time()
        
        return ok, msg
    
    def _on_connect(self):
        self.connect_btn.setEnabled(False)
        port = self.preferred_port or self.port_combo.currentText().strip()
        baud = int(self.baud_combo.currentText())
        if not port:
            self.status_signal.emit("Select a COM port first.")
            self.connect_btn.setEnabled(True)
            return

        try:
            if self._driver and hasattr(self._driver, 'ser') and self._driver.ser.is_open:
                self._driver.ser.close()

            ser = serial.Serial(port, baudrate=baud, timeout=1.5)
            if not ser.is_open:
                ser.open()

            # Configure RS485 mode for automatic RTS control
            if hasattr(ser, 'rs485_mode'):
                ser.rs485_mode = RS485Settings(
                    rts_level_for_tx=True,
                    rts_level_for_rx=False,
                    loopback=False
                )
            else:
                ser.setRTS(False)

            ser.reset_input_buffer()
            ser.reset_output_buffer()

            self._driver = MotorDriver(ser)

            # Stop any existing motion and clear alarms before connecting
            if hasattr(self._driver, 'stop'):
                try:
                    self._driver.stop()
                    time.sleep(0.2)
                except Exception:
                    pass
            
            if hasattr(self._driver, 'clear_alarm'):
                try:
                    self._driver.clear_alarm()
                    time.sleep(0.2)
                except Exception:
                    pass

            # Drain any leftover responses from stop/clear_alarm
            try:
                ser.reset_input_buffer()
                ser.reset_output_buffer()
                time.sleep(0.1)
            except Exception:
                pass

            self._connected = True
            self.move_btn.setEnabled(True)
            self.status_signal.emit(f"✔ Connected on {port} @ {baud} baud")

        except Exception as e:
            if 'ser' in locals() and ser.is_open:
                ser.close()
            self._driver = None
            self._connected = False
            self.move_btn.setEnabled(False)
            self.status_signal.emit(f"✖ Connect failed: {e}")

        finally:
            self.connect_btn.setEnabled(True)

    def _on_move(self):
        if not self._connected:
            self.status_signal.emit("Motor not connected.")
            return
        try:
            angle = int(self.angle_input.text().strip())
        except ValueError:
            self.status_signal.emit("Enter a valid integer angle.")
            return

        ok, msg = self._paced_move(angle)
        self.status_signal.emit(msg)

    def is_connected(self):
        return self._connected

    def move(self):
        try:
            txt = self.angle_input.text().strip()
            if not txt:
                self.status_signal.emit("Enter an angle first")
                return False
            angle = int(txt)
            success, message = self._paced_move(angle)
            self.status_signal.emit(message)
            return success
        except ValueError:
            self.status_signal.emit("Invalid angle value")
            return False
        except Exception as e:
            self.status_signal.emit(f"Move error: {e}")
            return False

    def connect(self):
        if self._connected:
            return
        if self.preferred_port:
            idx = self.port_combo.findText(self.preferred_port)
            if idx >= 0:
                self.port_combo.setCurrentIndex(idx)
            self._on_connect()
