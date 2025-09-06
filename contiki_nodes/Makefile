CONTIKI_PROJECT = node1 node2 node3
all: node1

SMALL = 1

# Include MQTT module for MQTT functionality
MODULES += os/net/app-layer/mqtt

CONTIKI = ../contiki-ng

include $(CONTIKI)/Makefile.dir-variables

# Critical flags to ignore warnings that cause build failures
CFLAGS += -Wno-error=unused-variable
CFLAGS += -Wno-error=unused-function

include $(CONTIKI)/Makefile.include