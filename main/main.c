/*
 * ESP32 (38-pin devkit) firmware:
 *  - Connects to Wi-Fi
 *  - Starts an MCP-over-MQTT server (EMQX esp-mcp-over-mqtt C SDK)
 *  - Exposes 6 tools: led_on, led_off, get_led_state, read_boot_button,
 *    set_servo_angle, get_servo_angle
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
#define MQTT_BROKER_URI "mqtt://broker.emqx.io:1883"
#define MQTT_CLIENT_ID  "esp32_devkit_001"
#define MQTT_USERNAME   ""
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

// No servo tools needed

static const char *tool_set_gpio_mode(int n_args, property_t *args)
{
    if (n_args < 2) {
        return "{\"error\": \"pin and mode arguments are required\"}";
    }
    int pin = (int)args[0].value.integer_value;
    const char *mode = args[1].value.string_value;

    if (pin < 0 || pin > 39) {
        return "{\"error\": \"GPIO pin must be between 0 and 39\"}";
    }

    gpio_config_t io_conf = {};
    io_conf.pin_bit_mask = (1ULL << pin);

    if (strcmp(mode, "output") == 0) {
        io_conf.mode = GPIO_MODE_OUTPUT;
        io_conf.pull_up_en = GPIO_PULLUP_DISABLE;
        io_conf.pull_down_en = GPIO_PULLDOWN_DISABLE;
    } else if (strcmp(mode, "input") == 0) {
        io_conf.mode = GPIO_MODE_INPUT;
        io_conf.pull_up_en = GPIO_PULLUP_DISABLE;
        io_conf.pull_down_en = GPIO_PULLDOWN_DISABLE;
    } else if (strcmp(mode, "input_pullup") == 0) {
        io_conf.mode = GPIO_MODE_INPUT;
        io_conf.pull_up_en = GPIO_PULLUP_ENABLE;
        io_conf.pull_down_en = GPIO_PULLDOWN_DISABLE;
    } else {
        return "{\"error\": \"mode must be 'output', 'input', or 'input_pullup'\"}";
    }

    esp_err_t err = gpio_config(&io_conf);
    static char result[80];
    if (err == ESP_OK) {
        snprintf(result, sizeof(result), "{\"status\": \"ok\", \"pin\": %d, \"mode\": \"%s\"}", pin, mode);
    } else {
        snprintf(result, sizeof(result), "{\"error\": \"failed to configure pin %d\"}", pin);
    }
    return result;
}

static const char *tool_write_gpio(int n_args, property_t *args)
{
    if (n_args < 2) {
        return "{\"error\": \"pin and level arguments are required\"}";
    }
    int pin = (int)args[0].value.integer_value;
    int level = (int)args[1].value.integer_value;

    if (pin < 0 || pin > 39) {
        return "{\"error\": \"GPIO pin must be between 0 and 39\"}";
    }
    if (level != 0 && level != 1) {
        return "{\"error\": \"level must be 0 or 1\"}";
    }

    esp_err_t err = gpio_set_level(pin, level);
    static char result[64];
    if (err == ESP_OK) {
        snprintf(result, sizeof(result), "{\"status\": \"ok\", \"pin\": %d, \"level\": %d}", pin, level);
    } else {
        snprintf(result, sizeof(result), "{\"error\": \"failed to write to pin %d\"}", pin);
    }
    return result;
}

static const char *tool_read_gpio(int n_args, property_t *args)
{
    if (n_args < 1) {
        return "{\"error\": \"pin argument is required\"}";
    }
    int pin = (int)args[0].value.integer_value;

    if (pin < 0 || pin > 39) {
        return "{\"error\": \"GPIO pin must be between 0 and 39\"}";
    }

    int level = gpio_get_level(pin);
    static char result[48];
    snprintf(result, sizeof(result), "{\"pin\": %d, \"level\": %d}", pin, level);
    return result;
}

static mcp_tool_t s_tools[] = {
    { .name = "led_on",          .description = "Turn the onboard LED on",              .property_count = 0, .properties = NULL, .call = tool_led_on },
    { .name = "led_off",         .description = "Turn the onboard LED off",             .property_count = 0, .properties = NULL, .call = tool_led_off },
    { .name = "get_led_state",   .description = "Get whether the onboard LED is on/off", .property_count = 0, .properties = NULL, .call = tool_get_led_state },
    { .name = "read_boot_button",.description = "Read whether the BOOT button is pressed", .property_count = 0, .properties = NULL, .call = tool_read_boot_button },
    { .name           = "set_gpio_mode",
      .description    = "Set GPIO pin mode (0 to 39) to 'output', 'input', or 'input_pullup'",
      .property_count = 2,
      .properties =
          (property_t[]) {
              { .name                = "pin",
                .description         = "GPIO pin number (0 to 39)",
                .type                = PROPERTY_INTEGER,
                .value.integer_value = 2 },
              { .name                = "mode",
                .description         = "Pin mode ('output', 'input', 'input_pullup')",
                .type                = PROPERTY_STRING,
                .value.string_value  = "output" },
          },
      .call = tool_set_gpio_mode },
    { .name           = "write_gpio",
      .description    = "Write digital level (0 or 1) to a GPIO pin (0 to 39)",
      .property_count = 2,
      .properties =
          (property_t[]) {
              { .name                = "pin",
                .description         = "GPIO pin number (0 to 39)",
                .type                = PROPERTY_INTEGER,
                .value.integer_value = 2 },
              { .name                = "level",
                .description         = "Digital output level (0 or 1)",
                .type                = PROPERTY_INTEGER,
                .value.integer_value = 0 },
          },
      .call = tool_write_gpio },
    { .name           = "read_gpio",
      .description    = "Read digital level (0 or 1) of a GPIO pin (0 to 39)",
      .property_count = 1,
      .properties =
          (property_t[]) {
              { .name                = "pin",
                .description         = "GPIO pin number (0 to 39)",
                .type                = PROPERTY_INTEGER,
                .value.integer_value = 0 },
          },
      .call = tool_read_gpio },
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

    ESP_LOGI(TAG, "MCP server running with full GPIO tools registered");
}
