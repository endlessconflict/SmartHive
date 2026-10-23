#pragma once

#include <stdbool.h>

#include "freertos/FreeRTOS.h"

// Starts the station with the SSID and password from menuconfig. Reconnects on its own after a drop.
// Needs nvs_flash_init, esp_netif_init and the default event loop first.
void wifi_start(void);

// True once the station has an IP address, false if `timeout` passed first.
bool wifi_wait_connected(TickType_t timeout);
