/*
 * Node 3 - Office Room Temperature Control Node
 * SOLO PROJECT Implementation with Temperature Prediction & Heating Control
 * MQTT to Border Router implementation
 *
 * Features:
 * - Temperature prediction using ML model (48-hour history)
 * - Weekly temperature schedule management
 * - Automatic heating control based on predictions
 * - Room occupancy simulation (sensor-based, not predicted)
 * - Ambient light monitoring
 * - Energy consumption tracking
 * - Physical button for manual control
 * - LED feedback for heating status
 * - MQTT messaging to border router
 * - CoAP endpoint for temperature schedule updates
 *
 * LED Usage:
 * - RED LED: Heating is ON
 * - GREEN LED: Temperature on target (heating OFF)
 * - YELLOW LED: Override active (manual heating control)
 * - BLUE LED: Communication indicator (brief flash when sending data)
 */

#include <contiki.h>
#include <sys/rtimer.h>

#include <net/app-layer/coap/coap-engine.h>
#include <net/app-layer/coap/coap-callback-api.h>

#include <net/routing/routing.h>
#include <net/routing/rpl-lite/rpl.h>
#include <net/ipv6/uip.h>
#include <net/ipv6/uiplib.h>
#include <net/netstack.h>
#include <contiki-net.h>
#include <net/ipv6/uip-ds6.h>

#include <os/lib/json/jsonparse.h>
#include <lib/random.h>
#include <math.h>
#include <string.h>
#include <mqtt.h>

#include <dev/leds.h>
#include <dev/button-hal.h>

#include <stdio.h>
#include <stdlib.h>

#include <sys/log.h>

#pragma GCC diagnostic ignored "-Wunused-variable"
#pragma GCC diagnostic pop

#include "temperature_model.h"

#define MANUAL_OVERRIDE_STR "mo"
#define OPTIMIZATION_EVENT_STR "oe"
#define HEATING_STATUS_STR "hs"
#define LED_STATUS_STR "ls"
#define OVERRIDE_DURATION_STR "od"
#define AUTO_BEHEAVIOUR_STR "ab"

// Temperature control settings
#define TEMP_CHECK_INTERVAL 120  // Check every 30 minutes (120 * 15s cycles)
#define TEMP_THRESHOLD_LOW 1.0f   // Turn ON heating if predicted temp is 1°C below target
#define TEMP_THRESHOLD_HIGH 2.0f  // Turn OFF heating if predicted temp is 2°C above target
#define TEMP_HISTORY_SIZE 96      // 96 readings = 24 hours at 15-min intervals

// cap permanent override to 100 years
#define MAX_CYCLE_OVERRIDE 1576800000

#define LOG_MODULE "Node3-Office"
#define LOG_LEVEL LOG_LEVEL_INFO

#define MQTT_BROKER_IP_ADDR "fd00::1"
#define MQTT_BROKER_PORT 1883
#define PUBLISH_INTERVAL (15 * CLOCK_SECOND)
#define MAX_TCP_SEGMENT_SIZE 768
#define MQTT_MESSAGE_BUFFER_SIZE 768
#define CLIENT_ID "node3"
#define MQTT_PUB_TOPIC "sensors/node3/data"

static int len = 0;                     // Length of the outgoing message

static int isManualOverride = 0;        // Manual control via button or request
static int isOptimizationEvent = 0;     // Optimization event flag (set when system detects temperature deviation)
static int isHeatingOn = 0;             // Heating system status
static int isLedOn = 0;                 // LED illumination status (separate from heating)
static int overrideCyclesRemaining = 0; // Override time remaining (in cycles)
static int isAutoBehaviorEnabled = 1;   // Auto behavior control

// Temperature prediction and control
static float temperatureHistory[TEMP_HISTORY_SIZE]; // Rolling buffer of past 96 temperature readings
static int tempHistoryIndex = 0;                    // Current index in temperature history
static int tempHistoryFilled = 0;                   // Flag to indicate if history buffer is full
static int cyclesSinceLastTempCheck = 0;            // Counter for 15-minute intervals
static float predictedTemperature = 22.0f;          // Predicted temperature for next 15 minutes (immediate)
static float predictionBuffer[TEMP_HISTORY_SIZE];   // 24-hour ahead predictions (96 values for 96 x 15min)
static int predictionBufferFilled = 0;              // Flag to indicate if prediction buffer is filled
static float targetTemperature = 0.0f;             // Current target temperature from schedule (0 = unset)
static float nextTargetTemperature = 0.0f;         // Next scheduled target temperature
static int nextTargetHour = -1;                     // Hour of next scheduled target

// Weekly temperature schedule (168 entries for 7 days * 24 hours)
// Each entry represents the target temperature for that hour (0.0 = unset)
static float weeklySchedule[168];
static int scheduleInitialized = 0;

// Temperature simulation with heating
static float simulatedTemperatureFloat = 22.0f;     // Actual simulated temperature (float for precision)
static float heatingRatePerCycle = 0.0f;           // Temperature increase per 15s cycle when heating
static float coolingRatePerCycle = 0.0f;           // Natural temperature decrease per cycle

static int heatingChangeCooldown = 0;       // Prevent rapid heating changes

static float simulatedHour = 0.0;           // Simulated time of day (0-24) for day-like rhythm
static int simulatedDay = 0;                // Simulated day of week (0-6, 0=Monday)

// Clock synchronization with server
static int clockSynced = 0;                 // Flag indicating if clock has been synced with server
static int serverDayOfWeek = 0;             // Server's day of week (0-6, 0=Monday)
static int serverHour = 0;                  // Server's hour (0-23)
static int serverMinute = 0;                // Server's minute (0-59)
// Note: Controller broadcasts time sync periodically - node does not track cycles

static int isButtonOccupancyActive = 0;     // Button-triggered simulation of room occupation
static int buttonOccupancyCyclesRemaining = 0;  // Timer for button occupation (in cycles)

static int isSystemOccupancyActive = 0;     // Is there an active system-simulated occupancy period?
static int systemOccupancyCyclesRemaining = 0;  // How many cycles left in current system occupancy period
static int systemOccupancyPeriodLength = 0;     // Total length of current system occupancy period

// Simulated sensor values
static int simulatedOccupancy = 0;          // Simulated occupancy state (from sensor, not predicted)
static int isSystemSimulatingOccupancy = 0; // Actual simulated occupancy (ground truth)
static int ambientLightLevel = 15;          // Ambient light level in lux
static int temperatureCelsius = 20;         // Temperature reading in Celsius for the Office
static int humidityPercent = 30;            // Humidity reading in percentage
static int co2Ppm = 400;                    // CO2 level in parts per million
static int roomEnergyUsageWh = 2;           // Room energy usage in Wh per 15-second interval

static char nodeIpAddress[64] = "";        // Node's IPv6 address as string

// Time synchronization state
static int historical_data_received = 0;  // Flag to track if we've received initial sync from controller

static struct etimer timer;            // App Timer
static struct etimer retry_timer;      // Retry Timer for MQTT reconnection

/*---------------------------------------------------------------------------*/
/* MQTT Variables */
static struct mqtt_connection mqttConnection;
static char mqttPublishMessage[MQTT_MESSAGE_BUFFER_SIZE];
static int retry_flag = 0;

static void stats_get_handler(coap_message_t *request, coap_message_t *response, uint8_t *buffer, uint16_t preferred_size, int32_t *offset);
static void stats_event_handler();
static void settings_get_handler(coap_message_t *request, coap_message_t *response, uint8_t *buffer, uint16_t preferred_size, int32_t *offset);
static void settings_put_handler(coap_message_t *request, coap_message_t *response, uint8_t *buffer, uint16_t preferred_size, int32_t *offset);
static void schedule_get_handler(coap_message_t *request, coap_message_t *response, uint8_t *buffer, uint16_t preferred_size, int32_t *offset);
static void schedule_put_handler(coap_message_t *request, coap_message_t *response, uint8_t *buffer, uint16_t preferred_size, int32_t *offset);
static void time_sync_get_handler(coap_message_t *request, coap_message_t *response, uint8_t *buffer, uint16_t preferred_size, int32_t *offset);
static void time_sync_put_handler(coap_message_t *request, coap_message_t *response, uint8_t *buffer, uint16_t preferred_size, int32_t *offset);
static void find_next_target_temperature();
static void predict_next_24_hours();

PROCESS(node3_process, "Node3 Process");
AUTOSTART_PROCESSES(&node3_process);

EVENT_RESOURCE(
    sensor_event,
    "title=\"Sensor statistics\"; rt=\"sensor-stats\"; if=\"core.s\"; ct=50; obs",
    stats_get_handler,
    NULL,
    NULL,
    NULL,
    stats_event_handler
);

RESOURCE(
    settings_resource,
    "title=\"Node settings\"; rt=\"node-settings\"; if=\"core.p\"; ct=50",
    settings_get_handler,
    NULL,
    settings_put_handler,
    NULL
);

RESOURCE(
    schedule_resource,
    "title=\"Temperature schedule\"; rt=\"temp-schedule\"; if=\"core.p\"; ct=50",
    schedule_get_handler,
    NULL,
    schedule_put_handler,
    NULL
);

RESOURCE(
    time_sync_resource,
    "title=\"Time synchronization\"; rt=\"time-sync\"; if=\"core.p\"; ct=50",
    time_sync_get_handler,
    NULL,
    time_sync_put_handler,
    NULL
);

static void stats_get_handler(coap_message_t *request, coap_message_t *response, uint8_t *buffer, uint16_t preferred_size, int32_t *offset)
{
    LOG_INFO("GET /node/stats\n");

    len = 0;
    len = snprintf(
        (char *)buffer,
        preferred_size,
        "{"
        "\"device_id\":\"node3\","
        "\"location\":\"office\","
        "\"lux\":%d,"
        "\"occupancy\":%d,"
        "\"temperature\":%d,"
        "\"predicted_temp\":%.2f,"
        "\"target_temp\":%.2f,"
        "\"humidity\":%d,"
        "\"co2\":%d,"
        "\"room_usage_wh\":%d,"
        "\"heating_status\":%d,"
        "\"manual_override\":%d,"
        "\"optimization_event\":%d,"
        "\"sim_occupancy\":%d"
        "}",
        ambientLightLevel, simulatedOccupancy, temperatureCelsius, predictedTemperature,
        targetTemperature, humidityPercent, co2Ppm,
        roomEnergyUsageWh, isHeatingOn, isManualOverride, isOptimizationEvent, isSystemSimulatingOccupancy
    );

    coap_set_header_content_format(response, APPLICATION_JSON);
    coap_set_payload(response, buffer, len);
}

static void stats_event_handler()
{
    coap_notify_observers(&sensor_event);
}

static void settings_get_handler(coap_message_t *request, coap_message_t *response, uint8_t *buffer, uint16_t preferred_size, int32_t *offset)
{
    LOG_INFO("GET /settings\n");

    len = 0;
    len = snprintf(
        (char *)buffer,
        preferred_size,
        "{"
        "\"device_id\":\"node3\","
        "\"location\":\"living_room\","
        "\"manual_override\":%d,"
        "\"optimization_event\":%d,"
        "\"heating_status\":%d,"
        "\"led_status\":%d,"
        "\"override_duration\":%d,"
        "\"auto_behavior_enabled\":%d,"
        "\"schedule_initialized\":%d,"
        "\"target_temp\":%.2f"
        "}",
        isManualOverride, isOptimizationEvent, isHeatingOn, isLedOn, overrideCyclesRemaining,
        isAutoBehaviorEnabled, scheduleInitialized, targetTemperature
    );

    coap_set_header_content_format(response, APPLICATION_JSON);
    coap_set_payload(response, buffer, len);
}

// Function to update visual feedback LEDs based on heating and LED status
static void update_status_leds() {
    if(isManualOverride) {
        // Manual override - Use combination of LEDs to show both states
        // RED = Heating ON, GREEN = LED ON, NO BLUE = Override active
        leds_off(LEDS_BLUE);  // Blue off indicates manual override
        leds_off(LEDS_YELLOW);

        if(isHeatingOn) {
            leds_on(LEDS_RED);
        } else {
            leds_off(LEDS_RED);
        }

        if(isLedOn) {
            leds_on(LEDS_GREEN);
        } else {
            leds_off(LEDS_GREEN);
        }

        LOG_INFO("\n");
        LOG_INFO("  .-------------.\n");
        LOG_INFO(" /  [O]   [O]   \\\n");
        LOG_INFO("|   MANUAL MODE  |\n");
        LOG_INFO("|   ===========  |\n");
        LOG_INFO("|   Heat: %-4s   |\n", isHeatingOn ? "ON " : "OFF");
        LOG_INFO("|   Light: %-3s   |\n", isLedOn ? "ON " : "OFF");
        LOG_INFO(" \\______________/\n\n");
    } else if(isHeatingOn) {
        // Heating ON - Red LED + Blue LED (auto mode)
        leds_on(LEDS_RED);
        leds_on(LEDS_BLUE);  // Blue indicates auto mode
        leds_off(LEDS_YELLOW);

        if(isLedOn) {
            leds_on(LEDS_GREEN);
        } else {
            leds_off(LEDS_GREEN);
        }

        LOG_INFO("\n");
        LOG_INFO("  .-------------.\n");
        LOG_INFO(" /    (^ u ^)    \\\n");
        LOG_INFO("|     HEATING!    |\n");
        LOG_INFO("|   ~~~AUTO~~~    |\n");
        LOG_INFO("|  [RED] + [BLUE] |\n");
        LOG_INFO("|   Light: %-3s    |\n", isLedOn ? "ON " : "OFF");
        LOG_INFO(" \\________________/\n\n");
    } else {
        // Heating OFF - Blue LED shows auto mode, Green for lights
        leds_off(LEDS_RED);
        leds_on(LEDS_BLUE);  // Blue indicates auto mode
        leds_off(LEDS_YELLOW);

        if(isLedOn) {
            leds_on(LEDS_GREEN);
        } else {
            leds_off(LEDS_GREEN);
        }

        LOG_INFO("\n");
        LOG_INFO("  .------------.\n");
        LOG_INFO(" /   (o w o)    \\\n");
        LOG_INFO("|    AUTO MODE   |\n");
        LOG_INFO("|   ---READY---  |\n");
        if(isLedOn) {
            LOG_INFO("|  [GRN] + [BLU] |\n");
        } else {
            LOG_INFO("|   [BLUE ONLY]  |\n");
        }
        LOG_INFO(" \\______________/\n\n");
    }
}

static void settings_put_handler(coap_message_t *request, coap_message_t *response, uint8_t *buffer, uint16_t preferred_size, int32_t *offset)
{
    // Parse json
    static int type;

    static struct jsonparse_state parser;

    static int newManualOverride;
    static int newOptimizationEvent;
    static int newIsHeatingOn;
    static int newOverrideCyclesRemaining;
    static int newIsAutoBehaviorEnabled;

    jsonparse_setup(&parser, (char *)request->payload, request->payload_len);
    while ((type = jsonparse_next(&parser)) != 0) {
        if (type == JSON_TYPE_PAIR_NAME) {
            if (jsonparse_strcmp_value(&parser, MANUAL_OVERRIDE_STR) == 0) {
                type = jsonparse_next(&parser);
                if (type == JSON_TYPE_NUMBER) {
                    newManualOverride = jsonparse_get_value_as_int(&parser);
                    isManualOverride = MIN(MAX(newManualOverride, 0), 1);
                }
            }
            else if (jsonparse_strcmp_value(&parser, OPTIMIZATION_EVENT_STR) == 0) {
                type = jsonparse_next(&parser);
                if (type == JSON_TYPE_NUMBER) {
                    newOptimizationEvent = jsonparse_get_value_as_int(&parser);
                    isOptimizationEvent = MIN(MAX(newOptimizationEvent, 0), 1);
                }
            }
            else if (jsonparse_strcmp_value(&parser, HEATING_STATUS_STR) == 0) {
                type = jsonparse_next(&parser);
                if (type == JSON_TYPE_NUMBER) {
                    newIsHeatingOn = (unsigned int)jsonparse_get_value_as_int(&parser);
                    isHeatingOn = MIN(MAX(newIsHeatingOn, 0), 1);
                    LOG_INFO("\n");
                    LOG_INFO("  >>>>>>>>>>>>>>>>>>>>>>>\n");
                    LOG_INFO("  > CONFIG UPDATED     >\n");
                    LOG_INFO("  > New Heating: %d     >\n", isHeatingOn);
                    LOG_INFO("  >>>>>>>>>>>>>>>>>>>>>>>\n\n");
                }
            }
            else if (jsonparse_strcmp_value(&parser, LED_STATUS_STR) == 0) {
                type = jsonparse_next(&parser);
                if (type == JSON_TYPE_NUMBER) {
                    int newIsLedOn = (unsigned int)jsonparse_get_value_as_int(&parser);
                    isLedOn = MIN(MAX(newIsLedOn, 0), 1);
                    LOG_INFO("\n");
                    LOG_INFO("  >>>>>>>>>>>>>>>>>>>>>>>\n");
                    LOG_INFO("  > CONFIG UPDATED     >\n");
                    LOG_INFO("  > New LED Status: %d  >\n", isLedOn);
                    LOG_INFO("  >>>>>>>>>>>>>>>>>>>>>>>\n\n");
                }
            }
            else if (jsonparse_strcmp_value(&parser, OVERRIDE_DURATION_STR) == 0) {
                type = jsonparse_next(&parser);
                if (type == JSON_TYPE_NUMBER) {
                    newOverrideCyclesRemaining = jsonparse_get_value_as_int(&parser);
                    overrideCyclesRemaining = MIN(MAX(newOverrideCyclesRemaining, 0), MAX_CYCLE_OVERRIDE);
                }
            }
            else if (jsonparse_strcmp_value(&parser, AUTO_BEHEAVIOUR_STR) == 0) {
                type = jsonparse_next(&parser);
                if (type == JSON_TYPE_NUMBER) {
                    newIsAutoBehaviorEnabled = jsonparse_get_value_as_int(&parser);
                    isAutoBehaviorEnabled = MIN(MAX(newIsAutoBehaviorEnabled, 0), 1);
                }
            }
            else {
                LOG_WARN("Unknown setting: %.*s\n", jsonparse_get_len(&parser), parser.json + parser.pos);
                coap_set_status_code(response, BAD_REQUEST_4_00);
                return;
            }
        }
    }
    coap_set_status_code(response, CHANGED_2_04);

    update_status_leds(); // Update status feedback LEDs

    settings_get_handler(request, response, buffer, preferred_size, offset);
}

/*---------------------------------------------------------------------------*/
/* Temperature schedule handlers */
static void schedule_get_handler(coap_message_t *request, coap_message_t *response, uint8_t *buffer, uint16_t preferred_size, int32_t *offset)
{
    LOG_INFO("GET /schedule\n");

    // Return compact status (full schedule is too large for CoAP response)
    // Format: {"initialized":1,"target":22.0,"set_count":120}
    int setCount = 0;
    for (int i = 0; i < 168; i++) {
        if (weeklySchedule[i] > 0) setCount++;
    }

    int len = snprintf((char *)buffer, preferred_size,
                    "{\"initialized\":%d,\"target\":%.1f,\"next_target\":%.1f,\"set_count\":%d}",
                    scheduleInitialized, (double)targetTemperature, (double)nextTargetTemperature, setCount);

    if (len >= preferred_size) {
        LOG_WARN("GET /schedule response truncated: %d >= %d\n", len, preferred_size);
    }

    coap_set_header_content_format(response, APPLICATION_JSON);
    coap_set_payload(response, buffer, len);
    coap_set_status_code(response, CONTENT_2_05);
}

static void schedule_put_handler(coap_message_t *request, coap_message_t *response, uint8_t *buffer, uint16_t preferred_size, int32_t *offset)
{
    LOG_INFO("\n");
    LOG_INFO("  ╔════════════════════════════════════════════╗\n");
    LOG_INFO("  ║    SCHEDULE UPDATE REQUEST RECEIVED        ║\n");
    LOG_INFO("  ╠════════════════════════════════════════════╣\n");
    LOG_INFO("  ║  Payload length: %d bytes                 ║\n", request->payload_len);
    LOG_INFO("  ╚════════════════════════════════════════════╝\n\n");

    // Parse JSON array of 168 temperature values
    // Expected format: {"schedule":[temp0, temp1, ..., temp167]}
    // Values can be 0 for unset hours
    struct jsonparse_state parser;
    int type;
    int scheduleIndex = 0;

    jsonparse_setup(&parser, (char *)request->payload, request->payload_len);

    while ((type = jsonparse_next(&parser)) != 0) {
        if (type == JSON_TYPE_PAIR_NAME) {
            if (jsonparse_strcmp_value(&parser, "schedule") == 0) {
                type = jsonparse_next(&parser); // Move to array
                if (type == JSON_TYPE_ARRAY) {
                    while ((type = jsonparse_next(&parser)) != 0 && scheduleIndex < 168) {
                        if (type == JSON_TYPE_NUMBER) {
                            int tempInt = jsonparse_get_value_as_int(&parser);
                            // Allow 0 for unset (changed from -1), or valid temperature range
                            if (tempInt == 0 || (tempInt >= 10 && tempInt <= 30)) {
                                weeklySchedule[scheduleIndex] = (float)tempInt;
                                if (scheduleIndex < 5 || scheduleIndex >= 163) {
                                    // Log first 5 and last 5 entries
                                    LOG_INFO("  [SCHEDULE] Index %d = %d°C\n", scheduleIndex, tempInt);
                                }
                                scheduleIndex++;
                            } else {
                                LOG_WARN("Invalid temperature value: %d at index %d\n", tempInt, scheduleIndex);
                                coap_set_status_code(response, BAD_REQUEST_4_00);
                                return;
                            }
                        }
                    }
                }
            }
        }
    }

    if (scheduleIndex == 168) {
        scheduleInitialized = 1;
        LOG_INFO("\n");
        LOG_INFO("  ╔════════════════════════════════════════════╗\n");
        LOG_INFO("  ║   SCHEDULE UPDATE SUCCESSFUL               ║\n");
        LOG_INFO("  ╠════════════════════════════════════════════╣\n");
        LOG_INFO("  ║  Total entries: 168                        ║\n");

        // Log summary of schedule
        int setCount = 0;
        for (int i = 0; i < 168; i++) {
            if (weeklySchedule[i] > 0) setCount++;
        }
        LOG_INFO("  ║  Set hours: %d/168                        ║\n", setCount);
        LOG_INFO("  ║  Unset hours: %d/168                        ║\n", 168 - setCount);
        LOG_INFO("  ╠════════════════════════════════════════════╣\n");
        LOG_INFO("  ║  BEFORE RECALCULATION:                     ║\n");
        LOG_INFO("  ║    Current time: Day %d, Hour %d            ║\n", simulatedDay, (int)simulatedHour);
        LOG_INFO("  ║    Old target: %d°C                         ║\n", (int)targetTemperature);
        LOG_INFO("  ║    Old next: %d°C @ hour %d                ║\n", (int)nextTargetTemperature, nextTargetHour);
        LOG_INFO("  ╚════════════════════════════════════════════╝\n\n");

        // Recalculate next target temperature after schedule update
        find_next_target_temperature();

        LOG_INFO("  ╔════════════════════════════════════════════╗\n");
        LOG_INFO("  ║  AFTER RECALCULATION:                      ║\n");
        LOG_INFO("  ║    New target: %d°C                         ║\n", (int)targetTemperature);
        LOG_INFO("  ║    New next: %d°C @ hour %d                ║\n", (int)nextTargetTemperature, nextTargetHour);
        LOG_INFO("  ╚════════════════════════════════════════════╝\n\n");

        // Recalculate 24-hour predictions after schedule update
        LOG_INFO("  [SCHEDULE] Recalculating 24h temperature predictions...\n");
        predict_next_24_hours();

        // Send compact success response
        int len = snprintf((char *)buffer, preferred_size,
                        "{\"success\":true,\"entries\":%d,\"set_count\":%d}",
                        scheduleIndex, setCount);

        coap_set_header_content_format(response, APPLICATION_JSON);
        coap_set_payload(response, buffer, len);
        coap_set_status_code(response, CHANGED_2_04);
    } else {
        LOG_WARN("Schedule update failed: received %d entries (expected 168)\n", scheduleIndex);

        int len = snprintf((char *)buffer, preferred_size,
                        "{\"success\":false,\"entries\":%d,\"expected\":168}",
                        scheduleIndex);

        coap_set_header_content_format(response, APPLICATION_JSON);
        coap_set_payload(response, buffer, len);
        coap_set_status_code(response, BAD_REQUEST_4_00);
    }
}

/*---------------------------------------------------------------------------*/
/* CoAP handler for GET /time_sync */
static void time_sync_get_handler(coap_message_t *request, coap_message_t *response, uint8_t *buffer, uint16_t preferred_size, int32_t *offset)
{
    LOG_INFO("GET /time_sync - Reporting clock synchronization status\n");

    int length = snprintf((char *)buffer, preferred_size,
                        "{\"synced\":%d,\"day\":%d,\"hour\":%d,\"minute\":%d}",
                        clockSynced, serverDayOfWeek, serverHour, serverMinute);

    coap_set_header_content_format(response, APPLICATION_JSON);
    coap_set_payload(response, buffer, length);
    coap_set_status_code(response, CONTENT_2_05);

    LOG_INFO("  - Synced: %s\n", clockSynced ? "YES" : "NO");
    LOG_INFO("  - Server time: Day %d, %02d:%02d\n", serverDayOfWeek, serverHour, serverMinute);
}

/*---------------------------------------------------------------------------*/
/* CoAP handler for PUT /time_sync */
static void time_sync_put_handler(coap_message_t *request, coap_message_t *response, uint8_t *buffer, uint16_t preferred_size, int32_t *offset)
{
    LOG_INFO("\n");
    LOG_INFO("  ╔════════════════════════════════╗\n");
    LOG_INFO("  ║   CLOCK SYNCHRONIZATION        ║\n");
    LOG_INFO("  ╠════════════════════════════════╣\n");

    // Parse JSON: {"day":0-6, "hour":0-23, "minute":0-59}
    struct jsonparse_state parser;
    int type;
    int newDay = -1, newHour = -1, newMinute = -1;

    jsonparse_setup(&parser, (char *)request->payload, request->payload_len);

    while ((type = jsonparse_next(&parser)) != 0) {
        if (type == JSON_TYPE_PAIR_NAME) {
            if (jsonparse_strcmp_value(&parser, "day") == 0) {
                jsonparse_next(&parser);
                newDay = jsonparse_get_value_as_int(&parser);
            } else if (jsonparse_strcmp_value(&parser, "hour") == 0) {
                jsonparse_next(&parser);
                newHour = jsonparse_get_value_as_int(&parser);
            } else if (jsonparse_strcmp_value(&parser, "minute") == 0) {
                jsonparse_next(&parser);
                newMinute = jsonparse_get_value_as_int(&parser);
            }
        }
    }

    // Validate inputs
    if (newDay < 0 || newDay > 6) {
        LOG_WARN("  ║  ERROR: Invalid day %d      ║\n", newDay);
        LOG_INFO("  ╚════════════════════════════════╝\n\n");
        coap_set_status_code(response, BAD_REQUEST_4_00);
        return;
    }
    if (newHour < 0 || newHour > 23) {
        LOG_WARN("  ║  ERROR: Invalid hour %d     ║\n", newHour);
        LOG_INFO("  ╚════════════════════════════════╝\n\n");
        coap_set_status_code(response, BAD_REQUEST_4_00);
        return;
    }
    if (newMinute < 0 || newMinute > 59) {
        LOG_WARN("  ║  ERROR: Invalid minute %d   ║\n", newMinute);
        LOG_INFO("  ╚════════════════════════════════╝\n\n");
        coap_set_status_code(response, BAD_REQUEST_4_00);
        return;
    }

    // Apply synchronization
    int oldDay = simulatedDay;
    int oldHour = (int)simulatedHour;

    simulatedDay = newDay;
    simulatedHour = (float)newHour + (newMinute / 60.0f);
    serverDayOfWeek = newDay;
    serverHour = newHour;
    serverMinute = newMinute;
    clockSynced = 1;
    // Note: cyclesSinceLastSync removed - controller broadcasts time periodically

    LOG_INFO("  ║  Old Time: Day %d, %02d:00        ║\n", oldDay, oldHour);
    LOG_INFO("  ║  New Time: Day %d, %02d:%02d        ║\n", newDay, newHour, newMinute);
    LOG_INFO("  ║                                ║\n");
    LOG_INFO("  ║        _____    ✓              ║\n");
    LOG_INFO("  ║       |  |  |  SYNCED          ║\n");
    LOG_INFO("  ║       |  *- |                  ║\n");
    LOG_INFO("  ║       |_____|                  ║\n");
    LOG_INFO("  ╚════════════════════════════════╝\n\n");

    // Recalculate next target after time change
    find_next_target_temperature();

    // Mark that we've received initial time sync from controller
    if (!historical_data_received) {
        historical_data_received = 1;
        tempHistoryFilled = 1;  // Use existing temperature history (initialized to 20°C)
        predictionBufferFilled = 0;  // Will be filled on first prediction

        LOG_INFO("  ║  ✓ INITIAL SYNC COMPLETE   ║\n");
        LOG_INFO("  ║    Node ready to operate   ║\n");

        // Trigger initial prediction
        predict_next_24_hours();
    }

    coap_set_status_code(response, CHANGED_2_04);

    // Return current sync status
    int length = snprintf((char *)buffer, preferred_size,
                         "{\"synced\":true,\"day\":%d,\"hour\":%d,\"minute\":%d}",
                         newDay, newHour, newMinute);
    coap_set_header_content_format(response, APPLICATION_JSON);
    coap_set_payload(response, buffer, length);
}

/*---------------------------------------------------------------------------*/
/* Helper function to initialize default schedule */
static void initialize_default_schedule() {
    // Initialize all to 0.0 (unset - 0 means no target set)
    for (int i = 0; i < 168; i++) {
        weeklySchedule[i] = 0.0f;
    }

    // Set key hours: wake up (7am), leave (9am), return (18pm), sleep (23pm)
    for (int day = 0; day < 7; day++) {
        int dayOffset = day * 24;
        weeklySchedule[dayOffset + 7] = 22.0f;   // 7am - wake up, warm house
        weeklySchedule[dayOffset + 9] = 18.0f;   // 9am - leave, reduce heating
        weeklySchedule[dayOffset + 18] = 22.0f;  // 6pm - return, warm house
        weeklySchedule[dayOffset + 23] = 18.0f;  // 11pm - sleep, reduce heating
    }

    scheduleInitialized = 1;

    // Calculate heating/cooling rates (1°C per 30 minutes = 120 cycles)
    heatingRatePerCycle = 1.0f / 120.0f;  // ~0.0083°C per 15s cycle
    coolingRatePerCycle = 0.5f / 120.0f;  // Natural cooling ~0.5°C per 30 min

    LOG_INFO("Default weekly schedule initialized\n");
    LOG_INFO("  - Heating rate: %.4f°C per cycle (1°C per 30 min)\n", heatingRatePerCycle);
    LOG_INFO("  - Cooling rate: %.4f°C per cycle (0.5°C per 30 min)\n", coolingRatePerCycle);
}

/*---------------------------------------------------------------------------*/
/* Helper function to find next scheduled target temperature */
static void find_next_target_temperature() {
    LOG_INFO("\n");
    LOG_INFO("  ╔════════════════════════════════════════════╗\n");
    LOG_INFO("  ║   FINDING NEXT TARGET TEMPERATURE          ║\n");
    LOG_INFO("  ╠════════════════════════════════════════════╣\n");
    LOG_INFO("  ║  Schedule initialized: %s                 ║\n", scheduleInitialized ? "YES" : "NO ");

    if (!scheduleInitialized) {
        LOG_INFO("  ║  ERROR: Schedule not initialized!          ║\n");
        LOG_INFO("  ╚════════════════════════════════════════════╝\n\n");
        nextTargetTemperature = 0.0f;
        nextTargetHour = -1;
        return;
    }

    int currentAbsoluteHour = simulatedDay * 24 + (int)simulatedHour;
    LOG_INFO("  ║  Current absolute hour: %d                ║\n", currentAbsoluteHour);
    LOG_INFO("  ║  (Day %d * 24 + Hour %d)                    ║\n", simulatedDay, (int)simulatedHour);
    LOG_INFO("  ╠════════════════════════════════════════════╣\n");
    LOG_INFO("  ║  Searching forward through schedule...     ║\n");

    // Search forward for next set temperature (within 168 hours)
    int foundCount = 0;
    for (int offset = 1; offset <= 168; offset++) {
        int searchIndex = (currentAbsoluteHour + offset) % 168;
        if (weeklySchedule[searchIndex] > 0) {  // Found a set temperature
            if (foundCount < 3) {  // Log first 3 found targets
                LOG_INFO("  ║  [+%d hrs] Index %d = %d°C                 ║\n", offset, searchIndex, (int)weeklySchedule[searchIndex]);
                foundCount++;
            }
            if (foundCount == 1) {  // Use the first one found
                nextTargetTemperature = weeklySchedule[searchIndex];
                nextTargetHour = searchIndex % 24;  // Hour of day (0-23)
                LOG_INFO("  ╠════════════════════════════════════════════╣\n");
                LOG_INFO("  ║  ✓ NEXT TARGET FOUND                       ║\n");
                LOG_INFO("  ║    Temperature: %d°C                       ║\n", (int)nextTargetTemperature);
                LOG_INFO("  ║    At hour: %d                             ║\n", nextTargetHour);
                LOG_INFO("  ║    In %d hours from now                     ║\n", offset);
                LOG_INFO("  ╚════════════════════════════════════════════╝\n\n");
                return;
            }
        }
    }

    // No scheduled temperature found
    LOG_INFO("  ║  ✗ NO TARGET FOUND                         ║\n");
    LOG_INFO("  ║    (No set temperatures in next 168 hrs)   ║\n");
    LOG_INFO("  ╚════════════════════════════════════════════╝\n\n");
    nextTargetTemperature = 0.0f;
    nextTargetHour = -1;
}

/*---------------------------------------------------------------------------*/
/* Helper function to get current target temperature from schedule */
static float get_target_temperature() {
    if (!scheduleInitialized) {
        LOG_INFO("  [TARGET] Schedule not initialized, returning 0\n");
        return 0.0f; // No schedule initialized
    }

    int currentIndex = simulatedDay * 24 + (int)simulatedHour;
    LOG_INFO("  [TARGET] Current index: %d (Day %d, Hour %d)\n", currentIndex, simulatedDay, (int)simulatedHour);

    if (currentIndex >= 0 && currentIndex < 168) {
        float temp = weeklySchedule[currentIndex];
        LOG_INFO("  [TARGET] Retrieved temperature: %d°C from schedule[%d]\n", (int)temp, currentIndex);
        return temp;
    }

    LOG_WARN("  [TARGET] Index out of range: %d, returning 0\n", currentIndex);
    return 0.0f; // Unset or out of range
}

/*---------------------------------------------------------------------------*/
/* Helper function to add temperature to history */
static void add_temperature_to_history(float temp) {
    temperatureHistory[tempHistoryIndex] = temp;
    tempHistoryIndex = (tempHistoryIndex + 1) % TEMP_HISTORY_SIZE;

    if (tempHistoryIndex == 0) {
        tempHistoryFilled = 1; // History buffer has wrapped around
    }
}

/*---------------------------------------------------------------------------*/
/* Helper function to predict next temperature using ML model (single step) */
static float predict_single_step(float* input_temps) {
    // Scale input features to [0, 1] range as expected by model
    int16_t scaled_features[TEMP_HISTORY_SIZE];
    for (int i = 0; i < TEMP_HISTORY_SIZE; i++) {
        float scaled = (input_temps[i] - TEMP_SCALER_MIN) / TEMP_SCALER_RANGE;
        // Convert to fixed-point int16_t (0-32767 range)
        scaled_features[i] = (int16_t)(scaled * 32767.0f);
    }

    // Use the ML model to predict (returns scaled value in [0, 1])
    float scaled_prediction = temperature_model_predict(scaled_features, TEMP_HISTORY_SIZE);

    // Convert back to Celsius
    float prediction = scaled_prediction * TEMP_SCALER_RANGE + TEMP_SCALER_MIN;

    return prediction;
}

/*---------------------------------------------------------------------------*/
/* Helper function to predict 24 hours ahead and update prediction buffer */
static void predict_next_24_hours() {
    LOG_INFO("\n");
    LOG_INFO("  ╔═══════════════════════════════════════════════════╗\n");
    LOG_INFO("  ║   24-HOUR TEMPERATURE PREDICTION                  ║\n");
    LOG_INFO("  ╠═══════════════════════════════════════════════════╣\n");

    // Use predictions even with dummy data (no longer require tempHistoryFilled)

    // Build array of 48 past temperatures in chronological order (rolling window)
    float rolling_window[TEMP_HISTORY_SIZE];
    int idx = tempHistoryIndex;
    for (int i = 0; i < TEMP_HISTORY_SIZE; i++) {
        rolling_window[i] = temperatureHistory[idx];
        idx = (idx + 1) % TEMP_HISTORY_SIZE;
    }

    int start_temp_int = (int)rolling_window[TEMP_HISTORY_SIZE - 1];
    int start_temp_dec = (int)((rolling_window[TEMP_HISTORY_SIZE - 1] - start_temp_int) * 10);
    LOG_INFO("  ║  Starting from current temperature: %d.%d°C        ║\n", start_temp_int, start_temp_dec);
    LOG_INFO("  ║  Computing 96 predictions (24 hours ahead)...     ║\n");
    LOG_INFO("  ╠═══════════════════════════════════════════════════╣\n");

    // Predict 96 steps ahead (24 hours at 15-minute intervals)
    for (int step = 0; step < TEMP_HISTORY_SIZE; step++) {
        // Predict next temperature based on current rolling window
        float next_prediction = predict_single_step(rolling_window);

        // Store prediction in buffer
        predictionBuffer[step] = next_prediction;

        // Shift rolling window: remove oldest, add new prediction
        for (int i = 0; i < TEMP_HISTORY_SIZE - 1; i++) {
            rolling_window[i] = rolling_window[i + 1];
        }
        rolling_window[TEMP_HISTORY_SIZE - 1] = next_prediction;

        // Log progress at key intervals (1h, 6h, 12h, 18h, 24h)
        if (step == 3 || step == 23 || step == 47 || step == 71 || step == 95) {
            float hours_ahead = (step + 1) * 0.25f;
            int hours_int = (int)hours_ahead;
            int hours_dec = (int)((hours_ahead - hours_int) * 10);
            int pred_int = (int)next_prediction;
            int pred_dec = (int)((next_prediction - pred_int) * 10);
            LOG_INFO("  ║  [+%d.%dh] Predicted: %d.%d°C                       ║\n",
                    hours_int, hours_dec, pred_int, pred_dec);
        }
    }

    predictionBufferFilled = 1;

    // Set immediate prediction (15 minutes ahead) for backward compatibility
    predictedTemperature = predictionBuffer[0];

    LOG_INFO("  ╠═══════════════════════════════════════════════════╣\n");
    LOG_INFO("  ║  ✓ 24-hour prediction complete                    ║\n");
    int imm_int = (int)predictionBuffer[0];
    int imm_dec = (int)((predictionBuffer[0] - imm_int) * 10);
    int mid_int = (int)predictionBuffer[47];
    int mid_dec = (int)((predictionBuffer[47] - mid_int) * 10);
    int long_int = (int)predictionBuffer[95];
    int long_dec = (int)((predictionBuffer[95] - long_int) * 10);
    LOG_INFO("  ║    Immediate (15min): %d.%d°C                      ║\n", imm_int, imm_dec);
    LOG_INFO("  ║    Mid-range (12h):   %d.%d°C                      ║\n", mid_int, mid_dec);
    LOG_INFO("  ║    Long-range (24h):  %d.%d°C                      ║\n", long_int, long_dec);
    LOG_INFO("  ╚═══════════════════════════════════════════════════╝\n\n");
}

/*---------------------------------------------------------------------------*/
/* Helper function to control heating based on prediction and next target */
static void control_heating() {
    if (isManualOverride) {
        LOG_INFO("  [CONTROL] Manual override active, skipping automatic control\n");
        return; // Don't change heating in manual mode
    }

    if (!isAutoBehaviorEnabled) {
        LOG_INFO("  [CONTROL] Auto behavior disabled, skipping automatic control\n");
        return;
    }

    LOG_INFO("\n");
    LOG_INFO("  ╔════════════════════════════════════════════╗\n");
    LOG_INFO("  ║   HEATING CONTROL DECISION PROCESS        ║\n");
    LOG_INFO("  ╠════════════════════════════════════════════╣\n");

    // Confirm current target temperature
    LOG_INFO("  ║  Step 1: Confirming current target temp   ║\n");
    targetTemperature = get_target_temperature();
    LOG_INFO("  ║  Current target = %d°C                     ║\n", (int)targetTemperature);

    // Find next scheduled target
    LOG_INFO("  ║  Step 2: Finding next scheduled target    ║\n");
    find_next_target_temperature();

    LOG_INFO("\n");
    LOG_INFO("  ╔════════════════════════════════╗\n");
    LOG_INFO("  ║   TEMPERATURE CONTROL CHECK   ║\n");
    LOG_INFO("  ╠════════════════════════════════╣\n");
    LOG_INFO("  ║  Current:    %5.1f°C          ║\n", (double)simulatedTemperatureFloat);
    LOG_INFO("  ║  Predicted:  %5.1f°C          ║\n", (double)predictedTemperature);

    if (targetTemperature > 0) {
        LOG_INFO("  ║  Target Now: %5.1f°C          ║\n", (double)targetTemperature);
    } else {
        LOG_INFO("  ║  Target Now: UNSET            ║\n");
    }

    if (nextTargetTemperature > 0) {
        LOG_INFO("  ║  Next Target: %5.1f°C @ %02dh   ║\n", (double)nextTargetTemperature, nextTargetHour);
    } else {
        LOG_INFO("  ║  Next Target: NONE SCHEDULED  ║\n");
    }

    LOG_INFO("  ╠════════════════════════════════╣\n");

    // Step 3: Analyze next 24 hours of predictions vs scheduled temperatures
    LOG_INFO("  ║  Step 3: Analyzing 24h forecast vs schedule ║\n");

    int shouldHeat = 0;
    int criticalGapFound = 0;
    float maxTempShortfall = 0.0f;  // Maximum temperature deficit found
    int shortfallStepIndex = -1;     // When the shortfall occurs

    if (!scheduleInitialized || !predictionBufferFilled) {
        LOG_INFO("  ║  WARNING: Predictions not ready          ║\n");
        // Fallback to simple control
        shouldHeat = isHeatingOn;
    } else {
        // Scan through prediction buffer (96 steps = 24 hours at 15-min intervals)
        int currentAbsoluteHour = simulatedDay * 24 + (int)simulatedHour;

        for (int step = 0; step < TEMP_HISTORY_SIZE; step++) {
            // Calculate absolute hour for this prediction step
            // Each step = 15 minutes = 0.25 hours ahead
            float hoursAhead = (step + 1) * 0.25f;
            int futureAbsoluteHour = currentAbsoluteHour + (int)(hoursAhead + 0.5f);
            int scheduleIndex = futureAbsoluteHour % 168;

            float scheduledTemp = weeklySchedule[scheduleIndex];
            float predictedTemp = predictionBuffer[step];

            // Only check hours where a temperature is set (scheduledTemp > 0)
            if (scheduledTemp > 0) {
                float tempGap = scheduledTemp - predictedTemp;

                // Track maximum shortfall (positive = need heating, negative = too hot)
                if (tempGap > maxTempShortfall) {
                    maxTempShortfall = tempGap;
                    shortfallStepIndex = step;
                }

                // Critical gap: prediction is significantly below schedule
                if (tempGap > TEMP_THRESHOLD_LOW) {
                    criticalGapFound = 1;
                    int hours_int = (int)hoursAhead;
                    int hours_dec = (int)((hoursAhead - hours_int) * 10);
                    LOG_INFO("  ║  ⚠ Gap at +%d.%dh: Need %d°C, Pred %d°C ║\n",
                            hours_int, hours_dec, (int)scheduledTemp, (int)predictedTemp);
                }
            }
        }

        // Decision logic based on 24-hour analysis
        if (criticalGapFound) {
            // Found at least one critical temperature shortfall - need heating
            shouldHeat = 1;
            int step_hours = (int)((shortfallStepIndex + 1) * 0.25f);
            if (!isHeatingOn) {
                LOG_INFO("  ║     HEATING ON                        ║\n");
                LOG_INFO("  ║  (Gap of +%.1f°C in ~%dh)              ║\n",
                        (double)maxTempShortfall, step_hours);
            } else {
                LOG_INFO("  ║     HEATING CONTINUES                 ║\n");
                LOG_INFO("  ║  (Still addressing %.1f°C gap)         ║\n", (double)maxTempShortfall);
            }
        } else if (maxTempShortfall < -TEMP_THRESHOLD_HIGH) {
            // Predictions are consistently too hot - turn off heating
            shouldHeat = 0;
            if (isHeatingOn) {
                LOG_INFO("  ║      HEATING OFF                      ║\n");
                LOG_INFO("  ║  (Overshoot: %.1f°C too hot)           ║\n", (double)(-maxTempShortfall));
                isOptimizationEvent = 1;
            } else {
                LOG_INFO("  ║      HEATING OFF (temps optimal)      ║\n");
            }
        } else {
            // Predictions align well with schedule - maintain current state
            shouldHeat = isHeatingOn;
            if (maxTempShortfall > 0) {
                LOG_INFO("  ║  ✓ MAINTAINING (minor gap %.1f°C)     ║\n", (double)maxTempShortfall);
            } else {
                LOG_INFO("  ║  ✓ MAINTAINING (temps on track)      ║\n");
            }
        }

        // Fallback: No scheduled temperatures in next 24h - maintain minimum
        int hasScheduledTemp = 0;
        for (int step = 0; step < TEMP_HISTORY_SIZE; step++) {
            int futureAbsoluteHour = currentAbsoluteHour + (int)((step + 1) * 0.25f + 0.5f);
            if (weeklySchedule[futureAbsoluteHour % 168] > 0) {
                hasScheduledTemp = 1;
                break;
            }
        }

        if (!hasScheduledTemp) {
            // No targets in next 24h - maintain minimum temperature (10°C)
            if (predictedTemperature < 10.0f) {
                shouldHeat = 1;
                if (!isHeatingOn) {
                    LOG_INFO("  ║  🔥 HEATING ON (min temp 10°C)        ║\n");
                }
            } else if (predictedTemperature > 20.0f) {
                shouldHeat = 0;
                if (isHeatingOn) {
                    LOG_INFO("  ║  ❄️  HEATING OFF (min reached)        ║\n");
                }
            } else {
                shouldHeat = isHeatingOn;
                LOG_INFO("  ║  ✓ NO TARGETS (maintaining baseline) ║\n");
            }
        }
    }

    isHeatingOn = shouldHeat;
    LOG_INFO("  ╚════════════════════════════════╝\n\n");

    update_status_leds();
}

/*---------------------------------------------------------------------------*/
/* MQTT Event Handler */
static void mqtt_event(struct mqtt_connection *m, mqtt_event_t event, void *data)
{
    switch(event) {
        case MQTT_EVENT_CONNECTED:
            LOG_INFO("\n");
            LOG_INFO("  ╔═══════════════════════════════╗\n");
            LOG_INFO("  ║    MQTT CONNECTION SUCCESS    ║\n");
            LOG_INFO("  ╠═══════════════════════════════╣\n");
            LOG_INFO("  ║         ___________           ║\n");
            LOG_INFO("  ║        |  BROKER  |           ║\n");
            LOG_INFO("  ║        |    ()    |           ║\n");
            LOG_INFO("  ║        |__________|           ║\n");
            LOG_INFO("  ║             ^                 ║\n");
            LOG_INFO("  ║             |                 ║\n");
            LOG_INFO("  ║         [CONNECTED]           ║\n");
            LOG_INFO("  ║             |                 ║\n");
            LOG_INFO("  ║             v                 ║\n");
            LOG_INFO("  ║           .---.               ║\n");
            LOG_INFO("  ║          ( ^_^ )              ║\n");
            LOG_INFO("  ║           |   |               ║\n");
            LOG_INFO("  ║          _|   |_              ║\n");
            LOG_INFO("  ║         |_NODE3_|             ║\n");
            LOG_INFO("  ╚═══════════════════════════════╝\n\n");
            retry_flag = 0;  // Reset retry flag on successful connection
            break;

        case MQTT_EVENT_DISCONNECTED:
            LOG_INFO("\n");
            LOG_INFO("  ╔════════════════════════════════╗\n");
            LOG_INFO("  ║   MQTT DISCONNECTED            ║\n");
            LOG_INFO("  ╠════════════════════════════════╣\n");
            LOG_INFO("  ║          .---.                 ║\n");
            LOG_INFO("  ║         ( O_O )                ║\n");
            LOG_INFO("  ║          |   |   X--X--X       ║\n");
            LOG_INFO("  ║         _|   |_                ║\n");
            LOG_INFO("  ║                                ║\n");
            LOG_INFO("  ║  Reason: %u               ║\n", *((uint16_t *)data));
            LOG_INFO("  ║  Attempting reconnect...       ║\n");
            LOG_INFO("  ╚════════════════════════════════╝\n\n");
            // Attempt to reconnect immediately
            mqtt_connect(&mqttConnection, MQTT_BROKER_IP_ADDR, MQTT_BROKER_PORT, PUBLISH_INTERVAL, MQTT_CLEAN_SESSION_ON);
            break;
        case MQTT_EVENT_CONNECTION_REFUSED_ERROR:
            LOG_INFO("\n");
            LOG_INFO("  ╔════════════════════════════════╗\n");
            LOG_INFO("  ║  /!\\  CONNECTION REFUSED  /!\\ ║\n");
            LOG_INFO("  ╠════════════════════════════════╣\n");
            LOG_INFO("  ║          .---.                 ║\n");
            LOG_INFO("  ║         ( X_X )                ║\n");
            LOG_INFO("  ║          |   |                 ║\n");
            LOG_INFO("  ║         _|   |_                ║\n");
            LOG_INFO("  ║                                ║\n");
            LOG_INFO("  ║  Error code: %u                ║\n", *((uint16_t *)data));
            LOG_INFO("  ║  Retry in 5 seconds...         ║\n");
            LOG_INFO("  ╚════════════════════════════════╝\n\n");
            // Retry connection after a short delay
            etimer_set(&retry_timer, CLOCK_SECOND * 5);  // Wait 5 seconds before retry
            retry_flag = 1;
            break;
        default:
            LOG_INFO("MQTT event: %i, data: %p\n", event, data);
            break;
    }
}

/*---------------------------------------------------------------------------*/
/* Function to publish sensor data */
static void publish_sensor_data() {
    // Ensure we have valid temperature values (0 = unset, not -1)
    float pred_temp = predictedTemperature;
    float tgt_temp = targetTemperature;

    // Convert any negative values to 0 for JSON compatibility
    if (pred_temp < 0) pred_temp = 0.0f;
    if (tgt_temp < 0) tgt_temp = 0.0f;

    // Convert floats to integers with 1 decimal place precision
    // Contiki-NG's snprintf doesn't support %f, so we split into integer and decimal parts
    int pred_temp_int = (int)pred_temp;
    int pred_temp_dec = (int)((pred_temp - pred_temp_int) * 10);
    int tgt_temp_int = (int)tgt_temp;
    int tgt_temp_dec = (int)((tgt_temp - tgt_temp_int) * 10);

    int msgLen = snprintf(mqttPublishMessage, sizeof(mqttPublishMessage),
        "{"
        "\"device_id\":\"node3\","
        "\"location\":\"Office\","
        "\"ip\":\"%s\","
        "\"lux\":%d,"
        "\"occupancy\":%d,"
        "\"temperature\":%d,"
        "\"predicted_temp\":%d.%d,"
        "\"target_temp\":%d.%d,"
        "\"humidity\":%d,"
        "\"co2\":%d,"
        "\"room_usage_wh\":%d,"
        "\"heating_status\":%d,"
        "\"led_status\":%d,"
        "\"manual_override\":%d,"
        "\"optimization_event\":%d,"
        "\"sim_occupancy\":%d,"
        "\"clock_synced\":%d,"
        "\"schedule_initialized\":%d,"
        "\"day\":%d,"
        "\"hour\":%d,"
        "\"minute\":%d"
        "}",
        nodeIpAddress, ambientLightLevel, simulatedOccupancy, temperatureCelsius,
        pred_temp_int, pred_temp_dec, tgt_temp_int, tgt_temp_dec,
        humidityPercent, co2Ppm, roomEnergyUsageWh, isHeatingOn, isLedOn,
        isManualOverride, isOptimizationEvent, isSystemSimulatingOccupancy,
        clockSynced, scheduleInitialized, simulatedDay, (int)simulatedHour, (int)((simulatedHour - (int)simulatedHour) * 60));

    // Check for buffer overflow
    if(msgLen >= sizeof(mqttPublishMessage)) {
        LOG_INFO("MQTT: ERROR - Message truncated! Size: %d, Buffer: %d\n", msgLen, sizeof(mqttPublishMessage));
        return; // Don't publish truncated message
    }

    int ret = mqtt_publish(&mqttConnection, NULL, MQTT_PUB_TOPIC, (uint8_t *)mqttPublishMessage, strlen(mqttPublishMessage), MQTT_QOS_LEVEL_0, MQTT_RETAIN_OFF);
    if(ret != 0) {
        LOG_INFO("MQTT: Publish failed with code %d\n", ret);
        if(ret == -1) {
            // Not connected, attempt to reconnect
            LOG_INFO("MQTT: Not connected, attempting reconnect\n");
            mqtt_connect(&mqttConnection, MQTT_BROKER_IP_ADDR, MQTT_BROKER_PORT, PUBLISH_INTERVAL, MQTT_CLEAN_SESSION_ON);
        }
    } else {
        LOG_INFO("MQTT: Published %d bytes to %s\n", msgLen, MQTT_PUB_TOPIC);
    }
}

/*---------------------------------------------------------------------------*/
// Function to check and handle override expiry
static void check_override_expiry() {
    if(isManualOverride && overrideCyclesRemaining > 0) {
        overrideCyclesRemaining--;
        if(overrideCyclesRemaining <= 0) {
            isManualOverride = 0;
            isAutoBehaviorEnabled = 1;
            heatingChangeCooldown = 5; // Brief cooldown
            LOG_INFO("\n");
            LOG_INFO("  *************************\n");
            LOG_INFO("  *  OVERRIDE EXPIRED!   *\n");
            LOG_INFO("  *************************\n");
            LOG_INFO("  *   ___     ___        *\n");
            LOG_INFO("  *  | M |-->| A |       *\n");
            LOG_INFO("  *  |___|   |_U_|       *\n");
            LOG_INFO("  *  MANUAL   AUTO       *\n");
            LOG_INFO("  *************************\n");
            LOG_INFO("  Returning to AUTO mode\n\n");
            update_status_leds(); // Update status feedback LEDs
        }
    }
}

// Function to calculate realistic light levels
static int calculate_realistic_light(int occupied) {
    int baseLight;

    if(occupied) {
        // During occupied periods (daytime), high light levels
        baseLight = 400 + (random_rand() % 200); // 400-600 lux
    } else {
        // During unoccupied periods (night), low light
        baseLight = 0 + (random_rand() % 10); // 0-10 lux
    }

    // Ensure reasonable bounds
    if(baseLight < 0) baseLight = 0;
    if(baseLight > 750) baseLight = 750;

    // Add 5% oscillation around the value
    int variation = baseLight / 20;
    if (variation < 1) variation = 1;
    baseLight += (random_rand() % (2 * variation + 1)) - variation;

    // Ensure always a little above 0
    if (baseLight < 1) baseLight = 1;

    return baseLight;
}

// Function to simulate realistic temperature with heating effects
static void simulate_realistic_temperature(int occupied) {
    // Apply heating effect if heating is on
    if (isHeatingOn) {
        simulatedTemperatureFloat += heatingRatePerCycle;
    } else {
        // Natural cooling towards ambient (influenced by occupancy)
        float ambientTemp = occupied ? 20.0f : 18.0f;

        // Temperature slowly drifts towards ambient
        if (simulatedTemperatureFloat > ambientTemp) {
            simulatedTemperatureFloat -= coolingRatePerCycle;
        } else if (simulatedTemperatureFloat < ambientTemp) {
            // Slight warming from outside if below ambient
            simulatedTemperatureFloat += coolingRatePerCycle * 0.3f;
        }
    }

    // Add small random fluctuations (±0.1°C)
    float randomVariation = ((random_rand() % 21) - 10) / 100.0f; // -0.1 to +0.1
    simulatedTemperatureFloat += randomVariation;

    // Ensure reasonable bounds
    if(simulatedTemperatureFloat < 10.0f) simulatedTemperatureFloat = 10.0f;
    if(simulatedTemperatureFloat > 35.0f) simulatedTemperatureFloat = 35.0f;

    // Convert to integer for sensor reading
    temperatureCelsius = (int)(simulatedTemperatureFloat + 0.5f); // Round to nearest int
}

// Function to calculate realistic humidity
static int calculate_realistic_humidity(int occupied) {
    int baseHumidity = 25; // Base humidity percentage

    // Daily humidity variation
    float hourRad = simulatedHour * 3.14159 / 12.0;
    baseHumidity += (int)(5.0 * sin(hourRad + 3.14159)); // Phase shifted for humidity pattern

    // Temperature affects humidity (inverse relationship)
    if(temperatureCelsius > 22) {
        baseHumidity -= (temperatureCelsius - 22) / 2; // Decrease humidity with higher temperature
    }

    // Occupancy affects humidity (breathing adds moisture)
    if(occupied) {
        baseHumidity += 2 + (random_rand() % 3); // 2-4% increase when occupied
    }

    // Random variation
    baseHumidity += (random_rand() % 5) - 2; // ±2% variation

    // Ensure reasonable bounds
    if(baseHumidity < 20) baseHumidity = 20;
    if(baseHumidity > 50) baseHumidity = 50;

    return baseHumidity;
}

// Function to calculate realistic CO2 levels
static int calculate_realistic_co2(int occupied) {
    int baseCo2;
    if (occupied) {
        // Occupied: uniform around 1000 ppm with ±10% range (900-1100)
        baseCo2 = 900 + (random_rand() % 201); // 900-1100
    } else {
        // Unoccupied: uniform around 500 ppm with ±10% range (450-550)
        baseCo2 = 450 + (random_rand() % 101); // 450-550
    }

    // Daily variation
    float hourRad = simulatedHour * 3.14159 / 12.0;
    baseCo2 += (int)(50.0 * sin(hourRad)); // ±50 ppm daily variation

    // Ensure reasonable bounds
    if(baseCo2 < 350) baseCo2 = 350;
    if(baseCo2 > 1500) baseCo2 = 1500;

    return baseCo2;
}

static void handle_sensor_event()
{
    etimer_reset(&timer);
    // Handle state management
    check_override_expiry();
    // Decrease cooldowns
    if(heatingChangeCooldown > 0) {
        heatingChangeCooldown--;
    }

    isSystemSimulatingOccupancy = 0; // Reset simulated occupancy each cycle

    // Update simulated time
    simulatedHour += 15.0 / 3600.0; // 15 seconds in hours
    if(simulatedHour >= 24.0) {
        simulatedHour = 0.0;
        simulatedDay = (simulatedDay + 1) % 7; // Move to next day (0-6)
    }

    // Note: Time sync is now pushed by controller periodically
    // Controller broadcasts time sync to all nodes via CoAP PUT to /time_sync
    // Node does not track or request re-sync - controller handles this automatically

    // Manage occupancy periods with probabilistic start and fixed duration
    if (!isSystemOccupancyActive) {
        // Not in a period, check if we should start one based on probability
        float occupancyProbability = 0.0;
        if ((simulatedHour >= 6.0 && simulatedHour <= 23.0)) {
            occupancyProbability = 0.01; // 1% chance per cycle during active hours (6 AM - 11 PM)
        } else {
            occupancyProbability = 0.005; // 0.5% chance per cycle during night hours
        }

        if (random_rand() % 100 < (int)(occupancyProbability * 100)) {
            // Start a new occupancy period
            isSystemOccupancyActive = 1;
            int minCycles = 6;   // Minimum 1.5 minutes (6 * 15s)
            int maxCycles = 80; // Maximum 20 minutes (80 * 15s)
            systemOccupancyPeriodLength = minCycles + (random_rand() % (maxCycles - minCycles + 1));
            systemOccupancyCyclesRemaining = systemOccupancyPeriodLength;
            LOG_INFO("\n");
            LOG_INFO("  ################################\n");
            LOG_INFO("  #   NEW OCCUPANCY DETECTED!   #\n");
            LOG_INFO("  ################################\n");
            LOG_INFO("  #  Duration: %3d cycles        #\n", systemOccupancyPeriodLength);
            LOG_INFO("  #  Time: %2d minutes           #\n", systemOccupancyPeriodLength * 15 / 60);
            LOG_INFO("  ################################\n\n");
        }
        else {
            isSystemOccupancyActive = 0;
        }
    }

    // Override with button simulation
    if(isButtonOccupancyActive) {
        isSystemSimulatingOccupancy = 1; // Button triggers occupancy
    }

    if (isSystemOccupancyActive) {
        isSystemSimulatingOccupancy = 1; // System-simulated occupancy
        systemOccupancyCyclesRemaining--;
        if (systemOccupancyCyclesRemaining <= 0) {
            isSystemOccupancyActive = 0;
            LOG_INFO("\n");
            LOG_INFO("  ╔════════════════════════╗\n");
            LOG_INFO("  ║  OCCUPANCY ENDED       ║\n");
            LOG_INFO("  ╚════════════════════════╝\n\n");
        }
    }

    // Set occupancy sensor value (simulated, not predicted)
    simulatedOccupancy = isSystemSimulatingOccupancy;

    // Wait for DAG formation
    if(NETSTACK_ROUTING.node_is_reachable()) {

        LOG_INFO("\n");
        LOG_INFO("  ┌─────────────────────────┐\n");
        LOG_INFO("  │  SENSOR DATA GENERATOR  │\n");
        LOG_INFO("  ├─────────────────────────┤\n");
        LOG_INFO("  │    Reading sensors...   │\n");
        LOG_INFO("  └─────────────────────────┘\n\n");

        // Generate realistic sensor data based on current state and time
        ambientLightLevel = calculate_realistic_light(isSystemSimulatingOccupancy);

        // Simulate temperature with heating effects (gradual changes)
        simulate_realistic_temperature(isSystemSimulatingOccupancy + isButtonOccupancyActive);
        humidityPercent = calculate_realistic_humidity(isSystemSimulatingOccupancy + isButtonOccupancyActive);
        co2Ppm = calculate_realistic_co2(isSystemSimulatingOccupancy + isButtonOccupancyActive);

        // Adjust sensors for button occupation
        if(isButtonOccupancyActive) {
            // Decrement simulation timer
            buttonOccupancyCyclesRemaining--;
            if (buttonOccupancyCyclesRemaining <= 0) {
                isButtonOccupancyActive = 0;
                LOG_INFO("\n  [BUTTON] Occupation ended\n\n");
            }
        }

        // Add current temperature to history for ML model
        add_temperature_to_history((float)temperatureCelsius);

        // Update current target temperature from schedule (every cycle for accurate MQTT reporting)
        float oldTarget = targetTemperature;
        targetTemperature = get_target_temperature();
        if ((int)oldTarget != (int)targetTemperature) {
            LOG_INFO("  [CYCLE] Target temperature changed: %d°C -> %d°C\n", (int)oldTarget, (int)targetTemperature);
        }

        // Increment cycle counter
        cyclesSinceLastTempCheck++;

        // Check temperature every 30 minutes (120 cycles of 15 seconds)
        if (cyclesSinceLastTempCheck >= TEMP_CHECK_INTERVAL) {
            cyclesSinceLastTempCheck = 0;

            // Predict 24 hours ahead using ML model (updates prediction buffer)
            predict_next_24_hours();

            LOG_INFO("\n");
            LOG_INFO("  ╔════════════════════════════════════════════════════╗\n");
            LOG_INFO("  ║   30-MINUTE TEMPERATURE CHECK                      ║\n");
            LOG_INFO("  ╠════════════════════════════════════════════════════╣\n");
            LOG_INFO("  ║  Current time: Day %d, Hour %d                     ║\n", simulatedDay, (int)simulatedHour);
            LOG_INFO("  ║  Current:    %d°C                                  ║\n", temperatureCelsius);
            LOG_INFO("  ║  Predicted (30min): %d°C                           ║\n", (int)predictedTemperature);
            LOG_INFO("  ║  Predicted (24h):   %d°C                           ║\n", predictionBufferFilled ? (int)predictionBuffer[47] : 0);
            LOG_INFO("  ║  Manual override: %s                               ║\n", isManualOverride ? "YES" : "NO");
            LOG_INFO("  ║  Auto behavior: %s                                 ║\n", isAutoBehaviorEnabled ? "ENABLED " : "DISABLED");
            LOG_INFO("  ╚════════════════════════════════════════════════════╝\n\n");

            // Control heating based on prediction
            if (isAutoBehaviorEnabled) {
                LOG_INFO("  [CHECK] Calling control_heating()...\n");
                control_heating();
            } else {
                LOG_INFO("  [CHECK] Auto behavior disabled, skipping control\n");
            }
        }

        char* occupationSource = "none";
        int cyclesRemaining = 0;
        if (isButtonOccupancyActive) {
            occupationSource = "button_override";
            cyclesRemaining = buttonOccupancyCyclesRemaining;
        } else if (isSystemOccupancyActive) {
            occupationSource = "normal_fluctuation";
            cyclesRemaining = systemOccupancyCyclesRemaining;
        }
        LOG_INFO("NODE3_LOG: Day %d, Hour %d.%d, Occupied: %s\n",
            simulatedDay, (int)simulatedHour, (int)((simulatedHour - (int)simulatedHour) * 10),
            isSystemSimulatingOccupancy ? "YES" : "NO");
        LOG_INFO("  Source: %s, Cycles remaining: %d\n", occupationSource, cyclesRemaining);
        // Energy consumption: heating uses more energy
        roomEnergyUsageWh = (isHeatingOn == 1) ? 15 : 2; // 15 Wh when heating (0.015 kWh), 2 Wh baseline

        // Add 5% oscillation around the value
        int energyVariation = roomEnergyUsageWh / 20;
        if (energyVariation < 1) energyVariation = 1;
        roomEnergyUsageWh += (random_rand() % (2 * energyVariation + 1)) - energyVariation;
        if (roomEnergyUsageWh < 1) roomEnergyUsageWh = 1;
        // Update heating status LEDs (if not in cooldown)
        if(!isManualOverride && heatingChangeCooldown <= 0) {
            update_status_leds();
        }
        else if(isManualOverride)
        {
            // Turn on or off LEDs to indicate if override is active
            update_status_leds();
        }

        // Check if clock is synchronized before proceeding with MQTT publishing
        if (!clockSynced) {
            LOG_WARN("\n");
            LOG_WARN("  ╔═══════════════════════════════════════╗\n");
            LOG_WARN("  ║        CLOCK NOT SYNCHRONIZED         ║\n");
            LOG_WARN("  ╠═══════════════════════════════════════╣\n");
            LOG_WARN("  ║  Waiting for time sync via CoAP...    ║\n");
            LOG_WARN("  ║  Controller must PUT /time_sync       ║\n");
            LOG_WARN("  ║  Skipping sensor cycle until synced   ║\n");
            LOG_WARN("  ╚═══════════════════════════════════════╝\n\n");

            // Skip rest of sensor processing until synchronized
            // Controller will send time via CoAP PUT to /time_sync
            return;
        }

        LOG_INFO("\n");
        LOG_INFO("  ╔═════════════════════════════════════════════╗\n");
        LOG_INFO("  ║            MQTT PUBLISHING DATA             ║\n");
        LOG_INFO("  ╠═════════════════════════════════════════════╣\n");

        // Display current node time
        const char* days[] = {"Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"};
        int currentHour = (int)simulatedHour;
        int currentMinute = (int)((simulatedHour - currentHour) * 60);
        LOG_INFO("  ║    Node Time: %s Day %d, %02d:%02d              ║\n",
                days[simulatedDay], simulatedDay, currentHour, currentMinute);
        LOG_INFO("  ║     (Clock synced: %s)                     ║\n", clockSynced ? "YES" : "NO ");
        LOG_INFO("  ╠═════════════════════════════════════════════╣\n");
        LOG_INFO("  ║                                             ║\n");
        LOG_INFO("  ║  ┌─────────────────┐   ┌─────────────────┐  ║\n");
        LOG_INFO("  ║  │ Heating: %-3s    │   │ Occupancy:  %d   │  ║\n",
                isHeatingOn ? "ON " : "OFF", simulatedOccupancy);
        LOG_INFO("  ║  └─────────────────┘   └─────────────────┘  ║\n");
        LOG_INFO("  ║  ┌─────────────────┐   ┌─────────────────┐  ║\n");
        // Convert float temperatures to integer display
        int tempInt = (int)temperatureCelsius;
        int targetInt = (int)targetTemperature;
        int targetDec = (int)((targetTemperature - targetInt) * 10);
        if (targetTemperature > 0) {
            LOG_INFO("  ║  │ Temp:  %4d°C   │   │ Target:  %2d.%d°C │  ║\n",
                    tempInt, targetInt, targetDec);
        } else {
            LOG_INFO("  ║  │ Temp:  %4d°C   │   │ Target: UNSET   │  ║\n", tempInt);
        }
        LOG_INFO("  ║  └─────────────────┘   └─────────────────┘  ║\n");
        LOG_INFO("  ║                                             ║\n");
        LOG_INFO("  ║  ╭───────────────────────────────────────╮  ║\n");
        int predInt = (int)predictedTemperature;
        int predDec = (int)((predictedTemperature - predInt) * 10);
        LOG_INFO("  ║  │  Predicted: %2d.%d°C  Lux: %4d         │  ║\n",
                predInt, predDec, ambientLightLevel);
        LOG_INFO("  ║  ╰───────────────────────────────────────╯  ║\n");
        LOG_INFO("  ║                                             ║\n");
        LOG_INFO("  ║  ╭───────────────────────────────────────╮  ║\n");
        LOG_INFO("  ║  │  Humidity: %2d%%   CO2: %4d ppm        │  ║\n",
                humidityPercent, co2Ppm);
        LOG_INFO("  ║  ╰───────────────────────────────────────╯  ║\n");
        LOG_INFO("  ║                                             ║\n");
        LOG_INFO("  ║  Energy Usage: %2d Wh                        ║\n",
                roomEnergyUsageWh);
        LOG_INFO("  ║  Optimization Event: [%s]                  ║\n",
                isOptimizationEvent ? "YES" : " NO");
        LOG_INFO("  ║  Override Status: %s                ║\n",
                isManualOverride ? "[ACTIVE]  " : "[INACTIVE]");
        LOG_INFO("  ╚═════════════════════════════════════════════╝\n\n");

        publish_sensor_data();

    } else {
        LOG_INFO("\n");
        LOG_INFO("  ╔════════════════════════════╗\n");
        LOG_INFO("  ║  /!\\  NETWORK ERROR  /!\\   ║\n");
        LOG_INFO("  ╠════════════════════════════╣\n");
        LOG_INFO("  ║         ( x_x )            ║\n");
        LOG_INFO("  ║  Not connected to network  ║\n");
        LOG_INFO("  ╚════════════════════════════╝\n\n");
    }
}

static void handle_button_press_event() {

    // Toggle heating override mode
    if(isManualOverride == 1)
    {
        // Deactivate manual override - return to automatic control
        isManualOverride = 0;
        overrideCyclesRemaining = 0;
        LOG_INFO("\n");
        LOG_INFO("  ╔═══════════════════════════════╗\n");
        LOG_INFO("  ║     BUTTON PRESS DETECTED!    ║\n");
        LOG_INFO("  ╠═══════════════════════════════╣\n");
        LOG_INFO("  ║                               ║\n");
        LOG_INFO("  ║          _______              ║\n");
        LOG_INFO("  ║         |       |             ║\n");
        LOG_INFO("  ║         |  [X]  |  <-- STOP   ║\n");
        LOG_INFO("  ║         |_______|             ║\n");
        LOG_INFO("  ║           |   |               ║\n");
        LOG_INFO("  ║           |   |               ║\n");
        LOG_INFO("  ║        ___|   |___            ║\n");
        LOG_INFO("  ║                               ║\n");
        LOG_INFO("  ║   MANUAL OVERRIDE: OFF        ║\n");
        LOG_INFO("  ║   AUTO CONTROL: RESTORED      ║\n");
        LOG_INFO("  ║                               ║\n");
        LOG_INFO("  ║  Heating now controlled by    ║\n");
        LOG_INFO("  ║  predictive algorithm         ║\n");
        LOG_INFO("  ╚═══════════════════════════════╝\n\n");
    }
    else
    {
        // Activate manual override - toggle heating state
        isManualOverride = 1;
        isHeatingOn = !isHeatingOn; // Toggle current heating state
        overrideCyclesRemaining = MAX_CYCLE_OVERRIDE; // Permanent until button pressed again
        
        LOG_INFO("\n");
        LOG_INFO("  ╔═══════════════════════════════╗\n");
        LOG_INFO("  ║     BUTTON PRESS DETECTED!    ║\n");
        LOG_INFO("  ╠═══════════════════════════════╣\n");
        LOG_INFO("  ║                               ║\n");
        if(isHeatingOn) {
            LOG_INFO("  ║         [HEATING ON]          ║\n");
            LOG_INFO("  ║            /\\  /\\             ║\n");
            LOG_INFO("  ║           /  \\/  \\            ║\n");
            LOG_INFO("  ║          |  HEAT  |           ║\n");
        } else {
            LOG_INFO("  ║        [HEATING OFF]          ║\n");
            LOG_INFO("  ║            _____              ║\n");
            LOG_INFO("  ║           |     |             ║\n");
            LOG_INFO("  ║           | OFF |             ║\n");
        }
        LOG_INFO("  ║                               ║\n");
        LOG_INFO("  ║   MANUAL OVERRIDE: ACTIVE     ║\n");
        LOG_INFO("  ║   AUTO CONTROL: DISABLED      ║\n");
        LOG_INFO("  ║                               ║\n");
        LOG_INFO("  ║  Press button again to        ║\n");
        LOG_INFO("  ║  return to auto mode          ║\n");
        LOG_INFO("  ╚═══════════════════════════════╝\n\n");
    }

    // Flash blue LED 10 times over 2 seconds
    for(int i = 0; i < 10; i++) {
        leds_toggle(LEDS_BLUE);
        clock_wait(CLOCK_SECOND / 5); // 0.2 seconds per toggle
    }

    // Ensure blue LED is back to its status state
    update_status_leds();
}

PROCESS_THREAD(node3_process, ev, data) {

    PROCESS_BEGIN();

    // Wait until we get a global IPv6 address
    LOG_INFO("  [INIT] Waiting for IP auto-configuration...\n");
    while(!uip_ds6_get_global(ADDR_PREFERRED)) {
        PROCESS_PAUSE();
    }
    LOG_INFO("  [INIT] IP Configured!\n");

    LOG_INFO("\n");
    LOG_INFO("  ╔═══════════════════════════════════════════════════╗\n");
    LOG_INFO("  ║                                                   ║\n");
    LOG_INFO("  ║    ███╗   ██╗ ██████╗ ██████╗ ███████╗██████╗     ║\n");
    LOG_INFO("  ║    ████╗  ██║██╔═══██╗██╔══██╗██╔════╝╚════██╗    ║\n");
    LOG_INFO("  ║    ██╔██╗ ██║██║   ██║██║  ██║█████╗   █████╔╝    ║\n");
    LOG_INFO("  ║    ██║╚██╗██║██║   ██║██║  ██║██╔══╝   ╚═══██╗    ║\n");
    LOG_INFO("  ║    ██║ ╚████║╚██████╔╝██████╔╝███████╗██████╔╝    ║\n");
    LOG_INFO("  ║    ╚═╝  ╚═══╝ ╚═════╝ ╚═════╝ ╚══════╝╚═════╝     ║\n");
    LOG_INFO("  ║                                                   ║\n");
    LOG_INFO("  ║     OFFICE TEMPERATURE CONTROL NODE           ║\n");
    LOG_INFO("  ║    IoT Temperature Management System              ║\n");
    LOG_INFO("  ║                                                   ║\n");
    LOG_INFO("  ╠═══════════════════════════════════════════════════╣\n");
    LOG_INFO("  ║    Starting Temperature Prediction System...      ║\n");
    LOG_INFO("  ╚═══════════════════════════════════════════════════╝\n\n");

    uip_ds6_addr_t *addr = uip_ds6_get_global(ADDR_PREFERRED);
    if (addr) {
        LOG_INFO("\n");
        LOG_INFO("  ┌───────────────────────────────────────────────┐\n");
        LOG_INFO("  │  IPv6 ADDRESS CONFIGURED                      │\n");
        LOG_INFO("  ├───────────────────────────────────────────────┤\n");
        LOG_INFO("  │  Node IPv6 addr:                              │\n");
        LOG_INFO("  │  ");
        LOG_INFO_6ADDR(&addr->ipaddr);
        LOG_INFO("│\n");
        LOG_INFO("  └───────────────────────────────────────────────┘\n");
        // Store IP address as string for MQTT payload
        uiplib_ipaddr_snprint(nodeIpAddress, sizeof(nodeIpAddress), &addr->ipaddr);
        LOG_INFO("  Stored IP: %s\n\n", nodeIpAddress);
    } else {
        LOG_INFO("  [ERROR] No global IPv6 addr, cannot connect\n");
    }

    /* ---- Init COAP ---- */
    coap_engine_init();
    coap_activate_resource(&sensor_event, "node/stats");
    coap_activate_resource(&settings_resource, "settings");
    coap_activate_resource(&schedule_resource, "schedule");
    coap_activate_resource(&time_sync_resource, "time_sync");

    LOG_INFO("  [INIT] CoAP resources registered\n");
    LOG_INFO("    - /node/stats (observable)\n");
    LOG_INFO("    - /settings (GET/PUT)\n");
    LOG_INFO("    - /schedule (GET/PUT)\n");
    LOG_INFO("    - /time_sync (GET/PUT)\n\n");

    /* ---- Init Clock Synchronization ---- */
    clockSynced = 0;  // Not synced yet
    LOG_INFO("  [INIT] Clock synchronization ready\n");
    LOG_INFO("    - Waiting for server time sync via CoAP\n");
    LOG_INFO("    - Controller broadcasts time periodically\n");
    LOG_INFO("    - Endpoint: PUT /time_sync\n");
    LOG_INFO("    - Current time: Day %d, %02d:%02d (not synced)\n\n",
            simulatedDay, (int)simulatedHour, (int)((simulatedHour - (int)simulatedHour) * 60));

    /* ---- Init Temperature System ---- */
    // Initialize simulated temperature
    simulatedTemperatureFloat = 20.0f;  // Start at 20°C
    temperatureCelsius = 20;

    // Initialize temperature history with default 20°C
    for (int i = 0; i < TEMP_HISTORY_SIZE; i++) {
        temperatureHistory[i] = 20.0f; // Default 20°C
    }
    tempHistoryIndex = 0;
    tempHistoryFilled = 1;  // Already initialized with defaults
    cyclesSinceLastTempCheck = 0;

    LOG_INFO("  [INIT] Temperature system initialized\\n");
    LOG_INFO("    - History buffer: %d slots (initialized to 20°C)\\n", TEMP_HISTORY_SIZE);
    LOG_INFO("    - Check interval: every 30 minutes (%d cycles)\\n", TEMP_CHECK_INTERVAL);
    LOG_INFO("    - Prediction horizon: 24 hours (48 predictions)\\n\\n");

    // Initialize default temperature schedule
    LOG_INFO("  [INIT] Initializing default schedule...\\n");
    initialize_default_schedule();

    LOG_INFO("  [INIT] Getting initial target temperature...\\n");
    targetTemperature = get_target_temperature();

    LOG_INFO("  [INIT] Finding initial next target...\\n");
    find_next_target_temperature();

    /* ---- Wait for Time Sync from Controller ---- */
    LOG_INFO("\\n");
    LOG_INFO("  ╔════════════════════════════════════════════╗\\n");
    LOG_INFO("  ║   WAITING FOR CONTROLLER TIME SYNC         ║\\n");
    LOG_INFO("  ╠════════════════════════════════════════════╣\\n");
    LOG_INFO("  ║  Node is ready and listening...            ║\\n");
    LOG_INFO("  ║  Controller must send CoAP PUT to:         ║\\n");
    LOG_INFO("  ║  → coap://[node-ip]/time_sync              ║\\n");
    LOG_INFO("  ║  Payload: {\\\"day\\\":N,\\\"hour\\\":H,\\\"minute\\\":M}║\\n");
    LOG_INFO("  ║                                            ║\\n");
    LOG_INFO("  ║  Node IP: %-36s ║\\n", nodeIpAddress);
    LOG_INFO("  ╚════════════════════════════════════════════╝\\n\\n");

    LOG_INFO("\\n");
    LOG_INFO("  ╔════════════════════════════════════════════╗\\n");
    LOG_INFO("  ║   TEMPERATURE PREDICTION SYSTEM INIT       ║\n");
    LOG_INFO("  ╠════════════════════════════════════════════╣\n");
    LOG_INFO("  ║  History buffer: 48 readings (24 hours)    ║\n");
    LOG_INFO("  ║  Check interval: 30 minutes                ║\n");
    LOG_INFO("  ║  Heating rate: 1°C per 30 minutes          ║\n");
    LOG_INFO("  ║  Cooling rate: 0.5°C per 30 minutes        ║\n");
    LOG_INFO("  ║  Schedule initialized: %s                 ║\n", scheduleInitialized ? "YES" : "NO ");
    LOG_INFO("  ╠════════════════════════════════════════════╣\n");
    if (targetTemperature > 0) {
        LOG_INFO("  ║  Current target: %d°C                      ║\n", (int)targetTemperature);
    } else {
        LOG_INFO("  ║  Current target: UNSET                     ║\n");
    }
    if (nextTargetTemperature > 0) {
        LOG_INFO("  ║  Next target: %d°C at hour %d              ║\n", (int)nextTargetTemperature, nextTargetHour);
    } else {
        LOG_INFO("  ║  Next target: NONE                        ║\n");
    }
    LOG_INFO("  ╚════════════════════════════════════════════╝\n\n");

    /* ---- Init MQTT ---- */
    mqtt_register(&mqttConnection, &node3_process, CLIENT_ID, mqtt_event, MAX_TCP_SEGMENT_SIZE);
    mqtt_connect(&mqttConnection, MQTT_BROKER_IP_ADDR, MQTT_BROKER_PORT, PUBLISH_INTERVAL, MQTT_CLEAN_SESSION_ON);

    /* Initial state */
    leds_init();
    leds_off(LEDS_ALL);
    update_status_leds();

    /* Avvia timer per pubblicazione periodica */
    etimer_set(&timer, PUBLISH_INTERVAL);

    while(1) {
        PROCESS_YIELD();
        if(etimer_expired(&timer)) {
            handle_sensor_event();
        }
        if(ev == button_hal_press_event) {
            handle_button_press_event();
        }
        // Check for MQTT reconnection retry
        if (retry_flag && etimer_expired(&retry_timer)) {
            LOG_INFO("MQTT: Retrying connection to broker\n");
            mqtt_connect(&mqttConnection, MQTT_BROKER_IP_ADDR, MQTT_BROKER_PORT, PUBLISH_INTERVAL, MQTT_CLEAN_SESSION_ON);
            retry_flag = 0;
        }
    }

    PROCESS_END();
}
