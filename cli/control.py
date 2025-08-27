import os
import sys
import mysql.connector
import paho.mqtt.publish as publish

MYSQL_HOST = os.environ.get("MYSQL_HOST", "mysql")
MYSQL_USER = os.environ.get("MYSQL_USER", "iotuser")
MYSQL_PASSWORD = os.environ.get("MYSQL_PASSWORD", "iotpass")
MYSQL_DB = os.environ.get("MYSQL_DB", "iotdb")

MQTT_BROKER = os.environ.get("MQTT_BROKER", "mosquitto")
MQTT_PORT = int(os.environ.get("MQTT_PORT", 1883))

def show_data():
    db = mysql.connector.connect(
        host=MYSQL_HOST, user=MYSQL_USER, password=MYSQL_PASSWORD, database=MYSQL_DB
    )
    cursor = db.cursor(dictionary=True)
    cursor.execute("SELECT * FROM sensor_data ORDER BY timestamp DESC LIMIT 10")
    rows = cursor.fetchall()
    for r in rows:
        print(r)

def control_device(device_id, state):
    payload = {"actuator_id": device_id, "state": state}
    publish.single(f"actuators/{device_id}", str(payload), hostname=MQTT_BROKER, port=MQTT_PORT)
    print(f"Sent command: {device_id} -> {state}")

if __name__ == "__main__":
    if len(sys.argv) == 1:
        print("Usage:")
        print("  python control.py show-data")
        print("  python control.py set <device_id> <on|off>")
        sys.exit(0)

    cmd = sys.argv[1]
    if cmd == "show-data":
        show_data()
    elif cmd == "set":
        if len(sys.argv) != 4:
            print("Usage: python control.py set <device_id> <on|off>")
            sys.exit(1)
        control_device(sys.argv[2], sys.argv[3])
    else:
        print("Unknown command")