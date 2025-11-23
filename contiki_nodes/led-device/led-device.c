#include <contiki.h>
#include <net/app-layer/coap/coap-engine.h>
#include <dev/leds.h>
#include <contiki-net.h>
#include <net/ipv6/uip-ds6.h>

#include <net/app-layer/coap/coap-callback-api.h>
#include <net/routing/routing.h>
#include <mqtt.h>
#include <net/routing/rpl-lite/rpl.h>
#include <os/lib/json/jsonparse.h>
#include <net/ipv6/uip.h>
#include <net/ipv6/uiplib.h>

#include <string.h>
#include <stdio.h>

#include "resources-led.h"   // risorsa CoAP per controllare il led

/*---------------------------------------------------------------------------*/
#define LOG_LEVEL LOG_LEVEL_INFO
#include "sys/log.h"
#define LOG_MODULE "MQTT-Client"

/*---------------------------------------------------------------------------*/
/* Variabili MQTT */
static struct mqtt_connection conn;

#define MQTT_BROKER_IP_ADDR "fd00::1"   // Border Router come gateway broker
#define MQTT_BROKER_PORT 1883
#define PUBLISH_INTERVAL (3 * CLOCK_SECOND)
#define MAX_TCP_SEGMENT_SIZE    256
#define CLIENT_ID "led_node"
#define MQTT_PUB_TOPIC "led/status"

extern coap_resource_t res_led;

static char pub_message[256];
struct node_data {
    int led_state;
};

static struct node_data node_data_state;

/*---------------------------------------------------------------------------*/
/* Timer per pubblicazione periodica */
static struct etimer publish_timer;
static int retry_flag = 0;

/*---------------------------------------------------------------------------*/
/* Function to convert MQTT connection state to string */
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

/*---------------------------------------------------------------------------*/
/* Funzione di pubblicazione stato LED */
static void publish_led_status(int state) {
    snprintf(pub_message, sizeof(pub_message), "%s", state ? "ON" : "OFF");
    int ret = mqtt_publish(&conn, NULL,
            MQTT_PUB_TOPIC,
            (uint8_t *) pub_message,
            strlen(pub_message),
            MQTT_QOS_LEVEL_0,
            MQTT_RETAIN_OFF);
    if(ret != 0) {
        printf("MQTT: Publish failed with code %d\n", ret);
    } else {
        printf("MQTT: Published %s to %s\n", pub_message, MQTT_PUB_TOPIC);
    }
}

/*---------------------------------------------------------------------------*/
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

/*---------------------------------------------------------------------------*/
/* MAIN PROCESS */

PROCESS(led_device_process, "MQTT Random Publisher");
AUTOSTART_PROCESSES(&led_device_process);

PROCESS_THREAD(led_device_process, ev, data)
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

    /* ---- Init COAP ---- */
    coap_engine_init();
    coap_activate_resource(&res_led, "led");

    /* ---- Init MQTT ---- */
    mqtt_register(&conn, &led_device_process, CLIENT_ID, mqtt_event, MAX_TCP_SEGMENT_SIZE);
    mqtt_connect(&conn, MQTT_BROKER_IP_ADDR, MQTT_BROKER_PORT, PUBLISH_INTERVAL, MQTT_CLEAN_SESSION_ON);

    /* Stato iniziale LED spento */
    node_data_state.led_state = 0;
    leds_off(LEDS_RED);
    publish_led_status(node_data_state.led_state);

    /* Avvia timer per pubblicazione periodica */
    etimer_set(&publish_timer, PUBLISH_INTERVAL);

    while(1) {
        PROCESS_YIELD();
        /* Eventi CoAP o MQTT vengono gestiti nei rispettivi task */
        if(etimer_expired(&publish_timer)) {
            if(conn.state == MQTT_CONN_STATE_CONNECTED_TO_BROKER) {
                LOG_INFO("Node seems connected, publishing\n");
                publish_led_status(node_data_state.led_state);
                LOG_INFO("Published %s to %s\n", pub_message, MQTT_PUB_TOPIC);
            }
            else
            {
                LOG_INFO("Node does not seem connected, connection state: %s .\n", mqtt_state_to_string(conn.state));
                if(retry_flag) {
                    LOG_INFO("Retrying MQTT connection...\n");
                    int ret = mqtt_connect(&conn, MQTT_BROKER_IP_ADDR,
                                MQTT_BROKER_PORT,
                                (CLOCK_SECOND * 60),
                                MQTT_CLEAN_SESSION_ON);
                    if(ret != 0) {
                        LOG_INFO("MQTT: Connect failed with code %d\n", ret);
                    }
                    retry_flag = 0;  // Reset flag after attempting retry
                }
            }

            etimer_reset(&publish_timer);
        }
    }

    PROCESS_END();
}

/*---------------------------------------------------------------------------*/
/* Funzioni usate dalla risorsa CoAP per aggiornare MQTT */
void led_set(int state) {
    if(state) leds_on(LEDS_RED);
    else leds_off(LEDS_RED);
    node_data_state.led_state = state;
}