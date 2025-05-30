import sys
import os
import cv2
from datetime import datetime
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                             QHBoxLayout, QStatusBar, QPushButton,
                             QLabel, QGroupBox, QTabWidget)
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QImage, QPixmap, QFont
import pyqtgraph as pg

from controllers.temp_controller import TempController
from controllers.thp_controller import THPController
from controllers.motor_controller import MotorController

import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Temp & THP Live Monitor")
        self.setMinimumSize(1200, 800)

        # Central widget & layout
        central = QWidget()
        central.setStyleSheet("background-color: #333333;")  # Dark grey background
        main_layout = QVBoxLayout(central)
        self.setCentralWidget(central)

        # Status bar
        self.status = QStatusBar()
        self.setStatusBar(self.status)

        # Top: Camera + Sensor Cards + Controllers
        top_layout = QHBoxLayout()
        top_layout.setSpacing(15)

        # Camera feed group
        camera_group = QGroupBox("Camera Feed")
        camera_group.setMaximumWidth(400)
        camera_group.setStyleSheet(
            "QGroupBox { background-color: #2c2c2c; border: 1px solid #444; border-radius: 10px; color: white; }"
            "QGroupBox::title { subcontrol-origin: margin; subcontrol-position: top center; }"
        )
        cam_layout = QVBoxLayout(camera_group)
        self.camera_label = QLabel("No Camera Feed", alignment=Qt.AlignCenter)
        self.camera_label.setMinimumSize(360, 240)
        self.camera_label.setStyleSheet("background-color: #111; border-radius: 8px; color: white;")
        cam_layout.addWidget(self.camera_label)
        cam_btns = QHBoxLayout()
        self.camera_connect_btn = QPushButton("Connect")
        self.camera_connect_btn.setStyleSheet("padding:8px; border-radius:5px; background:#4CAF50; color:white;")
        self.camera_connect_btn.clicked.connect(self.connect_camera)
        cam_btns.addWidget(self.camera_connect_btn)
        self.camera_disconnect_btn = QPushButton("Disconnect")
        self.camera_disconnect_btn.setStyleSheet("padding:8px; border-radius:5px; background:#f44336; color:white;")
        self.camera_disconnect_btn.setEnabled(False)
        self.camera_disconnect_btn.clicked.connect(self.disconnect_camera)
        cam_btns.addWidget(self.camera_disconnect_btn)
        cam_layout.addLayout(cam_btns)
        top_layout.addWidget(camera_group)

        # Sensor summary cards
        sensor_widget = QWidget()
        sensor_layout = QHBoxLayout(sensor_widget)
        sensor_layout.setSpacing(15)
        # Temperature card
        temp_card = QGroupBox()
        temp_card.setFixedSize(160, 220)
        temp_card.setStyleSheet("QGroupBox { background-color:#4e6d94; border-radius:10px; color:white; }")
        tc_layout = QVBoxLayout(temp_card)
        lbl_t_title = QLabel("Temperature", alignment=Qt.AlignCenter)
        lbl_t_title.setStyleSheet("color:white;")
        self.lbl_t_value = QLabel("--", alignment=Qt.AlignCenter)
        self.lbl_t_value.setFont(QFont("Segoe UI", 20, QFont.Bold))
        self.lbl_t_value.setStyleSheet("color:#FF7440;")
        lbl_t_unit = QLabel("°C", alignment=Qt.AlignCenter)
        lbl_t_unit.setStyleSheet("color:white;")
        tc_layout.addWidget(lbl_t_title)
        tc_layout.addWidget(self.lbl_t_value)
        tc_layout.addWidget(lbl_t_unit)
        sensor_layout.addWidget(temp_card)
        # Humidity card
        hum_card = QGroupBox()
        hum_card.setFixedSize(160, 220)
        hum_card.setStyleSheet("QGroupBox { background-color:#4e6d94; border-radius:10px; color:white; }")
        hu_layout = QVBoxLayout(hum_card)
        lbl_h_title = QLabel("Humidity", alignment=Qt.AlignCenter)
        lbl_h_title.setStyleSheet("color:white;")
        self.lbl_h_value = QLabel("--", alignment=Qt.AlignCenter)
        self.lbl_h_value.setFont(QFont("Segoe UI", 20, QFont.Bold))
        self.lbl_h_value.setStyleSheet("color:#55FF55;")
        lbl_h_unit = QLabel("%", alignment=Qt.AlignCenter)
        lbl_h_unit.setStyleSheet("color:white;")
        hu_layout.addWidget(lbl_h_title)
        hu_layout.addWidget(self.lbl_h_value)
        hu_layout.addWidget(lbl_h_unit)
        sensor_layout.addWidget(hum_card)
        # Pressure card
        pres_card = QGroupBox()
        pres_card.setFixedSize(160, 220)
        pres_card.setStyleSheet("QGroupBox { background-color:#4e6d94; border-radius:10px; color:white; }")
        pr_layout = QVBoxLayout(pres_card)
        lbl_p_title = QLabel("Pressure", alignment=Qt.AlignCenter)
        lbl_p_title.setStyleSheet("color:white;")
        self.lbl_p_value = QLabel("--", alignment=Qt.AlignCenter)
        self.lbl_p_value.setFont(QFont("Segoe UI", 20, QFont.Bold))
        self.lbl_p_value.setStyleSheet("color:#88B9FF;")
        lbl_p_unit = QLabel("hPa", alignment=Qt.AlignCenter)
        lbl_p_unit.setStyleSheet("color:white;")
        pr_layout.addWidget(lbl_p_title)
        pr_layout.addWidget(self.lbl_p_value)
        pr_layout.addWidget(lbl_p_unit)
        sensor_layout.addWidget(pres_card)
        top_layout.addWidget(sensor_widget)

        # Controllers group
        ctrl_layout = QVBoxLayout()
        self.temp_ctrl = TempController(parent=self)
        self.temp_ctrl.port = "COM2"
        self.temp_ctrl.connect_controller()
        self.temp_ctrl.widget.setMaximumWidth(250)
        self.temp_ctrl.widget.setStyleSheet("QGroupBox { background-color:#2c2c2c; border:1px solid #444; border-radius:10px; color:white; }")
        ctrl_layout.addWidget(self.temp_ctrl.widget)
        self.thp_ctrl = THPController(port="COM7", parent=self)
        self.thp_ctrl.groupbox.setMaximumWidth(250)
        self.thp_ctrl.groupbox.setStyleSheet("QGroupBox { background-color:#2c2c2c; border:1px solid #444; border-radius:10px; color:white; }")
        ctrl_layout.addWidget(self.thp_ctrl.groupbox)
        top_layout.addLayout(ctrl_layout)
        main_layout.addLayout(top_layout)

        # Motor controls & rain indicator
        motor_group = QGroupBox("Motor Control")
        motor_group.setStyleSheet("QGroupBox { background-color:#2c2c2c; border:1px solid #444; border-radius:10px; color:white; }")
        motor_layout = QVBoxLayout(motor_group)
        self.motor_ctrl = MotorController(parent=self)
        self.motor_ctrl.status_signal.connect(self.status.showMessage)
        self.motor_ctrl.preferred_port = "COM8"
        self.motor_ctrl.connect()
        motor_layout.addWidget(self.motor_ctrl.groupbox)
        self.rain_indicator = QLabel("Rain: Unknown")
        self.rain_indicator.setStyleSheet("font-weight:bold; font-size:14px; color:#CCCCCC;")
        motor_layout.addWidget(self.rain_indicator)
        btn_layout = QHBoxLayout()
        self.open_btn = QPushButton("OPEN")
        self.open_btn.setMinimumHeight(50)
        self.open_btn.setStyleSheet("font-size:16px; padding:8px; border-radius:5px; background:#4CAF50; color:white;")
        self.open_btn.clicked.connect(self.open_motor)
        btn_layout.addWidget(self.open_btn)
        self.close_btn = QPushButton("CLOSE")
        self.close_btn.setMinimumHeight(50)
        self.close_btn.setStyleSheet("font-size:16px; padding:8px; border-radius:5px; background:#f44336; color:white;")
        self.close_btn.clicked.connect(self.close_motor)
        btn_layout.addWidget(self.close_btn)
        motor_layout.addLayout(btn_layout)
        main_layout.addWidget(motor_group)

        # Wire status signals
        self.temp_ctrl.status_signal.connect(self.status.showMessage)
        self.thp_ctrl.status_signal.connect(self.status.showMessage)

        # Data storage & state
        self.timestamps = []
        self.thp_temps = []
        self.hums = []
        self.pressures = []
        self.current_position = None

        # 24h plots setup
        date_axis_temp = pg.DateAxisItem(orientation='bottom')
        date_axis_hum = pg.DateAxisItem(orientation='bottom')
        date_axis_pres = pg.DateAxisItem(orientation='bottom')

        tabs = QTabWidget()
        # Temperature plot
        temp_tab = QWidget(); t_layout = QVBoxLayout(temp_tab)
        self.temp_plot = pg.PlotWidget(axisItems={'bottom': date_axis_temp})
        self.temp_plot.setTitle("Temperature (24h)")
        self.temp_curve = self.temp_plot.plot(pen=pg.mkPen(width=2)); t_layout.addWidget(self.temp_plot)
        tabs.addTab(temp_tab, "Temperature")
        # Humidity plot
        hum_tab = QWidget(); h_layout = QVBoxLayout(hum_tab)
        self.hum_plot = pg.PlotWidget(axisItems={'bottom': date_axis_hum})
        self.hum_plot.setTitle("Humidity (24h)")
        self.hum_curve = self.hum_plot.plot(pen=pg.mkPen(width=2)); h_layout.addWidget(self.hum_plot)
        tabs.addTab(hum_tab, "Humidity")
        # Pressure plot
        pres_tab = QWidget(); p_layout = QVBoxLayout(pres_tab)
        self.pres_plot = pg.PlotWidget(axisItems={'bottom': date_axis_pres})
        self.pres_plot.setTitle("Pressure (24h)")
        self.pres_curve = self.pres_plot.plot(pen=pg.mkPen(width=2)); p_layout.addWidget(self.pres_plot)
        tabs.addTab(pres_tab, "Pressure")

        plots_group = QGroupBox("Sensor Data (Last 24 Hours)")
        plots_group.setStyleSheet("QGroupBox { background-color:#2c2c2c; border:1px solid #444; border-radius:10px; color:white; }")
        plots_layout = QVBoxLayout(plots_group)
        plots_layout.addWidget(tabs)
        main_layout.addWidget(plots_group)

        # Timers
        self.update_timer = QTimer(self)
        self.update_timer.timeout.connect(self.update_data)
        self.update_timer.start(1000)
        self.rain_timer = QTimer(self)
        self.rain_timer.timeout.connect(self.check_rain_status)
        self.rain_timer.start(1000)

        self.was_raining = False
        self.already_sent_mail = False

        # ── NEW: put your SMTP credentials here ─────────────────
        self.sender_email    = "alerts@sciglob.com"
        self.receiver_email = ["omar@sciglob.com", "ajoshi@sciglob.com", "jgallegos@sciglob.com"]
        self.sender_password = "tpnu xyav aybr wguk"
        self.smtp_server     = "smtp.gmail.com"
        self.smtp_port       = 587  # or 465 if you use SSL
    
        # Styling
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
            self.camera_feed = cv2.VideoCapture(0)
            if not self.camera_feed.isOpened():
                self.status.showMessage("Failed to open camera")
                return
            self.camera_timer = QTimer(self)
            self.camera_timer.timeout.connect(self.update_camera_feed)
            self.camera_timer.start(33)
            self.camera_connect_btn.setEnabled(False)
            self.camera_disconnect_btn.setEnabled(True)
            self.status.showMessage("Camera connected")
        except Exception as e:
            self.status.showMessage(f"Camera error: {e}")

    def disconnect_camera(self):
        """Disconnect from the camera"""
        if hasattr(self, 'camera_timer'):
            self.camera_timer.stop()
        if hasattr(self, 'camera_feed') and self.camera_feed:
            self.camera_feed.release()
        self.camera_label.setText("No Camera Feed")
        self.camera_label.setPixmap(QPixmap())
        self.camera_connect_btn.setEnabled(True)
        self.camera_disconnect_btn.setEnabled(False)
        self.status.showMessage("Camera disconnected")

    def update_camera_feed(self):
        """Rotate 90° CCW and decrease brightness/contrast"""
        if not getattr(self, 'camera_feed', None):
            return
        ret, frame = self.camera_feed.read()
        if not ret:
            self.status.showMessage("Failed to capture frame")
            return

        # Rotate 90° anticlockwise
        frame = cv2.rotate(frame, cv2.ROTATE_90_COUNTERCLOCKWISE)

        # Adjust contrast/brightness
        alpha = 0.8   # contrast (0.0–1.0 lowers, >1 raises)
        beta  = -30   # brightness (-100 to +100)
        frame = cv2.convertScaleAbs(frame, alpha=alpha, beta=beta)

        # Convert for Qt
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb.shape
        img = QImage(rgb.data, w, h, ch * w, QImage.Format_RGB888)
        pix = QPixmap.fromImage(img).scaled(
            self.camera_label.width(),
            self.camera_label.height(),
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation
        )
        self.camera_label.setPixmap(pix)
        
    def open_motor(self):
        """Move motor to open position"""
        if not self.motor_ctrl.is_connected():
            self.status.showMessage("Motor not connected")
            return
        self.motor_ctrl.angle_input.setText("-2300")
        self.motor_ctrl.move()
        self.current_position = 90
        self.status.showMessage("Opening - Moving to 90°")

    def close_motor(self):
        """Move motor to closed position"""
        if not self.motor_ctrl.is_connected():
            self.status.showMessage("Motor not connected")
            return
        self.motor_ctrl.angle_input.setText("0")
        self.motor_ctrl.move()
        self.current_position = 0
        self.status.showMessage("Closing - Moving to 0°")

    def send_rain_email(self):
        """Send a single 'it's raining' email."""
        msg = MIMEMultipart()
        msg["From"]    = self.sender_email
        msg["To"]      = self.receiver_email
        msg["Subject"] = "EM-27 Weather Update"

        body = (
            "Hello,\n\n"
            "It is raining outside. The head of EM-27 has been closed for the duration of the rain.\n\n"
            "Regards,\n"
            "EM-27 Monitoring System,\n"
            "SciGlob Instruments & Services, LLC"
        )
        msg.attach(MIMEText(body, "plain"))

        try:
            # If your server uses STARTTLS:
            server = smtplib.SMTP(self.smtp_server, self.smtp_port)
            server.ehlo()
            server.starttls()
            server.login(self.sender_email, self.sender_password)
            server.send_message(msg)
            server.quit()
            self.status.showMessage("Rain email sent")
        except Exception as e:
            self.status.showMessage(f"Failed to send rain email: {e}")

    def check_rain_status(self):
        """Check rain status from motor controller, auto‐open or email on transitions."""
        if not self.motor_ctrl.is_connected():
            self.rain_indicator.setText("Rain Status: Unknown (Motor disconnected)")
            self.rain_indicator.setStyleSheet("font-weight: bold; font-size: 16px; color: #CCCCCC;")
            return

        try:
            success, message = self.motor_ctrl.driver.check_rain_status()
            raining_now = success and "Raining" in message
        except Exception as e:
            self.rain_indicator.setText("Rain Status: Error checking")
            self.rain_indicator.setStyleSheet("font-weight: bold; font-size: 16px; color: #FFAA55;")
            self.status.showMessage(f"Rain check error: {e}")
            return

        if raining_now:
            # ── Raining ────────────────────────────────────────────
            self.rain_indicator.setText("Rain Status: RAINING")
            self.rain_indicator.setStyleSheet("font-weight: bold; font-size: 16px; color: #FF5555;")
            self.open_btn.setEnabled(False)

            # auto‐close if open
            if self.current_position == 90:
                self.status.showMessage("Auto-closing due to rain detection")
                self.close_motor()

            # send one email per rain event
            if not self.already_sent_mail:
                self.send_rain_email()
                self.already_sent_mail = True

            # remember that we're raining
            self.was_raining = True

        else:
            # ── Not Raining ────────────────────────────────────────
            self.rain_indicator.setText("Rain Status: Not raining")
            self.rain_indicator.setStyleSheet("font-weight: bold; font-size: 16px; color: #55FF55;")
            self.open_btn.setEnabled(True)

            # on transition R → ☀, auto‐open
            if self.was_raining:
                self.status.showMessage("Rain stopped — auto-opening motor")
                self.open_motor()

            # reset flags
            self.was_raining = False
            self.already_sent_mail = False

    def update_data(self):
        now = datetime.now().timestamp()
        latest = self.thp_ctrl.get_latest()
        temp = latest.get('temperature', float('nan'))
        hum = latest.get('humidity', float('nan'))
        pres = latest.get('pressure', float('nan'))
        # Update cards
        self.lbl_t_value.setText(f"{temp:.1f}")
        self.lbl_h_value.setText(f"{hum:.1f}")
        self.lbl_p_value.setText(f"{pres:.1f}")
        # Append to history
        self.timestamps.append(now)
        self.thp_temps.append(temp)
        self.hums.append(hum)
        self.pressures.append(pres)
        # Trim to 24h
        cutoff = now - 86400
        while self.timestamps and self.timestamps[0] < cutoff:
            self.timestamps.pop(0)
            self.thp_temps.pop(0)
            self.hums.pop(0)
            self.pressures.pop(0)
        # Update plots
        self.temp_curve.setData(self.timestamps, self.thp_temps)
        self.hum_curve.setData(self.timestamps, self.hums)
        self.pres_curve.setData(self.timestamps, self.pressures)
        self.temp_plot.enableAutoRange(axis='y')
        self.hum_plot.enableAutoRange(axis='y')
        self.pres_plot.enableAutoRange(axis='y')

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setFont(QFont("Segoe UI", 9))
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())
