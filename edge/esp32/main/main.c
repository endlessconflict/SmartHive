// SmartHive ESP32 node: reads a DHT11 and publishes temp_in / rh_in over MQTT.
// Payloads follow docs/05-backend/04-messaging-contract.md (telemetry and status).
#include <stdio.h>
#include <string.h>
#include <sys/time.h>
#include <time.h>

#include "dht11.h"
#include "esp_event.h"
#include "esp_log.h"
#include "esp_netif.h"
#include "esp_netif_sntp.h"
#include "esp_random.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "mqtt_client.h"
#include "nvs_flash.h"
#include "wifi.h"

#define TOPIC_PREFIX "smarthive/v1/nodes/" CONFIG_SMARTHIVE_NODE_ID "/"
#define SENSOR_ID "dht11-0"
#define MAX_PENDING 120  // samples kept in RAM while the broker is unreachable (2 h at 60 s)
#define BATCH_MAX 8      // samples per message, about 3 KB of JSON
#define PAYLOAD_MAX 4096 // also the MQTT client buffer, so a batch goes out in one piece
#define READ_ATTEMPTS 3
#define UUID_LEN 37
#define TS_LEN 25  // "2026-10-06T14:04:00.120Z" + NUL

static const char *TAG = "node";

typedef struct {
    int64_t unix_ms;
    int64_t mono_ms;
    bool clock_synced;
    bool ok;
    float temp_c;
    float rh_pct;
} sample_t;

static sample_t s_pending[MAX_PENDING];  // ring buffer, oldest at s_head
static int s_head, s_count;
static char s_boot_id[UUID_LEN];
static char s_buf[PAYLOAD_MAX];
static esp_mqtt_client_handle_t s_mqtt;
static volatile bool s_mqtt_up;
static volatile bool s_clock_synced;  // no RTC: false until the first NTP sync after boot

#if CONFIG_SMARTHIVE_MQTT_TLS
extern const char ca_crt_start[] asm("_binary_ca_crt_start");
extern const char node_crt_start[] asm("_binary_node_crt_start");
extern const char node_key_start[] asm("_binary_node_key_start");
#endif

static int64_t unix_ms(void)
{
    struct timeval tv;
    gettimeofday(&tv, NULL);
    return (int64_t)tv.tv_sec * 1000 + tv.tv_usec / 1000;
}

static void fmt_ts(int64_t ms, char out[TS_LEN])
{
    time_t s = ms / 1000;
    struct tm tm;
    gmtime_r(&s, &tm);
    size_t n = strftime(out, TS_LEN, "%Y-%m-%dT%H:%M:%S", &tm);
    snprintf(out + n, TS_LEN - n, ".%03dZ", (int)(ms % 1000));
}

static void fmt_uuid(uint8_t b[16], int version, char out[UUID_LEN])
{
    b[6] = (b[6] & 0x0f) | (version << 4);
    b[8] = (b[8] & 0x3f) | 0x80;  // RFC 9562 variant
    snprintf(out, UUID_LEN, "%02x%02x%02x%02x-%02x%02x-%02x%02x-%02x%02x-%02x%02x%02x%02x%02x%02x",
             b[0], b[1], b[2], b[3], b[4], b[5], b[6], b[7], b[8], b[9], b[10], b[11], b[12], b[13], b[14], b[15]);
}

static void uuid4(char out[UUID_LEN])
{
    uint8_t b[16];
    esp_fill_random(b, sizeof(b));
    fmt_uuid(b, 4, out);
}

// UUIDv7: 48-bit Unix milliseconds, then random. The server deduplicates on it.
static void uuid7(char out[UUID_LEN])
{
    uint8_t b[16];
    esp_fill_random(b, sizeof(b));
    int64_t ms = unix_ms();
    for (int i = 0; i < 6; i++) {
        b[i] = (uint8_t)(ms >> (40 - 8 * i));
    }
    fmt_uuid(b, 7, out);
}

static void on_time_sync(struct timeval *tv)
{
    s_clock_synced = true;
    ESP_LOGI(TAG, "clock synced");
}

static sample_t take_sample(void)
{
    gpio_num_t pin = CONFIG_SMARTHIVE_DHT11_GPIO;
    sample_t s = {.ok = false};
    for (int i = 0; i < READ_ATTEMPTS && !s.ok; i++) {
        if (i) {
            vTaskDelay(pdMS_TO_TICKS(1200));  // the DHT11 needs 1 s between reads
        }
        esp_err_t err = dht11_read(pin, &s.temp_c, &s.rh_pct);
        s.ok = err == ESP_OK;
        if (!s.ok) {
            ESP_LOGW(TAG, "dht11 read failed: %s", esp_err_to_name(err));
        }
    }
    s.unix_ms = unix_ms();
    s.mono_ms = esp_timer_get_time() / 1000;
    s.clock_synced = s_clock_synced;
    if (s.ok) {
        ESP_LOGI(TAG, "temp %.1f C, rh %.1f %%", s.temp_c, s.rh_pct);
    }
    return s;
}

static void push(sample_t s)
{
    if (s_count == MAX_PENDING) {
        ESP_LOGW(TAG, "buffer full, dropping the oldest sample");
        s_head = (s_head + 1) % MAX_PENDING;
        s_count--;
    }
    s_pending[(s_head + s_count) % MAX_PENDING] = s;
    s_count++;
}

// Appends one reading object. Returns the new length, or -1 if it does not fit.
static int put_reading(int len, const sample_t *s, const char *quantity, const char *unit, float value)
{
    char ts[TS_LEN], val[16];
    fmt_ts(s->unix_ms, ts);
    if (s->ok) {
        snprintf(val, sizeof(val), "%.1f", value);
    } else {
        strcpy(val, "null");
    }
    int n = snprintf(s_buf + len, sizeof(s_buf) - len,
                     "%s{\"ts\":\"%s\",\"mono_ms\":%lld,\"clock_synced\":%s,\"sensor\":\"" SENSOR_ID "\","
                     "\"quantity\":\"%s\",\"value\":%s,\"unit\":\"%s\",\"quality\":\"%s\"}",
                     s_buf[len - 1] == '[' ? "" : ",", ts, (long long)s->mono_ms,
                     s->clock_synced ? "true" : "false", quantity, val, unit, s->ok ? "ok" : "read_error");
    return n < (int)(sizeof(s_buf) - len) ? len + n : -1;
}

// Builds one telemetry message with up to `n` pending samples. Returns its length, or -1.
static int build_telemetry(int n)
{
    char msg_id[UUID_LEN], sent_at[TS_LEN];
    uuid7(msg_id);
    fmt_ts(unix_ms(), sent_at);
    int len = snprintf(s_buf, sizeof(s_buf),
                       "{\"schema\":\"smarthive.telemetry/1.0\",\"msg_id\":\"%s\",\"node_id\":\"" CONFIG_SMARTHIVE_NODE_ID
                       "\",\"boot_id\":\"%s\",\"sent_at\":\"%s\",\"readings\":[",
                       msg_id, s_boot_id, sent_at);
    for (int i = 0; i < n && len > 0; i++) {
        const sample_t *s = &s_pending[(s_head + i) % MAX_PENDING];
        len = put_reading(len, s, "temp_in", "degC", s->temp_c);
        if (len > 0) {
            len = put_reading(len, s, "rh_in", "pct_rh", s->rh_pct);
        }
    }
    if (len < 0 || len + 3 > (int)sizeof(s_buf)) {
        return -1;
    }
    return len + snprintf(s_buf + len, sizeof(s_buf) - len, "]}");
}

// Sends everything pending, oldest first. Samples leave the buffer once the client has queued them (QoS 1).
static void flush(void)
{
    while (s_count && s_mqtt_up) {
        int n = s_count < BATCH_MAX ? s_count : BATCH_MAX;
        int len = build_telemetry(n);
        if (len < 0) {
            ESP_LOGE(TAG, "batch does not fit in %d bytes", (int)sizeof(s_buf));
            return;
        }
        if (esp_mqtt_client_publish(s_mqtt, TOPIC_PREFIX "telemetry", s_buf, len, 1, 0) < 0) {
            ESP_LOGW(TAG, "publish failed, keeping %d samples", s_count);
            return;
        }
        ESP_LOGI(TAG, "published %d samples", n);
        s_head = (s_head + n) % MAX_PENDING;
        s_count -= n;
    }
}

static void on_mqtt(void *arg, esp_event_base_t base, int32_t id, void *data)
{
    esp_mqtt_event_handle_t ev = data;
    switch ((esp_mqtt_event_id_t)id) {
    case MQTT_EVENT_CONNECTED: {
        char status[96];
        int len = snprintf(status, sizeof(status), "{\"state\":\"online\",\"boot_id\":\"%s\"}", s_boot_id);
        esp_mqtt_client_publish(ev->client, TOPIC_PREFIX "status", status, len, 1, 1);
        s_mqtt_up = true;
        ESP_LOGI(TAG, "mqtt connected");
        break;
    }
    case MQTT_EVENT_DISCONNECTED:
        s_mqtt_up = false;
        ESP_LOGW(TAG, "mqtt disconnected");
        break;
    case MQTT_EVENT_ERROR:
        if (ev->error_handle->error_type == MQTT_ERROR_TYPE_TCP_TRANSPORT) {
            ESP_LOGE(TAG, "transport error 0x%x (tls 0x%x)", ev->error_handle->esp_tls_last_esp_err,
                     ev->error_handle->esp_tls_stack_err);
        } else {
            ESP_LOGE(TAG, "mqtt error type %d", ev->error_handle->error_type);
        }
        break;
    default:
        break;
    }
}

static void mqtt_start(void)
{
    static const char will[] = "{\"state\":\"offline\"}";
    esp_mqtt_client_config_t cfg = {
        .broker.address.uri = CONFIG_SMARTHIVE_MQTT_URI,
        .credentials.client_id = CONFIG_SMARTHIVE_NODE_ID,
        .buffer.size = PAYLOAD_MAX,
        .session.last_will = {
            .topic = TOPIC_PREFIX "status",
            .msg = will,
            .msg_len = sizeof(will) - 1,
            .qos = 1,
            .retain = 1,
        },
#if CONFIG_SMARTHIVE_MQTT_TLS
        // The broker takes the MQTT user from the certificate CN, so no username or password here
        .broker.verification.certificate = ca_crt_start,
#if CONFIG_SMARTHIVE_MQTT_SKIP_CN_CHECK
        .broker.verification.skip_cert_common_name_check = true,
#endif
        .credentials.authentication.certificate = node_crt_start,
        .credentials.authentication.key = node_key_start,
#endif
    };
    s_mqtt = esp_mqtt_client_init(&cfg);
    ESP_ERROR_CHECK(esp_mqtt_client_register_event(s_mqtt, ESP_EVENT_ANY_ID, on_mqtt, NULL));
    ESP_ERROR_CHECK(esp_mqtt_client_start(s_mqtt));  // reconnects on its own
}

void app_main(void)
{
    esp_err_t err = nvs_flash_init();
    if (err == ESP_ERR_NVS_NO_FREE_PAGES || err == ESP_ERR_NVS_NEW_VERSION_FOUND) {
        ESP_ERROR_CHECK(nvs_flash_erase());
        err = nvs_flash_init();
    }
    ESP_ERROR_CHECK(err);
    ESP_ERROR_CHECK(esp_netif_init());
    ESP_ERROR_CHECK(esp_event_loop_create_default());
    ESP_ERROR_CHECK(dht11_init(CONFIG_SMARTHIVE_DHT11_GPIO));
    uuid4(s_boot_id);
    ESP_LOGI(TAG, "node " CONFIG_SMARTHIVE_NODE_ID ", boot %s", s_boot_id);

    wifi_start();
    // Readings start even without a network; they wait in the buffer and carry clock_synced=false
    if (!wifi_wait_connected(pdMS_TO_TICKS(30000))) {
        ESP_LOGW(TAG, "no wi-fi yet, sampling anyway");
    }

    esp_sntp_config_t sntp = ESP_NETIF_SNTP_DEFAULT_CONFIG(CONFIG_SMARTHIVE_NTP_SERVER);
    sntp.sync_cb = on_time_sync;
    ESP_ERROR_CHECK(esp_netif_sntp_init(&sntp));
    if (esp_netif_sntp_sync_wait(pdMS_TO_TICKS(15000)) != ESP_OK) {
        ESP_LOGW(TAG, "no NTP yet, timestamps are unsynced until it arrives");
    }

    mqtt_start();

    TickType_t last = xTaskGetTickCount();
    for (;;) {
        push(take_sample());
        flush();
        vTaskDelayUntil(&last, pdMS_TO_TICKS(CONFIG_SMARTHIVE_SAMPLE_INTERVAL_S * 1000));
    }
}
