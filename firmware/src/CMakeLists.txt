idf_component_register(
    SRCS "main.c" "config_store.c" "frame_client.c" "status_screen.c" "discover.c" "image_store.c"
    INCLUDE_DIRS "."
    REQUIRES nvs_flash esp_wifi esp_netif esp_event esp_http_client esp_timer uc8251d driver esp_driver_usb_serial_jtag lwip
)
