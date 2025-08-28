#!/usr/bin/env python3
"""
Interactive IoT Virtual Nodes
==============================

Complete virtual IoT nodes that:
- Publish sensor data every 5 seconds
- Subscribe to control commands
- Respond to LED control requests
- Simulate realistic device behavior
- Handle override commands from the web interface
"""

import json
import time
import random
import threading
import math
from datetime import datetime, timedelta
import signal
import sys
import paho.mqtt.client as mqtt
import paho.mqtt.publish as publish
# Import MQTT with error handling
# Check if we should log (state change or every 10th transmission)
try:
    MQTT_AVAILABLE = True
    print("✅ MQTT module loaded successfully")
except ImportError as e:
    MQTT_AVAILABLE = False
    print(f"❌ MQTT module not available: {e}")
    sys.exit(1)

class VirtualIoTNode:
    """A virtual IoT node that simulates a smart room controller"""
    
    def __init__(self, node_id, location, lux_range, occupancy_rate):
        self.node_id = node_id
        self.location = location
        self.lux_range = lux_range
        self.occupancy_rate = occupancy_rate
        
        # Device state
        self.led_status = 0  # 0 = off, 1 = on
        self.manual_override = False
        self.override_expires = None
        self.energy_saving_mode = 1
        self.button_presses = 0
        
        # Realistic behavior variables
        self.led_change_cooldown = 0  # Prevent rapid LED changes
        self.occupancy_stability = 0  # Stable occupancy detection
        self.last_occupancy = 0
        self.light_transition_time = 0  # Smooth light transitions
        self.auto_behavior_enabled = True
        
        # State tracking for logging
        self.last_logged_state = {
            'led_status': 0,
            'occupancy': 0,
            'room_usage': 0.0
        }
        
        # Command acknowledgment
        self.last_command = None
        self.command_response_sent = False
        
        # MQTT client
        self.client = mqtt.Client(client_id=f"virtual_{node_id}")
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message
        self.client.on_disconnect = self.on_disconnect
        
        # Control flags
        self.running = True
        self.connected = False
        self.last_actuator_command = None  # Track last actuator command to prevent spam
        
    def on_connect(self, client, userdata, flags, rc):
        """Callback for MQTT connection"""
        if rc == 0:
            self.connected = True
            print(f"🟢 {self.node_id} connected to MQTT broker")
            
            # Subscribe to control topics
            topics = [
                f"devices/{self.node_id}/control",
                f"devices/{self.node_id}/override",
                f"devices/all/control",  # Global commands
                f"actuators/{self.node_id}/led",  # LED actuator commands from controller
                "system/commands"
            ]
            
            for topic in topics:
                client.subscribe(topic)
                print(f"📡 {self.node_id} subscribed to {topic}")
        else:
            self.connected = False
            print(f"❌ {self.node_id} failed to connect: {rc}")
    
    def on_disconnect(self, client, userdata, rc):
        """Callback for MQTT disconnection"""
        self.connected = False
        print(f"🔴 {self.node_id} disconnected from MQTT broker")
    
    def on_message(self, client, userdata, msg):
        """Handle incoming MQTT messages"""
        try:
            topic = msg.topic
            
            # Handle actuator commands separately (they're just string commands)
            if f"actuators/{self.node_id}/led" in topic:
                payload_str = msg.payload.decode()
                self.handle_actuator_command(topic, payload_str)
                return
            
            # For other messages, parse as JSON
            payload = json.loads(msg.payload.decode())
            
            print(f"📨 {self.node_id} received command on {topic}: {payload}")
            
            if f"devices/{self.node_id}/control" in topic:
                self.handle_device_control(payload)
            elif f"devices/{self.node_id}/override" in topic:
                self.handle_override_control(payload)
            elif "devices/all/control" in topic:
                self.handle_global_control(payload)
            elif "system/commands" in topic:
                self.handle_system_command(payload)
                
        except Exception as e:
            print(f"❌ {self.node_id} error processing message: {e}")
    
    def handle_device_control(self, payload):
        """Handle individual device control commands"""
        command = payload.get('command')
        
        if command == 'on':
            self.led_status = 1
            self.manual_override = True
            self.override_expires = datetime.now() + timedelta(hours=24)
            self.led_change_cooldown = 30  # Prevent changes for 30 seconds
            self.auto_behavior_enabled = False
            print(f"💡 {self.node_id} LED turned ON (manual override for 24h)")
            
        elif command == 'off':
            self.led_status = 0
            self.manual_override = True
            self.override_expires = datetime.now() + timedelta(hours=24)
            self.led_change_cooldown = 30  # Prevent changes for 30 seconds
            self.auto_behavior_enabled = False
            print(f"💡 {self.node_id} LED turned OFF (manual override for 24h)")
            
        elif command == 'auto':
            self.manual_override = False
            self.override_expires = None
            self.auto_behavior_enabled = True
            self.led_change_cooldown = 5  # Brief cooldown before auto behavior
            print(f"🤖 {self.node_id} returned to AUTO mode")
            
        # Send acknowledgment
        self.send_control_response(payload, True)
    
    def handle_override_control(self, payload):
        """Handle override control commands from web interface"""
        status = payload.get('status')
        override_type = payload.get('type', '24h')
        
        if status == 'disabled':
            # Remove override - return to auto mode
            self.led_status = 0  # Default to off when returning to auto
            self.manual_override = False
            self.override_expires = None
            self.auto_behavior_enabled = True
            self.led_change_cooldown = 5  # Brief cooldown
            print(f"🤖 {self.node_id} override DISABLED - returned to AUTO mode")
            
        elif status == 'on':
            self.led_status = 1
            self.manual_override = True
            self.auto_behavior_enabled = False
            
            # Set expiration based on type
            if override_type == '1h':
                hours = 1
            elif override_type == '4h':
                hours = 4
            elif override_type == '12h':
                hours = 12
            elif override_type == '24h':
                hours = 24
            elif override_type == 'permanent':
                hours = None
                self.override_expires = None
            else:
                hours = 24  # Default
                
            if hours is not None:
                self.override_expires = datetime.now() + timedelta(hours=hours)
            
            self.led_change_cooldown = 60  # Longer cooldown for web commands
            print(f"🔧 {self.node_id} LED override ON for {override_type} (web command)")
            
        elif status == 'off':
            self.led_status = 0
            self.manual_override = True
            self.auto_behavior_enabled = False
            
            # Set expiration based on type  
            if override_type == '1h':
                hours = 1
            elif override_type == '4h':
                hours = 4
            elif override_type == '12h':
                hours = 12
            elif override_type == '24h':
                hours = 24
            elif override_type == 'permanent':
                hours = None
                self.override_expires = None
            else:
                hours = 24  # Default
                
            if hours is not None:
                self.override_expires = datetime.now() + timedelta(hours=hours)
            
            self.led_change_cooldown = 60  # Longer cooldown for web commands
            print(f"🔧 {self.node_id} LED override OFF for {override_type} (web command)")
            
        # Send acknowledgment
        self.send_control_response(payload, True)
    
    def handle_global_control(self, payload):
        """Handle global control commands (all devices)"""
        command = payload.get('command')
        
        if command == 'all_on':
            self.led_status = 1
            self.manual_override = True
            self.override_expires = datetime.now() + timedelta(hours=24)
            self.led_change_cooldown = 60
            self.auto_behavior_enabled = False
            print(f"🌟 {self.node_id} LED turned ON (global command)")
        elif command == 'all_off':
            self.led_status = 0
            self.manual_override = True
            self.override_expires = datetime.now() + timedelta(hours=24)
            self.led_change_cooldown = 60
            self.auto_behavior_enabled = False
            print(f"🌙 {self.node_id} LED turned OFF (global command)")
        elif command == 'energy_saving':
            self.energy_saving_mode = 1
            self.auto_behavior_enabled = True
            print(f"⚡ {self.node_id} energy saving enabled")
    
    def handle_system_command(self, payload):
        """Handle system-wide commands"""
        command = payload.get('command')
        
        if command == 'status_refresh':
            print(f"🔄 {self.node_id} refreshing status")
            self.publish_sensor_data()  # Send immediate update
    
    def handle_actuator_command(self, topic, command_str):
        """Handle actuator commands from controller (LED on/off)"""
        # The command is a simple string: "on" or "off"
        command = command_str.strip()
        
        # Prevent spam - only process if command is different from last one
        if command == self.last_actuator_command:
            return
        
        self.last_actuator_command = command
        print(f"📨 {self.node_id} received actuator command: {command}")
        
        if command == 'on':
            self.led_status = 1
            print(f"💡 {self.node_id} LED turned ON (controller command)")
        elif command == 'off':
            self.led_status = 0  
            print(f"🌙 {self.node_id} LED turned OFF (controller command)")
        else:
            print(f"⚠️ {self.node_id} unknown actuator command: {command}")
        
        # Send immediate sensor update to reflect LED state change
        self.publish_sensor_data()
    
    def send_control_response(self, original_payload, success):
        """Send response to control commands"""
        response = {
            'device_id': self.node_id,
            'command': original_payload.get('command'),
            'success': success,
            'timestamp': datetime.now().isoformat(),
            'led_status': self.led_status,
            'manual_override': self.manual_override
        }
        
        try:
            topic = f"devices/{self.node_id}/response"
            self.client.publish(topic, json.dumps(response))
            print(f"📤 {self.node_id} sent response: {response}")
        except Exception as e:
            print(f"❌ {self.node_id} failed to send response: {e}")
    
    def check_override_expiry(self):
        """Check if manual override has expired"""
        if self.manual_override and self.override_expires:
            if datetime.now() > self.override_expires:
                self.manual_override = False
                self.override_expires = None
                print(f"⏰ {self.node_id} override expired, returning to AUTO mode")
    
    def get_season(self):
        """Determine current season based on month"""
        month = datetime.now().month
        if month in [12, 1, 2]:
            return 'winter'
        elif month in [3, 4, 5]:
            return 'spring'
        elif month in [6, 7, 8]:
            return 'summer'
        else:  # 9, 10, 11
            return 'autumn'
    
    def calculate_realistic_temperature(self):
        """Calculate realistic temperature based on time of day and season"""
        now = datetime.now()
        hour = now.hour
        minute = now.minute
        season = self.get_season()
        
        # Base temperatures by season
        base_temps = {
            'winter': {'min': 18, 'max': 22, 'outdoor_factor': 0.3},
            'spring': {'min': 20, 'max': 24, 'outdoor_factor': 0.4},
            'summer': {'min': 22, 'max': 26, 'outdoor_factor': 0.5},
            'autumn': {'min': 19, 'max': 23, 'outdoor_factor': 0.4}
        }
        
        temp_config = base_temps[season]
        
        # Daily temperature curve (sine wave with peak at 14:00, minimum at 4:00)
        time_decimal = hour + minute / 60.0
        # Shift sine wave so peak is at 14:00 and minimum at 4:00
        daily_cycle = math.sin((time_decimal - 4) * math.pi / 12)
        
        # Room-specific adjustments
        room_adjustments = {
            'Living Room': 0.5,  # Slightly warmer (people, electronics)
            'Kitchen': 1.0,      # Warmer (cooking, appliances)
            'Bedroom': -0.5      # Slightly cooler (better sleep)
        }
        
        room_adj = room_adjustments.get(self.location, 0)
        
        # Calculate temperature
        base_temp = (temp_config['min'] + temp_config['max']) / 2
        temp_range = (temp_config['max'] - temp_config['min']) / 2
        
        # Apply daily cycle, seasonal variation, and room adjustment
        temperature = base_temp + (daily_cycle * temp_range * temp_config['outdoor_factor']) + room_adj
        
        # Add small random variation (±0.5°C)
        temperature += random.uniform(-0.5, 0.5)
        
        # Occupancy effect (people generate heat)
        if hasattr(self, 'current_occupancy') and self.current_occupancy:
            temperature += random.uniform(0.2, 0.8)  # People add warmth
        
        return round(temperature, 1)
    
    def calculate_realistic_light(self):
        """Calculate realistic light levels based on time of day and season"""
        now = datetime.now()
        hour = now.hour
        minute = now.minute
        season = self.get_season()
        
        # Daylight hours by season (sunrise/sunset times)
        daylight_hours = {
            'winter': {'sunrise': 7.5, 'sunset': 16.5},    # 7:30 AM - 4:30 PM
            'spring': {'sunrise': 6.5, 'sunset': 18.5},    # 6:30 AM - 6:30 PM
            'summer': {'sunrise': 5.5, 'sunset': 20.0},    # 5:30 AM - 8:00 PM
            'autumn': {'sunrise': 7.0, 'sunset': 17.5}     # 7:00 AM - 5:30 PM
        }
        
        daylight = daylight_hours[season]
        time_decimal = hour + minute / 60.0
        
        # Calculate light level based on time
        if daylight['sunrise'] <= time_decimal <= daylight['sunset']:
            # Daylight hours - calculate sun position
            day_length = daylight['sunset'] - daylight['sunrise']
            time_since_sunrise = time_decimal - daylight['sunrise']
            sun_position = math.sin((time_since_sunrise / day_length) * math.pi)
            
            # Base light levels by season (cloudy/clear day variation)
            season_max_light = {
                'winter': 60,
                'spring': 85,
                'summer': 95,
                'autumn': 75
            }
            
            max_light = season_max_light[season]
            outdoor_light = max_light * sun_position
            
        else:
            # Night time - very low light
            outdoor_light = random.uniform(2, 8)
        
        # Room-specific light adjustments based on windows and orientation
        room_light_factors = {
            'Living Room': 0.8,  # Good windows, but some obstruction
            'Kitchen': 0.65,      # Some windows, but cabinets block light
            'Bedroom': 0.55       # Curtains, smaller windows
        }
        
        room_factor = room_light_factors.get(self.location, 0.7)
        indoor_natural_light = outdoor_light * room_factor
        
        # Add artificial lighting contribution
        artificial_light = 0
        if self.led_status:
            # LED adds significant light when on
            artificial_light = random.uniform(40, 60)
            # LED effect is stronger in darker conditions
            if indoor_natural_light < 20:
                artificial_light += random.uniform(10, 20)
        
        # Other artificial sources (TV, appliances, etc.)
        if hasattr(self, 'current_occupancy') and self.current_occupancy:
            artificial_light += random.uniform(1, 3)  # People add minor light sources with phones, etc
        
        total_light = indoor_natural_light + artificial_light
        
        # Add small random variation
        total_light += random.uniform(-3, 3)
        
        # Ensure within reasonable bounds
        return max(5, min(int(total_light), 120))
    
    def simulate_volumetric_occupancy(self):
        """Simulate occupancy as if detected by a volumetric sensor with realistic patterns"""
        now = datetime.now()
        hour = now.hour
        minute = now.minute
        day_of_week = now.weekday()  # 0 = Monday, 6 = Sunday
        
        # If in stability period, return last occupancy
        if self.occupancy_stability > 0:
            self.occupancy_stability -= 1
            return self.last_occupancy
        
        # Define realistic occupancy patterns by room and time
        occupancy_patterns = {
            'Living Room': {
                'weekday': {
                    6: 0.2,   # 6 AM - getting ready
                    7: 0.4,   # 7 AM - morning routine
                    8: 0.6,   # 8 AM - breakfast/preparation
                    9: 0.2,   # 9 AM - leaving for work
                    10: 0.1,  # 10 AM - empty
                    11: 0.1,  # 11 AM - empty
                    12: 0.2,  # 12 PM - maybe lunch break
                    13: 0.1,  # 1 PM - back to work
                    14: 0.1,  # 2 PM - empty
                    15: 0.1,  # 3 PM - empty
                    16: 0.2,  # 4 PM - early return possible
                    17: 0.4,  # 5 PM - coming home
                    18: 0.7,  # 6 PM - dinner time
                    19: 0.8,  # 7 PM - evening activities
                    20: 0.9,  # 8 PM - TV time
                    21: 0.8,  # 9 PM - relaxing
                    22: 0.6,  # 10 PM - winding down
                    23: 0.3,  # 11 PM - going to bed
                    0: 0.1,   # 12 AM - night
                    1: 0.05,  # 1 AM - sleeping
                    2: 0.05,  # 2 AM - sleeping
                    3: 0.05,  # 3 AM - sleeping
                    4: 0.05,  # 4 AM - sleeping
                    5: 0.1    # 5 AM - early morning
                },
                'weekend': {
                    6: 0.05,  # 6 AM - sleeping in
                    7: 0.1,   # 7 AM - some early risers
                    8: 0.3,   # 8 AM - getting up
                    9: 0.5,   # 9 AM - breakfast
                    10: 0.6,  # 10 AM - morning activities
                    11: 0.7,  # 11 AM - active time
                    12: 0.8,  # 12 PM - lunch
                    13: 0.7,  # 1 PM - afternoon
                    14: 0.8,  # 2 PM - peak weekend activity
                    15: 0.7,  # 3 PM - activities
                    16: 0.6,  # 4 PM - late afternoon
                    17: 0.7,  # 5 PM - evening prep
                    18: 0.8,  # 6 PM - dinner
                    19: 0.9,  # 7 PM - peak evening
                    20: 0.9,  # 8 PM - entertainment
                    21: 0.8,  # 9 PM - evening wind down
                    22: 0.6,  # 10 PM - late evening
                    23: 0.4,  # 11 PM - bedtime
                    0: 0.2,   # 12 AM - late night
                    1: 0.1,   # 1 AM - night
                    2: 0.05,  # 2 AM - sleeping
                    3: 0.05,  # 3 AM - sleeping
                    4: 0.05,  # 4 AM - sleeping
                    5: 0.05   # 5 AM - sleeping
                }
            },
            'Kitchen': {
                'weekday': {
                    6: 0.3,   # 6 AM - morning prep
                    7: 0.8,   # 7 AM - breakfast
                    8: 0.6,   # 8 AM - finishing breakfast
                    9: 0.2,   # 9 AM - cleanup
                    10: 0.1,  # 10 AM - empty
                    11: 0.1,  # 11 AM - empty
                    12: 0.6,  # 12 PM - lunch prep
                    13: 0.4,  # 1 PM - lunch cleanup
                    14: 0.1,  # 2 PM - empty
                    15: 0.1,  # 3 PM - empty
                    16: 0.2,  # 4 PM - snack time
                    17: 0.3,  # 5 PM - dinner prep starts
                    18: 0.9,  # 6 PM - peak dinner prep
                    19: 0.7,  # 7 PM - cooking/eating
                    20: 0.4,  # 8 PM - cleanup
                    21: 0.2,  # 9 PM - occasional use
                    22: 0.1,  # 10 PM - late snack
                    23: 0.05, # 11 PM - rare use
                    0: 0.05,  # 12 AM - very rare
                    1: 0.02,  # 1 AM - almost never
                    2: 0.02,  # 2 AM - almost never
                    3: 0.02,  # 3 AM - almost never
                    4: 0.02,  # 4 AM - almost never
                    5: 0.05   # 5 AM - early morning
                },
                'weekend': {
                    6: 0.05,  # 6 AM - sleeping
                    7: 0.2,   # 7 AM - some early breakfast
                    8: 0.4,   # 8 AM - morning coffee
                    9: 0.7,   # 9 AM - breakfast
                    10: 0.8,  # 10 AM - late breakfast/brunch
                    11: 0.6,  # 11 AM - brunch cleanup
                    12: 0.4,  # 12 PM - light lunch
                    13: 0.3,  # 1 PM - cleanup
                    14: 0.2,  # 2 PM - snacks
                    15: 0.2,  # 3 PM - afternoon snacks
                    16: 0.3,  # 4 PM - prep for dinner
                    17: 0.4,  # 5 PM - dinner prep
                    18: 0.8,  # 6 PM - dinner cooking
                    19: 0.7,  # 7 PM - eating
                    20: 0.5,  # 8 PM - cleanup
                    21: 0.3,  # 9 PM - evening snacks
                    22: 0.2,  # 10 PM - late snacks
                    23: 0.1,  # 11 PM - rare use
                    0: 0.05,  # 12 AM - very rare
                    1: 0.02,  # 1 AM - almost never
                    2: 0.02,  # 2 AM - almost never
                    3: 0.02,  # 3 AM - almost never
                    4: 0.02,  # 4 AM - almost never
                    5: 0.05   # 5 AM - very early
                }
            },
            'Bedroom': {
                'weekday': {
                    6: 0.8,   # 6 AM - waking up
                    7: 0.6,   # 7 AM - getting ready
                    8: 0.3,   # 8 AM - leaving
                    9: 0.1,   # 9 AM - empty
                    10: 0.05, # 10 AM - empty
                    11: 0.05, # 11 AM - empty
                    12: 0.1,  # 12 PM - maybe quick visit
                    13: 0.05, # 1 PM - empty
                    14: 0.05, # 2 PM - empty
                    15: 0.05, # 3 PM - empty
                    16: 0.1,  # 4 PM - early return possible
                    17: 0.2,  # 5 PM - changing clothes
                    18: 0.2,  # 6 PM - brief visits
                    19: 0.1,  # 7 PM - brief visits
                    20: 0.2,  # 8 PM - brief visits
                    21: 0.4,  # 9 PM - preparing for bed
                    22: 0.7,  # 10 PM - bedtime routine
                    23: 0.9,  # 11 PM - going to bed
                    0: 0.95,  # 12 AM - sleeping
                    1: 0.98,  # 1 AM - sleeping
                    2: 0.98,  # 2 AM - sleeping
                    3: 0.98,  # 3 AM - sleeping
                    4: 0.95,  # 4 AM - deep sleep
                    5: 0.8    # 5 AM - light sleep
                },
                'weekend': {
                    6: 0.9,   # 6 AM - sleeping in
                    7: 0.8,   # 7 AM - sleeping in
                    8: 0.6,   # 8 AM - some wake up
                    9: 0.4,   # 9 AM - getting up
                    10: 0.2,  # 10 AM - up and about
                    11: 0.1,  # 11 AM - empty
                    12: 0.2,  # 12 PM - brief visit
                    13: 0.1,  # 1 PM - empty
                    14: 0.3,  # 2 PM - afternoon nap possible
                    15: 0.2,  # 3 PM - changing clothes
                    16: 0.1,  # 4 PM - brief visits
                    17: 0.2,  # 5 PM - changing clothes
                    18: 0.1,  # 6 PM - brief visits
                    19: 0.1,  # 7 PM - brief visits
                    20: 0.2,  # 8 PM - brief visits
                    21: 0.3,  # 9 PM - earlier bedtime prep
                    22: 0.6,  # 10 PM - bedtime routine
                    23: 0.8,  # 11 PM - going to bed
                    0: 0.9,   # 12 AM - sleeping
                    1: 0.95,  # 1 AM - sleeping
                    2: 0.98,  # 2 AM - sleeping
                    3: 0.98,  # 3 AM - sleeping
                    4: 0.95,  # 4 AM - sleeping
                    5: 0.9    # 5 AM - sleeping
                }
            }
        }
        
        # Determine if weekday or weekend
        is_weekend = day_of_week >= 5  # Saturday = 5, Sunday = 6
        schedule_type = 'weekend' if is_weekend else 'weekday'
        
        # Get occupancy probability for current room and time
        room_schedule = occupancy_patterns.get(self.location, occupancy_patterns['Living Room'])
        schedule = room_schedule[schedule_type]
        
        # Get base probability for current hour
        base_prob = schedule.get(hour, 0.1)
        
        # Add minute-based variation (small adjustments within the hour)
        minute_variation = math.sin((minute / 60) * 2 * math.pi) * 0.1
        occupancy_prob = max(0, min(1, base_prob + minute_variation))
        
        # Generate occupancy decision
        new_occupancy = 1 if random.random() < occupancy_prob else 0
        
        # If occupancy changes, set stability period (people don't constantly move)
        if new_occupancy != self.last_occupancy:
            # Different stability periods based on transition type and room
            if new_occupancy == 1:  # Entering room
                stability_min = 10 if self.location == 'Kitchen' else 20  # Kitchen visits can be shorter
                stability_max = 60 if self.location == 'Bedroom' else 40
            else:  # Leaving room
                stability_min = 30  # Once you leave, stay away for a while
                stability_max = 120
                
            self.occupancy_stability = random.randint(stability_min, stability_max)
            
            # Log significant changes
            transition = "entered" if new_occupancy else "left"
            print(f"👤 {self.node_id} ({self.location}): Person {transition} room (stability: {self.occupancy_stability}s)")
        
        self.last_occupancy = new_occupancy
        return new_occupancy
    
    def simulate_auto_behavior(self, occupancy, lux):
        """Simulate intelligent automatic LED control with stability"""
        if not self.auto_behavior_enabled or self.manual_override:
            return
        
        # Don't change LED too frequently
        if self.led_change_cooldown > 0:
            self.led_change_cooldown -= 1
            return
        
        # Smart lighting logic
        should_be_on = False
        
        # Rule 1: Turn on if occupied and dark
        if occupancy and lux < 50:
            should_be_on = True
        
        # Rule 2: Turn on if very dark regardless (security lighting)
        elif lux < 20:
            should_be_on = True
        
        # Rule 3: Energy saving mode - more conservative
        if self.energy_saving_mode:
            if occupancy and lux < 30:  # Stricter threshold
                should_be_on = True
            elif not occupancy:
                should_be_on = False
        
        # Rule 4: Time-based logic
        hour = datetime.now().hour
        if 22 <= hour or hour <= 6:  # Night time
            if occupancy and lux < 60:  # More sensitive at night
                should_be_on = True
        
        # Only change LED state if needed and not in cooldown
        if should_be_on != bool(self.led_status):
            self.led_status = 1 if should_be_on else 0
            self.led_change_cooldown = random.randint(8, 15)  # Prevent rapid changes
            
            reason = ""
            if should_be_on:
                if occupancy and lux < 50:
                    reason = "occupied + low light"
                elif lux < 20:
                    reason = "very dark"
                elif 22 <= hour or hour <= 6:
                    reason = "night mode"
            else:
                if not occupancy:
                    reason = "unoccupied"
                elif lux > 60:
                    reason = "bright enough"
                elif self.energy_saving_mode:
                    reason = "energy saving"
            
            action = "ON" if should_be_on else "OFF"
            print(f"🤖 {self.node_id} AUTO: LED {action} ({reason})")
    
    def generate_sensor_data(self):
        """Generate realistic sensor data"""
        # Check override expiry
        self.check_override_expiry()
        
        # Generate realistic sensor values based on time and environment
        # Use volumetric sensor simulation for occupancy
        occupancy = self.simulate_volumetric_occupancy()
        self.current_occupancy = occupancy  # Store for other calculations
        
        # Calculate realistic temperature and light based on time/season
        temperature = self.calculate_realistic_temperature()
        lux = self.calculate_realistic_light()
        
        # Simulate auto behavior if not in manual override
        self.simulate_auto_behavior(occupancy, lux)
        
        # Calculate room usage with distinct LED consumption (150W = 0.15 kW when on)
        base_usage = 0.02 if occupancy else 0.005  # Base consumption when occupied/empty
        led_usage = 0.15 if self.led_status else 0  # LED consumption: 150W when on, 0W when off
        device_usage = 0.008 if occupancy else 0.002  # Other devices usage
        
        # Add some realistic variation (smaller variation to keep LED difference clear)
        variation = random.uniform(-0.002, 0.002)
        room_usage = round(base_usage + led_usage + device_usage + variation, 3)
        
        return {
            'sensor_id': self.node_id,
            'location': self.location,
            'lux': lux,
            'occupancy': occupancy,
            'temperature': temperature,
            'room_usage': max(0, room_usage),
            'led_status': self.led_status,
            'manual_override': self.manual_override,
            'energy_saving_mode': self.energy_saving_mode,
            'button_presses': self.button_presses,
            'timestamp': datetime.now().isoformat()
        }
    
    def publish_sensor_data(self):
        """Publish sensor data to MQTT"""
        if not self.connected:
            return
            
        try:
            data = self.generate_sensor_data()
            topic = f"sensors/{self.node_id}/data"
            self.client.publish(topic, json.dumps(data))
            
            # Only log if significant state change occurred
            current_state = {
                'led_status': data['led_status'],
                'occupancy': data['occupancy'],
                'room_usage': round(data['room_usage'], 3)
            }
            
            # Check if we should log (state change or every 10th transmission)
            should_log = (
                current_state['led_status'] != self.last_logged_state['led_status'] or
                current_state['occupancy'] != self.last_logged_state['occupancy'] or
                abs(current_state['room_usage'] - self.last_logged_state['room_usage']) > 0.05 or  # Higher threshold due to 150W LED consumption
                random.randint(1, 10) == 1  # Log 10% of the time anyway
            )
            
            if should_log:
                status_icon = "💡" if self.led_status else "🌙"
                mode_icon = "🔧" if self.manual_override else "🤖"
                
                print(f"{status_icon} {self.node_id} ({self.location}) {mode_icon}: "
                    f"lux={data['lux']}, occ={data['occupancy']}, "
                    f"temp={data['temperature']}°C, usage={data['room_usage']}kWh")
                
                self.last_logged_state = current_state
        except Exception as e:
            print(f"❌ {self.node_id} failed to publish data: {e}")
    
    def connect_mqtt(self):
        """Connect to MQTT broker"""
        try:
            print(f"🔌 {self.node_id} connecting to MQTT broker...")
            self.client.connect("localhost", 1883, 60)
            self.client.loop_start()
            return True
        except Exception as e:
            print(f"❌ {self.node_id} MQTT connection failed: {e}")
            return False
    
    def disconnect_mqtt(self):
        """Disconnect from MQTT broker"""
        if self.connected:
            self.client.loop_stop()
            self.client.disconnect()
            print(f"🔴 {self.node_id} disconnected from MQTT")
    
    def run(self):
        """Main run loop for the virtual node"""
        if not self.connect_mqtt():
            return
        
        print(f"🚀 {self.node_id} virtual node started")
        
        while self.running:
            try:
                if self.connected:
                    self.publish_sensor_data()
                time.sleep(1)  # Publish every 1 second
            except KeyboardInterrupt:
                break
            except Exception as e:
                print(f"❌ {self.node_id} runtime error: {e}")
                time.sleep(1)
        
        self.disconnect_mqtt()
        print(f"🛑 {self.node_id} virtual node stopped")
    
    def stop(self):
        """Stop the virtual node"""
        self.running = False

class VirtualNodeManager:
    """Manager for multiple virtual IoT nodes"""
    
    def __init__(self):
        self.nodes = []
        self.threads = []
        self.running = True
        
        # Register signal handlers for graceful shutdown
        signal.signal(signal.SIGINT, self.signal_handler)
        signal.signal(signal.SIGTERM, self.signal_handler)
    
    def signal_handler(self, signum, frame):
        """Handle shutdown signals"""
        print(f"\n🛑 Received signal {signum}, shutting down...")
        self.stop_all()
        sys.exit(0)
    
    def add_node(self, node_id, location, lux_range, occupancy_rate):
        """Add a virtual node"""
        node = VirtualIoTNode(node_id, location, lux_range, occupancy_rate)
        self.nodes.append(node)
        return node
    
    def start_all(self):
        """Start all virtual nodes"""
        print("🎭 Starting Virtual IoT Node System...")
        print("=" * 50)
        
        for node in self.nodes:
            thread = threading.Thread(target=node.run, daemon=True)
            thread.start()
            self.threads.append(thread)
            print(f"✅ Started {node.node_id} ({node.location})")
        
        print(f"\n🚀 All {len(self.nodes)} virtual nodes are running")
        print("📡 Publishing sensor data every 5 seconds...")
        print("🎮 Listening for control commands...")
        print("🛑 Press Ctrl+C to stop\n")
    
    def stop_all(self):
        """Stop all virtual nodes"""
        print("\n🛑 Stopping all virtual nodes...")
        
        for node in self.nodes:
            node.stop()
        
        # Wait for threads to finish
        for thread in self.threads:
            thread.join(timeout=2)
        
        print("✅ All virtual nodes stopped")
    
    def run(self):
        """Run the virtual node system"""
        self.start_all()
        
        try:
            while self.running:
                time.sleep(1)
        except KeyboardInterrupt:
            pass
        
        self.stop_all()

def main():
    """Main function"""
    if not MQTT_AVAILABLE:
        print("❌ MQTT not available. Install with: pip install paho-mqtt")
        return
    
    # Create virtual node manager
    manager = VirtualNodeManager()
    
    # Add virtual nodes
    # (node_id, location, lux_range, occupancy_probability)
    manager.add_node('node1', 'Living Room', (30, 90), 0.6)
    manager.add_node('node2', 'Kitchen', (40, 90), 0.75)
    manager.add_node('node3', 'Bedroom', (15, 60), 0.5)
    
    # Run the system
    manager.run()

if __name__ == "__main__":
    main()
