CONTIKI_PROJECT = led-device
all: $(CONTIKI_PROJECT)

CONTIKI = ../../contiki-ng

# The BR is either native or embedded, and in the latter case must support SLIP
PLATFORMS_EXCLUDE = z1

MODULES_REL += ./resources
PROJECT_SOURCEFILES += resources-led.c

# Include RPL BR module
include $(CONTIKI)/Makefile.dir-variables

MODULES += $(CONTIKI_NG_APP_LAYER_DIR)/coap
MODULES += $(CONTIKI_NG_APP_LAYER_DIR)/mqtt
MODULES += $(CONTIKI_NG_NET_DIR)/ipv6

MAKE_NET = 1
MAKE_NET_IPV6 = 1
MAKE_ROUTING = MAKE_ROUTING_RPL_LITE

# Critical flags to ignore warnings that cause build failures
CFLAGS += -Wno-error=unused-variable
CFLAGS += -Wno-error=unused-function
CFLAGS += -DNETSTACK_CONF_WITH_IPV6=1

include $(CONTIKI)/Makefile.include