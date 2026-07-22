#include "config_store.h"

#include <stdio.h>
#include <string.h>

#include "nvs.h"
#include "nvs_flash.h"

static const char *NS = "desk";

void config_set_defaults(desk_config_t *cfg)
{
    memset(cfg, 0, sizeof(*cfg));
    strncpy(cfg->wifi[0].ssid, "ADVX-players", sizeof(cfg->wifi[0].ssid) - 1);
    strncpy(cfg->wifi[0].pass, "AdventureX", sizeof(cfg->wifi[0].pass) - 1);
    cfg->wifi_count = 1;
    cfg->server_host[0] = '\0';
    cfg->server_port = 8787;
    cfg->poll_sec = 30;
    cfg->show_custom_image = 0;
}

static void migrate_legacy(nvs_handle_t h, desk_config_t *cfg)
{
    char ssid[CFG_SSID_MAX] = {0};
    char pass[CFG_PASS_MAX] = {0};
    size_t len = sizeof(ssid);
    if (nvs_get_str(h, "ssid", ssid, &len) == ESP_OK && ssid[0]) {
        len = sizeof(pass);
        nvs_get_str(h, "pass", pass, &len);
        config_wifi_clear(cfg);
        config_wifi_add(cfg, ssid, pass);
    }
}

bool config_load(desk_config_t *cfg)
{
    config_set_defaults(cfg);
    nvs_handle_t h;
    if (nvs_open(NS, NVS_READONLY, &h) != ESP_OK) {
        return false;
    }

    uint8_t count = 0;
    if (nvs_get_u8(h, "wcnt", &count) == ESP_OK && count > 0) {
        if (count > CFG_WIFI_MAX) {
            count = CFG_WIFI_MAX;
        }
        cfg->wifi_count = 0;
        for (uint8_t i = 0; i < count; i++) {
            char kssid[8], kpass[8];
            snprintf(kssid, sizeof(kssid), "ws%u", (unsigned)i);
            snprintf(kpass, sizeof(kpass), "wp%u", (unsigned)i);
            size_t len = sizeof(cfg->wifi[i].ssid);
            if (nvs_get_str(h, kssid, cfg->wifi[i].ssid, &len) != ESP_OK || !cfg->wifi[i].ssid[0]) {
                break;
            }
            len = sizeof(cfg->wifi[i].pass);
            cfg->wifi[i].pass[0] = '\0';
            nvs_get_str(h, kpass, cfg->wifi[i].pass, &len);
            cfg->wifi_count++;
        }
    } else {
        migrate_legacy(h, cfg);
    }

    size_t len = sizeof(cfg->server_host);
    nvs_get_str(h, "host", cfg->server_host, &len);
    nvs_get_u16(h, "port", &cfg->server_port);
    nvs_get_u16(h, "poll", &cfg->poll_sec);
    nvs_get_u8(h, "cimg", &cfg->show_custom_image);
    nvs_close(h);

    if (cfg->server_port == 0) {
        cfg->server_port = 8787;
    }
    if (cfg->poll_sec < 10) {
        cfg->poll_sec = 10;
    }
    return config_has_wifi(cfg);
}

bool config_save(const desk_config_t *cfg)
{
    nvs_handle_t h;
    if (nvs_open(NS, NVS_READWRITE, &h) != ESP_OK) {
        return false;
    }
    nvs_set_u8(h, "wcnt", cfg->wifi_count);
    for (uint8_t i = 0; i < CFG_WIFI_MAX; i++) {
        char kssid[8], kpass[8];
        snprintf(kssid, sizeof(kssid), "ws%u", (unsigned)i);
        snprintf(kpass, sizeof(kpass), "wp%u", (unsigned)i);
        if (i < cfg->wifi_count) {
            nvs_set_str(h, kssid, cfg->wifi[i].ssid);
            nvs_set_str(h, kpass, cfg->wifi[i].pass);
        } else {
            nvs_erase_key(h, kssid);
            nvs_erase_key(h, kpass);
        }
    }
    /* Keep legacy keys in sync for older tooling. */
    if (cfg->wifi_count > 0) {
        nvs_set_str(h, "ssid", cfg->wifi[0].ssid);
        nvs_set_str(h, "pass", cfg->wifi[0].pass);
    }
    nvs_set_str(h, "host", cfg->server_host);
    nvs_set_u16(h, "port", cfg->server_port);
    nvs_set_u16(h, "poll", cfg->poll_sec);
    nvs_set_u8(h, "cimg", cfg->show_custom_image);
    esp_err_t err = nvs_commit(h);
    nvs_close(h);
    return err == ESP_OK;
}

bool config_has_wifi(const desk_config_t *cfg)
{
    return cfg && cfg->wifi_count > 0 && cfg->wifi[0].ssid[0] != '\0';
}

const char *config_active_ssid(const desk_config_t *cfg)
{
    return (cfg && cfg->wifi_count) ? cfg->wifi[0].ssid : "";
}

const char *config_active_pass(const desk_config_t *cfg)
{
    return (cfg && cfg->wifi_count) ? cfg->wifi[0].pass : "";
}

bool config_wifi_add(desk_config_t *cfg, const char *ssid, const char *pass)
{
    if (!cfg || !ssid || !ssid[0]) {
        return false;
    }
    if (!pass) {
        pass = "";
    }
    for (uint8_t i = 0; i < cfg->wifi_count; i++) {
        if (strncmp(cfg->wifi[i].ssid, ssid, CFG_SSID_MAX) == 0) {
            strncpy(cfg->wifi[i].pass, pass, sizeof(cfg->wifi[i].pass) - 1);
            cfg->wifi[i].pass[sizeof(cfg->wifi[i].pass) - 1] = '\0';
            return true;
        }
    }
    if (cfg->wifi_count >= CFG_WIFI_MAX) {
        return false;
    }
    uint8_t i = cfg->wifi_count++;
    memset(&cfg->wifi[i], 0, sizeof(cfg->wifi[i]));
    strncpy(cfg->wifi[i].ssid, ssid, sizeof(cfg->wifi[i].ssid) - 1);
    strncpy(cfg->wifi[i].pass, pass, sizeof(cfg->wifi[i].pass) - 1);
    return true;
}

bool config_wifi_del(desk_config_t *cfg, const char *ssid)
{
    if (!cfg || !ssid) {
        return false;
    }
    for (uint8_t i = 0; i < cfg->wifi_count; i++) {
        if (strncmp(cfg->wifi[i].ssid, ssid, CFG_SSID_MAX) == 0) {
            for (uint8_t j = i; j + 1 < cfg->wifi_count; j++) {
                cfg->wifi[j] = cfg->wifi[j + 1];
            }
            cfg->wifi_count--;
            memset(&cfg->wifi[cfg->wifi_count], 0, sizeof(cfg->wifi[0]));
            return true;
        }
    }
    return false;
}

void config_wifi_clear(desk_config_t *cfg)
{
    if (!cfg) {
        return;
    }
    memset(cfg->wifi, 0, sizeof(cfg->wifi));
    cfg->wifi_count = 0;
}
