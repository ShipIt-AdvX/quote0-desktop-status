#include "discover.h"

#include <stdio.h>
#include <string.h>

#include "esp_log.h"
#include "esp_netif.h"
#include "lwip/inet.h"
#include "lwip/sockets.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

static const char *TAG = "discover";

static bool parse_reply(const char *buf, desk_config_t *cfg)
{
    char host[CFG_HOST_MAX] = {0};
    unsigned port = 0;
    if (sscanf(buf, "QUOTE0_SERVER %63s %u", host, &port) == 2 && host[0] && port > 0 && port < 65536) {
        strncpy(cfg->server_host, host, sizeof(cfg->server_host) - 1);
        cfg->server_host[sizeof(cfg->server_host) - 1] = '\0';
        cfg->server_port = (uint16_t)port;
        return true;
    }
    /* also accept announce packet with same format */
    if (sscanf(buf, "QUOTE0_ANNOUNCE %63s %u", host, &port) == 2 && host[0] && port > 0 && port < 65536) {
        strncpy(cfg->server_host, host, sizeof(cfg->server_host) - 1);
        cfg->server_host[sizeof(cfg->server_host) - 1] = '\0';
        cfg->server_port = (uint16_t)port;
        return true;
    }
    return false;
}

static void send_discover(int sock, uint32_t addr_be)
{
    struct sockaddr_in dest = {0};
    dest.sin_family = AF_INET;
    dest.sin_port = htons(DISCOVER_UDP_PORT);
    dest.sin_addr.s_addr = addr_be;
    const char *req = "QUOTE0_DISCOVER 1\n";
    sendto(sock, req, strlen(req), 0, (struct sockaddr *)&dest, sizeof(dest));
}

bool discover_server(desk_config_t *cfg, int timeout_ms)
{
    if (!cfg) {
        return false;
    }
    if (timeout_ms < 1500) {
        timeout_ms = 1500;
    }

    int sock = socket(AF_INET, SOCK_DGRAM, IPPROTO_UDP);
    if (sock < 0) {
        ESP_LOGE(TAG, "socket failed");
        return false;
    }

    int yes = 1;
    setsockopt(sock, SOL_SOCKET, SO_BROADCAST, &yes, sizeof(yes));
    setsockopt(sock, SOL_SOCKET, SO_REUSEADDR, &yes, sizeof(yes));

    /* Bind discovery port so we also hear periodic QUOTE0_ANNOUNCE. */
    struct sockaddr_in local = {0};
    local.sin_family = AF_INET;
    local.sin_port = htons(DISCOVER_UDP_PORT);
    local.sin_addr.s_addr = htonl(INADDR_ANY);
    if (bind(sock, (struct sockaddr *)&local, sizeof(local)) != 0) {
        /* Fall back to ephemeral if 18787 is busy. */
        local.sin_port = htons(0);
        bind(sock, (struct sockaddr *)&local, sizeof(local));
    }

    struct timeval tv = {.tv_sec = 0, .tv_usec = 200 * 1000};
    setsockopt(sock, SOL_SOCKET, SO_RCVTIMEO, &tv, sizeof(tv));

    uint32_t subnet_bcast = htonl(INADDR_BROADCAST);
    esp_netif_t *netif = esp_netif_get_handle_from_ifkey("WIFI_STA_DEF");
    if (netif) {
        esp_netif_ip_info_t ip_info;
        if (esp_netif_get_ip_info(netif, &ip_info) == ESP_OK && ip_info.ip.addr != 0) {
            subnet_bcast = ip_info.ip.addr | ~ip_info.netmask.addr;
            ESP_LOGI(TAG, "subnet bcast %s", inet_ntoa(*(struct in_addr *)&subnet_bcast));
        }
    }

    ESP_LOGI(TAG, "discovery burst (%d ms)...", timeout_ms);
    TickType_t deadline = xTaskGetTickCount() + pdMS_TO_TICKS(timeout_ms);
    int burst = 0;
    bool ok = false;
    char buf[192];

    while (xTaskGetTickCount() < deadline && !ok) {
        /* Send a few packets each round: global + subnet + last known host. */
        if ((burst % 2) == 0) {
            send_discover(sock, htonl(INADDR_BROADCAST));
            send_discover(sock, subnet_bcast);
            if (cfg->server_host[0]) {
                struct in_addr known;
                if (inet_aton(cfg->server_host, &known)) {
                    send_discover(sock, known.s_addr);
                }
            }
        }
        burst++;

        struct sockaddr_in from = {0};
        socklen_t fromlen = sizeof(from);
        int n = recvfrom(sock, buf, sizeof(buf) - 1, 0, (struct sockaddr *)&from, &fromlen);
        if (n > 0) {
            buf[n] = '\0';
            if (parse_reply(buf, cfg)) {
                ESP_LOGI(TAG, "found server %s:%u (from %s)", cfg->server_host, cfg->server_port,
                         inet_ntoa(from.sin_addr));
                ok = true;
                break;
            }
        }
        vTaskDelay(pdMS_TO_TICKS(80));
    }

    if (!ok) {
        ESP_LOGW(TAG, "no discovery reply in %d ms", timeout_ms);
    }

    close(sock);
    return ok;
}
