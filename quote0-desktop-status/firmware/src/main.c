#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "config_store.h"
#include "discover.h"
#include "driver/usb_serial_jtag.h"
#include "esp_event.h"
#include "esp_log.h"
#include "esp_netif.h"
#include "esp_system.h"
#include "esp_wifi.h"
#include "frame_client.h"
#include "freertos/FreeRTOS.h"
#include "freertos/event_groups.h"
#include "freertos/task.h"
#include "image_store.h"
#include "nvs_flash.h"
#include "status_screen.h"
#include "uc8251d_minimal.h"

static const char *TAG = "main";

#define WIFI_CONNECTED_BIT BIT0

static EventGroupHandle_t s_wifi_events;
static int s_retry = 0;
static int s_wifi_index = 0;
static desk_config_t s_cfg;
static uint8_t s_frame[UC8251D_BUFFER_SIZE];
static volatile bool s_wifi_ready = false;
static volatile bool s_want_sta = false;
static bool s_wifi_started = false;

static bool s_img_rx = false;
static size_t s_img_need = 0;
static size_t s_img_got = 0;
static uint8_t s_img_buf[IMAGE_BYTES];

static const uc8251d_config_t display_config = {
    .spi_host = SPI2_HOST,
    .pin_vin = 20,
    .pin_busy = 3,
    .pin_reset = 4,
    .pin_dc = 5,
    .pin_cs = 6,
    .pin_sck = 10,
    .pin_mosi = 7,
    .spi_clock_hz = 15 * 1000 * 1000,
};

static void show_msg(const char *a, const char *b, const char *c)
{
    status_screen_message(s_frame, a, b, c);
    ESP_ERROR_CHECK(uc8251d_display(s_frame));
}

static void apply_sta_for_index(int idx)
{
    if (idx < 0 || idx >= s_cfg.wifi_count) {
        return;
    }
    wifi_config_t wifi_config = {0};
    strncpy((char *)wifi_config.sta.ssid, s_cfg.wifi[idx].ssid, sizeof(wifi_config.sta.ssid));
    strncpy((char *)wifi_config.sta.password, s_cfg.wifi[idx].pass, sizeof(wifi_config.sta.password));
    if (s_cfg.wifi[idx].pass[0] == '\0') {
        wifi_config.sta.threshold.authmode = WIFI_AUTH_OPEN;
    } else {
        wifi_config.sta.threshold.authmode = WIFI_AUTH_WPA_PSK;
    }
    wifi_config.sta.pmf_cfg.capable = true;
    wifi_config.sta.pmf_cfg.required = false;
    wifi_config.sta.scan_method = WIFI_ALL_CHANNEL_SCAN;
    wifi_config.sta.sort_method = WIFI_CONNECT_AP_BY_SIGNAL;
    wifi_config.sta.failure_retry_cnt = 3;
    esp_wifi_set_config(WIFI_IF_STA, &wifi_config);
}

static void wifi_event(void *arg, esp_event_base_t base, int32_t id, void *data)
{
    if (base == WIFI_EVENT && id == WIFI_EVENT_STA_START) {
        if (s_want_sta && config_has_wifi(&s_cfg)) {
            esp_wifi_connect();
        }
    } else if (base == WIFI_EVENT && id == WIFI_EVENT_STA_DISCONNECTED) {
        wifi_event_sta_disconnected_t *disc = (wifi_event_sta_disconnected_t *)data;
        s_wifi_ready = false;
        xEventGroupClearBits(s_wifi_events, WIFI_CONNECTED_BIT);
        if (!s_want_sta) {
            return;
        }
        s_retry++;
        ESP_LOGW(TAG, "wifi disconnect reason=%u retry=%d", (unsigned)disc->reason, s_retry);
        if (s_cfg.wifi_count > 1 && (s_retry % 6) == 0) {
            s_wifi_index = (s_wifi_index + 1) % s_cfg.wifi_count;
            apply_sta_for_index(s_wifi_index);
        }
        vTaskDelay(pdMS_TO_TICKS(300 + (s_retry % 6) * 200));
        if (s_want_sta) {
            esp_wifi_connect();
        }
    } else if (base == IP_EVENT && id == IP_EVENT_STA_GOT_IP) {
        ip_event_got_ip_t *event = (ip_event_got_ip_t *)data;
        ESP_LOGI(TAG, "got ip " IPSTR, IP2STR(&event->ip_info.ip));
        s_retry = 0;
        s_wifi_ready = true;
        xEventGroupSetBits(s_wifi_events, WIFI_CONNECTED_BIT);
    }
}

static void wifi_stack_init(void)
{
    s_wifi_events = xEventGroupCreate();
    ESP_ERROR_CHECK(esp_netif_init());
    ESP_ERROR_CHECK(esp_event_loop_create_default());
    esp_netif_create_default_wifi_sta();

    wifi_init_config_t cfg = WIFI_INIT_CONFIG_DEFAULT();
    ESP_ERROR_CHECK(esp_wifi_init(&cfg));
    ESP_ERROR_CHECK(esp_event_handler_register(WIFI_EVENT, ESP_EVENT_ANY_ID, &wifi_event, NULL));
    ESP_ERROR_CHECK(esp_event_handler_register(IP_EVENT, IP_EVENT_STA_GOT_IP, &wifi_event, NULL));
}

static void wifi_radio_start(void)
{
    s_want_sta = config_has_wifi(&s_cfg);
    s_wifi_ready = false;
    xEventGroupClearBits(s_wifi_events, WIFI_CONNECTED_BIT);
    s_retry = 0;

    ESP_ERROR_CHECK(esp_wifi_set_mode(WIFI_MODE_STA));
    if (s_want_sta) {
        apply_sta_for_index(s_wifi_index);
    }
    ESP_ERROR_CHECK(esp_wifi_start());
    s_wifi_started = true;
    ESP_ERROR_CHECK(esp_wifi_set_ps(WIFI_PS_MIN_MODEM));
}

static void wifi_radio_stop(void)
{
    s_want_sta = false;
    s_wifi_ready = false;
    xEventGroupClearBits(s_wifi_events, WIFI_CONNECTED_BIT);
    if (s_wifi_started) {
        esp_wifi_stop();
    }
}

static bool wait_sta_connected(int timeout_ms)
{
    EventBits_t bits = xEventGroupWaitBits(s_wifi_events, WIFI_CONNECTED_BIT, pdFALSE, pdFALSE,
                                           pdMS_TO_TICKS(timeout_ms));
    return (bits & WIFI_CONNECTED_BIT) != 0;
}

static void print_cfg_json(void)
{
    printf("{\"ok\":true,\"wifi\":[");
    for (uint8_t i = 0; i < s_cfg.wifi_count; i++) {
        if (i) {
            printf(",");
        }
        printf("{\"ssid\":\"%s\",\"has_pass\":%s}", s_cfg.wifi[i].ssid,
               s_cfg.wifi[i].pass[0] ? "true" : "false");
    }
    printf("],\"server_host\":\"%s\",\"server_port\":%u,\"poll_sec\":%u,"
           "\"has_image\":%s,\"show_custom_image\":%u,\"wifi_ready\":%s}\n",
           s_cfg.server_host, s_cfg.server_port, s_cfg.poll_sec,
           image_store_has() ? "true" : "false", (unsigned)s_cfg.show_custom_image,
           s_wifi_ready ? "true" : "false");
}

static void handle_line(char *line)
{
    while (*line == ' ' || *line == '\t') {
        line++;
    }
    if (!*line) {
        return;
    }

    if (strcmp(line, "PING") == 0) {
        printf("PONG\n");
    } else if (strcmp(line, "GET") == 0 || strcmp(line, "GET_JSON") == 0) {
        print_cfg_json();
    } else if (strncmp(line, "WIFI_ADD ", 9) == 0) {
        char *ssid = line + 9;
        char *pass = strchr(ssid, ' ');
        if (pass) {
            *pass++ = '\0';
        } else {
            pass = "";
        }
        if (!ssid[0]) {
            printf("ERR need: WIFI_ADD ssid [password]\n");
            return;
        }
        if (!config_wifi_add(&s_cfg, ssid, pass)) {
            printf("ERR wifi full (max %d)\n", CFG_WIFI_MAX);
            return;
        }
        printf("OK wifi_add %s count=%u\n", ssid, (unsigned)s_cfg.wifi_count);
    } else if (strncmp(line, "WIFI_DEL ", 9) == 0) {
        char *ssid = line + 9;
        if (!config_wifi_del(&s_cfg, ssid)) {
            printf("ERR not found\n");
            return;
        }
        printf("OK wifi_del %s count=%u\n", ssid, (unsigned)s_cfg.wifi_count);
    } else if (strncmp(line, "SET_WIFI ", 9) == 0) {
        char *ssid = line + 9;
        char *pass = strchr(ssid, ' ');
        if (pass) {
            *pass++ = '\0';
        } else {
            pass = "";
        }
        config_wifi_clear(&s_cfg);
        config_wifi_add(&s_cfg, ssid, pass);
        printf("OK wifi ssid=%s\n", ssid);
    } else if (strncmp(line, "SET_SERVER ", 11) == 0) {
        char host[CFG_HOST_MAX];
        unsigned port = 0;
        if (sscanf(line + 11, "%63s %u", host, &port) != 2) {
            printf("ERR need: SET_SERVER host port\n");
            return;
        }
        strncpy(s_cfg.server_host, host, sizeof(s_cfg.server_host) - 1);
        s_cfg.server_host[sizeof(s_cfg.server_host) - 1] = '\0';
        s_cfg.server_port = (uint16_t)port;
        printf("OK server %s:%u\n", s_cfg.server_host, s_cfg.server_port);
    } else if (strncmp(line, "SET_POLL ", 9) == 0) {
        unsigned p = 0;
        if (sscanf(line + 9, "%u", &p) != 1 || p < 10) {
            printf("ERR need: SET_POLL seconds (>=10)\n");
            return;
        }
        s_cfg.poll_sec = (uint16_t)p;
        printf("OK poll=%u\n", s_cfg.poll_sec);
    } else if (strncmp(line, "SET_MODE ", 9) == 0) {
        if (strcmp(line + 9, "image") == 0) {
            s_cfg.show_custom_image = 1;
            printf("OK mode=image\n");
        } else if (strcmp(line + 9, "server") == 0) {
            s_cfg.show_custom_image = 0;
            printf("OK mode=server\n");
        } else {
            printf("ERR need: SET_MODE image|server\n");
        }
    } else if (strncmp(line, "IMG_BEGIN ", 10) == 0) {
        unsigned n = 0;
        if (sscanf(line + 10, "%u", &n) != 1 || n != IMAGE_BYTES) {
            printf("ERR need: IMG_BEGIN %d\n", IMAGE_BYTES);
            return;
        }
        s_img_rx = true;
        s_img_need = n;
        s_img_got = 0;
        printf("OK send %u bytes\n", n);
    } else if (strcmp(line, "IMG_CLEAR") == 0) {
        printf(image_store_clear() ? "OK img cleared\n" : "ERR clear\n");
        s_cfg.show_custom_image = 0;
    } else if (strcmp(line, "IMG_SHOW") == 0) {
        if (!image_store_load(s_frame, sizeof(s_frame))) {
            printf("ERR no image\n");
            return;
        }
        uc8251d_display(s_frame);
        s_cfg.show_custom_image = 1;
        printf("OK shown\n");
    } else if (strcmp(line, "DISCOVER") == 0) {
        if (discover_server(&s_cfg, 3000)) {
            config_save(&s_cfg);
            printf("OK discovered %s:%u\n", s_cfg.server_host, s_cfg.server_port);
        } else {
            printf("ERR discover failed\n");
        }
    } else if (strcmp(line, "SAVE") == 0) {
        printf(config_save(&s_cfg) ? "OK saved\n" : "ERR save failed\n");
    } else if (strcmp(line, "REBOOT") == 0) {
        printf("rebooting...\n");
        vTaskDelay(pdMS_TO_TICKS(200));
        esp_restart();
    } else {
        printf("ERR unknown cmd\n");
    }
}

static bool ensure_server(void)
{
    if (s_cfg.server_host[0] && server_reachable(&s_cfg)) {
        return true;
    }
    for (int i = 0; i < 4; i++) {
        if (discover_server(&s_cfg, 2500)) {
            config_save(&s_cfg);
            return true;
        }
        vTaskDelay(pdMS_TO_TICKS(200));
    }
    return false;
}

static void usb_cmd_task(void *arg)
{
    (void)arg;
    usb_serial_jtag_driver_config_t cfg = USB_SERIAL_JTAG_DRIVER_CONFIG_DEFAULT();
    cfg.rx_buffer_size = 4096;
    cfg.tx_buffer_size = 2048;
    if (usb_serial_jtag_driver_install(&cfg) != ESP_OK) {
        ESP_LOGW(TAG, "usb serial jtag driver install failed");
    }

    char line[256];
    size_t n = 0;
    uint8_t ch;
    while (1) {
        int r = usb_serial_jtag_read_bytes(&ch, 1, pdMS_TO_TICKS(50));
        if (r <= 0) {
            continue;
        }
        if (s_img_rx) {
            s_img_buf[s_img_got++] = ch;
            if (s_img_got >= s_img_need) {
                s_img_rx = false;
                if (image_store_save(s_img_buf, s_img_need)) {
                    memcpy(s_frame, s_img_buf, IMAGE_BYTES);
                    uc8251d_display(s_frame);
                    s_cfg.show_custom_image = 1;
                    config_save(&s_cfg);
                    printf("OK img saved+shown\n");
                } else {
                    printf("ERR img save\n");
                }
            }
            continue;
        }
        if (ch == '\r') {
            continue;
        }
        if (ch == '\n') {
            line[n] = '\0';
            handle_line(line);
            n = 0;
            continue;
        }
        if (n + 1 < sizeof(line)) {
            line[n++] = (char)ch;
        }
    }
}

static bool online_fetch_once(void)
{
    char hostline[80];
    if (!wait_sta_connected(25000)) {
        return false;
    }
    if (s_cfg.show_custom_image) {
        return true;
    }
    if (!ensure_server()) {
        return false;
    }
    esp_err_t err = frame_fetch(&s_cfg, s_frame, sizeof(s_frame));
    if (err != ESP_OK) {
        snprintf(hostline, sizeof(hostline), "%s:%u", s_cfg.server_host, s_cfg.server_port);
        show_msg("FETCH?", hostline, esp_err_to_name(err));
        return false;
    }
    ESP_ERROR_CHECK(uc8251d_display(s_frame));
    ESP_LOGI(TAG, "frame ok from %s:%u", s_cfg.server_host, s_cfg.server_port);
    return true;
}

void app_main(void)
{
    esp_err_t err = nvs_flash_init();
    if (err == ESP_ERR_NVS_NO_FREE_PAGES || err == ESP_ERR_NVS_NEW_VERSION_FOUND) {
        ESP_ERROR_CHECK(nvs_flash_erase());
        ESP_ERROR_CHECK(nvs_flash_init());
    }

    config_load(&s_cfg);
    ESP_LOGI(TAG, "Quote/0 USB config + power-save poll");

    ESP_ERROR_CHECK(uc8251d_init(&display_config));
    xTaskCreate(usb_cmd_task, "usb_cmd", 6144, NULL, 5, NULL);

    if (s_cfg.show_custom_image && image_store_load(s_frame, sizeof(s_frame))) {
        uc8251d_display(s_frame);
    } else {
        show_msg("USB CFG", "0.1.2.3:8080", "on PC portal");
    }

    wifi_stack_init();

    if (!config_has_wifi(&s_cfg)) {
        show_msg("NO WIFI", "USB portal", "0.1.2.3:8080");
        while (1) {
            vTaskDelay(pdMS_TO_TICKS(1000));
            if (config_has_wifi(&s_cfg)) {
                show_msg("SAVED", "rebooting", "");
                vTaskDelay(pdMS_TO_TICKS(400));
                esp_restart();
            }
        }
    }

    while (1) {
        if (s_cfg.show_custom_image) {
            if (image_store_load(s_frame, sizeof(s_frame))) {
                uc8251d_display(s_frame);
            }
            wifi_radio_stop();
            vTaskDelay(pdMS_TO_TICKS(s_cfg.poll_sec * 1000));
            continue;
        }

        wifi_radio_start();
        online_fetch_once();
        /* Keep last frame on screen; radio off during wait. */
        wifi_radio_stop();
        ESP_LOGI(TAG, "WiFi off, keep display %u s", (unsigned)s_cfg.poll_sec);
        vTaskDelay(pdMS_TO_TICKS(s_cfg.poll_sec * 1000));
    }
}
