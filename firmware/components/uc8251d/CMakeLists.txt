idf_component_register(
    SRCS "uc8251d_minimal.c"
    INCLUDE_DIRS "."
    REQUIRES esp_driver_spi esp_driver_gpio driver esp_timer freertos
)
