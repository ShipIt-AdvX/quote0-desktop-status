#include "frame_client.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "esp_http_client.h"
#include "esp_log.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

static const char *TAG = "frame";

typedef struct {
    uint8_t *buf;
    size_t cap;
    size_t len;
} recv_ctx_t;

static esp_err_t _http_event(esp_http_client_event_t *evt)
{
    recv_ctx_t *ctx = (recv_ctx_t *)evt->user_data;
    if (evt->event_id == HTTP_EVENT_ON_DATA && evt->data_len > 0 && ctx) {
        size_t room = ctx->cap - ctx->len;
        size_t n = evt->data_len < room ? evt->data_len : room;
        memcpy(ctx->buf + ctx->len, evt->data, n);
        ctx->len += n;
    }
    return ESP_OK;
}

static esp_err_t frame_fetch_once(const desk_config_t *cfg, uint8_t *out, size_t out_len)
{
    char url[160];
    snprintf(url, sizeof(url), "http://%s:%u/api/frame.bin", cfg->server_host, cfg->server_port);

    recv_ctx_t ctx = {.buf = out, .cap = out_len, .len = 0};
    memset(out, 0xFF, out_len);

    esp_http_client_config_t http_cfg = {
        .url = url,
        .timeout_ms = 6000,
        .event_handler = _http_event,
        .user_data = &ctx,
        .keep_alive_enable = false,
        .disable_auto_redirect = true,
    };

    esp_http_client_handle_t client = esp_http_client_init(&http_cfg);
    if (!client) {
        return ESP_FAIL;
    }

    esp_err_t err = esp_http_client_perform(client);
    int status = esp_http_client_get_status_code(client);
    ESP_LOGI(TAG, "GET %s -> %s status=%d bytes=%u", url, esp_err_to_name(err), status, (unsigned)ctx.len);
    esp_http_client_cleanup(client);

    if (err != ESP_OK) {
        return err;
    }
    if (status != 200) {
        return ESP_FAIL;
    }
    if (ctx.len < FRAME_BYTES) {
        ESP_LOGW(TAG, "short frame %u < %d", (unsigned)ctx.len, FRAME_BYTES);
        return ESP_ERR_INVALID_SIZE;
    }
    return ESP_OK;
}

esp_err_t frame_fetch(const desk_config_t *cfg, uint8_t *out, size_t out_len)
{
    if (!cfg || !out || out_len < FRAME_BYTES || cfg->server_host[0] == '\0') {
        return ESP_ERR_INVALID_ARG;
    }

    esp_err_t last = ESP_FAIL;
    for (int i = 0; i < 3; i++) {
        last = frame_fetch_once(cfg, out, out_len);
        if (last == ESP_OK) {
            return ESP_OK;
        }
        vTaskDelay(pdMS_TO_TICKS(300 + i * 200));
    }
    return last;
}

bool server_reachable(const desk_config_t *cfg)
{
    if (!cfg || cfg->server_host[0] == '\0') {
        return false;
    }
    char url[160];
    snprintf(url, sizeof(url), "http://%s:%u/health", cfg->server_host, cfg->server_port);
    esp_http_client_config_t http_cfg = {
        .url = url,
        .timeout_ms = 2500,
        .keep_alive_enable = false,
    };
    esp_http_client_handle_t client = esp_http_client_init(&http_cfg);
    if (!client) {
        return false;
    }
    esp_err_t err = esp_http_client_perform(client);
    int status = esp_http_client_get_status_code(client);
    esp_http_client_cleanup(client);
    return err == ESP_OK && status == 200;
}
