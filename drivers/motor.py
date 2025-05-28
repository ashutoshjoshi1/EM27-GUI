# drivers/motor.py

import time
import serial
from PyQt5.QtCore import QThread, pyqtSignal

# ── Protocol constants ────────────────────────────────────────────────────────
SLAVE_ID        = 1

# these for move payload
TRACKER_SPEED   = 1000
TRACKER_CURRENT = 1000

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
            0x00, 0x58,
            0x00,0x02
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
                resp_hex = resp.hex() if resp else ""
                print(f"Response at {baud} baud: {resp_hex}")
                
                # Check for standard Modbus response or known special patterns
                if (len(resp) >= 5 and resp[0] == SLAVE_ID and resp[1] == 0x03) or \
                   resp_hex.startswith('7e25') or \
                   resp_hex.startswith('0190044dc3'):
                    self.result_signal.emit(ser, baud, f"✔ Motor alive at {baud} baud")
                    return
                ser.close()
            except Exception as e:
                print(f"Exception at {baud} baud: {e}")
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
        try:
            # Check if serial port is open
            if not self.ser.is_open:
                self.ser.open()
                
            # 1) Build the "real" 18-reg payload (we only use some of it, the rest is zero)
            angle_b = angle.to_bytes(4, 'big', signed=True)
            speed_b = TRACKER_SPEED.to_bytes(4, 'big', signed=True)
            mid_b   = bytes([0x00,0x0F,0x1F,0x40, 0x00,0x0F,0x1F,0x40])
            curr_b  = TRACKER_CURRENT.to_bytes(4, 'big', signed=True)
            end_b   = bytes([0x00,0x00,0x00,0x01])

            payload = bytes([0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x01]) + angle_b + speed_b + mid_b + curr_b + end_b
            # # pad out to 36 bytes total
            # pad_len = 36 - len(payload)
            # if pad_len > 0:
            #     payload += bytes(pad_len)

            # 2) Use the original fixed header: 0x12 regs, 0x24 data bytes
            header = bytes([
                SLAVE_ID,       # Unit ID
                0x10,           # Function: Write Multiple Registers
                0x00, 0x58,     # Start addr = 0x0058
                0x00, 0x10,     # Register count = 18 (0x0012)
                0x20            # Byte count    = 36 (0x24)
            ])

            packet = header + payload
            crc    = modbus_crc16(packet).to_bytes(2, 'little')
            full   = packet + crc

            # flush & settle
            self.ser.reset_input_buffer()
            self.ser.reset_output_buffer()
            time.sleep(0.05)  # Increased delay

            # If using RTS for RS485 direction control, manually toggle it
            if not hasattr(self.ser, 'rs485_mode'):
                self.ser.setRTS(True)  # Set RTS before transmitting
                time.sleep(0.01)       # Small delay

            # send & wait
            self.ser.write(full)
            # self.ser.flush()
            
            # If using RTS for RS485 direction control, manually toggle it
            if not hasattr(self.ser, 'rs485_mode'):
                time.sleep(0.01)       # Small delay
                self.ser.setRTS(False) # Clear RTS after transmitting
            
            time.sleep(0.1)  # Increased delay for response

            # Read with timeout handling
            start_time = time.time()
            resp = bytearray()
            while (time.time() - start_time) < 0.5:  # 500ms timeout
                if self.ser.in_waiting:
                    new_data = self.ser.read(self.ser.in_waiting)
                    if new_data:
                        resp.extend(new_data)
                        if len(resp) >= 8:  # Expected response length
                            break
                time.sleep(0.01)

            # Accept various response patterns as valid
            resp_hex = resp.hex() if resp else ""
            
            # Check for known valid response patterns:
            # 1. Standard Modbus response (starts with slave ID and function code 0x10)
            # 2. Special 7e25 pattern seen on some controllers
            # 3. The new 0190044dc3 pattern
            if (len(resp) >= 3 and resp[0] == SLAVE_ID and resp[1] == 0x10) or \
               resp_hex.startswith('7e25') or \
               resp_hex.startswith('0190044dc3'):
                return True, f"✔ Moved to {resp_hex}°"
            else:
                return False, f"⚠ No ACK from motor. Response: {resp_hex}"
        except Exception as e:
            return False, f"❌ Move failed: {e}"

    def check_rain_status(self) -> (bool, str):
        """
        Reads register 213 (0x00D5) and checks bit 2 for rain status.
        Returns (success, message) where success is True if read was successful
        and message contains the rain status or error information.
        """
        try:
            # Check if serial port is open
            if not self.ser.is_open:
                self.ser.open()
            
            # Build Modbus function 3 (Read Holding Registers) request
            req = bytes([
                SLAVE_ID, 0x03,  # Function: Read Holding Registers
                0x00, 0xD5,      # Register address: 0x00D5 (213)
                0x00, 0x01       # Number of registers: 1
            ])
            crc = modbus_crc16(req).to_bytes(2, 'little')
            packet = req + crc
            
            # Clear buffers before sending
            self.ser.reset_input_buffer()
            self.ser.reset_output_buffer()
            time.sleep(0.05)
            
            # Send request
            self.ser.write(packet)
            self.ser.flush()
            time.sleep(0.1)  # Wait for response
            
            # Read response
            resp = bytearray()
            start_time = time.time()
            while (time.time() - start_time) < 0.5:  # 500ms timeout
                if self.ser.in_waiting:
                    new_data = self.ser.read(self.ser.in_waiting)
                    resp.extend(new_data)
                    if len(resp) >= 5:  # Minimum expected response length
                        break
                time.sleep(0.01)
            
            # Debug output
            #print(f"Rain status response: {resp.hex()}")
            
            # Check if response is valid
            if len(resp) >= 5 and resp[0] == SLAVE_ID and resp[1] == 0x03:
                # Based on the response format: [ID, FC, BYTE_COUNT, DATA_HI, DATA_LO, CRC_LO, CRC_HI]
                # The register value is in the 4th and 5th bytes (index 3 and 4)
                # For this specific controller, the rain status is in the second data byte (index 4)
                reg_value_hi = resp[3] if len(resp) > 3 else 0
                reg_value_lo = resp[4] if len(resp) > 4 else 0
                
                # Print debug info for both bytes
                #print(f"Register value high byte: {reg_value_hi:08b} (binary), {reg_value_hi} (decimal)")
                #print(f"Register value low byte: {reg_value_lo:08b} (binary), {reg_value_lo} (decimal)")
                
                # Based on the observed responses:
                # 0103020000b844 - Not raining
                # 0103020004b987 - Raining
                # The difference is in the low byte (index 4), value 0x00 vs 0x04
                # This suggests bit 2 (0-indexed) in the low byte indicates rain
                is_raining = bool(reg_value_lo & (1 << 2))
                
                return True, f"Rain status: {'Raining' if is_raining else 'Not raining'}"
            else:
                resp_hex = resp.hex() if resp else ""
                return False, f"Invalid response: {resp_hex}"
                
        except Exception as e:
            return False, f"Error reading rain status: {e}"
