#ifndef PROJECT_CONF_H_
    #define PROJECT_CONF_H_

    #define UIP_CONF_TCP 1

    #define LOG_CONF_LEVEL_APP LOG_LEVEL_INFO
    #define LOG_CONF_LEVEL_COAP LOG_LEVEL_INFO
    #define LOG_CONF_LEVEL_MQTT LOG_LEVEL_INFO
    #define LOG_CONF_LEVEL_RPL LOG_LEVEL_INFO

    /* Increase buffer sizes for large CoAP payloads (temperature schedules) */
    #define UIP_CONF_BUFFER_SIZE 1280
    #define COAP_MAX_CHUNK_SIZE 1024

    /* Enable CoAP block-wise transfer for large payloads */
    #define COAP_MAX_BLOCK_SIZE 1024

#endif /* PROJECT_CONF_H_ */