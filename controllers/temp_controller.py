from PyQt5.QtCore import QObject, pyqtSignal, QTimer
from PyQt5.QtWidgets import QGroupBox, QGridLayout, QLabel, QLineEdit, QPushButton, QHBoxLayout
import serial.tools.list_ports

from drivers.tc36_25_driver import TC36_25

class TempController(QObject):
    status_signal = pyqtSignal(str)
    data_signal = pyqtSignal(float)  # emits current temperature each update

    def __init__(self, parent=None):
        super().__init__(parent)
        self.tc = None
        self.connected = False
        
        # Group box for Temperature Controller
        self.widget = QGroupBox("Temperature Controller")
        self.widget.setStyleSheet("""
            QGroupBox { color: white; }      /* title of the box */
            QLabel    { color: white; }      /* all labels */
            QLineEdit { color: white; }      /* the input text */
            QPushButton { color: white; }    /* your buttons */
        """)
        layout = QGridLayout()

        # Add connect button
        self.connect_btn = QPushButton("Connect")
        self.connect_btn.clicked.connect(self.connect_controller)
        layout.addWidget(self.connect_btn, 0, 0, 1, 3)

        layout.addWidget(QLabel("Setpoint (°C):"), 1, 0)
        self.set_input = QLineEdit()
        self.set_input.setFixedWidth(60)
        layout.addWidget(self.set_input, 1, 1)
        self.set_btn = QPushButton("Set")
        self.set_btn.setEnabled(False)
        self.set_btn.clicked.connect(self.set_temperature)
        layout.addWidget(self.set_btn, 1, 2)

        layout.addWidget(QLabel("Current (°C):"), 2, 0)
        self.cur_lbl = QLabel("-- °C")
        layout.addWidget(self.cur_lbl, 2, 1)

        self.widget.setLayout(layout)

        # Get port from config if available
        self.port = None
        if parent is not None and hasattr(parent, 'config'):
            self.port = parent.config.get("temp_controller")
            
        # Start with auto-connect if port is specified
        if self.port:
            self.connect_controller()

    def connect_controller(self):
        if self.connected:
            # Disconnect
            if self.tc:
                try:
                    self.tc.close()
                except:
                    pass
                self.tc = None
            
            if hasattr(self, 'timer'):
                self.timer.stop()
                
            self.connected = False
            self.set_btn.setEnabled(False)
            self.connect_btn.setText("Connect")
            self.status_signal.emit("Temperature controller disconnected")
            return

        # Auto-detect port if not specified
        if not self.port:
            self.port = self._find_tc_port()
            if not self.port:
                self.status_signal.emit("Temperature controller not found")
                return

        # Try to connect
        try:
            self.tc = TC36_25(self.port)
            # Test connection
            self.tc.get_temperature()
            
            # Once connected, enable computer control and turn on power
            self.tc.enable_computer_setpoint()
            self.tc.power(True)
            
            # Start periodic update
            if not hasattr(self, 'timer'):
                self.timer = QTimer(self)
                self.timer.timeout.connect(self._upd)
            self.timer.start(1000)
            
            self.connected = True
            self.set_btn.setEnabled(True)
            self.connect_btn.setText("Disconnect")
            self.status_signal.emit(f"Temperature controller connected on {self.port}")
            self._upd()  # Update immediately
            
        except Exception as e:
            self.status_signal.emit(f"TempController connection failed: {e}")
            if self.tc:
                try:
                    self.tc.close()
                except:
                    pass
                self.tc = None

    def _find_tc_port(self):
        """Try to auto-detect the temperature controller port"""
        ports = list(serial.tools.list_ports.comports())
        for port in ports:
            try:
                test_tc = TC36_25(port.device)
                test_tc.get_temperature()  # Test if we can read temperature
                test_tc.close()
                return port.device
            except:
                continue
        return None

    def set_temperature(self):
        if not self.connected or not self.tc:
            self.status_signal.emit("Not connected to temperature controller")
            return
            
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
        if not self.connected or not self.tc:
            return
            
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
        return self.connected
