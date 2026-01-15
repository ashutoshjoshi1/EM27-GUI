import sys
import os
import json
from datetime import datetime
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                             QHBoxLayout, QStatusBar, QPushButton,
                             QLabel, QGroupBox, QTabWidget, QSplashScreen)
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QFont, QPixmap, QIcon
import pyqtgraph as pg

from controllers.temp_controller import TempController
from controllers.thp_controller import THPController
from controllers.motor_controller import MotorController
from controllers.ac_controller import ACController

import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("EM27 Control & Monitoring System - SciGlob")
        
        # Set window icon
        icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sciglob_symbol.icns")
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))
        
        # Set window to maximized but not fullscreen (respects taskbar)
        self.showMaximized()
        
        # Load configuration
        self.config = self.load_config()

        # Central widget & layout
        central = QWidget()
        central.setStyleSheet("background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #0f1419, stop:1 #1a1f2e);")
        main_layout = QVBoxLayout(central)
        main_layout.setSpacing(15)
        main_layout.setContentsMargins(15, 15, 15, 15)
        self.setCentralWidget(central)
        
        # Create main tab widget
        self.main_tabs = QTabWidget()
        self.main_tabs.setStyleSheet("""
            QTabWidget::pane {
                background-color: transparent;
                border: none;
            }
            QTabBar::tab {
                background-color: #252b38;
                color: #a0a8b8;
                padding: 15px 30px;
                margin-right: 3px;
                border-top-left-radius: 10px;
                border-top-right-radius: 10px;
                font-weight: bold;
                font-size: 13px;
            }
            QTabBar::tab:selected {
                background-color: #1e2430;
                color: white;
                border-bottom: 3px solid #667eea;
            }
            QTabBar::tab:hover {
                background-color: #2a3441;
            }
        """)
        main_layout.addWidget(self.main_tabs)

        # Status bar
        self.status = QStatusBar()
        self.status.setStyleSheet("""
            QStatusBar {
                background-color: #1a1f2e;
                color: #a0a8b8;
                border-top: 1px solid #2a3441;
                padding: 8px;
                font-size: 12px;
            }
        """)
        self.setStatusBar(self.status)
        
        # Initialize data storage
        self.timestamps = []
        self.thp_temps = []
        self.hums = []
        self.pressures = []
        self.current_position = None
        self.was_raining = False
        self.already_sent_mail = False
        
        # Email settings
        self.sender_email = "alerts@sciglob.com"
        self.receiver_email = ["omar@sciglob.com", "ajoshi@sciglob.com", "jgallegos@sciglob.com"]
        self.sender_password = "tpnu xyav aybr wguk"
        self.smtp_server = "smtp.gmail.com"
        self.smtp_port = 587
        
        # Create tabs
        self._create_dashboard_tab()
        self._create_controllers_tab()
        self._create_motor_tab()
        
        # Setup timers
        self.update_timer = QTimer(self)
        self.update_timer.timeout.connect(self.update_data)
        self.update_timer.start(1000)
        self.rain_timer = QTimer(self)
        self.rain_timer.timeout.connect(self.check_rain_status)
        self.rain_timer.start(1000)
        
        # Initial rain check
        try:
            success, message = self.motor_ctrl.driver.check_rain_status()
            if success and "Raining" in message:
                self.status.showMessage("Startup: It's raining → keeping head closed")
                self.close_motor()
            else:
                self.status.showMessage("Startup: Not raining → auto-opening head")
                self.open_motor()
        except Exception as e:
            self.status.showMessage(f"Startup rain check failed: {e}")
    
    def _create_dashboard_tab(self):
        """Create the main dashboard tab with sensor cards and plots"""
        dashboard = QWidget()
        dashboard_layout = QVBoxLayout(dashboard)
        dashboard_layout.setSpacing(20)
        dashboard_layout.setContentsMargins(15, 15, 15, 15)

        # Sensor Cards Row
        sensor_cards_layout = QHBoxLayout()
        sensor_cards_layout.setSpacing(25)
        sensor_cards_layout.addStretch()
        
        # Temperature card - Warm gradient
        temp_card = QGroupBox()
        temp_card.setFixedSize(220, 260)
        temp_card.setStyleSheet("""
            QGroupBox { 
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #FF6B6B, stop:1 #FF8E53);
                border-radius: 15px;
                border: 2px solid rgba(255, 255, 255, 0.2);
                padding: 15px;
            }
        """)
        tc_layout = QVBoxLayout(temp_card)
        tc_layout.setSpacing(10)
        lbl_t_title = QLabel("🌡️ Temperature", alignment=Qt.AlignCenter)
        lbl_t_title.setFont(QFont("Segoe UI", 14, QFont.Bold))
        lbl_t_title.setStyleSheet("color: white; background: transparent;")
        self.lbl_t_value = QLabel("--", alignment=Qt.AlignCenter)
        self.lbl_t_value.setFont(QFont("Segoe UI", 38, QFont.Bold))
        self.lbl_t_value.setStyleSheet("color: white; background: transparent;")
        lbl_t_unit = QLabel("°C", alignment=Qt.AlignCenter)
        lbl_t_unit.setFont(QFont("Segoe UI", 14))
        lbl_t_unit.setStyleSheet("color: rgba(255, 255, 255, 0.9); background: transparent;")
        tc_layout.addWidget(lbl_t_title)
        tc_layout.addWidget(self.lbl_t_value)
        tc_layout.addWidget(lbl_t_unit)
        sensor_cards_layout.addWidget(temp_card)
        
        # Humidity card - Cool teal gradient
        hum_card = QGroupBox()
        hum_card.setFixedSize(220, 260)
        hum_card.setStyleSheet("""
            QGroupBox { 
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #4ECDC4, stop:1 #44A08D);
                border-radius: 15px;
                border: 2px solid rgba(255, 255, 255, 0.2);
                padding: 15px;
            }
        """)
        hu_layout = QVBoxLayout(hum_card)
        hu_layout.setSpacing(10)
        lbl_h_title = QLabel("💧 Humidity", alignment=Qt.AlignCenter)
        lbl_h_title.setFont(QFont("Segoe UI", 14, QFont.Bold))
        lbl_h_title.setStyleSheet("color: white; background: transparent;")
        self.lbl_h_value = QLabel("--", alignment=Qt.AlignCenter)
        self.lbl_h_value.setFont(QFont("Segoe UI", 38, QFont.Bold))
        self.lbl_h_value.setStyleSheet("color: white; background: transparent;")
        lbl_h_unit = QLabel("%", alignment=Qt.AlignCenter)
        lbl_h_unit.setFont(QFont("Segoe UI", 14))
        lbl_h_unit.setStyleSheet("color: rgba(255, 255, 255, 0.9); background: transparent;")
        hu_layout.addWidget(lbl_h_title)
        hu_layout.addWidget(self.lbl_h_value)
        hu_layout.addWidget(lbl_h_unit)
        sensor_cards_layout.addWidget(hum_card)
        
        # Pressure card - Cool blue-purple gradient
        pres_card = QGroupBox()
        pres_card.setFixedSize(220, 260)
        pres_card.setStyleSheet("""
            QGroupBox { 
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #667eea, stop:1 #764ba2);
                border-radius: 15px;
                border: 2px solid rgba(255, 255, 255, 0.2);
                padding: 15px;
            }
        """)
        pr_layout = QVBoxLayout(pres_card)
        pr_layout.setSpacing(10)
        lbl_p_title = QLabel("📊 Pressure", alignment=Qt.AlignCenter)
        lbl_p_title.setFont(QFont("Segoe UI", 14, QFont.Bold))
        lbl_p_title.setStyleSheet("color: white; background: transparent;")
        self.lbl_p_value = QLabel("--", alignment=Qt.AlignCenter)
        self.lbl_p_value.setFont(QFont("Segoe UI", 38, QFont.Bold))
        self.lbl_p_value.setStyleSheet("color: white; background: transparent;")
        lbl_p_unit = QLabel("hPa", alignment=Qt.AlignCenter)
        lbl_p_unit.setFont(QFont("Segoe UI", 14))
        lbl_p_unit.setStyleSheet("color: rgba(255, 255, 255, 0.9); background: transparent;")
        pr_layout.addWidget(lbl_p_title)
        pr_layout.addWidget(self.lbl_p_value)
        pr_layout.addWidget(lbl_p_unit)
        sensor_cards_layout.addWidget(pres_card)
        sensor_cards_layout.addStretch()
        
        dashboard_layout.addLayout(sensor_cards_layout)
        self.temp_ctrl = TempController(parent=self)
        temp_port = self.config.get("com_ports", {}).get("temp_controller", "")
        if temp_port:
            self.temp_ctrl.port = temp_port
        self.temp_ctrl.connect_controller()
        self.temp_ctrl.widget.setMaximumWidth(280)
        self.temp_ctrl.widget.setStyleSheet("""
            QGroupBox { 
                background-color: #1e2430;
                border: 2px solid #3a4553;
                border-radius: 12px;
                color: white;
                padding: 15px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                subcontrol-position: top center;
                padding: 0 8px;
                color: #a0a8b8;
                font-weight: bold;
            }
        """)
        ctrl_layout.addWidget(self.temp_ctrl.widget)
        thp_port = self.config.get("com_ports", {}).get("thp_controller", "")
        self.thp_ctrl = THPController(port=thp_port, parent=self)
        self.thp_ctrl.groupbox.setMaximumWidth(280)
        self.thp_ctrl.groupbox.setStyleSheet("""
            QGroupBox { 
                background-color: #1e2430;
                border: 2px solid #3a4553;
                border-radius: 12px;
                color: white;
                padding: 15px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                subcontrol-position: top center;
                padding: 0 8px;
                color: #a0a8b8;
                font-weight: bold;
            }
        """)
        ctrl_layout.addWidget(self.thp_ctrl.groupbox)
        self.ac_ctrl = ACController(parent=self)
        ac_port = self.config.get("com_ports", {}).get("ac_controller", "")
        if ac_port:
            self.ac_ctrl.port = ac_port
        self.ac_ctrl.widget.setMaximumWidth(280)
        self.ac_ctrl.widget.setStyleSheet("""
            QGroupBox { 
                background-color: #1e2430;
                border: 2px solid #3a4553;
                border-radius: 12px;
                color: white;
                padding: 15px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                subcontrol-position: top center;
                padding: 0 8px;
                color: #a0a8b8;
                font-weight: bold;
            }
        """)
        ctrl_layout.addWidget(self.ac_ctrl.widget)
        top_layout.addLayout(ctrl_layout)
        main_layout.addLayout(top_layout)

        # Motor controls & rain indicator
        motor_group = QGroupBox("⚙️ Motor Control")
        motor_group.setStyleSheet("""
            QGroupBox { 
                background-color: #1e2430;
                border: 2px solid #3a4553;
                border-radius: 12px;
                color: white;
                padding: 15px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                subcontrol-position: top center;
                padding: 0 8px;
                color: #a0a8b8;
                font-weight: bold;
                font-size: 14px;
            }
        """)
        motor_layout = QVBoxLayout(motor_group)
        motor_layout.setSpacing(15)
        self.motor_ctrl = MotorController(parent=self)
        self.motor_ctrl.status_signal.connect(self.status.showMessage)
        motor_port = self.config.get("com_ports", {}).get("motor_controller", "")
        self.motor_ctrl.preferred_port = motor_port
        self.motor_ctrl.connect()
        motor_layout.addWidget(self.motor_ctrl.groupbox)
        self.rain_indicator = QLabel("🌦️ Rain: Unknown")
        self.rain_indicator.setStyleSheet("""
            font-weight: bold; 
            font-size: 16px; 
            color: #a0a8b8;
            padding: 10px;
            background-color: #252b38;
            border-radius: 8px;
        """)
        motor_layout.addWidget(self.rain_indicator)
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(15)
        self.open_btn = QPushButton("🟢 OPEN")
        self.open_btn.setMinimumHeight(55)
        self.open_btn.setFont(QFont("Segoe UI", 14, QFont.Bold))
        self.open_btn.setStyleSheet("""
            QPushButton {
                font-size: 14px;
                padding: 12px;
                border-radius: 10px;
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #4CAF50, stop:1 #45a049);
                color: white;
                border: none;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #66BB6A, stop:1 #4CAF50);
            }
            QPushButton:pressed {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #388E3C, stop:1 #2E7D32);
            }
            QPushButton:disabled {
                background: #3a4553;
                color: #6a7585;
            }
        """)
        self.open_btn.clicked.connect(self.open_motor)
        btn_layout.addWidget(self.open_btn)
        self.close_btn = QPushButton("🔴 CLOSE")
        self.close_btn.setMinimumHeight(55)
        self.close_btn.setFont(QFont("Segoe UI", 14, QFont.Bold))
        self.close_btn.setStyleSheet("""
            QPushButton {
                font-size: 14px;
                padding: 12px;
                border-radius: 10px;
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #f44336, stop:1 #d32f2f);
                color: white;
                border: none;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #EF5350, stop:1 #f44336);
            }
            QPushButton:pressed {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #c62828, stop:1 #b71c1c);
            }
        """)
        self.close_btn.clicked.connect(self.close_motor)
        btn_layout.addWidget(self.close_btn)
        motor_layout.addLayout(btn_layout)
        main_layout.addWidget(motor_group)

        # Wire status signals
        self.temp_ctrl.status_signal.connect(self.status.showMessage)
        self.thp_ctrl.status_signal.connect(self.status.showMessage)
        self.ac_ctrl.status_signal.connect(self.status.showMessage)

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
        tabs.setStyleSheet("""
            QTabWidget::pane {
                background-color: #1e2430;
                border: 2px solid #3a4553;
                border-radius: 12px;
            }
            QTabBar::tab {
                background-color: #252b38;
                color: #a0a8b8;
                padding: 12px 24px;
                margin-right: 3px;
                border-top-left-radius: 8px;
                border-top-right-radius: 8px;
                font-weight: bold;
            }
            QTabBar::tab:selected {
                background-color: #1e2430;
                color: white;
                border-bottom: 2px solid #667eea;
            }
            QTabBar::tab:hover {
                background-color: #2a3441;
            }
        """)
        # Temperature plot
        temp_tab = QWidget(); t_layout = QVBoxLayout(temp_tab)
        t_layout.setContentsMargins(10, 10, 10, 10)
        self.temp_plot = pg.PlotWidget(axisItems={'bottom': date_axis_temp})
        self.temp_plot.setTitle("Temperature (24h)", color='#FF6B6B', size='14pt')
        self.temp_plot.setLabel('left', 'Temperature', units='°C', color='#a0a8b8')
        self.temp_plot.setLabel('bottom', 'Time', color='#a0a8b8')
        self.temp_plot.setBackground('#1e2430')
        self.temp_plot.showGrid(x=True, y=True, alpha=0.3)
        self.temp_curve = self.temp_plot.plot(pen=pg.mkPen(color='#FF6B6B', width=3))
        t_layout.addWidget(self.temp_plot)
        tabs.addTab(temp_tab, "🌡️ Temperature")
        # Humidity plot
        hum_tab = QWidget(); h_layout = QVBoxLayout(hum_tab)
        h_layout.setContentsMargins(10, 10, 10, 10)
        self.hum_plot = pg.PlotWidget(axisItems={'bottom': date_axis_hum})
        self.hum_plot.setTitle("Humidity (24h)", color='#4ECDC4', size='14pt')
        self.hum_plot.setLabel('left', 'Humidity', units='%', color='#a0a8b8')
        self.hum_plot.setLabel('bottom', 'Time', color='#a0a8b8')
        self.hum_plot.setBackground('#1e2430')
        self.hum_plot.showGrid(x=True, y=True, alpha=0.3)
        self.hum_curve = self.hum_plot.plot(pen=pg.mkPen(color='#4ECDC4', width=3))
        h_layout.addWidget(self.hum_plot)
        tabs.addTab(hum_tab, "💧 Humidity")
        # Pressure plot
        pres_tab = QWidget(); p_layout = QVBoxLayout(pres_tab)
        p_layout.setContentsMargins(10, 10, 10, 10)
        self.pres_plot = pg.PlotWidget(axisItems={'bottom': date_axis_pres})
        self.pres_plot.setTitle("Pressure (24h)", color='#667eea', size='14pt')
        self.pres_plot.setLabel('left', 'Pressure', units='hPa', color='#a0a8b8')
        self.pres_plot.setLabel('bottom', 'Time', color='#a0a8b8')
        self.pres_plot.setBackground('#1e2430')
        self.pres_plot.showGrid(x=True, y=True, alpha=0.3)
        self.pres_curve = self.pres_plot.plot(pen=pg.mkPen(color='#667eea', width=3))
        p_layout.addWidget(self.pres_plot)
        tabs.addTab(pres_tab, "📊 Pressure")

        plots_group = QGroupBox("📈 Sensor Data (Last 24 Hours)")
        plots_group.setStyleSheet("""
            QGroupBox { 
                background-color: #1e2430;
                border: 2px solid #3a4553;
                border-radius: 12px;
                color: white;
                padding: 15px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                subcontrol-position: top center;
                padding: 0 8px;
                color: #a0a8b8;
                font-weight: bold;
                font-size: 14px;
            }
        """)
        plots_layout = QVBoxLayout(plots_group)
        plots_layout.setContentsMargins(10, 10, 10, 10)
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

        try:
            success, message = self.motor_ctrl.driver.check_rain_status()
            if success and "Raining" in message:
                self.status.showMessage("Startup: It's raining → keeping head closed")
                self.close_motor()
            else:
                self.status.showMessage("Startup: Not raining → auto-opening head")
                self.open_motor()
        except Exception as e:
            self.status.showMessage(f"Startup rain check failed: {e}")

    
        # Global styling
        self.setStyleSheet("""
            QMainWindow {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #0f1419, stop:1 #1a1f2e);
            }
            QLabel {
                color: #e0e8f0;
            }
            QPushButton {
                color: white;
            }
            QComboBox, QLineEdit {
                background-color: #252b38;
                border: 2px solid #3a4553;
                border-radius: 6px;
                padding: 6px;
                color: white;
                selection-background-color: #667eea;
            }
            QComboBox:hover, QLineEdit:hover {
                border-color: #4a5568;
            }
            QComboBox::drop-down {
                border: none;
                background-color: #3a4553;
                border-radius: 6px;
            }
            QComboBox QAbstractItemView {
                background-color: #252b38;
                color: white;
                selection-background-color: #667eea;
                border: 2px solid #3a4553;
                border-radius: 6px;
            }
        """)
    
    def load_config(self):
        """Load configuration from config.json file"""
        config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")
        default_config = {
            "com_ports": {
                "temp_controller": "COM2",
                "thp_controller": "COM8",
                "motor_controller": "COM7",
                "ac_controller": "COM10"
            }
        }
        
        try:
            if os.path.exists(config_path):
                with open(config_path, 'r') as f:
                    config = json.load(f)
                    # Merge with defaults to ensure all keys exist
                    if "com_ports" not in config:
                        config["com_ports"] = default_config["com_ports"]
                    else:
                        # Merge com_ports to ensure all ports are present
                        for key in default_config["com_ports"]:
                            if key not in config["com_ports"]:
                                config["com_ports"][key] = default_config["com_ports"][key]
                    print(f"Configuration loaded from {config_path}")
                    return config
            else:
                # Create default config file if it doesn't exist
                with open(config_path, 'w') as f:
                    json.dump(default_config, f, indent=4)
                print(f"Created default config.json at {config_path}")
                return default_config
        except Exception as e:
            print(f"Error loading config: {e}. Using defaults.")
            return default_config
        
    def open_motor(self):
        """Move motor to open position"""
        if not self.motor_ctrl.is_connected():
            self.status.showMessage("Motor not connected")
            return
        self.motor_ctrl.angle_input.setText("-2100")
        self.motor_ctrl.move()
        self.current_position = 90
        self.status.showMessage("Opening - Moving to -2100")

    def close_motor(self):
        """Move motor to closed position"""
        if not self.motor_ctrl.is_connected():
            self.status.showMessage("Motor not connected")
            return
        self.motor_ctrl.angle_input.setText("-30")
        self.motor_ctrl.move()
        self.current_position = 0
        self.status.showMessage("Closing - Moving to -30")

    def send_rain_email(self):
        """Send a single 'it's raining' email."""
        msg = MIMEMultipart()
        msg["From"]    = self.sender_email
        msg["To"]      = ", ".join(self.receiver_email)
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
            self.rain_indicator.setText("❓ Rain Status: Unknown (Motor disconnected)")
            self.rain_indicator.setStyleSheet("""
                font-weight: bold; 
                font-size: 16px; 
                color: #a0a8b8;
                padding: 10px;
                background-color: #252b38;
                border-radius: 8px;
            """)
            return

        try:
            success, message = self.motor_ctrl.driver.check_rain_status()
            raining_now = success and "Raining" in message
        except Exception as e:
            self.rain_indicator.setText("⚠️ Rain Status: Error checking")
            self.rain_indicator.setStyleSheet("""
                font-weight: bold; 
                font-size: 16px; 
                color: #FFB74D;
                padding: 10px;
                background-color: rgba(255, 183, 77, 0.15);
                border-radius: 8px;
                border: 2px solid rgba(255, 183, 77, 0.3);
            """)
            self.status.showMessage(f"Rain check error: {e}")
            return

        if raining_now:
            # ── Raining ────────────────────────────────────────────
            self.rain_indicator.setText("🌧️ Rain Status: RAINING")
            self.rain_indicator.setStyleSheet("""
                font-weight: bold; 
                font-size: 16px; 
                color: #FF6B6B;
                padding: 10px;
                background-color: rgba(255, 107, 107, 0.15);
                border-radius: 8px;
                border: 2px solid rgba(255, 107, 107, 0.3);
            """)
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
            self.rain_indicator.setText("☀️ Rain Status: Not raining")
            self.rain_indicator.setStyleSheet("""
                font-weight: bold; 
                font-size: 16px; 
                color: #4ECDC4;
                padding: 10px;
                background-color: rgba(78, 205, 196, 0.15);
                border-radius: 8px;
                border: 2px solid rgba(78, 205, 196, 0.3);
            """)
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
