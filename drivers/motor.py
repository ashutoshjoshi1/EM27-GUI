# drivers/motor.py

import time
import serial
import os
from datetime import datetime
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

# ── Helper function to log motor responses ─────────────────────────────────
def log_motor_response(command, angle, response, is_retry=False):
    """Log motor responses to a file for debugging"""
    log_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs")
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, "motor_responses.log")
    
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    retry_str = " [RETRY]" if is_retry else ""
    log_entry = f"{timestamp} | {command} | Angle: {angle}° | Response: {response}{retry_str}\n"
    
    try:
        with open(log_file, 'a') as f:
            f.write(log_entry)
    except Exception as e:
        print(f"Failed to log motor response: {e}")

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
        16 registers (32 bytes) starting at 0x0058.
        """
        try:
            # Check if serial port is open
            if not self.ser.is_open:
                self.ser.open()
                
            # 1) Build the "real" payload
            angle_b = angle.to_bytes(4, 'big', signed=True)
            speed_b = TRACKER_SPEED.to_bytes(4, 'big', signed=True)
            mid_b   = bytes([0x00,0x0F,0x1F,0x40, 0x00,0x0F,0x1F,0x40])
            curr_b  = TRACKER_CURRENT.to_bytes(4, 'big', signed=True)
            end_b   = bytes([0x00,0x00,0x00,0x01])

            payload = bytes([0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x01]) + angle_b + speed_b + mid_b + curr_b + end_b

            # 2) Use the original fixed header
            header = bytes([
                SLAVE_ID,       # Unit ID
                0x10,           # Function: Write Multiple Registers
                0x00, 0x58,     # Start addr = 0x0058
                0x00, 0x10,     # Register count = 16 (0x0010)
                0x20            # Byte count    = 32 (0x20)
            ])

            packet = header + payload
            crc    = modbus_crc16(packet).to_bytes(2, 'little')
            full   = packet + crc

            # flush & settle
            self.ser.reset_input_buffer()
            self.ser.reset_output_buffer()
            time.sleep(0.05)

            # If using RTS for RS485 direction control, manually toggle it
            if not hasattr(self.ser, 'rs485_mode'):
                self.ser.setRTS(True)
                time.sleep(0.01)

            # send & wait
            self.ser.write(full)
            
            # If using RTS for RS485 direction control, manually toggle it
            if not hasattr(self.ser, 'rs485_mode'):
                time.sleep(0.01)
                self.ser.setRTS(False)
            
            time.sleep(0.1)

            # Read with timeout handling
            start_time = time.time()
            resp = bytearray()
            while (time.time() - start_time) < 0.5:
                if self.ser.in_waiting:
                    new_data = self.ser.read(self.ser.in_waiting)
                    if new_data:
                        resp.extend(new_data)
                        if len(resp) >= 8:
                            break
                time.sleep(0.01)

            # Accept various response patterns as valid
            resp_hex = resp.hex() if resp else ""
            
            # Log response for debugging
            print(f"Motor move_to response: {resp_hex} (angle: {angle})")
            log_motor_response("move_to", angle, resp_hex)
            
            # Check for known valid response patterns
            if (len(resp) >= 3 and resp[0] == SLAVE_ID and resp[1] == 0x10) or \
               resp_hex.startswith('7e25') or \
               resp_hex.startswith('0190044dc3'):
                return True, f"✔ Moved to {resp_hex}°"
            else:
                return False, f"⚠ No ACK from motor. Response: {resp_hex}"
        except Exception as e:
            return False, f"❌ Move failed: {e}"

    def clear_alarm(self) -> bool:
        """
        Clear alarm on the motor driver. 
        Returns True if successful, False otherwise.
        """
        try:
            if not self.ser.is_open:
                self.ser.open()
            
            # Build Modbus function 5 (Write Single Coil) request to clear alarm
            # Common alarm clear address is 0x0801 (Alarm Reset)
            req = bytes([
                SLAVE_ID, 0x05,  # Function: Write Single Coil
                0x08, 0x01,      # Address: 0x0801 (Alarm Reset)
                0xFF, 0x00       # Value: ON (0xFF00) to clear alarm
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
            time.sleep(0.1)
            
            # Read response
            resp = self.ser.read(8)
            if len(resp) >= 4:
                return True
            return False
        except Exception as e:
            print(f"Clear alarm failed: {e}")
            return False

    def stop(self) -> bool:
        """
        Send stop command to halt motion gracefully.
        Returns True if successful, False otherwise.
        """
        try:
            if not self.ser.is_open:
                self.ser.open()
            
            # Build Modbus stop command - typically function 6 (Write Single Register)
            # Use register 0x0088 (Velocity Command) with value 0
            req = bytes([
                SLAVE_ID, 0x06,  # Function: Write Single Register
                0x00, 0x88,      # Address: 0x0088 (Velocity Command)
                0x00, 0x00       # Value: 0 (stop)
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
            time.sleep(0.1)
            
            # Read response
            resp = self.ser.read(8)
            if len(resp) >= 4:
                return True
            return False
        except Exception as e:
            print(f"Stop command failed: {e}")
            return False

    def is_busy(self) -> bool:
        """
        Check if motor is currently moving.
        Returns True if busy, False if idle.
        """
        try:
            if not self.ser.is_open:
                return False
            
            # Build Modbus function 3 (Read Holding Registers) request
            # Read register 0x0074 (Operating Status)
            req = bytes([
                SLAVE_ID, 0x03,  # Function: Read Holding Registers
                0x00, 0x74,      # Address: 0x0074 (Operating Status)
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
            time.sleep(0.1)
            
            # Read response
            resp = self.ser.read(8)
            if len(resp) >= 5 and resp[0] == SLAVE_ID and resp[1] == 0x03:
                # Bit 0 typically indicates motion status
                status_value = (resp[3] << 8) | resp[4]
                is_moving = bool(status_value & 0x01)
                return is_moving
            return False
        except Exception as e:
            print(f"Check busy failed: {e}")
            return False

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
