import os
import json
import paho.mqtt.client as mqtt
import mysql.connector
import paho.mqtt.publish as publish
from datetime import datetime
from typing import Optional

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

# Load trained ML model parameters
def load_energy_saving_model():
    """Load the energy-saving ML model parameters"""
    try:
        with open('/app/ml/train_params.json', 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        print("ML model parameters not found, using fallback rules")
        return {
            "model_type": "energy_saving_lighting_control",
            "objective": "minimize_lighting_energy_consumption",
            "energy_saving_rules": {
                "lights_on_threshold": 0.1,
                "high_consumption_threshold": 0.4,
                "occupancy_required": True,
                "peak_waste_hours": [6, 7, 8, 9, 11],
                "turn_off_when_empty": True
            },
            "feature_importance": {
                "total_room_usage": 0.587,
                "lights_currently_on": 0.237,
                "space_occupied": 0.091,
                "hour_of_day": 0.043
            }
        }

model_params = load_energy_saving_model()

def energy_saving_decision(sensor_data: dict) -> tuple:
    """
    Energy-saving lighting decision based on ML model
    Returns: (action, energy_saved_kwh, reason)
    """
    
    # Extract sensor data with defaults
    lux = sensor_data.get('lux', 50)
    occupancy = sensor_data.get('occupancy', 0)
    temperature = sensor_data.get('temperature', 22)
    
    # Enhanced energy data (from updated IoT nodes)
    solar_surplus = sensor_data.get('solar_surplus', 0.0)
    room_usage = sensor_data.get('room_usage', 0.0)
    cloud_cover = sensor_data.get('cloud_cover', 0.5)
    
    # Calculate current energy state
    lights_currently_on = 1 if room_usage > model_params['energy_saving_rules']['lights_on_threshold'] else 0
    space_occupied = occupancy
    high_consumption = room_usage > model_params['energy_saving_rules']['high_consumption_threshold']
    
    # Get current hour
    current_hour = datetime.now().hour
    peak_waste_hour = current_hour in model_params['energy_saving_rules']['peak_waste_hours']
    
    print(f"Energy Analysis: Room={room_usage:.3f}kWh, Lights={lights_currently_on}, Occupied={space_occupied}, Hour={current_hour}")
    
    # ENERGY SAVING DECISIONS:
    
    # Rule 1: Lights ON but space NOT occupied = ENERGY WASTE
    if lights_currently_on == 1 and space_occupied == 0:
        energy_saved = room_usage  # Save all lighting consumption
        return "turn_off", energy_saved, "empty_space_energy_waste"
    
    # Rule 2: Excessive consumption during peak waste hours
    if peak_waste_hour and high_consumption and space_occupied == 1:
        energy_saved = room_usage - 0.12  # Reduce to efficient level
        return "reduce_lighting", energy_saved, "excessive_consumption_peak_hours"
    
    # Rule 3: Very high consumption (likely multiple lights/wasteful)
    if room_usage > 0.3 and space_occupied == 1:
        energy_saved = room_usage - 0.15  # Reduce to reasonable level  
        return "reduce_lighting", energy_saved, "excessive_energy_usage"
    
    # Rule 4: Late night energy waste (23-5)
    if (current_hour >= 23 or current_hour <= 5) and lights_currently_on == 1 and space_occupied == 0:
        energy_saved = room_usage
        return "turn_off", energy_saved, "nighttime_energy_waste"
    
    # Rule 5: Daytime with good natural light + high consumption
    if 9 <= current_hour <= 15 and room_usage > 0.15 and cloud_cover < 0.5:
        if space_occupied == 1:
            energy_saved = room_usage - 0.08  # Minimal lighting with natural light
            return "reduce_lighting", energy_saved, "natural_light_efficiency"
    
    # Default: Current usage is efficient
    if lights_currently_on == 0:
        return "keep_off", 0.0, "lights_already_efficient"
    else:
        return "keep_current", 0.0, "energy_usage_efficient"
        print("[WARNING] ML model parameters not found, using fallback model")
        # Fallback parameters if file not found
        return {
            "decision_rules": {
                "light_threshold_low": 30,
                "light_threshold_medium": 50,
                "evening_start": 18,
                "evening_end": 23,
                "night_start": 0,
                "night_end": 6,
                "occupancy_required": True,
                "energy_efficient": True
            }
        }

model_params = load_energy_saving_model()
print(f"[ML] Loaded model: {model_params.get('model_type', 'fallback')}")
print(f"[ML] Model accuracy: {model_params.get('accuracy', 'N/A')}")
print(f"[ML] Energy objective: {model_params.get('objective', 'N/A')}")
print(f"[ML] Energy efficiency: {model_params.get('energy_efficiency_improvement', 'N/A')}")

### Smart Energy Lighting ML Model for IoT Deployment
# LEGACY FUNCTION - This function optimized for lighting comfort but not energy savings
# New approach uses energy_saving_decision() which focuses on minimizing consumption
def predict_led_state(lux_value: int, occupancy: int = 1, hour_of_day: Optional[int] = None, 
                     solar_surplus: float = 0.0, cloud_cover: float = 0.5, 
                     visibility: float = 10.0, room_usage: float = 0.1) -> str:
    """
    Smart Energy Lighting Control - Energy Efficiency Optimized
    Domain: Smart Homes and Buildings - Renewable energy optimization
    
    Args:
        lux_value: Ambient light level (0-200) - legacy parameter for compatibility
        occupancy: Room occupancy (0=empty, 1=occupied)
        hour_of_day: Current hour (0-23), if None uses current time
        solar_surplus: Solar generation - consumption (kW), positive = excess solar
        cloud_cover: Cloud coverage (0-1), higher = more cloudy
        visibility: Visibility in km, lower = poorer conditions
        room_usage: Total room energy usage (kW), higher = more activity
    
    Returns:
        "on" or "off" decision optimized for energy efficiency
    """
    if hour_of_day is None:
        hour_of_day = datetime.now().hour
    
    rules = model_params.get('energy_saving_rules', {})
    
    # Rule 1: Energy Conservation - No lighting without occupancy
    if not occupancy:
        return "off"
    
    # Rule 2: Evening/Night Hours - Occupied spaces need lighting
    evening_start = rules.get('evening_start', 17)
    night_end = rules.get('night_end', 7)
    if hour_of_day >= evening_start or hour_of_day <= night_end:
        # Use lighting but prefer when not heavily using grid power
        grid_limit = rules.get('grid_power_limit', -0.1)
        if solar_surplus > grid_limit:
            return "on"
        else:
            return "on"  # Still provide lighting, but with lower preference
    
    # Rule 3: Weather-Based Lighting - Poor conditions during daytime
    cloud_threshold = rules.get('cloud_cover_threshold', 0.7)
    vis_threshold = rules.get('visibility_threshold', 5.0)
    poor_weather = cloud_cover > cloud_threshold or visibility < vis_threshold
    
    if poor_weather and 7 < hour_of_day < 17:  # Daytime poor weather
        min_solar = rules.get('min_solar_for_comfort', 0.2)
        if solar_surplus > min_solar:  # Use excess solar for comfort
            return "on"
        elif solar_surplus > rules.get('solar_surplus_threshold', 0.0):
            return "on"  # Use moderate solar surplus
    
    # Rule 4: Activity-Based Lighting - High activity with renewable energy
    activity_threshold = rules.get('room_activity_threshold', 0.1)
    if room_usage > activity_threshold:
        min_solar = rules.get('min_solar_for_comfort', 0.2)
        if solar_surplus > min_solar:
            return "on"
    
    # Rule 5: Smart Solar Utilization - Use excess renewable energy
    if solar_surplus > 0.3 and 8 < hour_of_day < 16:  # Significant midday surplus
        if cloud_cover > 0.5:  # Some reduction in natural light
            return "on"
    
    # Legacy compatibility: very low light levels
    if lux_value < 20 and occupancy:
        return "on"
    
    # Default: Energy conservation
    return "off"

def on_message(client, userdata, msg):
    try:
        payload = json.loads(msg.payload.decode())
        device_id = payload.get("sensor_id", "unknown")
        lux = payload.get("lux", 0)
        
        # Extract enhanced sensor data for energy-optimized ML model
        occupancy = payload.get("occupancy", 1)  # Default assume occupied
        temperature = payload.get("temperature", 22)  # Default room temp
        
        # Simulate energy and weather data (in real deployment, these would come from sensors)
        # For demo purposes, we'll use reasonable defaults that can be overridden
        solar_surplus = payload.get("solar_surplus", 0.1)  # Slight solar surplus
        cloud_cover = payload.get("cloud_cover", 0.5)  # Moderate cloudiness
        visibility = payload.get("visibility", 10.0)  # Good visibility
        room_usage = payload.get("room_usage", 0.1)  # Moderate room activity
        
        # Insert into DB with enhanced energy data
        enhanced_payload = {
            **payload,
            "model_version": model_params.get("version", "3.0"),
            "model_type": "smart_energy_lighting_control",
            "timestamp": datetime.now().isoformat(),
            # Add energy optimization metadata
            "energy_features": {
                "solar_surplus": solar_surplus,
                "cloud_cover": cloud_cover,
                "visibility": visibility,
                "room_usage": room_usage
            }
        }
        
        cursor.execute("INSERT INTO sensor_data (device_id, payload) VALUES (%s, %s)", 
                       (device_id, json.dumps(enhanced_payload)))
        db.commit()
        print(f"[DB] Inserted from {device_id}: energy-optimized data")

        # Run energy-saving decision algorithm
        action, energy_saved, reason = energy_saving_decision({
            'lux': lux,
            'occupancy': occupancy,
            'solar_surplus': solar_surplus,
            'cloud_cover': cloud_cover,
            'visibility': visibility,
            'room_usage': room_usage
        })
        
        # Convert energy-saving action to LED command
        if action in ["turn_off", "reduce_lighting"]:
            led_command = "off"
        elif action == "keep_current" and room_usage > 0.1:  # Lights currently on
            led_command = "on"
        else:
            led_command = "off"  # Default to energy saving
        
        actuator_id = device_id  # link sensor→actuator by ID
        command_topic = f"actuators/{actuator_id}/led"

        publish.single(command_topic, led_command, hostname=MQTT_BROKER, port=MQTT_PORT)
        
        # Enhanced logging for energy optimization
        print(f"[ENERGY] Action: {action}, Saved: {energy_saved:.3f}kWh, Reason: {reason}")
        print(f"[ENERGY] Sensors: lux={lux}, occ={occupancy}, room={room_usage:.3f}kW, solar={solar_surplus:+.1f}kW")
        print(f"[DECISION] LED={led_command.upper()} → {command_topic}")

    except Exception as e:
        print(f"Error processing message: {e}")

client = mqtt.Client()
client.on_message = on_message
client.connect(MQTT_BROKER, MQTT_PORT, 60)
client.subscribe("sensors/#")

print(f"[Collector] Smart Home Energy Management System Started")
print(f"[Collector] Using energy-saving model: {model_params.get('model_type', 'fallback')}")
print(f"[Collector] Subscribed to sensors/# on {MQTT_BROKER}:{MQTT_PORT}")
client.loop_forever()