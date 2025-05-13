# drivers/motor.py

import time
import serial
from PyQt5.QtCore import QThread, pyqtSignal

# ── Protocol constants ────────────────────────────────────────────────────────
SLAVE_ID        = 0x01
START_ADDR_HI   = 0x00
START_ADDR_LO   = 0x58   # register 0x0058
READ_COUNT_HI   = 0x00
READ_COUNT_LO   = 0x01   # for connect check, read 1 register

# these for move payload
TRACKER_SPEED   = 100
TRACKER_CURRENT = 100

# ── CRC helper ───────────────────────────────────────────────────────────────
def modbus_crc16(data: bytes) -> int:
    crc = 0xFFFF
    for b in data:
        crc ^= b
        for _ in range(8):
            if crc & 1:
                crc >>= 1
                crc ^= 0xA001
            else:
                crc >>= 1
    return crc

# ── Baud‐detect thread ───────────────────────────────────────────────────────
class MotorConnectThread(QThread):
    """
    Tries a Modbus Read Holding Registers at various baud rates.
    Emits (serial_obj, baud, message).
    """
    result_signal = pyqtSignal(object, int, str)

    def __init__(self, port_name, parent=None):
        super().__init__(parent)
        self.port_name  = port_name
        self.baud_rates = [9600, 19200, 38400, 57600, 115200]
        self.timeout    = 0.5

    def run(self):
        # build a Modbus function‐3 read request
        req = bytes([
            SLAVE_ID, 0x03,
            START_ADDR_HI, START_ADDR_LO,
            READ_COUNT_HI, READ_COUNT_LO
        ])
        crc = modbus_crc16(req).to_bytes(2, 'little')
        packet = req + crc

        for baud in self.baud_rates:
            try:
                ser = serial.Serial(self.port_name, baudrate=baud, timeout=self.timeout)
                ser.reset_input_buffer(); ser.reset_output_buffer()
                time.sleep(0.02)

                ser.write(packet)
                ser.flush()
                time.sleep(0.05)

                resp = ser.read(5)  # expect [ID,0x03,bytecount,hi,lo]
                if len(resp) >= 5 and resp[0] == SLAVE_ID and resp[1] == 0x03:
                    self.result_signal.emit(ser, baud, f"✔ Motor alive at {baud} baud")
                    return
                ser.close()
            except Exception:
                continue

        self.result_signal.emit(None, None, "✖ No motor response at any baud rate.")

# ── High‐level driver ───────────────────────────────────────────────────────
class MotorDriver:
    """
    Wraps an open serial.Serial and sends Modbus‐write commands.
    """
    def __init__(self, serial_obj):
        self.ser = serial_obj

    def move_to(self, angle: int) -> (bool, str):
        """
        Sends a 0x10 Write Multiple Registers command of exactly
        18 registers (36 bytes) starting at 0x0058, padded to length.
        """
        # 1) Build the “real” 18-reg payload (we only use some of it, the rest is zero)
        angle_b = angle.to_bytes(4, 'big', signed=True)
        speed_b = TRACKER_SPEED.to_bytes(4, 'big', signed=True)
        mid_b   = bytes([0x00,0x00,0x1F,0x40, 0x00,0x00,0x1F,0x40])
        curr_b  = TRACKER_CURRENT.to_bytes(4, 'big', signed=True)
        end_b   = bytes([0x00,0x00,0x00,0x01, 0x00,0x00,0x00,0x01])

        payload = angle_b + speed_b + mid_b + curr_b + end_b
        # pad out to 36 bytes total
        pad_len = 36 - len(payload)
        if pad_len > 0:
            payload += bytes(pad_len)

        # 2) Use the original fixed header: 0x12 regs, 0x24 data bytes
        header = bytes([
            SLAVE_ID,       # Unit ID
            0x10,           # Function: Write Multiple Registers
            0x00, 0x58,     # Start addr = 0x0058
            0x00, 0x12,     # Register count = 18 (0x0012)
            0x24            # Byte count    = 36 (0x24)
        ])

        packet = header + payload
        crc    = modbus_crc16(packet).to_bytes(2, 'little')
        full   = packet + crc

        try:
            # flush & settle
            self.ser.reset_input_buffer()
            self.ser.reset_output_buffer()
            time.sleep(0.02)

            # send & wait
            self.ser.write(full)
            self.ser.flush()
            time.sleep(0.05)

            resp = self.ser.readline()
            if resp and len(resp) >= 3 and resp[1] == 0x10:
                return True, f"✔ Moved to {angle}°"
            else:
                return False, "⚠ No ACK from motor."
        except Exception as e:
            return False, f"❌ Move failed: {e}"
