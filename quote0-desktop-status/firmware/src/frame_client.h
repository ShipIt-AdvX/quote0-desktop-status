#pragma once

#include <stddef.h>
#include <stdint.h>

#include "config_store.h"
#include "esp_err.h"

#define FRAME_BYTES 5624

esp_err_t frame_fetch(const desk_config_t *cfg, uint8_t *out, size_t out_len);
bool server_reachable(const desk_config_t *cfg);
