#include <contiki.h>
#include <net/app-layer/coap/coap-engine.h>
#include <dev/leds.h>
#include <string.h>
#include <stdio.h>

#include "resources-led.h"

/* Handler POST: payload = "ON" oppure "OFF" */
static void res_post_handler(coap_message_t *request, coap_message_t *response,
                            uint8_t *buffer, uint16_t preferred_size, int32_t *offset);

RESOURCE(res_led,
        "title=\"LED Control (POST-led)\";rt=\"Control\"",
        NULL,               // GET
        res_post_handler,   // POST
        NULL,               // PUT
        NULL);              // DELETE

extern void led_set(int state);

static void res_post_handler(coap_message_t *request, coap_message_t *response,
                            uint8_t *buffer, uint16_t preferred_size, int32_t *offset) {

    const char *payload = NULL;
    int len = coap_get_payload(request, (const uint8_t**)&payload);
    int state = 0;

    printf("Turning on blue led since we got something");

    leds_on(LEDS_BLUE);
    clock_wait(CLOCK_SECOND);
    leds_off(LEDS_BLUE);

    printf("DEBUG: payload len=%d, data='%.*s'\n", len, len, payload);

    if(len > 0) {
        if(strncmp(payload, "ON", len) == 0) {
            state = 1;
        } else if(strncmp(payload, "OFF", len) == 0) {
            state = 0;
        }
        led_set(state);
        snprintf((char *)buffer, preferred_size, "LED-%s", state?"ON":"OFF");
        coap_set_payload(response, buffer, strlen((char*)buffer));
        coap_set_status_code(response, CONTENT_2_05);
    } else {
        coap_set_status_code(response, BAD_REQUEST_4_00);
    }
}