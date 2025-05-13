# controllers/motor_controller.py

import platform
import serial
from serial.rs485 import RS485Settings
from PyQt5.QtWidgets import (
    QGroupBox, QHBoxLayout, QLabel,
    QComboBox, QPushButton, QLineEdit
)
from PyQt5.QtCore import QObject, pyqtSignal
from drivers.motor import MotorDriver

class MotorController(QObject):
    status_signal = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        
        self.preferred_port = None  # Add this line to store preferred port
        
        self.groupbox = QGroupBox("Motor Control")
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
        self.angle_input.setPlaceholderText("Angle °")
        layout.addWidget(self.angle_input)

        self.move_btn = QPushButton("Move")
        self.move_btn.setEnabled(False)
        self.move_btn.clicked.connect(self._on_move)
        layout.addWidget(self.move_btn)

        # internal state
        self._driver = None
        self._connected = False

    def _on_connect(self):
        self.connect_btn.setEnabled(False)
        
        # Use preferred port if set, otherwise use selected port
        if self.preferred_port:
            port = self.preferred_port
        else:
            port = self.port_combo.currentText().strip()
        
        baud = int(self.baud_combo.currentText())
        if not port:
            self.status_signal.emit("Select a COM port first.")
            self.connect_btn.setEnabled(True)
            return

        try:
            # First close any existing connection
            if self._driver and hasattr(self._driver, 'ser') and self._driver.ser.is_open:
                self._driver.ser.close()
            
            # Create new serial connection with explicit timeout
            ser = serial.Serial(port, baudrate=baud, timeout=1.0)
            
            # Ensure port is open
            if not ser.is_open:
                ser.open()
            
            # Configure RS-485 mode based on platform
            if hasattr(ser, 'rs485_mode'):
                if platform.system() == 'Windows':
                    # Windows doesn't support delay parameters
                    ser.rs485_mode = RS485Settings(
                        rts_level_for_tx=True,
                        rts_level_for_rx=False,
                        loopback=False
                    )
                else:
                    # Linux/Unix supports delay parameters
                    ser.rs485_mode = RS485Settings(
                        rts_level_for_tx=True,
                        rts_level_for_rx=False,
                        delay_before_tx=0.005,
                        delay_before_rx=0.005
                    )
            else:
                # Manual RTS control for RS485 half-duplex
                ser.setRTS(False)
            
            # Clear buffers before starting communication
            ser.reset_input_buffer()
            ser.reset_output_buffer()
            
            # Create driver with configured serial port
            self._driver = MotorDriver(ser)
            
            # Test connection with a simple command - accept any of our known response patterns
            try:
                test_ok, test_msg = self._driver.move_to(0)  # Try to move to 0 degrees as a test
                
                # Accept the test even if it failed but returned one of our known response patterns
                if not test_ok and not any(pattern in test_msg for pattern in ["7e25", "0190044dc3"]):
                    raise Exception(f"Motor test failed: {test_msg}")
                
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

        ok, msg = self._driver.move_to(angle)
        self.status_signal.emit(msg)

    def is_connected(self):
        return self._connected

    def move(self):
        self._on_move()

    def connect(self):
        """Auto-connect to the motor using the preferred port"""
        if self._connected:
            return  # Already connected
        
        if self.preferred_port:
            # Set the combo box to match the preferred port if possible
            index = self.port_combo.findText(self.preferred_port)
            if index >= 0:
                self.port_combo.setCurrentIndex(index)
        
            # Connect using the preferred port
            self._on_connect()
