#pragma once

#include <stdint.h>

#include "uc8251d_minimal.h"

void status_screen_message(uint8_t *frame, const char *title, const char *line2, const char *line3);
void status_screen_clear_white(uint8_t *frame);
