CONTIKI_PROJECT = node1 node2 node3
all: $(CONTIKI_PROJECT)

CONTIKI = ../contiki-ng

include $(CONTIKI)/Makefile.dir-variables
MODULES += $(CONTIKI_NG_APP_LAYER_DIR)/mqtt

include $(CONTIKI)/Makefile.include