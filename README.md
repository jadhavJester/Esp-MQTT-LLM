# ESP32 (38-pin) + MCP over MQTT + Ollama Cloud

Two pieces:
- `firmware/` — ESP-IDF project for the ESP32. Exposes 4 tools (`led_on`, `led_off`,
  `get_led_state`, `read_boot_button`) over MQTT using the [MCP over MQTT](https://docs.emqx.com/en/emqx/latest/emqx-ai/mcp-over-mqtt/overview.html) protocol.
- `agent/` — Python script for your PC. Connects to the same broker as an MCP client,
  discovers the ESP32's tools, and lets Ollama Cloud call them.

## 1. Firmware setup

1. Install ESP-IDF (v5.x) and confirm `idf.py` is on your PATH.
2. Get the MCP-over-MQTT component into your project:
   ```
   cd firmware
   mkdir -p components
   git clone https://github.com/mqtt-ai/esp-mcp-over-mqtt components/esp-mcp-over-mqtt
   ```
3. Edit `main/main.c`: set `WIFI_SSID`, `WIFI_PASS`, and `MQTT_BROKER_URI`
   (point it at your own EMQX/Mosquitto broker, or `mqtt://broker.emqx.io` for
   quick testing — that's a shared public broker, fine for experiments, not for
   anything you care about keeping private).
4. Build and flash (plain 38-pin devkit is the original Xtensa ESP32, target `esp32`):
   ```
   idf.py set-target esp32
   idf.py -p /dev/ttyUSB0 build flash monitor
   ```
   (swap `/dev/ttyUSB0` for your port — `COMx` on Windows)
5. Watch the monitor output for "MCP server running" — that means it registered
   its 4 tools with the broker.

## 2. Agent setup (run this from Antigravity's terminal, or any terminal)

```
pip install ollama "mcp[cli]" --break-system-packages
pip install "git+https://github.com/emqx/mcp-python-sdk@main" --break-system-packages

export OLLAMA_API_KEY=your_ollama_cloud_key   # from https://ollama.com/settings/keys
export MQTT_BROKER_HOST=broker.emqx.io        # same host as MQTT_BROKER_URI above (just the hostname, no scheme/port)

python agent/ollama_agent.py
```

Then type things like `turn the LED on` — Ollama Cloud decides to call the
`led_on` tool, the agent forwards that call over MQTT to the ESP32, and the
device executes it.

## Notes / things to double-check

- **Board target**: confirmed as a plain 38-pin ESP32 devkit (module silkscreen
  just says "ESP32") → `idf.py set-target esp32`. If it turns out to be an
  S3/C3 variant later, that target line is the only thing that changes.
- **LED/button pins**: assumed GPIO2 (LED) and GPIO0 (BOOT button), the common
  default on most 38-pin DevKitC-style boards. Adjust `LED_GPIO`/`BUTTON_GPIO`
  in `main.c` if your board differs.
- **Tool parameters**: the 4 firmware tools are intentionally zero-argument —
  that's the only tool shape confirmed in EMQX's public docs for the C SDK. If
  you want parameterized tools (e.g. `set_pwm(duty)`), check the `property_t`
  struct in the component's `mcp_server.h` after cloning it.
- **Security**: this setup has no MQTT auth/TLS configured by default. Fine for
  a bench project; for anything reachable from the internet, set a broker
  username/password (or client cert) and fill in `MQTT_USERNAME`/`MQTT_PASSWORD`
  in `main.c`.
