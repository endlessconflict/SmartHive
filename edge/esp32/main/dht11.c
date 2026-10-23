// DHT11 single-wire protocol, bit-banged.
// Start: host holds the line low >= 18 ms and releases it. Sensor answers 80 us low + 80 us high,
// then 40 bits, each 50 us low followed by 26-28 us high (0) or 70 us high (1). Last byte is the checksum.
#include "dht11.h"

#include "esp_rom_sys.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

#define BIT_ONE_MIN_US 40  // a high pulse longer than this is a 1

static portMUX_TYPE s_mux = portMUX_INITIALIZER_UNLOCKED;

// Waits while the line is at `level`. Returns the microseconds spent, or -1 after `timeout_us`.
static int wait_while(gpio_num_t pin, int level, int timeout_us)
{
    int64_t start = esp_timer_get_time();
    while (gpio_get_level(pin) == level) {
        if (esp_timer_get_time() - start > timeout_us) {
            return -1;
        }
    }
    return (int)(esp_timer_get_time() - start);
}

esp_err_t dht11_init(gpio_num_t pin)
{
    gpio_config_t cfg = {
        .pin_bit_mask = 1ULL << pin,
        .mode = GPIO_MODE_INPUT_OUTPUT_OD,
        .pull_up_en = GPIO_PULLUP_ENABLE,  // weak; most DHT11 modules also carry a 10k pull-up
    };
    esp_err_t err = gpio_config(&cfg);
    if (err == ESP_OK) {
        gpio_set_level(pin, 1);
    }
    return err;
}

esp_err_t dht11_read(gpio_num_t pin, float *temp_c, float *rh_pct)
{
    uint8_t d[5] = {0};
    bool ok = true;

    gpio_set_level(pin, 0);
    vTaskDelay(pdMS_TO_TICKS(20));

    // The bit timing is a few tens of microseconds, so no interrupts on this core for the ~5 ms transfer
    portENTER_CRITICAL(&s_mux);
    gpio_set_level(pin, 1);
    esp_rom_delay_us(30);
    ok = wait_while(pin, 1, 60) >= 0      // sensor pulls low
         && wait_while(pin, 0, 100) >= 0  // 80 us low
         && wait_while(pin, 1, 100) >= 0; // 80 us high
    for (int i = 0; ok && i < 40; i++) {
        int high = 0;
        ok = wait_while(pin, 0, 80) >= 0 && (high = wait_while(pin, 1, 100)) >= 0;
        if (ok && high > BIT_ONE_MIN_US) {
            d[i / 8] |= 1 << (7 - i % 8);
        }
    }
    portEXIT_CRITICAL(&s_mux);

    if (!ok) {
        return ESP_ERR_TIMEOUT;
    }
    if (((d[0] + d[1] + d[2] + d[3]) & 0xff) != d[4] || d[0] == 0) {  // RH is never 0 on a DHT11
        return ESP_ERR_INVALID_CRC;
    }
    *rh_pct = d[0] + d[1] / 10.0f;
    // Newer DHT11 revisions send a tenths digit and use bit 7 of byte 3 as the sign
    *temp_c = d[2] + (d[3] & 0x7f) / 10.0f;
    if (d[3] & 0x80) {
        *temp_c = -*temp_c;
    }
    return ESP_OK;
}
