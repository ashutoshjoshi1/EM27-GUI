from PyQt5.QtCore import QObject, pyqtSignal, QTimer
from PyQt5.QtWidgets import QGroupBox, QGridLayout, QLabel, QLineEdit, QPushButton

from drivers.tc36_25_driver import TC36_25

class TempController(QObject):
    status_signal = pyqtSignal(str)
    data_signal = pyqtSignal(float)  # emits current temperature each update

    def __init__(self, parent=None):
        super().__init__(parent)
        # Group box for Temperature Controller
        self.widget = QGroupBox("Temperature Controller")
        layout = QGridLayout()

        layout.addWidget(QLabel("Setpoint (°C):"), 0, 0)
        self.set_input = QLineEdit()
        self.set_input.setFixedWidth(60)
        layout.addWidget(self.set_input, 0, 1)
        self.set_btn = QPushButton("Set")
        self.set_btn.setEnabled(False)
        self.set_btn.clicked.connect(self.set_temperature)
        layout.addWidget(self.set_btn, 0, 2)

        layout.addWidget(QLabel("Current (°C):"), 1, 0)
        self.cur_lbl = QLabel("-- °C")
        layout.addWidget(self.cur_lbl, 1, 1)

        self.widget.setLayout(layout)

        # Initialize temperature controller hardware
        port = None
        if parent is not None and hasattr(parent, 'config'):
            port = parent.config.get("temp_controller")
        try:
            self.tc = TC36_25(port if port else "COM16")
        except Exception as e:
            self.status_signal.emit(f"TempController connection failed: {e}")
            return

        # Once connected, enable computer control and turn on power
        try:
            self.tc.enable_computer_setpoint()
            self.tc.power(True)
        except Exception as e:
            self.status_signal.emit(f"TC init failed: {e}")

        # Start periodic update
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._upd)
        self.timer.start(1000)
        self.set_btn.setEnabled(True)

    def set_temperature(self):
        try:
            t = float(self.set_input.text().strip())
        except Exception:
            self.status_signal.emit("Invalid setpoint")
            return
        try:
            self.tc.set_setpoint(t)
            self.status_signal.emit(f"SP={t:.1f}°C")
        except Exception as e:
            self.status_signal.emit(f"Set fail: {e}")

    def _upd(self):
        try:
            current = self.tc.get_temperature()
            self.cur_lbl.setText(f"{current:.2f} °C")
            self.data_signal.emit(current)
        except Exception as e:
            self.cur_lbl.setText("-- °C")
            self.status_signal.emit(f"Read err: {e}")

    @property
    def current_temp(self):
        try:
            return float(self.cur_lbl.text().split()[0])
        except:
            return 0.0

    @property
    def setpoint(self):
        try:
            return float(self.set_input.text().strip())
        except:
            return 0.0

    def is_connected(self):
        return True
