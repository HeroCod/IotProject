#include "contiki.h"
#include "sys/log.h"
#include "dev/leds.h"

#define LOG_MODULE "SimpleTest"
#define LOG_LEVEL LOG_LEVEL_INFO

PROCESS(simple_test_process, "Simple Test Process");
AUTOSTART_PROCESSES(&simple_test_process);

PROCESS_THREAD(simple_test_process, ev, data) {
  static struct etimer timer;

  PROCESS_BEGIN();

  leds_init();
  leds_off(LEDS_ALL);
  
  LOG_INFO("🚀 Simple Test Node Started\n");

  etimer_set(&timer, CLOCK_SECOND * 2);

  while(1) {
    printf("Hello, world\n");
    PROCESS_WAIT_EVENT_UNTIL(etimer_expired(&timer));
    leds_toggle(LEDS_RED);
    LOG_INFO("💡 LED Toggle\n");
    etimer_reset(&timer);
  }

  PROCESS_END();
}
