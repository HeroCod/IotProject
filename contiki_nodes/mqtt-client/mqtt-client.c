#include <contiki.h>
#include <contiki-net.h>
#include <net/ipv6/uip-ds6.h>
#include <net/routing/routing.h>
#include <mqtt.h>
#include <lib/random.h>

#include <string.h>
#include <stdio.h>

#define LOG_LEVEL LOG_LEVEL_INFO
#include "sys/log.h"
#define LOG_MODULE "MQTT-Client"

// MQTT Configuration
#define BROKER_IP_ADDR "fd00::1"
#define BROKER_PORT 1883
#define MQTT_CLIENT_ID "sensor_node"
#define MQTT_PUB_TOPIC "led/status"
#define MQTT_STATUS_INTERVAL (CLOCK_SECOND * 3)
#define MAX_TCP_SEGMENT_SIZE 32
#define MQTT_BUF_SIZE 256

static struct mqtt_connection conn;
static char pub_message[32];
static struct etimer periodic_timer;
static int retry_flag = 0;

// Function to generate random value
static int get_random_number()
{
    return (random_rand() % 10) + 1;
}

// Function to convert MQTT connection state to string
static const char* mqtt_state_to_string(mqtt_conn_state_t state) {
    switch(state) {
        case MQTT_CONN_STATE_NOT_CONNECTED:
            return "NOT_CONNECTED";
        case MQTT_CONN_STATE_TCP_CONNECTING:
            return "CONNECTING";
        case MQTT_CONN_STATE_TCP_CONNECTED:
            return "CONNECTED";
        case MQTT_CONN_STATE_DISCONNECTING:
            return "DISCONNECTING";
        case MQTT_CONN_STATE_ERROR:
            return "ERROR";
        case MQTT_CONN_STATE_DNS_ERROR:
            return "DNS_ERROR";
        case MQTT_CONN_STATE_ABORT_IMMEDIATE:
            return "ABORT_IMMEDIATE";
        case MQTT_CONN_STATE_DNS_LOOKUP:
            return "DNS_LOOKUP";
        case MQTT_CONN_STATE_CONNECTING_TO_BROKER:
            return "CONNECTING_TO_BROKER";
        case MQTT_CONN_STATE_CONNECTED_TO_BROKER:
            return "CONNECTED_TO_BROKER";
        case MQTT_CONN_STATE_SENDING_MQTT_DISCONNECT:
            return "SENDING_MQTT_DISCONNECT";
        default:
            return "UNKNOWN";
    }
}

// Callback for MQTT events
static void mqtt_event(struct mqtt_connection *m,
                    mqtt_event_t event,
                    void *data)
{
    switch(event) {
        case MQTT_EVENT_CONNECTED:
            LOG_INFO("MQTT connected\n");
            retry_flag = 0;  // Reset retry flag on successful connection
            break;

        case MQTT_EVENT_DISCONNECTED:
            LOG_INFO("MQTT disconnected, reason: %u\n", *((uint16_t *)data));
            retry_flag = 1;  // Set flag to retry connection
            break;
        case MQTT_EVENT_CONNECTION_REFUSED_ERROR:
            LOG_INFO("MQTT connect failed, error: %u\n", *((uint16_t *)data));
            retry_flag = 1;  // Set flag to retry on connection refused
            break;
        default:
            LOG_INFO("MQTT event: %i, data: %p\n", event, data);
            break;
    }
}

PROCESS(mqtt_random_process, "MQTT Random Publisher");
AUTOSTART_PROCESSES(&mqtt_random_process);

PROCESS_THREAD(mqtt_random_process, ev, data)
{
    PROCESS_BEGIN();

    LOG_INFO("Starting MQTT Random Status Publisher\n");

    // Wait until we get a global IPv6 address
    while(!uip_ds6_get_global(ADDR_PREFERRED)) {
        LOG_INFO("Waiting for IP auto-configuration\n");
        PROCESS_PAUSE();
    }

    uip_ds6_addr_t *addr = uip_ds6_get_global(ADDR_PREFERRED);
    if (addr) {
        LOG_INFO("Node IPv6 addr: ");
        LOG_INFO_6ADDR(&addr->ipaddr);
        LOG_INFO_("\n");
    } else {
        LOG_INFO("No global IPv6 addr, cannot connect\n");
    }

    // Set up MQTT connection
    mqtt_register(&conn, &mqtt_random_process, MQTT_CLIENT_ID, mqtt_event, MQTT_BUF_SIZE);

    mqtt_connect(&conn, BROKER_IP_ADDR, BROKER_PORT,
                 (CLOCK_SECOND * 60), MQTT_CLEAN_SESSION_ON);
    LOG_INFO("Attempting MQTT connect to %s:%d\n", BROKER_IP_ADDR, BROKER_PORT);

    // Set periodic timer to publish every 3 seconds
    etimer_set(&periodic_timer, MQTT_STATUS_INTERVAL);

    while(1) {
        PROCESS_YIELD();

        if(etimer_expired(&periodic_timer)) {
            LOG_INFO("Timer expired, trying to publish...\n");
            if(conn.state == MQTT_CONN_STATE_CONNECTED_TO_BROKER) {
                LOG_INFO("Node seems connected, publishing\n");
                int number = get_random_number();

                snprintf(pub_message, sizeof(pub_message), "%d", number);

                mqtt_publish(&conn, NULL,
                            MQTT_PUB_TOPIC, (uint8_t *)pub_message, strlen(pub_message),
                            MQTT_QOS_LEVEL_0, MQTT_RETAIN_OFF);

                LOG_INFO("Published %s to %s\n", pub_message, MQTT_PUB_TOPIC);
            }
            else
            {
                LOG_INFO("Node does not seem connected, connection state: %s .\n", mqtt_state_to_string(conn.state));
                if(retry_flag) {
                    LOG_INFO("Retrying MQTT connection...\n");
                    mqtt_connect(&conn, BROKER_IP_ADDR, BROKER_PORT,
                                 (CLOCK_SECOND * 60), MQTT_CLEAN_SESSION_ON);
                    retry_flag = 0;  // Reset flag after attempting retry
                }
            }

            etimer_reset(&periodic_timer);
        }
    }

    PROCESS_END();
}