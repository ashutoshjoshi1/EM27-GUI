import sys
import os
import csv
import cv2
from datetime import datetime
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                            QHBoxLayout, QGridLayout, QStatusBar, QPushButton, 
                            QFileDialog, QLabel, QFrame, QSizePolicy, QGroupBox)
from PyQt5.QtCore import Qt, QTimer, pyqtSlot, QSize
from PyQt5.QtGui import QImage, QPixmap, QFont, QColor, QPalette
import pyqtgraph as pg
import numpy as np

from controllers.temp_controller import TempController
from controllers.thp_controller import THPController
from controllers.motor_controller import MotorController

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Temp & THP Live Monitor")
        self.setMinimumSize(1200, 800)  # Set minimum window size
        
        # Central layout
        central = QWidget()
        main_layout = QVBoxLayout()
        central.setLayout(main_layout)
        self.setCentralWidget(central)

        # Status bar - create this before controllers
        self.status = QStatusBar()
        self.setStatusBar(self.status)

        # Top section - Camera feed and controls
        top_layout = QHBoxLayout()
        
        # Camera feed on the left
        camera_group = QGroupBox("Camera Feed")
        camera_layout = QVBoxLayout()
        self.camera_label = QLabel("No Camera Feed")
        self.camera_label.setAlignment(Qt.AlignCenter)
        self.camera_label.setMinimumSize(480, 320)  # 4:3 aspect ratio
        self.camera_label.setStyleSheet("background-color: #222; color: white; border-radius: 5px;")
        camera_layout.addWidget(self.camera_label)
        
        # Camera controls
        camera_controls = QHBoxLayout()
        self.camera_connect_btn = QPushButton("Connect Camera")
        self.camera_connect_btn.clicked.connect(self.connect_camera)
        camera_controls.addWidget(self.camera_connect_btn)
        
        self.camera_disconnect_btn = QPushButton("Disconnect")
        self.camera_disconnect_btn.clicked.connect(self.disconnect_camera)
        self.camera_disconnect_btn.setEnabled(False)
        camera_controls.addWidget(self.camera_disconnect_btn)
        
        camera_layout.addLayout(camera_controls)
        camera_group.setLayout(camera_layout)
        top_layout.addWidget(camera_group)
        
        # Controllers section on the right
        ctrl_layout = QVBoxLayout()
        
        # Temperature controller
        self.temp_ctrl = TempController(parent=self)
        self.temp_ctrl.port = "COM2"  # Set specific port
        self.temp_ctrl.connect_controller()  # Auto-connect at startup
        ctrl_layout.addWidget(self.temp_ctrl.widget)
        
        # THP controller
        self.thp_ctrl = THPController(port="COM7", parent=self)
        ctrl_layout.addWidget(self.thp_ctrl.groupbox)
        
        top_layout.addLayout(ctrl_layout)
        main_layout.addLayout(top_layout)
        
        # Middle section - Motor controls
        motor_group = QGroupBox("Motor Control")
        motor_layout = QVBoxLayout()
        
        # Add motor controller
        self.motor_ctrl = MotorController(parent=self)
        self.motor_ctrl.status_signal.connect(self.status.showMessage)
        # Store preferred port for motor
        self.motor_ctrl.preferred_port = "COM8"
        motor_layout.addWidget(self.motor_ctrl.groupbox)
        
        # Add rain status indicator
        self.rain_indicator = QLabel("Rain Status: Unknown")
        self.rain_indicator.setStyleSheet("font-weight: bold; font-size: 16px;")
        motor_layout.addWidget(self.rain_indicator)
        
        # Add big Open/Close buttons in horizontal layout
        btn_layout = QHBoxLayout()
        
        self.open_btn = QPushButton("OPEN")
        self.open_btn.setMinimumHeight(60)
        self.open_btn.setStyleSheet("font-size: 18px; font-weight: bold; background-color: #4CAF50; color: white; border-radius: 5px;")
        self.open_btn.clicked.connect(self.open_motor)
        btn_layout.addWidget(self.open_btn)
        
        self.close_btn = QPushButton("CLOSE")
        self.close_btn.setMinimumHeight(60)
        self.close_btn.setStyleSheet("font-size: 18px; font-weight: bold; background-color: #f44336; color: white; border-radius: 5px;")
        self.close_btn.clicked.connect(self.close_motor)
        btn_layout.addWidget(self.close_btn)
        
        motor_layout.addLayout(btn_layout)
        motor_group.setLayout(motor_layout)
        main_layout.addWidget(motor_group)
        
        # Wire status signals
        self.temp_ctrl.status_signal.connect(self.status.showMessage)
        self.thp_ctrl.status_signal.connect(self.status.showMessage)
        
        # Current motor position tracking
        self.current_position = None  # None = unknown, 0 = closed, 90 = open

        # Create date axis items for all plots
        date_axis_tc = pg.DateAxisItem(orientation='bottom')
        date_axis_temp = pg.DateAxisItem(orientation='bottom')
        date_axis_hum = pg.DateAxisItem(orientation='bottom')
        date_axis_pres = pg.DateAxisItem(orientation='bottom')

        # Bottom section - Plots
        plots_group = QGroupBox("Sensor Data Plots")
        plots_layout = QVBoxLayout()
        
        # Temperature Controller plot - only show current temp
        self.tc_plot = pg.PlotWidget(title="Temperature Controller", axisItems={'bottom': date_axis_tc})
        self.tc_plot.addLegend()
        self.tc_plot.setLabel('left', 'Temperature', units='°C')
        self.temp_curve = self.tc_plot.plot(name="Temp", pen=pg.mkPen('r', width=2))
        plots_layout.addWidget(self.tc_plot)

        # THP Sensor - create a GraphicsLayoutWidget to hold 3 separate plots
        self.thp_layout = pg.GraphicsLayoutWidget()
        
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
        
        plots_layout.addWidget(self.thp_layout)
        plots_group.setLayout(plots_layout)
        main_layout.addWidget(plots_group)

        # Logging controls
        log_group = QGroupBox("Data Logging")
        log_layout = QHBoxLayout()
        
        self.start_btn = QPushButton("Start Logging")
        self.start_btn.setStyleSheet("font-weight: bold; background-color: #4CAF50; color: white; padding: 8px; border-radius: 4px;")
        self.start_btn.clicked.connect(self.start_logging)
        log_layout.addWidget(self.start_btn)
        
        self.stop_btn = QPushButton("Stop Logging")
        self.stop_btn.setStyleSheet("font-weight: bold; background-color: #f44336; color: white; padding: 8px; border-radius: 4px;")
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self.stop_logging)
        log_layout.addWidget(self.stop_btn)
        
        log_group.setLayout(log_layout)
        main_layout.addWidget(log_group)

        # Data storage
        self.timestamps = []
        self.tc_temps   = []
        self.tc_setpts  = []
        self.thp_temps  = []
        self.hums       = []
        self.pressures  = []
        self.logging    = False
        self.csv_file   = None
        
        # Camera properties
        self.camera_feed = None
        self.camera_connected = False

        # Update timer
        self.update_timer = QTimer(self)
        self.update_timer.timeout.connect(self.update_data)
        self.update_timer.start(1000)
        
        # Add rain check timer
        self.rain_timer = QTimer(self)
        self.rain_timer.timeout.connect(self.check_rain_status)
        self.rain_timer.start(10000)  # Check every 10 seconds
        
        # Apply some styling to the entire app
        self.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                border: 1px solid #555;
                border-radius: 5px;
                margin-top: 1ex;
                padding: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                subcontrol-position: top center;
                padding: 0 5px;
            }
        """)

    def connect_camera(self):
        """Connect to the camera and start the video feed"""
        try:
            self.camera_feed = cv2.VideoCapture(0)  # Use default camera (index 0)
            if not self.camera_feed.isOpened():
                self.status.showMessage("Failed to open camera")
                return
                
            # Start camera update timer (30 fps)
            self.camera_timer = QTimer(self)
            self.camera_timer.timeout.connect(self.update_camera_feed)
            self.camera_timer.start(33)  # ~30 fps
            
            # Update UI
            self.camera_connect_btn.setEnabled(False)
            self.camera_disconnect_btn.setEnabled(True)
            self.camera_connected = True
            self.status.showMessage("Camera connected")
        except Exception as e:
            self.status.showMessage(f"Camera error: {str(e)}")

    def disconnect_camera(self):
        """Disconnect from the camera"""
        if self.camera_feed is not None:
            self.camera_timer.stop()
            self.camera_feed.release()
            self.camera_feed = None
            self.camera_connected = False
            
            # Reset camera display
            self.camera_label.setText("No Camera Feed")
            self.camera_label.setPixmap(QPixmap())
            
            # Update UI
            self.camera_connect_btn.setEnabled(True)
            self.camera_disconnect_btn.setEnabled(False)
            self.status.showMessage("Camera disconnected")

    def update_camera_feed(self):
        """Update the camera feed display"""
        if self.camera_feed is None or not self.camera_connected:
            return
        
        ret, frame = self.camera_feed.read()
        if not ret:
            self.status.showMessage("Failed to capture frame")
            return
        
        # Convert the frame to RGB format (OpenCV uses BGR)
        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        
        # Convert to QImage
        h, w, ch = frame_rgb.shape
        bytes_per_line = ch * w
        image = QImage(frame_rgb.data, w, h, bytes_per_line, QImage.Format_RGB888)
        
        # Scale the image to fit the label while maintaining aspect ratio
        pixmap = QPixmap.fromImage(image)
        pixmap = pixmap.scaled(self.camera_label.width(), self.camera_label.height(), 
                              Qt.KeepAspectRatio, Qt.SmoothTransformation)
        
        # Display the image
        self.camera_label.setPixmap(pixmap)

    def open_motor(self):
        """Move motor to 90 degrees (open position)"""
        if not self.motor_ctrl.is_connected():
            self.status.showMessage("Motor not connected")
            return
        
        # Set angle to exactly 90 degrees and move
        self.motor_ctrl.angle_input.setText("-2300")
        self.motor_ctrl.move()
        self.current_position = 90
        self.update_button_states()
        self.status.showMessage("Opening - Moving to 90°")
        
    def close_motor(self):
        """Move motor to 0 degrees (closed position)"""
        if not self.motor_ctrl.is_connected():
            self.status.showMessage("Motor not connected")
            return
        
        # Set angle to exactly 0 degrees and move
        self.motor_ctrl.angle_input.setText("0")
        self.motor_ctrl.move()
        self.current_position = 0
        self.update_button_states()
        self.status.showMessage("Closing - Moving to 0°")
        
    def update_button_states(self):
        """Update button enabled states based on current position"""
        if self.current_position == 90:  # Open position
            self.open_btn.setEnabled(False)
            self.close_btn.setEnabled(True)
        elif self.current_position == 0:  # Closed position
            self.open_btn.setEnabled(True)
            self.close_btn.setEnabled(False)
        else:  # Unknown position or in between
            self.open_btn.setEnabled(True)
            self.close_btn.setEnabled(True)
            
    def check_rain_status(self):
        """Check rain status from motor controller"""
        if not self.motor_ctrl.is_connected():
            self.rain_indicator.setText("Rain Status: Unknown (Motor disconnected)")
            self.rain_indicator.setStyleSheet("font-weight: bold; font-size: 16px; color: #CCCCCC;")
            return
        
        # Check if driver is available
        if not hasattr(self.motor_ctrl, 'driver') or self.motor_ctrl.driver is None:
            self.rain_indicator.setText("Rain Status: Unknown (Driver not initialized)")
            self.rain_indicator.setStyleSheet("font-weight: bold; font-size: 16px; color: #CCCCCC;")
            return
        
        success, message = self.motor_ctrl.driver.check_rain_status()
        if success:
            is_raining = "Raining" in message
            
            # Update rain indicator with color
            if is_raining:
                self.rain_indicator.setText("Rain Status: RAINING")
                self.rain_indicator.setStyleSheet("font-weight: bold; font-size: 16px; color: #FF5555;")
                
                # Auto-close if open and raining
                if self.current_position == 90:  # If open
                    self.status.showMessage("Auto-closing due to rain detection")
                    self.close_motor()
            else:
                self.rain_indicator.setText("Rain Status: Not raining")
                self.rain_indicator.setStyleSheet("font-weight: bold; font-size: 16px; color: #55FF55;")
        else:
            self.rain_indicator.setText(f"Rain Status: Error checking")
            self.rain_indicator.setStyleSheet("font-weight: bold; font-size: 16px; color: #FFAA55;")
    
    def update_data(self):
        """Update all data displays and graphs"""
        now = datetime.now().timestamp()
        self.timestamps.append(now)
        
        # Limit data points to keep performance high
        max_points = 300  # 5 minutes at 1 second intervals
        if len(self.timestamps) > max_points:
            self.timestamps = self.timestamps[-max_points:]
            self.tc_temps = self.tc_temps[-max_points:]
            self.tc_setpts = self.tc_setpts[-max_points:]
            self.thp_temps = self.thp_temps[-max_points:]
            self.hums = self.hums[-max_points:]
            self.pressures = self.pressures[-max_points:]
        
        # Get temperature controller data
        tc_temp = self.temp_ctrl.current_temp
        tc_setpt = self.temp_ctrl.setpoint
        self.tc_temps.append(tc_temp if tc_temp is not None else float('nan'))
        self.tc_setpts.append(tc_setpt if tc_setpt is not None else float('nan'))
        
        # Get THP sensor data
        thp_data = self.thp_ctrl.get_latest()
        thp_temp = thp_data.get('temperature')
        humidity = thp_data.get('humidity')
        pressure = thp_data.get('pressure')
        
        self.thp_temps.append(thp_temp if thp_temp is not None else float('nan'))
        self.hums.append(humidity if humidity is not None else float('nan'))
        self.pressures.append(pressure if pressure is not None else float('nan'))
        
        # Update graphs
        self.temp_curve.setData(self.timestamps, self.tc_temps)
        self.thp_temp_curve.setData(self.timestamps, self.thp_temps)
        self.hum_curve.setData(self.timestamps, self.hums)
        self.pres_curve.setData(self.timestamps, self.pressures)
        
        # Auto-scale Y axis
        self.tc_plot.enableAutoRange(axis='y')
        self.thp_temp_plot.enableAutoRange(axis='y')
        self.hum_plot.enableAutoRange(axis='y')
        self.pres_plot.enableAutoRange(axis='y')
        
        # Log data if logging is enabled
        if self.logging and self.csv_file:
            try:
                writer = csv.writer(self.csv_file)
                timestamp_str = datetime.fromtimestamp(now).strftime('%Y-%m-%d %H:%M:%S')
                writer.writerow([
                    timestamp_str, 
                    self.tc_temps[-1], 
                    self.tc_setpts[-1],
                    self.thp_temps[-1], 
                    self.hums[-1], 
                    self.pressures[-1]
                ])
                self.csv_file.flush()  # Ensure data is written immediately
            except Exception as e:
                self.status.showMessage(f"Logging error: {str(e)}")
                self.stop_logging()
    
    def start_logging(self):
        """Start logging data to CSV file"""
        try:
            # Create a filename with current timestamp
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"sensor_log_{timestamp}.csv"
            
            # Ask user for save location
            options = QFileDialog.Options()
            filepath, _ = QFileDialog.getSaveFileName(
                self, "Save Log File", filename, "CSV Files (*.csv)", options=options
            )
            
            if not filepath:  # User canceled
                return
                
            # Open file and write header
            self.csv_file = open(filepath, 'w', newline='')
            writer = csv.writer(self.csv_file)
            writer.writerow([
                'Timestamp', 
                'Temperature (°C)', 
                'Setpoint (°C)',
                'THP Temperature (°C)', 
                'Humidity (%)', 
                'Pressure (hPa)'
            ])
            
            # Update UI
            self.logging = True
            self.start_btn.setEnabled(False)
            self.stop_btn.setEnabled(True)
            self.status.showMessage(f"Logging started: {filepath}")
            
        except Exception as e:
            self.status.showMessage(f"Error starting logging: {str(e)}")
            if self.csv_file:
                self.csv_file.close()
                self.csv_file = None
    
    def stop_logging(self):
        """Stop logging data"""
        if self.csv_file:
            self.csv_file.close()
            self.csv_file = None
        
        self.logging = False
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.status.showMessage("Logging stopped")
    
    def closeEvent(self, event):
        """Handle application close event"""
        # Stop logging if active
        if self.logging:
            self.stop_logging()
        
        # Stop timers
        self.update_timer.stop()
        self.rain_timer.stop()
        
        # Close camera
        if hasattr(self, 'camera_feed'):
            if hasattr(self.camera_feed, 'cap') and self.camera_feed.cap:
                self.camera_feed.cap.release()
        
        # Accept the close event
        event.accept()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    
    # Set application-wide font
    font = QFont("Segoe UI", 9)
    app.setFont(font)
    
    # Create and show the main window
    window = MainWindow()
    window.show()
    
    sys.exit(app.exec_())
