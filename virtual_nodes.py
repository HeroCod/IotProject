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
    
    def simulate_realistic_occupancy(self):
        """Generate more stable and realistic occupancy patterns"""
        # Simulate occupancy with stability (people don't constantly enter/exit)
        if self.occupancy_stability > 0:
            self.occupancy_stability -= 1
            return self.last_occupancy
        
        # Generate new occupancy with time-based patterns
        hour = datetime.now().hour
        
        # Different patterns for different rooms and times
        if self.location == 'Living Room':
            if 7 <= hour <= 10 or 18 <= hour <= 23:  # Morning and evening
                occupancy_prob = 0.8
            elif 11 <= hour <= 17:  # Afternoon
                occupancy_prob = 0.4
            else:  # Night
                occupancy_prob = 0.1
        elif self.location == 'Kitchen':
            if 7 <= hour <= 9 or 12 <= hour <= 13 or 18 <= hour <= 20:  # Meal times
                occupancy_prob = 0.9
            elif 10 <= hour <= 11 or 14 <= hour <= 17:  # Light activity
                occupancy_prob = 0.3
            else:
                occupancy_prob = 0.1
        elif self.location == 'Bedroom':
            if 6 <= hour <= 8 or 22 <= hour <= 23:  # Wake up and bedtime
                occupancy_prob = 0.9
            elif 9 <= hour <= 21:  # Day
                occupancy_prob = 0.2
            else:  # Night sleep
                occupancy_prob = 0.95
        else:
            occupancy_prob = self.occupancy_rate
        
        new_occupancy = 1 if random.random() < occupancy_prob else 0
        
        # If occupancy changes, set stability period
        if new_occupancy != self.last_occupancy:
            self.occupancy_stability = random.randint(15, 45)  # Stay stable for 1.5-4 minutes
            print(f"👤 {self.node_id} occupancy changed: {self.last_occupancy} -> {new_occupancy}")
        
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
        
        # Generate base sensor values with more realistic patterns
        lux = random.randint(self.lux_range[0], self.lux_range[1])
        
        # Use realistic occupancy simulation
        occupancy = self.simulate_realistic_occupancy()
        
        temperature = round(random.uniform(18, 26), 1)
        
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
