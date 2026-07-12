/*
 * ESP32 (38-pin devkit) firmware:
 *  - Connects to Wi-Fi
 *  - Starts an MCP-over-MQTT server (EMQX esp-mcp-over-mqtt C SDK)
 *  - Exposes 4 zero-argument tools that a PC-side MCP client (e.g. driven
 *    by Ollama Cloud) can call: led_on, led_off, get_led_state, read_boot_button
 *
 * Onboard LED assumption: GPIO2 (the usual "blue LED" pin on most 38-pin
 * ESP32 DevKitC-style boards). BOOT button assumption: GPIO0. If your board
 * wires these differently, change LED_GPIO / BUTTON_GPIO below.
 *
 * NOTE ON TOOL ARGUMENTS: the esp-mcp-over-mqtt C SDK's mcp_tool_t /
 * property_t structs support tools with parameters, but the public docs
 * only show the zero-argument shape (property_count = 0, properties = NULL).
 * These 4 tools are deliberately argument-free so this file only relies on
 * the confirmed API. Check mcp_server.h in the component if you want to add
 * parameterized tools (e.g. set_led(state)).
 */

#include <string.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/event_groups.h"
#include "esp_wifi.h"
#include "esp_event.h"
#include "esp_log.h"
#include "esp_netif.h"
#include "nvs_flash.h"
#include "driver/gpio.h"

#include "mcp_server.h"

// ---- Configure these for your setup ----
#define WIFI_SSID       "Airtel_anja_9990"
#define WIFI_PASS       "air55904"
#define MQTT_BROKER_URI "mqtt://broker.emqx.io:1883"   // e.g. your own EMQX/Mosquitto, or mqtt://broker.emqx.io for quick testing
#define MQTT_CLIENT_ID  "esp32_devkit_001"
#define MQTT_USERNAME   ""   // leave empty if broker has no auth
#define MQTT_PASSWORD   ""

#define LED_GPIO    GPIO_NUM_2
#define BUTTON_GPIO GPIO_NUM_0

static const char *TAG = "esp32_mcp";
static EventGroupHandle_t s_wifi_event_group;
#define WIFI_CONNECTED_BIT BIT0

static bool s_led_state = false;

// ---------------- Wi-Fi ----------------

static void wifi_event_handler(void *arg, esp_event_base_t event_base,
                                int32_t event_id, void *event_data)
{
    if (event_base == WIFI_EVENT && event_id == WIFI_EVENT_STA_START) {
        esp_wifi_connect();
    } else if (event_base == WIFI_EVENT && event_id == WIFI_EVENT_STA_DISCONNECTED) {
        ESP_LOGW(TAG, "Wi-Fi disconnected, retrying...");
        esp_wifi_connect();
    } else if (event_base == IP_EVENT && event_id == IP_EVENT_STA_GOT_IP) {
        ip_event_got_ip_t *event = (ip_event_got_ip_t *) event_data;
        ESP_LOGI(TAG, "Got IP: " IPSTR, IP2STR(&event->ip_info.ip));
        xEventGroupSetBits(s_wifi_event_group, WIFI_CONNECTED_BIT);
    }
}

static void wifi_init_sta(void)
{
    s_wifi_event_group = xEventGroupCreate();

    ESP_ERROR_CHECK(esp_netif_init());
    ESP_ERROR_CHECK(esp_event_loop_create_default());
    esp_netif_create_default_wifi_sta();

    wifi_init_config_t cfg = WIFI_INIT_CONFIG_DEFAULT();
    ESP_ERROR_CHECK(esp_wifi_init(&cfg));

    ESP_ERROR_CHECK(esp_event_handler_register(WIFI_EVENT, ESP_EVENT_ANY_ID, &wifi_event_handler, NULL));
    ESP_ERROR_CHECK(esp_event_handler_register(IP_EVENT, IP_EVENT_STA_GOT_IP, &wifi_event_handler, NULL));

    wifi_config_t wifi_config = {
        .sta = {
            .ssid = WIFI_SSID,
            .password = WIFI_PASS,
        },
    };
    ESP_ERROR_CHECK(esp_wifi_set_mode(WIFI_MODE_STA));
    ESP_ERROR_CHECK(esp_wifi_set_config(WIFI_IF_STA, &wifi_config));
    ESP_ERROR_CHECK(esp_wifi_start());

    ESP_LOGI(TAG, "Connecting to Wi-Fi SSID: %s", WIFI_SSID);
    xEventGroupWaitBits(s_wifi_event_group, WIFI_CONNECTED_BIT, pdFALSE, pdTRUE, portMAX_DELAY);
}

// ---------------- GPIO ----------------

static void gpio_setup(void)
{
    gpio_reset_pin(LED_GPIO);
    gpio_set_direction(LED_GPIO, GPIO_MODE_OUTPUT);
    gpio_set_level(LED_GPIO, 0);

    gpio_reset_pin(BUTTON_GPIO);
    gpio_set_direction(BUTTON_GPIO, GPIO_MODE_INPUT);
    gpio_set_pull_mode(BUTTON_GPIO, GPIO_PULLUP_ONLY);
}

// ---------------- MCP tools ----------------

static const char *tool_led_on(int n_args, property_t *args)
{
    (void) n_args; (void) args;
    gpio_set_level(LED_GPIO, 1);
    s_led_state = true;
    return "{\"status\": \"ok\", \"led\": \"on\"}";
}

static const char *tool_led_off(int n_args, property_t *args)
{
    (void) n_args; (void) args;
    gpio_set_level(LED_GPIO, 0);
    s_led_state = false;
    return "{\"status\": \"ok\", \"led\": \"off\"}";
}

static const char *tool_get_led_state(int n_args, property_t *args)
{
    (void) n_args; (void) args;
    static char result[48];
    snprintf(result, sizeof(result), "{\"led\": \"%s\"}", s_led_state ? "on" : "off");
    return result;
}

static const char *tool_read_boot_button(int n_args, property_t *args)
{
    (void) n_args; (void) args;
    int level = gpio_get_level(BUTTON_GPIO);
    static char result[48];
    // BOOT button reads LOW (0) when pressed due to pull-up
    snprintf(result, sizeof(result), "{\"pressed\": %s}", level == 0 ? "true" : "false");
    return result;
}

static mcp_tool_t s_tools[] = {
    { .name = "led_on",          .description = "Turn the onboard LED on",              .property_count = 0, .properties = NULL, .call = tool_led_on },
    { .name = "led_off",         .description = "Turn the onboard LED off",             .property_count = 0, .properties = NULL, .call = tool_led_off },
    { .name = "get_led_state",   .description = "Get whether the onboard LED is on/off", .property_count = 0, .properties = NULL, .call = tool_get_led_state },
    { .name = "read_boot_button",.description = "Read whether the BOOT button is pressed", .property_count = 0, .properties = NULL, .call = tool_read_boot_button },
};

void app_main(void)
{
    ESP_ERROR_CHECK(nvs_flash_init());
    gpio_setup();
    wifi_init_sta();

    mcp_server_t *server = mcp_server_init(
        "esp32_devkit",                 // Server name
        "38-pin ESP32 devkit MCP server", // Description
        MQTT_BROKER_URI,
        MQTT_CLIENT_ID,
        MQTT_USERNAME,
        MQTT_PASSWORD,
        NULL                            // Certificate (optional, for TLS)
    );

    mcp_server_register_tool(server, sizeof(s_tools) / sizeof(s_tools[0]), s_tools);
    mcp_server_run(server);

    ESP_LOGI(TAG, "MCP server running, tools registered: led_on, led_off, get_led_state, read_boot_button");
}
