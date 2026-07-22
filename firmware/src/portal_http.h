#pragma once

#include <stdbool.h>

#include "config_store.h"

void portal_set_cfg(desk_config_t *cfg);
void portal_httpd_start(void);
void portal_httpd_stop(void);
void portal_configure_softap_ip(void);
