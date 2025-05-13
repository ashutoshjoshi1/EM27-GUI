# controllers/motor_controller.py

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
        port = self.port_combo.currentText().strip()
        baud = int(self.baud_combo.currentText())
        if not port:
            self.status_signal.emit("Select a COM port first.")
            self.connect_btn.setEnabled(True)
            return

        try:
            ser = serial.Serial(port, baudrate=baud, timeout=0.5)
            # RS-485 mode for DE/RE toggling
            if hasattr(ser, 'rs485_mode'):
                ser.rs485_mode = RS485Settings(
                    rts_level_for_tx=True,
                    rts_level_for_rx=False,
                    delay_before_tx=0.001,
                    delay_before_rx=0.001
                )
            else:
                ser.setRTS(False)

            self._driver = MotorDriver(ser)
            self._connected = True
            self.move_btn.setEnabled(True)
            self.status_signal.emit(f"✔ Connected on {port} @ {baud} baud")
        except Exception as e:
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
