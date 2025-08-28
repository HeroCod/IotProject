#!/usr/bin/env python3
"""
Command Line Interface for Smart Home Energy-Saving IoT System
SOLO PROJECT Implementation - User Input Requirement

This CLI provides user control for the IoT energy optimization system including:
- Device status monitoring
- Manual LED control
- Energy statistics viewing
- System configuration management
"""

import json
import sys
import os
import mysql.connector
import paho.mqtt.publish as publish
from datetime import datetime, timedelta
from typing import Dict, List

# Configuration
MQTT_BROKER = os.environ.get("MQTT_BROKER", "localhost")
MQTT_PORT = int(os.environ.get("MQTT_PORT", 1883))

MYSQL_HOST = os.environ.get("MYSQL_HOST", "localhost")
MYSQL_USER = os.environ.get("MYSQL_USER", "iotuser")  
MYSQL_PASSWORD = os.environ.get("MYSQL_PASSWORD", "iotpass")
MYSQL_DB = os.environ.get("MYSQL_DB", "iotdb")

class EnergyIoTCLI:
    def __init__(self):
        self.config = self.load_device_config()
        self.db_connection = None
        self.connect_database()
        
    def load_device_config(self) -> Dict:
        """Load static device configuration for SOLO PROJECT"""
        try:
            with open('/home/herocod/Documents/UniPi/IOT/IotProject/config/devices_static.json', 'r') as f:
                return json.load(f)
        except FileNotFoundError:
            print("❌ Error: Device configuration file not found!")
            sys.exit(1)
            
    def connect_database(self):
        """Connect to MySQL database for energy data retrieval"""
        try:
            self.db_connection = mysql.connector.connect(
                host=MYSQL_HOST,
                user=MYSQL_USER,
                password=MYSQL_PASSWORD,
                database=MYSQL_DB
            )
            print("✅ Connected to energy monitoring database")
        except mysql.connector.Error as e:
            print(f"⚠️  Database connection failed: {e}")
            print("📊 Energy statistics will not be available")
            
    def show_main_menu(self):
        """Display main CLI menu"""
        print("\n" + "="*60)
        print("🏠 SMART HOME ENERGY-SAVING IoT SYSTEM")
        print("   SOLO PROJECT - User Control Interface")
        print("="*60)
        print("1. 📊 View Device Status")
        print("2. 💡 Manual LED Control")
        print("3. ⚡ Energy Statistics")
        print("4. 🌞 Ambient Light Optimization Report")
        print("5. ⚙️  System Configuration")
        print("6. 🔧 Device Configuration Info")
        print("7. 📈 Recent Energy Data")
        print("8. 🚪 Exit")
        print("="*60)
        
    def view_device_status(self):
        """Display current status of all configured devices"""
        print("\n📊 DEVICE STATUS OVERVIEW")
        print("-" * 40)
        
        devices = self.config['devices']
        
        print(f"📍 SENSORS ({len(devices['sensors'])} devices):")
        for sensor in devices['sensors']:
            print(f"  🔸 {sensor['device_id']} ({sensor['location']})")
            print(f"     Description: {sensor['description']}")
            print(f"     MQTT Topics: {sensor['mqtt_topics']['sensor_data']}")
            print()
            
        print(f"💡 ACTUATORS ({len(devices['actuators'])} devices):")
        for actuator in devices['actuators']:
            print(f"  🔸 {actuator['device_id']} ({actuator['location']})")
            print(f"     Type: {actuator['actuator_type']}")
            print(f"     Energy: {actuator['energy_consumption']}")
            print(f"     Control: {actuator['mqtt_topics']['control']}")
            print()
            
    def manual_led_control(self):
        """Manual LED control interface"""
        print("\n💡 MANUAL LED CONTROL")
        print("-" * 30)
        
        actuators = self.config['devices']['actuators']
        
        print("Available LEDs:")
        for i, actuator in enumerate(actuators, 1):
            print(f"  {i}. {actuator['device_id']} ({actuator['location']})")
            
        try:
            choice = int(input("\nSelect LED (number): ")) - 1
            if 0 <= choice < len(actuators):
                actuator = actuators[choice]
                
                print(f"\nSelected: {actuator['device_id']} ({actuator['location']})")
                command = input("Enter command (on/off): ").lower().strip()
                
                if command in ['on', 'off']:
                    topic = actuator['mqtt_topics']['control']
                    
                    try:
                        publish.single(topic, command, hostname=MQTT_BROKER, port=MQTT_PORT)
                        print(f"✅ Command sent: {command} → {topic}")
                        print(f"💡 LED {actuator['device_id']} should now be {command.upper()}")
                        
                        if command == 'on':
                            print(f"⚡ Energy consumption: {actuator['energy_consumption']}")
                            
                    except Exception as e:
                        print(f"❌ Failed to send command: {e}")
                else:
                    print("❌ Invalid command. Use 'on' or 'off'")
            else:
                print("❌ Invalid selection")
                
        except ValueError:
            print("❌ Invalid input. Please enter a number.")
            
    def energy_statistics(self):
        """Display energy consumption statistics"""
        print("\n⚡ ENERGY STATISTICS")
        print("-" * 25)
        
        if not self.db_connection:
            print("❌ Database not available. Cannot show energy statistics.")
            return
            
        try:
            cursor = self.db_connection.cursor()
            
            # Get recent energy data
            query = """
            SELECT device_id, payload, timestamp 
            FROM sensor_data 
            WHERE timestamp >= %s 
            ORDER BY timestamp DESC 
            LIMIT 50
            """
            
            since_time = datetime.now() - timedelta(hours=1)
            cursor.execute(query, (since_time,))
            results = cursor.fetchall()
            
            if not results:
                print("📊 No recent energy data found")
                return
                
            # Analyze energy patterns
            device_stats = {}
            total_energy_saved = 0.0
            
            for device_id, payload_str, timestamp in results:
                try:
                    payload = json.loads(str(payload_str))
                    
                    if device_id not in device_stats:
                        device_stats[device_id] = {
                            'readings': 0,
                            'avg_room_usage': 0.0,
                            'occupancy_rate': 0.0,
                            'last_update': timestamp
                        }
                    
                    room_usage = payload.get('room_usage', 0.0)
                    occupancy = payload.get('occupancy', 0)
                    
                    stats = device_stats[device_id]
                    stats['readings'] += 1
                    stats['avg_room_usage'] = (stats['avg_room_usage'] + room_usage) / 2
                    stats['occupancy_rate'] = (stats['occupancy_rate'] + occupancy) / 2
                    if timestamp > stats['last_update']:
                        stats['last_update'] = timestamp
                    
                except json.JSONDecodeError:
                    continue
                    
            # Display statistics
            print(f"📊 Energy Data Summary (Last hour - {len(results)} readings)")
            print(f"🕒 Analysis time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            print()
            
            for device_id, stats in device_stats.items():
                print(f"🏠 {device_id.upper()}:")
                print(f"   📈 Readings: {stats['readings']}")
                print(f"   ⚡ Avg room usage: {stats['avg_room_usage']:.3f} kWh")
                print(f"   👤 Occupancy rate: {stats['occupancy_rate']*100:.1f}%")
                print(f"   🕐 Last update: {stats['last_update']}")
                
                # Energy waste estimation
                if stats['occupancy_rate'] < 0.5 and stats['avg_room_usage'] > 0.1:
                    waste_estimate = stats['avg_room_usage'] * (1 - stats['occupancy_rate'])
                    print(f"   ⚠️  Potential waste: {waste_estimate:.3f} kWh")
                    total_energy_saved += waste_estimate
                    
                print()
                
            if total_energy_saved > 0:
                print(f"💰 ENERGY OPTIMIZATION OPPORTUNITY: {total_energy_saved:.3f} kWh could be saved")
                cost_savings = total_energy_saved * 0.25  # Assume €0.25/kWh
                print(f"💶 Estimated cost savings: €{cost_savings:.2f}")
                
        except mysql.connector.Error as e:
            print(f"❌ Database error: {e}")
        finally:
            if cursor:
                cursor.close()
                
    def ambient_optimization_report(self):
        """Display ambient light optimization performance"""
        print("\n🌞 AMBIENT LIGHT OPTIMIZATION REPORT")
        print("-" * 40)
        
        print("📋 Current Configuration:")
        ambient_config = self.config['energy_optimization']['ambient_light_optimization']
        print(f"   Status: {'✅ Enabled' if ambient_config['enabled'] else '❌ Disabled'}")
        print(f"   Threshold: {ambient_config['threshold']}")
        print(f"   Target: {ambient_config['target']}")
        print(f"   Energy saving per override: {ambient_config['energy_saving']}")
        print()
        
        print("🎯 Optimization Strategy:")
        print("   • When ambient light ≥ 65 lux, prevent turning ON unnecessary lighting")
        print("   • Save ~0.1 kWh per prevented lighting event")
        print("   • Maintain comfort while maximizing energy efficiency")
        print()
        
        print("📊 Expected Performance:")
        print("   • 10-20% of lighting decisions optimized by ambient light detection")
        print("   • Additional 5-10% energy savings beyond ML model")
        print("   • Zero comfort loss (only prevents unnecessary lighting)")
        
    def system_configuration(self):
        """Display system configuration and technical details"""
        print("\n⚙️  SYSTEM CONFIGURATION")
        print("-" * 30)
        
        project_info = self.config['project_info']
        print(f"📋 Project Type: {project_info['type']}")
        print(f"📝 Description: {project_info['description']}")
        print()
        
        print(f"🌐 Protocol: {project_info['protocol']}")
        print(f"📡 Justification: {project_info['protocol_justification']}")
        print()
        
        encoding = self.config['data_encoding']
        print(f"📊 Data Encoding: {encoding['format']}")
        print(f"💭 Justification: {encoding['justification']}")
        print()
        
        ml_config = self.config['energy_optimization']['ml_model']
        print(f"🤖 ML Model: {ml_config['type']}")
        print(f"🎯 Objective: {ml_config['objective']}")
        print(f"🧠 Algorithm: {ml_config['algorithm']}")
        print(f"📈 Accuracy: {ml_config['accuracy']}")
        print(f"⚡ Energy Reduction: {ml_config['energy_reduction']}")
        
    def device_configuration_info(self):
        """Show detailed device configuration information"""
        print("\n🔧 DEVICE CONFIGURATION DETAILS")
        print("-" * 40)
        
        print("📊 Configuration Source: devices_static.json (SOLO PROJECT requirement)")
        print(f"📍 Total Sensors: {len(self.config['devices']['sensors'])}")
        print(f"💡 Total Actuators: {len(self.config['devices']['actuators'])}")
        print()
        
        for sensor in self.config['devices']['sensors']:
            print(f"🔸 {sensor['device_id']} - {sensor['location'].upper()}")
            print(f"   📝 {sensor['description']}")
            print(f"   🔍 Sensors: Light, Occupancy, Energy Monitor, Button")
            print(f"   📡 MQTT Data: {sensor['mqtt_topics']['sensor_data']}")
            print(f"   🔘 MQTT Button: {sensor['mqtt_topics']['button_press']}")
            print()
            
    def recent_energy_data(self):
        """Show recent energy data from database"""
        print("\n📈 RECENT ENERGY DATA")
        print("-" * 25)
        
        if not self.db_connection:
            print("❌ Database not available")
            return
            
        try:
            cursor = self.db_connection.cursor()
            query = """
            SELECT device_id, payload, timestamp 
            FROM sensor_data 
            ORDER BY timestamp DESC 
            LIMIT 10
            """
            cursor.execute(query)
            results = cursor.fetchall()
            
            if not results:
                print("📊 No energy data found")
                return
                
            print("🕒 Latest 10 sensor readings:")
            print()
            
            for device_id, payload_str, timestamp in results:
                try:
                    payload = json.loads(str(payload_str))
                    lux = payload.get('lux', 'N/A')
                    occupancy = payload.get('occupancy', 'N/A')
                    room_usage = payload.get('room_usage', 'N/A')
                    
                    print(f"📅 {timestamp} | 🏠 {device_id}")
                    print(f"   💡 Lux: {lux} | 👤 Occupied: {occupancy} | ⚡ Usage: {room_usage} kWh")
                    print()
                    
                except json.JSONDecodeError:
                    print(f"📅 {timestamp} | 🏠 {device_id} | ❌ Invalid data format")
                    print()
                    
        except mysql.connector.Error as e:
            print(f"❌ Database error: {e}")
        finally:
            if cursor:
                cursor.close()
                
    def run(self):
        """Main CLI loop"""
        print("🏠 Smart Home Energy-Saving IoT System - User Interface")
        print("   SOLO PROJECT Implementation")
        
        while True:
            self.show_main_menu()
            
            try:
                choice = input("\nEnter your choice (1-8): ").strip()
                
                if choice == '1':
                    self.view_device_status()
                elif choice == '2':
                    self.manual_led_control()
                elif choice == '3':
                    self.energy_statistics()
                elif choice == '4':
                    self.ambient_optimization_report()
                elif choice == '5':
                    self.system_configuration()
                elif choice == '6':
                    self.device_configuration_info()
                elif choice == '7':
                    self.recent_energy_data()
                elif choice == '8':
                    print("\n👋 Goodbye! Energy optimization continues automatically.")
                    break
                else:
                    print("\n❌ Invalid choice. Please select 1-8.")
                    
                input("\nPress Enter to continue...")
                
            except KeyboardInterrupt:
                print("\n\n👋 Goodbye! Energy optimization continues automatically.")
                break
            except Exception as e:
                print(f"\n❌ Error: {e}")
                input("Press Enter to continue...")
                
        # Close database connection
        if self.db_connection:
            self.db_connection.close()

if __name__ == "__main__":
    cli = EnergyIoTCLI()
    cli.run()
