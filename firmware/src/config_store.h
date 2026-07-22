#pragma once

#include <stdbool.h>
#include <stdint.h>

#define CFG_SSID_MAX 32
#define CFG_PASS_MAX 64
#define CFG_HOST_MAX 64
#define CFG_WIFI_MAX 4

typedef struct {
    char ssid[CFG_SSID_MAX];
    char pass[CFG_PASS_MAX];
} wifi_cred_t;

typedef struct {
    wifi_cred_t wifi[CFG_WIFI_MAX];
    uint8_t wifi_count;
    char server_host[CFG_HOST_MAX];
    uint16_t server_port;
    uint16_t poll_sec;
    /* 0 = pull frames from server; 1 = show stored custom image */
    uint8_t show_custom_image;
} desk_config_t;

void config_set_defaults(desk_config_t *cfg);
bool config_load(desk_config_t *cfg);
bool config_save(const desk_config_t *cfg);
bool config_has_wifi(const desk_config_t *cfg);

/* Active STA credentials (first entry or currently selected). */
const char *config_active_ssid(const desk_config_t *cfg);
const char *config_active_pass(const desk_config_t *cfg);

bool config_wifi_add(desk_config_t *cfg, const char *ssid, const char *pass);
bool config_wifi_del(desk_config_t *cfg, const char *ssid);
void config_wifi_clear(desk_config_t *cfg);
