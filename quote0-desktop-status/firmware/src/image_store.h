#pragma once

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#include "uc8251d_minimal.h"

#define IMAGE_BYTES UC8251D_BUFFER_SIZE

bool image_store_has(void);
bool image_store_load(uint8_t *out, size_t out_len);
bool image_store_save(const uint8_t *data, size_t len);
bool image_store_clear(void);
