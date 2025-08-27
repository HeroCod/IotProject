import os
import json
import paho.mqtt.client as mqtt
import mysql.connector
import paho.mqtt.publish as publish

MQTT_BROKER = os.environ.get("MQTT_BROKER", "mosquitto")
MQTT_PORT = int(os.environ.get("MQTT_PORT", 1883))

MYSQL_HOST = os.environ.get("MYSQL_HOST", "mysql")
MYSQL_USER = os.environ.get("MYSQL_USER", "iotuser")
MYSQL_PASSWORD = os.environ.get("MYSQL_PASSWORD", "iotpass")
MYSQL_DB = os.environ.get("MYSQL_DB", "iotdb")

# connect to MySQL
db = mysql.connector.connect(
    host=MYSQL_HOST,
    user=MYSQL_USER,
    password=MYSQL_PASSWORD,
    database=MYSQL_DB
)
cursor = db.cursor()
cursor.execute("""
CREATE TABLE IF NOT EXISTS sensor_data (
  id INT AUTO_INCREMENT PRIMARY KEY,
  device_id VARCHAR(50),
  payload JSON,
  timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
""")
db.commit()

### Simple ML model (hard-coded threshold as "trained model")
def predict_led_state(lux_value: int) -> str:
    # Example: if lux is less than 40, turn ON LED, else turn OFF (to save energy)
    return "on" if lux_value < 40 else "off"

def on_message(client, userdata, msg):
    try:
        payload = json.loads(msg.payload.decode())
        device_id = payload.get("sensor_id", "unknown")
        lux = payload.get("lux", 0)

        # Insert into DB
        cursor.execute("INSERT INTO sensor_data (device_id, payload) VALUES (%s, %s)", 
                       (device_id, json.dumps(payload)))
        db.commit()
        print(f"[DB] Inserted from {device_id}: {payload}")

        # Run ML prediction
        decision = predict_led_state(lux)
        actuator_id = device_id  # link sensor→actuator by ID
        command_topic = f"actuators/{actuator_id}/led"

        publish.single(command_topic, decision, hostname=MQTT_BROKER, port=MQTT_PORT)
        print(f"[ML] Predicted LED={decision} → published to {command_topic}")

    except Exception as e:
        print(f"Error inserting: {e}")

client = mqtt.Client()
client.on_message = on_message
client.connect(MQTT_BROKER, MQTT_PORT, 60)
client.subscribe("sensors/#")

print("Collector: subscribed to sensors/#")
client.loop_forever()