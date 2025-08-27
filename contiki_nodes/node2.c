#include "contiki.h"
#include "sys/log.h"
#include "net/ipv6/simple-udp.h"
#include "net/ipv6/uip.h"
#include "mqtt.h"
#include "dev/leds.h"
#include "dev/button-hal.h"

#define LOG_MODULE "Node2"
#define LOG_LEVEL LOG_LEVEL_INFO

// MQTT broker config (Docker mosquito container)
#define MQTT_CLIENT_ID "node2"
#define MQTT_BROKER_IP "fd00::1"    // border router IPv6, change in Cooja
#define MQTT_BROKER_PORT 1883

static struct mqtt_connection conn;
static char pub_topic[] = "sensors/node2/light";
static char sub_topic[] = "actuators/node2/led";

PROCESS(node2_process, "Node2 Process");
AUTOSTART_PROCESSES(&node2_process);

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
        if(strncmp((char *)msg->payload_chunk, "on", 2) == 0) {
          leds_on(LEDS_GREEN);
        } else {
          leds_off(LEDS_GREEN);
        }
      }
      break;
    }
    default:
      break;
  }
}

PROCESS_THREAD(node2_process, ev, data) {
  static struct etimer timer;
  static int light_val;

  PROCESS_BEGIN();

  mqtt_register(&conn, &node2_process, MQTT_CLIENT_ID, mqtt_event, 256);
  mqtt_connect(&conn, MQTT_BROKER_IP, MQTT_BROKER_PORT, 1000, 1);

  etimer_set(&timer, CLOCK_SECOND * 10);

  while(1) {
    PROCESS_WAIT_EVENT();
    if(etimer_expired(&timer)) {
      // Generate realistic smart home energy sensor data
      light_val = random_rand() % 100; // ambient light sensor
      
      // Simulate occupancy based on activity patterns
      static int occupancy = 1; // Assume occupied for demo
      
      // Simulate temperature (indoor range)
      int temperature = 20 + (random_rand() % 10); // 20-30°C
      
      // Simulate energy sensors for smart energy optimization
      // Solar surplus: positive = excess solar, negative = using grid
      float solar_surplus = -0.5 + (random_rand() % 100) / 100.0; // -0.5 to +0.5 kW
      
      // Room energy usage (simulated from appliances)
      float room_usage = 0.02 + (random_rand() % 20) / 100.0; // 0.02-0.22 kW
      
      // Weather simulation for energy model
      float cloud_cover = (random_rand() % 100) / 100.0; // 0.0-1.0
      float visibility = 5 + (random_rand() % 10); // 5-15 km
      
      char msg[256];
      snprintf(msg, sizeof(msg), 
               "{\"sensor_id\":\"node2\",\"lux\":%d,\"occupancy\":%d,\"temperature\":%d,"
               "\"solar_surplus\":%.2f,\"room_usage\":%.2f,\"cloud_cover\":%.2f,\"visibility\":%.1f}", 
               light_val, occupancy, temperature, solar_surplus, room_usage, cloud_cover, visibility);
      
      mqtt_publish(&conn, NULL, pub_topic, (uint8_t *)msg, strlen(msg), MQTT_QOS_LEVEL_0, MQTT_RETAIN_OFF);

      LOG_INFO("Published: light=%d, occ=%d, temp=%d, solar=%.2f, room=%.2f\n", 
               light_val, occupancy, temperature, solar_surplus, room_usage);
      etimer_reset(&timer);
    }
  }

  PROCESS_END();
}