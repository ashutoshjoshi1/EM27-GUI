import time
import serial
from motor import MotorDriver

# =================== User-tunable pacing ===================
COM_PORT = 'COM7'
BAUD_RATE = 9600

OPEN_ANGLE = -2250
CLOSE_ANGLE = -30
CYCLE_COUNT = 4000

# Give each move at most this much time before reversing
PER_MOVE_BUDGET_SEC = 5.0   # <-- your 5 seconds
# Small settle after stop() so the driver is ready to accept the next command
POST_STOP_SETTLE_SEC = 0.35
# Serial / RS-485 hygiene
INTER_CMD_GAP_SEC = 0.12
SERIAL_TIMEOUT_SEC = 1.5
WRITE_TIMEOUT_SEC = 1.5
POLL_INTERVAL_SEC = 0.12
# ===========================================================

def _drain_serial(sp):
    try:
        sp.reset_input_buffer()
        sp.reset_output_buffer()
    except Exception:
        pass

def _rs485_config(sp):
    try:
        import serial.rs485 as rs485
        if hasattr(rs485, "RS485Settings"):
            sp.rs485_mode = rs485.RS485Settings(
                rts_level_for_tx=True,
                rts_level_for_rx=False,
                loopback=False,
                delay_before_tx=0,
                delay_before_rx=0,
            )
        else:
            if hasattr(sp, "setRTS"):
                sp.setRTS(False)
    except Exception:
        try:
            if hasattr(sp, "setRTS"):
                sp.setRTS(False)
        except Exception:
            pass

def _supports(obj, name):
    return hasattr(obj, name) and callable(getattr(obj, name))

def _try_clear_alarm(md: MotorDriver):
    if _supports(md, "clear_alarm"):
        try:
            md.clear_alarm()
            time.sleep(0.2)
            return True
        except Exception:
            return False
    return False

def _budget_wait_or_stop(md: MotorDriver, budget_sec: float):
    """
    Wait up to 'budget_sec' for motion to finish; if still moving, send a soft stop.
    """
    start = time.time()
    has_is_busy = _supports(md, "is_busy")

    # If we can poll busy, do so within the budget window
    if has_is_busy:
        while (time.time() - start) < budget_sec:
            try:
                if not md.is_busy():
                    return  # Finished within budget
            except Exception:
                break
            time.sleep(POLL_INTERVAL_SEC)
    else:
        # No motion status; just wait the budget
        time.sleep(budget_sec)

    # Budget exhausted: request a soft stop before reversing
    if _supports(md, "stop"):
        try:
            md.stop()  # decelerate to a controlled stop
        except Exception:
            pass

    # Best-effort wait until not busy (short)
    t2 = time.time()
    if has_is_busy:
        while (time.time() - t2) < 1.2:  # brief grace period
            try:
                if not md.is_busy():
                    break
            except Exception:
                break
            time.sleep(POLL_INTERVAL_SEC)

    time.sleep(POST_STOP_SETTLE_SEC)

def _paced_move(md: MotorDriver, sp: serial.Serial, target_deg: float):
    """
    Send a move with inter-command spacing and alarm clear retry.
    """
    time.sleep(INTER_CMD_GAP_SEC)
    _drain_serial(sp)

    ok, msg = md.move_to(target_deg)
    if not ok:
        _try_clear_alarm(md)
        time.sleep(0.25)
        _drain_serial(sp)
        time.sleep(INTER_CMD_GAP_SEC)
        ok, msg = md.move_to(target_deg)
    return ok, msg

def run_motor_cycle():
    sp = None
    md = None
    try:
        print(f"Connecting {COM_PORT} @ {BAUD_RATE}…")
        sp = serial.Serial(
            COM_PORT,
            baudrate=BAUD_RATE,
            timeout=SERIAL_TIMEOUT_SEC,
            write_timeout=WRITE_TIMEOUT_SEC,
        )
        _rs485_config(sp)
        _drain_serial(sp)

        md = MotorDriver(sp)

        # Sane start: stop motion & clear alarms
        if _supports(md, "stop"):
            try: md.stop()
            except Exception: pass
        _try_clear_alarm(md)

        # Optional: move once to CLOSE to start from a known side, but do it within budget
        print("Homing to CLOSE side (budgeted)…")
        ok, msg = _paced_move(md, sp, CLOSE_ANGLE)
        print(f"Home command: {msg}")
        _budget_wait_or_stop(md, PER_MOVE_BUDGET_SEC)

        for i in range(CYCLE_COUNT):
            print(f"\n— Cycle {i+1}/{CYCLE_COUNT} —")

            print(f"Opening to {OPEN_ANGLE}° (budget {PER_MOVE_BUDGET_SEC}s)…")
            ok, msg = _paced_move(md, sp, OPEN_ANGLE)
            print(f"Response: {msg}")
            if not ok:
                print("Move command failed; attempting alarm clear and stopping.")
                _try_clear_alarm(md)
                if _supports(md, "stop"):
                    try: md.stop()
                    except Exception: pass
                break
            _budget_wait_or_stop(md, PER_MOVE_BUDGET_SEC)

            print(f"Closing to {CLOSE_ANGLE}° (budget {PER_MOVE_BUDGET_SEC}s)…")
            ok, msg = _paced_move(md, sp, CLOSE_ANGLE)
            print(f"Response: {msg}")
            if not ok:
                print("Move command failed; attempting alarm clear and stopping.")
                _try_clear_alarm(md)
                if _supports(md, "stop"):
                    try: md.stop()
                    except Exception: pass
                break
            _budget_wait_or_stop(md, PER_MOVE_BUDGET_SEC)

        print("\n✔ Done.")

    except serial.SerialException as e:
        print(f"✖ Serial error on {COM_PORT}: {e}")
    except Exception as e:
        print(f"✖ Unexpected error: {e}")
    finally:
        if sp and sp.is_open:
            sp.close()
            print("Serial port closed.")

if __name__ == "__main__":
    run_motor_cycle()
