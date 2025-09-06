#ifndef PROJECT_CONF_H_
#define PROJECT_CONF_H_

/* Enable TCP */
#define UIP_CONF_TCP 1

/* MQTT broker configuration */
#define MQTT_CLIENT_CONF_BROKER_IP_ADDR "fd00::1"
#define MQTT_CLIENT_CONF_BROKER_PORT 1883

/* Memory optimization settings from working example */
#undef NBR_TABLE_CONF_MAX_NEIGHBORS
#define NBR_TABLE_CONF_MAX_NEIGHBORS     10

#undef UIP_CONF_MAX_ROUTES
#define UIP_CONF_MAX_ROUTES   10

#undef UIP_CONF_BUFFER_SIZE
#define UIP_CONF_BUFFER_SIZE    680

#define LOG_LEVEL_APP LOG_LEVEL_DBG

#endif /* PROJECT_CONF_H_ */
