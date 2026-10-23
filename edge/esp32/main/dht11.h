#pragma once

#include "driver/gpio.h"
#include "esp_err.h"

// Configures the data pin as open drain with pull-up. The sensor needs 1 s after power-up before the first read.
esp_err_t dht11_init(gpio_num_t pin);

// One read. ESP_ERR_TIMEOUT if the sensor does not answer, ESP_ERR_INVALID_CRC on a bad checksum.
// Reads must be at least 1 s apart.
esp_err_t dht11_read(gpio_num_t pin, float *temp_c, float *rh_pct);
