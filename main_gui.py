import sys
import os
import csv
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                            QHBoxLayout, QStatusBar, QPushButton, QFileDialog)
from PyQt5.QtCore import Qt, QTimer
from datetime import datetime
import pyqtgraph as pg

from controllers.temp_controller import TempController
from controllers.thp_controller import THPController
from controllers.motor_controller import MotorController

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Temp & THP Live Monitor")
        # Central layout
        central = QWidget()
        main_layout = QVBoxLayout()
        central.setLayout(main_layout)
        self.setCentralWidget(central)

        # Status bar - create this before controllers
        self.status = QStatusBar()
        self.setStatusBar(self.status)

        # Controllers
        ctrl_layout = QHBoxLayout()
        
        # Temperature controller
        self.temp_ctrl = TempController(parent=self)
        self.temp_ctrl.port = "COM13"  # Set specific port
        self.temp_ctrl.connect_controller()  # Auto-connect at startup
        ctrl_layout.addWidget(self.temp_ctrl.widget)
        
        # Motor control buttons in the middle
        motor_layout = QVBoxLayout()
        motor_layout.setSpacing(10)
        
        # Add motor controller
        self.motor_ctrl = MotorController(parent=self)
        self.motor_ctrl.status_signal.connect(self.status.showMessage)
        # Store preferred port for motor
        self.motor_ctrl.preferred_port = "COM5"
        motor_layout.addWidget(self.motor_ctrl.groupbox)
        
        # Add big Open/Close buttons
        self.open_btn = QPushButton("OPEN")
        self.open_btn.setMinimumHeight(60)
        self.open_btn.setStyleSheet("font-size: 18px; font-weight: bold; background-color: #4CAF50; color: white;")
        self.open_btn.clicked.connect(self.open_motor)
        motor_layout.addWidget(self.open_btn)
        
        self.close_btn = QPushButton("CLOSE")
        self.close_btn.setMinimumHeight(60)
        self.close_btn.setStyleSheet("font-size: 18px; font-weight: bold; background-color: #f44336; color: white;")
        self.close_btn.clicked.connect(self.close_motor)
        motor_layout.addWidget(self.close_btn)
        
        ctrl_layout.addLayout(motor_layout)
        
        # THP controller
        self.thp_ctrl = THPController(port="COM10", parent=self)
        ctrl_layout.addWidget(self.thp_ctrl.groupbox)
        
        # Wire status signals
        self.temp_ctrl.status_signal.connect(self.status.showMessage)
        self.thp_ctrl.status_signal.connect(self.status.showMessage)
        
        main_layout.addLayout(ctrl_layout)

        # Create date axis items for all plots
        date_axis_tc = pg.DateAxisItem(orientation='bottom')
        date_axis_temp = pg.DateAxisItem(orientation='bottom')
        date_axis_hum = pg.DateAxisItem(orientation='bottom')
        date_axis_pres = pg.DateAxisItem(orientation='bottom')

        # Plots
        # Temperature Controller plot - only show current temp
        self.tc_plot = pg.PlotWidget(title="Temperature Controller", axisItems={'bottom': date_axis_tc})
        self.tc_plot.addLegend()
        self.tc_plot.setLabel('left', 'Temperature', units='°C')
        self.temp_curve = self.tc_plot.plot(name="Temp", pen=pg.mkPen('r', width=2))
        main_layout.addWidget(self.tc_plot)

        # THP Sensor - create a GraphicsLayoutWidget to hold 3 separate plots
        self.thp_layout = pg.GraphicsLayoutWidget()
        main_layout.addWidget(self.thp_layout)

        # Create three separate plots for THP with date axes
        # For GraphicsLayoutWidget, we need to use addPlot instead of PlotWidget
        self.thp_temp_plot = self.thp_layout.addPlot(row=0, col=0, title="Temperature (°C)", axisItems={'bottom': date_axis_temp})
        self.thp_temp_plot.addLegend()
        self.thp_temp_plot.setLabel('left', 'Temperature', units='°C')
        self.thp_temp_curve = self.thp_temp_plot.plot(name="Temp", pen=pg.mkPen('r', width=2))

        self.hum_plot = self.thp_layout.addPlot(row=1, col=0, title="Humidity (%)", axisItems={'bottom': date_axis_hum})
        self.hum_plot.addLegend()
        self.hum_plot.setLabel('left', 'Humidity', units='%')
        self.hum_curve = self.hum_plot.plot(name="Humidity", pen=pg.mkPen('b', width=2))

        self.pres_plot = self.thp_layout.addPlot(row=2, col=0, title="Pressure (hPa)", axisItems={'bottom': date_axis_pres})
        self.pres_plot.addLegend()
        self.pres_plot.setLabel('left', 'Pressure', units='hPa')
        self.pres_curve = self.pres_plot.plot(name="Pressure", pen=pg.mkPen('g', width=2))

        # Link X axes of all THP plots so they zoom/pan together
        self.hum_plot.setXLink(self.thp_temp_plot)
        self.pres_plot.setXLink(self.thp_temp_plot)

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
        
    def open_motor(self):
        """Move motor to 90 degrees (open position)"""
        if not self.motor_ctrl.is_connected():
            self.status.showMessage("Motor not connected")
            return
        
        # Set angle to exactly 90 degrees and move
        self.motor_ctrl.angle_input.setText("2250")
        self.motor_ctrl.move()
        self.status.showMessage("Opening - Moving to 90°")
        
    def close_motor(self):
        """Move motor to 0 degrees (closed position)"""
        if not self.motor_ctrl.is_connected():
            self.status.showMessage("Motor not connected")
            return
        
        # Set angle to exactly 0 degrees and move
        self.motor_ctrl.angle_input.setText("0")
        self.motor_ctrl.move()
        self.status.showMessage("Closing - Moving to 0°")

    def update_data(self):
        now = datetime.now()
        timestamp = now.timestamp()  # Unix timestamp in seconds
        
        # TC values
        t = self.temp_ctrl.current_temp
        sp = self.temp_ctrl.setpoint
        # THP values
        thp = self.thp_ctrl.get_latest()
        thpt = thp["temperature"]
        hum = thp["humidity"]
        pres = thp["pressure"]

        # store
        self.timestamps.append(timestamp)
        self.tc_temps.append(t)
        self.tc_setpts.append(sp)
        self.thp_temps.append(thpt)
        self.hums.append(hum)
        self.pressures.append(pres)

        # Keep only the last 100 points to prevent memory issues
        if len(self.timestamps) > 100:
            self.timestamps = self.timestamps[-100:]
            self.tc_temps = self.tc_temps[-100:]
            self.tc_setpts = self.tc_setpts[-100:]
            self.thp_temps = self.thp_temps[-100:]
            self.hums = self.hums[-100:]
            self.pressures = self.pressures[-100:]

        # update plots with timestamps on x-axis
        self.temp_curve.setData(self.timestamps, self.tc_temps)
        
        # Update the three separate THP plots
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
