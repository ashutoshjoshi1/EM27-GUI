from PyQt5.QtCore import QObject, QTimer, pyqtSignal
from PyQt5.QtWidgets import QGroupBox, QLabel, QVBoxLayout

from drivers.thp_sensor import read_thp_sensor_data

class THPController(QObject):
    status_signal = pyqtSignal(str)
    data_signal = pyqtSignal(dict)  # emits full sensor dict on each update

    def __init__(self, port, parent=None):
        super().__init__(parent)
        self.port = port
        self.groupbox = QGroupBox("THP Sensor")
        layout = QVBoxLayout()

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

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._update_data)
        self.timer.start(3000)

    def _update_data(self):
        data = read_thp_sensor_data(self.port)
        if data:
            self.latest = data
            self.temp_lbl.setText(f"Temp: {data['temperature']:.1f} °C")
            self.hum_lbl.setText(f"Humidity: {data['humidity']:.1f} %")
            self.pres_lbl.setText(f"Pressure: {data['pressure']:.1f} hPa")
            self.data_signal.emit(data)
        else:
            self.status_signal.emit("THP sensor read failed.")

    def get_latest(self):
        return self.latest

    def is_connected(self):
        return self.latest["temperature"] != 0.0
