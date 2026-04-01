import os
from datetime import datetime

from PyQt5.QtCore import QObject, QTimer, pyqtSignal
from PyQt5.QtWidgets import QGroupBox, QLabel, QVBoxLayout, QPushButton, QHBoxLayout
import serial.tools.list_ports

from drivers.thp_sensor import read_thp_sensor_data

THP_LOG_DIR = "logs/Data-csv"

class THPController(QObject):
    status_signal = pyqtSignal(str)
    data_signal = pyqtSignal(dict)  # emits full sensor dict on each update

    def __init__(self, port=None, parent=None):
        super().__init__(parent)
        self.port = port
        self.connected = False
        self.groupbox = QGroupBox("THP Sensor")
        self.groupbox.setStyleSheet("""
            QGroupBox   { color: white; }   /* the title */
            QLabel      { color: white; }
            QComboBox   { color: white; }
            QLineEdit   { color: white; }
            QPushButton { color: white; }
        """)
        layout = QVBoxLayout()

        # Add connect button
        btn_layout = QHBoxLayout()
        self.connect_btn = QPushButton("Connect")
        self.connect_btn.clicked.connect(self.connect_sensor)
        btn_layout.addWidget(self.connect_btn)
        layout.addLayout(btn_layout)

        self.temp_lbl = QLabel("Temp: -- °C")
        self.hum_lbl = QLabel("Humidity: -- %")
        self.pres_lbl = QLabel("Pressure: -- hPa")

        layout.addWidget(self.temp_lbl)
        layout.addWidget(self.hum_lbl)
        layout.addWidget(self.pres_lbl)

        self.groupbox.setLayout(layout)

        self.latest = {
            "temperature": 0.0,
            "humidity": 0.0,
            "pressure": 0.0
        }

        self._ac_ctrl = None
        self._temp_ctrl = None

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._update_data)
        # Only start timer if port was provided
        if self.port:
            self.connect_sensor()

    def connect_sensor(self):
        if self.connected:
            self.timer.stop()
            self.connected = False
            self.connect_btn.setText("Connect")
            self.status_signal.emit("THP sensor disconnected")
            return

        # Auto-detect port if not specified
        if not self.port:
            self.port = self._find_thp_port()
            if not self.port:
                self.status_signal.emit("THP sensor not found")
                return
        
        # Test connection
        test_data = read_thp_sensor_data(self.port)
        if test_data:
            self.connected = True
            self.connect_btn.setText("Disconnect")
            self.timer.start(3000)
            self.status_signal.emit(f"THP sensor connected on {self.port}")
            self._update_data()  # Update immediately
        else:
            self.status_signal.emit(f"Failed to connect to THP sensor on {self.port}")

    def _find_thp_port(self):
        """Try to auto-detect the THP sensor port"""
        ports = list(serial.tools.list_ports.comports())
        for port in ports:
            try:
                test_data = read_thp_sensor_data(port.device)
                if test_data and test_data.get('temperature') is not None:
                    return port.device
            except:
                continue
        return None

    def set_companion_controllers(self, ac_ctrl, temp_ctrl):
        """Register AC and Temperature controllers for joint CSV logging."""
        self._ac_ctrl = ac_ctrl
        self._temp_ctrl = temp_ctrl

    def _get_log_path(self):
        """Return absolute path to logs/THP-daily-readings/ directory."""
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        return os.path.join(root, THP_LOG_DIR)

    def _log_thp_reading(self, data):
        """Append THP + AC + TempController readings to the daily CSV file."""
        nan = float("nan")

        # AC Controller fields
        if self._ac_ctrl is not None and self._ac_ctrl.is_connected():
            ac_temp = self._ac_ctrl.latest_temp
            ac_heater, ac_cooling = self._ac_ctrl.range_slider.get_values()
        else:
            ac_temp = ac_heater = ac_cooling = nan

        # Temperature Controller fields
        if self._temp_ctrl is not None and self._temp_ctrl.is_connected():
            tc_setpoint = self._temp_ctrl.setpoint
            tc_current  = self._temp_ctrl.current_temp
        else:
            tc_setpoint = tc_current = nan

        def fmt(v):
            return "NaN" if v != v else f"{v:.2f}"  # NaN != NaN is True

        try:
            log_dir = self._get_log_path()
            os.makedirs(log_dir, exist_ok=True)
            filename = datetime.now().strftime("%b%d%Y") + ".csv"
            filepath = os.path.join(log_dir, filename)
            write_header = not os.path.exists(filepath)
            with open(filepath, "a") as f:
                if write_header:
                    f.write(
                        "timestamp,"
                        "temperature_C,humidity_percent,pressure_hPa,"
                        "ac_temperature_C,ac_heater_setpoint_C,ac_cooling_setpoint_C,"
                        "tc_setpoint_C,tc_current_C\n"
                    )
                ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                f.write(
                    f"{ts},"
                    f"{data['temperature']:.2f},{data['humidity']:.2f},{data['pressure']:.2f},"
                    f"{fmt(ac_temp)},{fmt(ac_heater)},{fmt(ac_cooling)},"
                    f"{fmt(tc_setpoint)},{fmt(tc_current)}\n"
                )
        except Exception as e:
            print(f"Failed to log THP reading: {e}")

    def _update_data(self):
        if not self.connected:
            return
            
        data = read_thp_sensor_data(self.port)
        if data:
            self.latest = data
            self.temp_lbl.setText(f"Temp: {data['temperature']:.1f} °C")
            self.hum_lbl.setText(f"Humidity: {data['humidity']:.1f} %")
            self.pres_lbl.setText(f"Pressure: {data['pressure']:.1f} hPa")
            self.data_signal.emit(data)
            self._log_thp_reading(data)
        else:
            self.status_signal.emit("THP sensor read failed.")

    def get_latest(self):
        return self.latest

    def is_connected(self):
        return self.connected
