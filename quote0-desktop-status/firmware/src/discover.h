#pragma once

#include <stdbool.h>

#include "config_store.h"

#define DISCOVER_UDP_PORT 18787

/**
 * Broadcast LAN discovery and fill cfg->server_host / server_port on success.
 * Returns true if a Quote/0 status server replied.
 */
bool discover_server(desk_config_t *cfg, int timeout_ms);
