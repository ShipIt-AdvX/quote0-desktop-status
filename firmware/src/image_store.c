#include "image_store.h"

#include <string.h>

#include "nvs.h"
#include "nvs_flash.h"

static const char *NS = "desk";

bool image_store_has(void)
{
    nvs_handle_t h;
    if (nvs_open(NS, NVS_READONLY, &h) != ESP_OK) {
        return false;
    }
    uint8_t flag = 0;
    esp_err_t err = nvs_get_u8(h, "imgf", &flag);
    nvs_close(h);
    return err == ESP_OK && flag == 1;
}

bool image_store_load(uint8_t *out, size_t out_len)
{
    if (!out || out_len < IMAGE_BYTES) {
        return false;
    }
    nvs_handle_t h;
    if (nvs_open(NS, NVS_READONLY, &h) != ESP_OK) {
        return false;
    }
    size_t len = out_len;
    esp_err_t err = nvs_get_blob(h, "img", out, &len);
    nvs_close(h);
    return err == ESP_OK && len == IMAGE_BYTES;
}

bool image_store_save(const uint8_t *data, size_t len)
{
    if (!data || len != IMAGE_BYTES) {
        return false;
    }
    nvs_handle_t h;
    if (nvs_open(NS, NVS_READWRITE, &h) != ESP_OK) {
        return false;
    }
    esp_err_t err = nvs_set_blob(h, "img", data, len);
    if (err == ESP_OK) {
        err = nvs_set_u8(h, "imgf", 1);
    }
    if (err == ESP_OK) {
        err = nvs_commit(h);
    }
    nvs_close(h);
    return err == ESP_OK;
}

bool image_store_clear(void)
{
    nvs_handle_t h;
    if (nvs_open(NS, NVS_READWRITE, &h) != ESP_OK) {
        return false;
    }
    nvs_erase_key(h, "img");
    nvs_set_u8(h, "imgf", 0);
    esp_err_t err = nvs_commit(h);
    nvs_close(h);
    return err == ESP_OK;
}
