"""
tc36_25.py  –  Light‑weight driver for TE Technology TC‑36‑25‑RS232
Tested with Python ≥3.9 and PySerial ≥3.5 on Windows 10/11
"""

import time
import serial
from typing import Optional

STX = "*"           # 0x2A
ETX = "\r"          # 0x0D  (carriage‑return)
ACK = "^"           # 0x5E
ADDR = "00"         # Controller is always address 00  :contentReference[oaicite:0]{index=0}&#8203;:contentReference[oaicite:1]{index=1}

# Command codes (Appendix C)
CMD_INPUT1                  = "01"   # read actual temperature  :contentReference[oaicite:2]{index=2}&#8203;:contentReference[oaicite:3]{index=3}
CMD_DESIRED_CONTROL_VALUE   = "03"   # read effective set‑point
CMD_SET_TYPE_DEFINE         = "29"   # write 0 → computer‑set value  :contentReference[oaicite:4]{index=4}&#8203;:contentReference[oaicite:5]{index=5}
CMD_FIXED_DESIRED_SETTING   = "1c"   # write / read fixed set‑point   :contentReference[oaicite:6]{index=6}&#8203;:contentReference[oaicite:7]{index=7}
CMD_POWER_ON_OFF            = "2d"   # write 1=on, 0=off            :contentReference[oaicite:8]{index=8}&#8203;:contentReference[oaicite:9]{index=9}

class TC36_25:
    """
    Thin, blocking interface – add your own threading / async wrapper if needed.
    """

    def __init__(self, port: str = "COM16", delay_char: float = 0.001):
        """
        delay_char : seconds to wait after every byte – controller
                     needs a little think‑time :contentReference[oaicite:10]{index=10}&#8203;:contentReference[oaicite:11]{index=11}
        """
        self.delay_char = delay_char
        self.ser = serial.Serial(
            port=port,
            baudrate=9600,
            bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            timeout=1.0,          # 1 s read timeout
            write_timeout=1.0
        )

    # -------------  Low–level helpers  ---------------------------------

    @staticmethod
    def _to_hex32(value: int) -> str:
        """8‑digit, lowercase, zero‑padded two’s‑complement hex."""
        return f"{value & 0xFFFFFFFF:08x}"

    @staticmethod
    def _csum(payload: str) -> str:
        """8‑bit mod‑256 sum of ASCII byte values, returned as 2‑char hex."""
        total = sum(ord(c) for c in payload) & 0xFF
        return f"{total:02x}"

    def _tx(self, cmd: str, value_hex: str) -> str:
        payload = ADDR + cmd + value_hex
        frame = STX + payload + self._csum(payload) + ETX
        for ch in frame:
            self.ser.write(ch.encode())
            time.sleep(self.delay_char)

        # Reply: *DDDDDDDDSS^  (12 bytes)
        reply = self.ser.read_until(ACK.encode()).decode()
        if len(reply) != 12 or reply[0] != STX or reply[-1] != ACK:
            raise RuntimeError(f"Malformed reply: {reply!r}")

        data, rcv_sum = reply[1:9], reply[9:11]
        if rcv_sum != self._csum(data):
            raise RuntimeError("Checksum mismatch")

        return data.lower()


    def _write(self, cmd: str, value_hex: str = "00000000"):
        self._tx(cmd, value_hex)

    def _read(self, cmd: str) -> str:
        return self._tx(cmd, "00000000")

    # -------------  Public API  ----------------------------------------

    def enable_computer_setpoint(self) -> None:
        """Put controller in ‘computer set‑value’ mode (cmd 29 = 0)."""
        self._write(CMD_SET_TYPE_DEFINE, "00000000")

    def power(self, on: bool) -> None:
        """Turn main output on/off (True = on)."""
        self._write(CMD_POWER_ON_OFF, self._to_hex32(1 if on else 0))

    # ---- set / get temperatures ---------------------------------------

    def get_temperature(self) -> float:
        """Primary sensor temperature in °C (or °F if controller so set)."""
        hexval = self._read(CMD_INPUT1)
        return int(hexval, 16) / 100.0

    def get_setpoint(self) -> float:
        """Current effective set‑point (whatever source provides it)."""
        hexval = self._read(CMD_DESIRED_CONTROL_VALUE)
        return int(hexval, 16) / 100.0

    def set_setpoint(self, temp_c: float) -> None:
        """
        Change the set‑point *immediately*.  Controller must already be in
        computer‑set mode (use enable_computer_setpoint once at startup).
        """
        raw = round(temp_c * 100)
        self._write(CMD_FIXED_DESIRED_SETTING, self._to_hex32(raw))

    # -------------------------------------------------------------------

    def close(self):
        self.ser.close()

    # Context‑manager sugar
    def __enter__(self): return self
    def __exit__(self, exc_type, exc, tb): self.close()

# --------------------  Quick demo  -------------------------------------

if __name__ == "__main__":
    with TC36_25("COM16") as tc:
        tc.enable_computer_setpoint()   # one‑time per session
        tc.set_setpoint(10.00)          # °C
        tc.power(True)                  # enable output
        while True:
            print(f"T = {tc.get_temperature():.2f} °C   "
                  f"SP = {tc.get_setpoint():.2f} °C")
            time.sleep(2)
