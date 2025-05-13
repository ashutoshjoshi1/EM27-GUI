import sys, csv
from datetime import datetime
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QFileDialog, QStatusBar
)
from PyQt5.QtCore import QTimer
import pyqtgraph as pg

from temp_controller import TempController
from thp_controller import THPController

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Temp & THP Live Monitor")
        # Central layout
        central = QWidget()
        main_layout = QVBoxLayout()
        central.setLayout(main_layout)
        self.setCentralWidget(central)

        # Controllers
        ctrl_layout = QHBoxLayout()
        self.temp_ctrl = TempController(parent=self)
        self.thp_ctrl  = THPController(port="COM17", parent=self)
        # wire status
        self.temp_ctrl.status_signal.connect(self.status.showMessage)
        self.thp_ctrl.status_signal.connect(self.status.showMessage)
        ctrl_layout.addWidget(self.temp_ctrl.widget)
        ctrl_layout.addWidget(self.thp_ctrl.groupbox)
        main_layout.addLayout(ctrl_layout)

        # Plots
        self.tc_plot = pg.PlotWidget(title="Temperature Controller")
        self.tc_plot.addLegend()
        self.temp_curve  = self.tc_plot.plot(name="Temp")
        self.setpt_curve = self.tc_plot.plot(name="Setpoint")
        main_layout.addWidget(self.tc_plot)

        self.thp_plot = pg.PlotWidget(title="THP Sensor")
        self.thp_plot.addLegend()
        self.thp_temp_curve = self.thp_plot.plot(name="Temp")
        self.hum_curve      = self.thp_plot.plot(name="Humidity")
        self.pres_curve     = self.thp_plot.plot(name="Pressure")
        main_layout.addWidget(self.thp_plot)

        # Logging controls
        log_layout = QHBoxLayout()
        self.start_btn = QPushButton("Start Logging")
        self.start_btn.clicked.connect(self.start_logging)
        log_layout.addWidget(self.start_btn)
        self.stop_btn = QPushButton("Stop Logging")
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self.stop_logging)
        log_layout.addWidget(self.stop_btn)
        main_layout.addLayout(log_layout)

        # Status bar
        self.status = QStatusBar()
        self.setStatusBar(self.status)

        # Data storage
        self.timestamps = []
        self.tc_temps   = []
        self.tc_setpts  = []
        self.thp_temps  = []
        self.hums       = []
        self.pressures  = []
        self.logging    = False
        self.csv_file   = None

        # Update timer
        self.update_timer = QTimer(self)
        self.update_timer.timeout.connect(self.update_data)
        self.update_timer.start(1000)

    def update_data(self):
        now = datetime.now()
        # TC values
        t  = self.temp_ctrl.current_temp
        sp = self.temp_ctrl.setpoint
        # THP values
        thp = self.thp_ctrl.get_latest()
        thpt = thp["temperature"]
        hum  = thp["humidity"]
        pres = thp["pressure"]

        # store
        self.timestamps.append(now.timestamp())
        self.tc_temps.append(t)
        self.tc_setpts.append(sp)
        self.thp_temps.append(thpt)
        self.hums.append(hum)
        self.pressures.append(pres)

        # update plots
        self.temp_curve.setData(self.timestamps, self.tc_temps)
        self.setpt_curve.setData(self.timestamps, self.tc_setpts)
        self.thp_temp_curve.setData(self.timestamps, self.thp_temps)
        self.hum_curve.setData(self.timestamps, self.hums)
        self.pres_curve.setData(self.timestamps, self.pressures)

        # write log
        if self.logging and self.csv_file:
            self.csv_writer.writerow({
                "timestamp": now.isoformat(),
                "tc_temp": t,
                "tc_setpoint": sp,
                "thp_temp": thpt,
                "humidity": hum,
                "pressure": pres
            })
            self.csv_file.flush()

    def start_logging(self):
        fname, _ = QFileDialog.getSaveFileName(self, "Save Log As", "", "CSV Files (*.csv)")
        if not fname:
            return
        self.csv_file = open(fname, "w", newline="")
        self.csv_writer = csv.DictWriter(
            self.csv_file,
            fieldnames=["timestamp","tc_temp","tc_setpoint","thp_temp","humidity","pressure"]
        )
        self.csv_writer.writeheader()
        self.logging    = True
        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.status.showMessage(f"Logging → {fname}")

    def stop_logging(self):
        self.logging = False
        if self.csv_file:
            self.csv_file.close()
            self.csv_file = None
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.status.showMessage("Logging stopped")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    win = MainWindow()
    win.resize(900, 600)
    win.show()
    sys.exit(app.exec_())
