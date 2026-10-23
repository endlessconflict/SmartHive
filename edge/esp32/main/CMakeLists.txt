set(certs "")
if(CONFIG_SMARTHIVE_MQTT_TLS)
    # Copied from infra/pki, see certs/README.md. Git-ignored.
    set(certs certs/ca.crt certs/node.crt certs/node.key)
endif()

idf_component_register(
    SRCS "main.c" "dht11.c" "wifi.c"
    INCLUDE_DIRS "."
    REQUIRES esp_driver_gpio esp_wifi esp_netif esp_event esp_timer nvs_flash mqtt
    EMBED_TXTFILES ${certs}
)
