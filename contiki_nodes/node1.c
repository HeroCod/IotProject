#include "contiki.h"
#include "sys/log.h"
#include "net/ipv6/simple-udp.h"
#include "net/ipv6/uip.h"
#include "mqtt.h"
#include "dev/leds.h"
#include "dev/button-hal.h"

#define LOG_MODULE "Node1"
#define LOG_LEVEL LOG_LEVEL_INFO

// MQTT broker config (Docker mosquito container)
#define MQTT_CLIENT_ID "node1"
#define MQTT_BROKER_IP "fd00::1"    // border router IPv6, change in Cooja
#define MQTT_BROKER_PORT 1883

static struct mqtt_connection conn;
static char pub_topic[] = "sensors/node1/light";
static char sub_topic[] = "actuators/node1/led";

PROCESS(node1_process, "Node1 Process");
AUTOSTART_PROCESSES(&node1_process);

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

PROCESS_THREAD(node1_process, ev, data) {
  static struct etimer timer;
  static int light_val;

  PROCESS_BEGIN();

  mqtt_register(&conn, &node1_process, MQTT_CLIENT_ID, mqtt_event, 256);
  mqtt_connect(&conn, MQTT_BROKER_IP, MQTT_BROKER_PORT, 1000, 1);

  etimer_set(&timer, CLOCK_SECOND * 10);

  while(1) {
    PROCESS_WAIT_EVENT();
    if(etimer_expired(&timer)) {
      light_val = random_rand() % 100; // fake sensor value
      char msg[50];
      snprintf(msg, sizeof(msg), "{\"sensor_id\":\"node1\",\"lux\":%d}", light_val);
      mqtt_publish(&conn, NULL, pub_topic, (uint8_t *)msg, strlen(msg), MQTT_QOS_LEVEL_0, MQTT_RETAIN_OFF);

      LOG_INFO("Published light=%d\n", light_val);
      etimer_reset(&timer);
    }
  }

  PROCESS_END();
}