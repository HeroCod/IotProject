/*
 * Node 1 - Living Room Sensor Node
 * SOLO PROJECT Implementation with Button/LED Physical Interactions
 * 
 * Features:
 * - Room occupancy detection
 * - Ambient light monitoring  
 * - Energy consumption tracking
 * - Physical button for manual control
 * - LED feedback for energy saving status
 */

#include "contiki.h"
#include "sys/log.h"
#include "net/ipv6/simple-udp.h"
#include "net/ipv6/uip.h"
#include "mqtt.h"
#include "dev/leds.h"
#include "dev/button-hal.h"
#include "dev/button-sensor.h"

#define LOG_MODULE "Node1-Living"
#define LOG_LEVEL LOG_LEVEL_INFO

// MQTT broker config (Docker mosquito container)
#define MQTT_CLIENT_ID "node1"
#define MQTT_BROKER_IP "fd00::1"    // border router IPv6, change in Cooja
#define MQTT_BROKER_PORT 1883

static struct mqtt_connection conn;
static char pub_topic[] = "sensors/node1/data";
static char sub_topic[] = "actuators/node1/led";
static char button_topic[] = "sensors/node1/button";

// SOLO PROJECT - Physical interaction states
static int manual_override = 0;  // Manual control via button
static int energy_saving_mode = 1; // Energy saving status
static int button_count = 0;    // Button press counter
static int led_status = 0;      // LED illumination status

PROCESS(node1_process, "Node1 Process");
PROCESS(button_handler_process, "Button handler");
AUTOSTART_PROCESSES(&node1_process, &button_handler_process);

static void mqtt_event(struct mqtt_connection *m, mqtt_event_t event, void *data) {
  switch(event) {
    case MQTT_EVENT_CONNECTED:
      LOG_INFO("Connected to broker\n");
      mqtt_subscribe(&conn, NULL, sub_topic, MQTT_QOS_LEVEL_0);
      break;
    case MQTT_EVENT_PUBLISH: {
      struct mqtt_message *msg = (struct mqtt_message *)data;
      LOG_INFO("Incoming actuator cmd: %.*s\n", msg->payload_chunk_length, (char *)msg->payload_chunk);
      if(msg->payload_chunk_length > 0) {
        // SOLO PROJECT - LED Control with Physical Feedback
        if(strncmp((char *)msg->payload_chunk, "on", 2) == 0) {
          led_status = 1;
          leds_on(LEDS_RED);  // Red = LED illumination ON
          LOG_INFO("💡 LED turned ON via command\n");
        } else {
          led_status = 0;
          leds_off(LEDS_RED);
          LOG_INFO("💡 LED turned OFF via command\n");
        }
      }
      break;
    }
    default:
      break;
  }
}

/*---------------------------------------------------------------------------*/
/* SOLO PROJECT - Physical Button Interaction Handler */
PROCESS_THREAD(button_handler_process, ev, data)
{
    PROCESS_BEGIN();
    
    // Activate button sensor
    SENSORS_ACTIVATE(button_sensor);
    
    while(1) {
        PROCESS_WAIT_EVENT_UNTIL(ev == sensors_event && data == &button_sensor);
        
        button_count++;
        manual_override = !manual_override; // Toggle manual override
        
        LOG_INFO("🔘 BUTTON PRESSED! Count: %d, Manual Override: %s\n", 
               button_count, manual_override ? "ON" : "OFF");
        
        // LED feedback for button press
        if(manual_override) {
            leds_on(LEDS_BLUE);  // Blue = Manual mode
            LOG_INFO("💡 Manual control activated - LEDs under user control\n");
        } else {
            leds_off(LEDS_BLUE);
            LOG_INFO("🤖 Automatic control restored - ML energy optimization active\n");
        }
        
        // Send button press notification via MQTT
        char button_msg[128];
        snprintf(button_msg, sizeof(button_msg), 
                 "{\"button_press\":%d,\"manual_override\":%d,\"device_id\":\"node1\"}", 
                 button_count, manual_override);
        
        mqtt_publish(&conn, NULL, button_topic, (uint8_t *)button_msg, 
                    strlen(button_msg), MQTT_QOS_LEVEL_0, MQTT_RETAIN_OFF);
                         
        LOG_INFO("📡 Button event sent via MQTT\n");
    }
    
    PROCESS_END();
}

PROCESS_THREAD(node1_process, ev, data) {
  static struct etimer timer;
  static int light_val;

  PROCESS_BEGIN();

  mqtt_register(&conn, &node1_process, MQTT_CLIENT_ID, mqtt_event, 256);
  mqtt_connect(&conn, MQTT_BROKER_IP, MQTT_BROKER_PORT, 1000, 1);

  etimer_set(&timer, CLOCK_SECOND * 10);

  // Initialize SOLO PROJECT physical components
  leds_init();
  leds_off(LEDS_ALL);
  
  LOG_INFO("🏠 Node 1 (Living Room) - SOLO PROJECT Implementation\n");
  LOG_INFO("🔘 Button: Manual LED override control\n");
  LOG_INFO("💡 LEDs: Red=Illumination, Green=Energy Saving, Blue=Manual Mode\n");

  while(1) {
    PROCESS_WAIT_EVENT();
    if(etimer_expired(&timer)) {
      // Generate realistic ambient light sensor data for optimization testing
      // Simulate varying light conditions throughout day for Cooja testing
      light_val = 30 + (random_rand() % 60); // 30-90 lux range (realistic indoor)
      
      // Simulate occupancy patterns for energy saving testing
      static int occupancy_counter = 0;
      occupancy_counter++;
      // Simulate occupancy patterns: sometimes empty for energy saving testing
      int occupancy = (occupancy_counter % 3 != 0) ? 1 : 0; // ~67% occupied
      
      // Simulate temperature (indoor range)
      int temperature = 20 + (random_rand() % 10); // 20-30°C
      
      // Energy consumption based on occupancy and manual override
      float room_usage;
      if(manual_override) {
          // Manual control - user decides LED status regardless of optimization
          room_usage = led_status ? 0.15 : 0.05;
          energy_saving_mode = 0;
      } else {
          // Automatic energy optimization mode
          if(occupancy == 0 && room_usage > 0.1) {
              // Energy waste detection - lights on but room empty
              room_usage = 0.02;  // Reduce consumption
              energy_saving_mode = 1;
              leds_on(LEDS_GREEN);  // Green = Energy saving active
          } else if(occupancy == 1) {
              room_usage = 0.12 + (random_rand() % 8) / 100.0;  // 0.12-0.20 kWh
              leds_off(LEDS_GREEN);
              energy_saving_mode = 0;
          } else {
              room_usage = 0.02 + (random_rand() % 3) / 100.0;  // Low consumption when empty
          }
      }
      
      char msg[512];
      snprintf(msg, sizeof(msg), 
               "{"
               "\"device_id\":\"node1\","
               "\"location\":\"living_room\","
               "\"lux\":%d,"
               "\"occupancy\":%d,"
               "\"temperature\":%d,"
               "\"room_usage\":%.3f,"
               "\"led_status\":%d,"
               "\"manual_override\":%d,"
               "\"energy_saving_mode\":%d,"
               "\"button_presses\":%d"
               "}", 
               light_val, occupancy, temperature, room_usage,
               led_status, manual_override, energy_saving_mode, button_count);
      
      mqtt_publish(&conn, NULL, pub_topic, (uint8_t *)msg, strlen(msg), MQTT_QOS_LEVEL_0, MQTT_RETAIN_OFF);

      LOG_INFO("📊 [LIVING] Lux:%d, Occ:%d, T:%d°C, Usage:%.3fkWh, LED:%s, Mode:%s\n", 
               light_val, occupancy, temperature, room_usage,
               led_status ? "ON" : "OFF",
               manual_override ? "MANUAL" : "AUTO");
      etimer_reset(&timer);
    }
  }

  PROCESS_END();
}