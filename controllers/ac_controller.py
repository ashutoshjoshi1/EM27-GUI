from PyQt5.QtCore import QObject, pyqtSignal, QTimer, Qt, QPointF
from PyQt5.QtWidgets import (QGroupBox, QVBoxLayout, QHBoxLayout, QPushButton, 
                             QLabel, QLineEdit, QWidget, QCheckBox)
from PyQt5.QtGui import QPainter, QPen, QBrush, QColor, QFont, QMouseEvent
import inspect
import threading
from contextlib import suppress
from typing import Tuple

# ---- pymodbus compatibility (3.x preferred; 2.x fallback) ----
try:
    from pymodbus.client import ModbusSerialClient  # 3.x
except Exception:
    try:
        from pymodbus.client.sync import ModbusSerialClient  # 2.x
    except ImportError:
        ModbusSerialClient = None
        print("Warning: pymodbus not installed. AC Controller will not be functional.")
        print("Install with: pip install pymodbus")
try:
    from pymodbus.exceptions import ModbusException
except ImportError:
    class ModbusException(Exception):
        pass

# ----------------------------
# Defaults & register map
# ----------------------------
DEFAULT_PORT     = "COM10"
DEFAULT_BAUD     = 19200
DEFAULT_PARITY   = "E"   # Even
DEFAULT_STOPBITS = 1
DEFAULT_BYTESIZE = 8
DEFAULT_TIMEOUT  = 2.0
DEFAULT_UNIT_ID  = 1

REG_SET_COOL       = 0
REG_SET_ALARM_HI   = 1
REG_SET_ALARM_LO   = 2
REG_SET_HEATER     = 3

REG_ENABLE_FLAGS_READ       = 4
REG_ENABLE_FLAGS_WRITE_CAND = [4, 6]  # some firmwares require 6 for writing flags

REG_READ_SENSOR = 12

# Enable Flags bits (Seifert/SCE NextGen family)
BIT_INPUT1_INVERT        = 8     # used as "Power" (active-low on this unit)
BIT_LOCK_KEYPAD          = 10    # always ON
BIT_TEMP_UNIT_FAHRENHEIT = 11    # always OFF (Celsius)
BIT_NETWORK_SETPOINTS = 9   # set None if the unit doesn't support it

# Reasonable safety limits (device enforces similar)
SAFE_C_LIMITS = {
    "low":   (-20.0,  25.0),
    "heat":  ( -5.0,  35.0),
    "cool":  ( 20.0,  60.0),  # most models reject cooling < ~20–25 C
    "high":  ( 30.0,  80.0),
}

# ----------------------------
# Helpers (0.1° scaling)
# ----------------------------
def to_signed_16(u: int) -> int:
    return u - 0x10000 if u >= 0x8000 else u

def reg_to_val(raw: int) -> float:
    return to_signed_16(int(raw)) / 10.0

def c_to_reg(val_c: float) -> int:
    return int(round(float(val_c) * 10))

def clamp(v: float, lo: float, hi: float) -> float:
    v = float(v)
    return lo if v < lo else hi if v > hi else v

# ----------------------------
# AC Controller Class
# ----------------------------
class ACModbusController:
    def __init__(self, port=DEFAULT_PORT, baudrate=DEFAULT_BAUD, parity=DEFAULT_PARITY,
                 stopbits=DEFAULT_STOPBITS, bytesize=DEFAULT_BYTESIZE, timeout=DEFAULT_TIMEOUT,
                 unit=DEFAULT_UNIT_ID):
        self.port = port
        self.baudrate = baudrate
        self.parity = parity
        self.stopbits = stopbits
        self.bytesize = bytesize
        self.timeout = timeout
        self.unit = unit
        self.client = None
        self.flags_write_addr = None  # auto-detected
        self.io_lock = threading.RLock()

    # --- connect/disconnect ---
    def connect(self) -> bool:
        if ModbusSerialClient is None:
            raise RuntimeError("pymodbus not installed. Install with: pip install pymodbus")
        with self.io_lock:
            # Close any stale handle first
            with suppress(Exception):
                if self.client:
                    self.client.close()
            self.client = ModbusSerialClient(
                port=self.port,
                baudrate=self.baudrate,
                parity=self.parity,
                stopbits=self.stopbits,
                bytesize=self.bytesize,
                timeout=self.timeout,
            )
            ok = self.client.connect()
            if ok:
                with suppress(Exception):
                    self._detect_flags_write_address()
                # Enforce policy on connect
                with suppress(Exception):
                    cur = self.read_enable_flags()
                    cur_power_on = self._power_on_from_flags(cur)
                    cur_net = self._net_on_from_flags(cur)
                    self.write_flags(power_on=cur_power_on, force_net=cur_net)
            return ok

    def is_connected(self) -> bool:
        return self.client is not None

    def close(self):
        with self.io_lock:
            if self.client:
                with suppress(Exception):
                    self.client.close()
                self.client = None

    # --- modbus compat helpers ---
    def _kw_unit_for(self, fn):
        try:
            params = inspect.signature(fn).parameters
            if "slave" in params: return "slave"  # 3.x
            if "unit"  in params: return "unit"   # 2.x
        except Exception:
            pass
        return None

    def _supports_param(self, fn, name: str) -> bool:
        try: return name in inspect.signature(fn).parameters
        except Exception: return False

    def _read_hregs(self, address, count=1):
        with self.io_lock:
            fn = getattr(self.client, "read_holding_registers", None)
            if fn is not None:
                kw = self._kw_unit_for(fn)
                kwargs = {kw: self.unit} if kw else {}
                try:
                    if self._supports_param(fn, "count") or self._supports_param(fn, "quantity"):
                        rr = fn(address, count, **kwargs)
                    else:
                        rr = fn(address, **kwargs)
                except TypeError:
                    try: rr = fn(address, **kwargs)
                    except TypeError: rr = fn(address)
                if rr.isError(): raise ModbusException(rr)
                return rr
            fn = getattr(self.client, "read_holding_register", None)
            if fn is None: raise RuntimeError("Client missing read_holding_register(s)")
            kw = self._kw_unit_for(fn)
            kwargs = {kw: self.unit} if kw else {}
            try: rr = fn(address, **kwargs)
            except TypeError: rr = fn(address)
            if rr.isError(): raise ModbusException(rr)
            return rr

    def _write_reg(self, address, value):
        with self.io_lock:
            fn = getattr(self.client, "write_register", None)
            if fn is None: raise RuntimeError("Client missing write_register")
            kw = self._kw_unit_for(fn)
            kwargs = {kw: self.unit} if kw else {}
            wr = fn(address, int(value), **kwargs) if kwargs else fn(address, int(value))
            if wr.isError():
                code = getattr(wr, "exception_code", "??")
                raise ModbusException(f"ExceptionResponse(dev_id={self.unit}, function_code={wr.function_code}, exception_code={code})")
            return wr

    def _try_echo_write(self, addr, value) -> bool:
        try:
            self._write_reg(addr, value)
            return True
        except Exception:
            return False

    def _detect_flags_write_address(self):
        cur = self.read_enable_flags()
        for cand in REG_ENABLE_FLAGS_WRITE_CAND:
            if self._try_echo_write(cand, cur):
                self.flags_write_addr = cand
                return
        self.flags_write_addr = None

    # --- reads ---
    def read_enable_flags(self) -> int:
        rr = self._read_hregs(REG_ENABLE_FLAGS_READ, 1)
        return getattr(rr, "registers", [getattr(rr, "register", 0)])[0]

    def read_sensor_c(self) -> float:
        rr = self._read_hregs(REG_READ_SENSOR, 1)
        raw = getattr(rr, "registers", [getattr(rr, "register", 0)])[0]
        return reg_to_val(raw)

    # --- flag helpers (ACTIVE-LOW power mapping) ---
    def _power_on_from_flags(self, flags: int) -> bool:
        # ACTIVE-LOW: bit=0 -> ON, bit=1 -> OFF
        return ((flags >> BIT_INPUT1_INVERT) & 1) == 0

    def _net_on_from_flags(self, flags: int) -> bool:
        return BIT_NETWORK_SETPOINTS is not None and ((flags >> BIT_NETWORK_SETPOINTS) & 1) == 1

    def write_flags(self, power_on: bool, force_net=None):
        """Lock keypad, force Celsius, control power. Preserve or set NET bit."""
        current = 0
        with suppress(Exception):
            current = self.read_enable_flags()
        net_on = self._net_on_from_flags(current) if force_net is None else bool(force_net)

        word = 0
        # ACTIVE-LOW: to turn ON, we must CLEAR the invert bit
        if not power_on:
            word |= (1 << BIT_INPUT1_INVERT)
        word |= (1 << BIT_LOCK_KEYPAD)
        if net_on and BIT_NETWORK_SETPOINTS is not None:
            word |= (1 << BIT_NETWORK_SETPOINTS)

        addrs = [self.flags_write_addr] if self.flags_write_addr is not None else REG_ENABLE_FLAGS_WRITE_CAND
        last = None
        for a in [x for x in addrs if x is not None]:
            try:
                self._write_reg(a, word)
                self.flags_write_addr = a
                return
            except Exception as e:
                last = e
        if last: raise last

    # --- setpoints (Celsius only) ---
    def write_setpoints_c(self, heater_c: float, cooling_c: float):
        # Compute alarms to keep relationships valid
        lo = heater_c - 2.0
        hi = cooling_c + 5.0

        # clamp to safe ranges
        lo       = clamp(lo,       *SAFE_C_LIMITS["low"])
        heater_c = clamp(heater_c, *SAFE_C_LIMITS["heat"])
        cooling_c= clamp(cooling_c,*SAFE_C_LIMITS["cool"])
        hi       = clamp(hi,       *SAFE_C_LIMITS["high"])

        # enforce order with 1°C separation
        eps = 1.0
        if not (lo < heater_c - eps and heater_c < cooling_c - eps and cooling_c < hi - eps):
            raise ValueError("Range must satisfy: Low < Heater < Cooling < High (≥1°C apart).")

        def do_writes():
            for addr, val in [
                (REG_SET_ALARM_LO, c_to_reg(lo)),
                (REG_SET_HEATER,   c_to_reg(heater_c)),
                (REG_SET_COOL,     c_to_reg(cooling_c)),
                (REG_SET_ALARM_HI, c_to_reg(hi)),
            ]:
                self._write_reg(addr, val)

        initial = self.read_enable_flags()
        had_net = self._net_on_from_flags(initial)
        had_power = self._power_on_from_flags(initial)
        try:
            if BIT_NETWORK_SETPOINTS is not None and not had_net:
                self.write_flags(power_on=had_power, force_net=True)
            do_writes()
        finally:
            if BIT_NETWORK_SETPOINTS is not None and not had_net:
                    with suppress(Exception):
                        self.write_flags(power_on=had_power, force_net=False)

# ----------------------------
# PyQt5 Range Slider Widget
# ----------------------------
class RangeSlider(QWidget):
    """Dual-handle range slider for heater/cooling temperature selection"""
    values_changed = pyqtSignal(float, float)  # emits (low, high)
    
    def __init__(self, parent=None, min_val=0.0, max_val=60.0, 
                 init_low=15.0, init_high=20.0, step=0.5):
        super().__init__(parent)
        self.min_val = float(min_val)
        self.max_val = float(max_val)
        self.low_val = float(init_low)
        self.high_val = float(init_high)
        self.step = float(step)
        self.pad = 12
        self.track_h = 6
        self.handle_r = 8
        self.dragging = None
        self.setMinimumSize(400, 70)
        self.setMaximumHeight(70)
        
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        w, h = self.width(), self.height()
        x0, x1 = self.pad, w - self.pad
        y = h // 2
        
        # Track background
        pen = QPen(QColor("#ddd"), self.track_h, Qt.SolidLine, Qt.RoundCap)
        painter.setPen(pen)
        painter.drawLine(int(x0), int(y), int(x1), int(y))
        
        # Range fill (active range)
        lx = self._val_to_x(self.low_val)
        hx = self._val_to_x(self.high_val)
        pen = QPen(QColor("#8aa"), self.track_h, Qt.SolidLine, Qt.RoundCap)
        painter.setPen(pen)
        painter.drawLine(int(lx), int(y), int(hx), int(y))
        
        # Handles
        brush = QBrush(QColor("#fff"))
        pen = QPen(QColor("#444"), 2)
        painter.setBrush(brush)
        painter.setPen(pen)
        
        # Low handle
        painter.drawEllipse(QPointF(lx, y), self.handle_r, self.handle_r)
        
        # High handle
        painter.drawEllipse(QPointF(hx, y), self.handle_r, self.handle_r)
        
        # Labels with background for visibility
        font = QFont("Segoe UI", 10, QFont.Bold)
        painter.setFont(font)
        
        # Low value label
        low_text = f"{self.low_val:.1f}°C"
        low_rect_x = int(lx) - 30
        low_rect_y = int(y) - 35
        low_rect_w = 60
        low_rect_h = 22
        
        # Draw background for low label
        painter.setBrush(QBrush(QColor("#2a3441")))
        painter.setPen(QPen(QColor("#4a5568"), 2))
        painter.drawRoundedRect(low_rect_x, low_rect_y, low_rect_w, low_rect_h, 5, 5)
        
        # Draw low label text
        painter.setPen(QPen(QColor("#4ECDC4")))
        painter.drawText(low_rect_x, low_rect_y, low_rect_w, low_rect_h, 
                        Qt.AlignCenter, low_text)
        
        # High value label
        high_text = f"{self.high_val:.1f}°C"
        high_rect_x = int(hx) - 30
        high_rect_y = int(y) - 35
        high_rect_w = 60
        high_rect_h = 22
        
        # Draw background for high label
        painter.setBrush(QBrush(QColor("#2a3441")))
        painter.setPen(QPen(QColor("#4a5568"), 2))
        painter.drawRoundedRect(high_rect_x, high_rect_y, high_rect_w, high_rect_h, 5, 5)
        
        # Draw high label text
        painter.setPen(QPen(QColor("#FF6B6B")))
        painter.drawText(high_rect_x, high_rect_y, high_rect_w, high_rect_h, 
                        Qt.AlignCenter, high_text)
    
    def _val_to_x(self, v):
        v = max(self.min_val, min(self.max_val, v))
        w = self.width()
        x0, x1 = self.pad, w - self.pad
        return x0 + (x1 - x0) * ((v - self.min_val) / (self.max_val - self.min_val))
    
    def _x_to_val(self, x):
        w = self.width()
        x0, x1 = self.pad, w - self.pad
        x = max(x0, min(x1, x))
        v = self.min_val + (self.max_val - self.min_val) * ((x - x0) / (x1 - x0))
        return round(v / self.step) * self.step
    
    def mousePressEvent(self, event: QMouseEvent):
        if event.button() != Qt.LeftButton:
            return
        lx = self._val_to_x(self.low_val)
        hx = self._val_to_x(self.high_val)
        if abs(event.x() - lx) < abs(event.x() - hx):
            self.dragging = "low"
        else:
            self.dragging = "high"
        self.update()
    
    def mouseMoveEvent(self, event: QMouseEvent):
        if self.dragging is None:
            return
        v = self._x_to_val(event.x())
        if self.dragging == "low":
            self.low_val = min(v, self.high_val - 1.0)  # keep ≥1°C gap
        else:
            self.high_val = max(v, self.low_val + 1.0)
        self.update()
        self.values_changed.emit(self.low_val, self.high_val)
    
    def mouseReleaseEvent(self, event: QMouseEvent):
        if event.button() == Qt.LeftButton:
            self.dragging = None
            self.update()
    
    def get_values(self) -> Tuple[float, float]:
        """Returns (heater, cooling) temperatures"""
        return (self.low_val, self.high_val)
    
    def set_values(self, low: float, high: float):
        """Set the slider values"""
        self.low_val = max(self.min_val, min(self.max_val, float(low)))
        self.high_val = max(self.min_val, min(self.max_val, float(high)))
        if self.high_val <= self.low_val:
            self.high_val = self.low_val + 1.0
        self.update()

class ACController(QObject):
    status_signal = pyqtSignal(str)
    data_signal = pyqtSignal(float)  # emits current temperature
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.modbus_controller = ACModbusController()
        self.connected = False
        
        # Group box for AC Controller
        self.widget = QGroupBox("🌡️ AC Controller")
        self.widget.setStyleSheet("""
            QGroupBox { color: white; }
            QLabel    { color: white; }
            QLineEdit { color: white; }
            QPushButton { color: white; }
        """)
        layout = QVBoxLayout()
        layout.setSpacing(12)

        # Connection row with indicator
        conn_layout = QHBoxLayout()
        conn_layout.setSpacing(8)
        # Connection status indicator (small colored circle)
        self.conn_indicator = QLabel("●")
        self.conn_indicator.setStyleSheet("font-size: 16px; color: #e74c3c;")
        self.conn_indicator.setFixedWidth(20)
        conn_layout.addWidget(self.conn_indicator)
        
        self.connect_btn = QPushButton("Connect")
        self.connect_btn.clicked.connect(self.connect_controller)
        conn_layout.addWidget(self.connect_btn)
        conn_layout.addStretch()
        layout.addLayout(conn_layout)

        # Current temperature display
        temp_frame = QHBoxLayout()
        temp_frame.addWidget(QLabel("Temperature:"))
        self.cur_lbl = QLabel("--.- °C")
        self.cur_lbl.setStyleSheet("font-size: 16px; font-weight: bold; color: #4ECDC4;")
        temp_frame.addWidget(self.cur_lbl)
        temp_frame.addStretch()
        temp_frame.addWidget(QLabel("(updates every 5s)"))
        temp_frame.addStretch()
        layout.addLayout(temp_frame)

        # Range slider for Heater/Cooling
        range_label = QLabel("Temperature Range (Heater → Cooling)")
        range_label.setStyleSheet("font-weight: bold;")
        layout.addWidget(range_label)
        
        self.range_slider = RangeSlider(self.widget, min_val=0.0, max_val=60.0, 
                                        init_low=15.0, init_high=20.0, step=0.5)
        self.range_slider.values_changed.connect(self._on_slider_changed)
        layout.addWidget(self.range_slider)
        
        self.apply_range_btn = QPushButton("Apply Range")
        self.apply_range_btn.setEnabled(False)
        self.apply_range_btn.clicked.connect(self.apply_range)
        layout.addWidget(self.apply_range_btn)

        # Power control
        power_frame = QHBoxLayout()
        self.power_checkbox = QCheckBox("AC Power")
        self.power_checkbox.setEnabled(False)
        self.power_checkbox.stateChanged.connect(self.on_power_changed)
        power_frame.addWidget(self.power_checkbox)
        power_frame.addStretch()
        layout.addLayout(power_frame)

        self.widget.setLayout(layout)

        self.latest_temp = 0.0
        self.power_on = False
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._update_temp)

        # Get port from config if available
        self.port = None
        if parent is not None and hasattr(parent, 'config'):
            self.port = parent.config.get("com_ports", {}).get("ac_controller")

    def connect_controller(self):
        if self.connected:
            # Disconnect
            try:
                self.modbus_controller.close()
            except:
                pass
            self.timer.stop()
            self.connected = False
            self.connect_btn.setText("Connect")
            self.apply_range_btn.setEnabled(False)
            self.power_checkbox.setEnabled(False)
            self._update_connection_indicator(False)
            self.status_signal.emit("AC controller disconnected")
            return

        # Use configured port or default
        port = self.port or DEFAULT_PORT
        self.modbus_controller.port = port

        # Try to connect
        try:
            if not self.modbus_controller.connect():
                self.status_signal.emit("Failed to connect to AC controller")
                self._update_connection_indicator(False)
                return
            
            # Read current power state
            try:
                flags = self.modbus_controller.read_enable_flags()
                self.power_on = self.modbus_controller._power_on_from_flags(flags)
            except:
                self.power_on = False
            self.power_checkbox.setChecked(self.power_on)
            
            # Start periodic update
            self.timer.start(5000)  # Update every 5 seconds
            self.connected = True
            self.apply_range_btn.setEnabled(True)
            self.power_checkbox.setEnabled(True)
            self.connect_btn.setText("Disconnect")
            self._update_connection_indicator(True)
            self.status_signal.emit(f"AC controller connected on {port}")
            self._update_temp()
            
        except Exception as e:
            self.status_signal.emit(f"AC controller connection failed: {e}")
            self._update_connection_indicator(False)
            try:
                self.modbus_controller.close()
            except:
                pass

    def _update_temp(self):
        if not self.connected:
            return
        try:
            temp = self.modbus_controller.read_sensor_c()
            self.latest_temp = temp
            self.cur_lbl.setText(f"{temp:.1f} °C")
            self.data_signal.emit(temp)
        except Exception as e:
            self.cur_lbl.setText("--.- °C")
            self.status_signal.emit(f"Read error: {e}")

    def _on_slider_changed(self, low: float, high: float):
        """Called when slider values change (for potential live updates)"""
        pass
    
    def apply_range(self):
        """Apply the range slider values to the AC controller"""
        if not self.connected:
            self.status_signal.emit("Not connected to AC controller")
            return
        try:
            heater, cooling = self.range_slider.get_values()
            self.modbus_controller.write_setpoints_c(heater_c=heater, cooling_c=cooling)
            self.status_signal.emit(f"Range applied: Heater {heater:.1f}°C → Cooling {cooling:.1f}°C")
        except Exception as e:
            self.status_signal.emit(f"Set range failed: {e}")
    
    def on_power_changed(self, state):
        """Handle power checkbox state change"""
        if not self.connected:
            self.power_checkbox.setChecked(False)
            self.status_signal.emit("Not connected to AC controller")
            return
        try:
            self.power_on = (state == Qt.Checked)
            self.modbus_controller.write_flags(power_on=self.power_on, force_net=None)
            self.status_signal.emit(f"Power {'ON' if self.power_on else 'OFF'}")
        except Exception as e:
            self.status_signal.emit(f"Power toggle failed: {e}")
            # Revert checkbox state on error
            self.power_checkbox.blockSignals(True)
            self.power_checkbox.setChecked(not self.power_on)
            self.power_checkbox.blockSignals(False)
    
    def _update_connection_indicator(self, connected: bool):
        """Update the connection status indicator"""
        if connected:
            self.conn_indicator.setStyleSheet("font-size: 16px; color: #2ecc71;")
        else:
            self.conn_indicator.setStyleSheet("font-size: 16px; color: #e74c3c;")

    @property
    def current_temp(self):
        return self.latest_temp

    def is_connected(self):
        return self.connected

