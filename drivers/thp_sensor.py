import serial
import json
import time

def read_thp_sensor_data(port_name, baud_rate=9600, timeout=1):
    try:
        ser = serial.Serial(port_name, baud_rate, timeout=timeout)
        time.sleep(1)
        ser.write(b'p\r\n')

        response = ""
        start_time = time.time()
        while time.time() - start_time < timeout:
            if ser.in_waiting > 0:
                line = ser.readline().decode('utf-8').strip()
                response += line
                try:
                    data = json.loads(response)
                    break
                except json.JSONDecodeError:
                    continue
        ser.close()

        data = json.loads(response)
        sensors = data.get('Sensors', [])
        if sensors:
            s = sensors[0]
            return {
                'sensor_id': s.get('ID'),
                'temperature': s.get('Temperature'),
                'humidity': s.get('Humidity'),
                'pressure': s.get('Pressure')
            }
        return None
    except Exception as e:
        print(f"THP sensor error: {e}")
        return None
