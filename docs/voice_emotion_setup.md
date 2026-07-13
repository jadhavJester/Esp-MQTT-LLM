# Curiosity Robot: Voice & Emotion Setup Guide

This guide details the hardware connections, firmware logic, and browser-based voice integration (TTS/STT) required to give the curious learning robot a face (OLED eyes), a voice (browser speech/speaker beeps), and the ability to converse with you.

---

## 1. System Architecture

```
  ┌─────────────────────────────────────────────────────────────┐
  │                        USER'S PHONE                         │
  │                      (Web Dashboard)                        │
  │                                                             │
  │   🎙️ Speak (STT) ───[Web Speech API]───> Text (via MQTT)    │
  │   🔊 Listen (TTS) <───[Speech Synthesis]─── Robot Questions  │
  └───────────────────────────▲─────────────────────────────────┘
                              │ MQTT
                              ▼
  ┌─────────────────────────────────────────────────────────────┐
  │                       VERCEL CLOUD                          │
  │                     (Cognitive Brain)                       │
  │                                                             │
  │   - Receives voice input and sensory logs.                  │
  │   - Queries Ollama Cloud to generate next goal.             │
  │   - Decides robot emotions/sound and publishes actions.      │
  └───────────────────────────▲─────────────────────────────────┘
                              │ MQTT
                              ▼
  ┌─────────────────────────────────────────────────────────────┐
  │                       PHYSICAL ROBOT                        │
  │                        (ESP32 Dev)                          │
  │                                                             │
  │   - SSD1306 OLED Screen  ─── Displays active eyes           │
  │   - MAX98357A + Speaker ─── Plays physical sound effects   │
  └─────────────────────────────────────────────────────────────┘
```

---

## 2. Hardware Connections & Pinout

Below is the recommended wiring diagram for connecting the display and audio module to a standard ESP32 DevKit:

| Component | ESP32 Pin | Description |
| :--- | :--- | :--- |
| **SSD1306 OLED** | | **I2C Interface** |
| VCC | 3.3V | Power supply |
| GND | GND | Ground |
| SCL | GPIO 22 | Serial Clock |
| SDA | GPIO 21 | Serial Data |
| **MAX98357A DAC** | | **I2S Interface** |
| VIN | 5V | Power supply |
| GND | GND | Ground |
| LRC (WS) | GPIO 25 | Left/Right Clock (Word Select) |
| BCLK (SCK) | GPIO 26 | Bit Clock |
| DIN (SD) | GPIO 27 | Serial Data Input |

---

## 3. OLED Emotion Display (Firmware Addition)

Using the standard ESP-IDF `ssd1306` driver or Arduino's `Adafruit_SSD1306` library, the ESP32 can render pixel expressions for the robot's eyes:

```c
// Example: Drawing expressions on the OLED screen
void draw_expression(const char* emotion) {
    display.clearDisplay();
    
    if (strcmp(emotion, "happy") == 0) {
        // Draw arched/curved happy eyes (^^)
        display.drawCircle(32, 32, 10, WHITE);
        display.drawCircle(96, 32, 10, WHITE);
    } 
    else if (strcmp(emotion, "hurt") == 0) {
        // Draw "X X" squinting eyes representing pain
        display.drawLine(20, 20, 44, 44, WHITE);
        display.drawLine(44, 20, 20, 44, WHITE);
        display.drawLine(84, 20, 108, 44, WHITE);
        display.drawLine(108, 20, 84, 44, WHITE);
    } 
    else if (strcmp(emotion, "curious") == 0) {
        // Draw round eyes shifted upwards looking around
        display.fillCircle(32, 20, 12, WHITE);
        display.fillCircle(96, 20, 12, WHITE);
    } 
    else { // "normal"
        // Draw centered round eyes with pupil reflections
        display.fillCircle(32, 32, 12, WHITE);
        display.fillCircle(96, 32, 12, WHITE);
    }
    
    display.display();
}
```

---

## 4. Web Dashboard Voice Interface (TTS/STT)

To make the robot speak and listen using your smartphone, paste these code updates into your web interface:

### Text-To-Speech (Robot Speaks to User)
When Vercel identifies an unknown object, it publishes a voice request packet to `$mcp-event/robot_1/speak`. The dashboard captures this and reads the string aloud:

```javascript
// Speaks a text input out loud in a child-like robot pitch
function speakRobotText(message) {
    if ('speechSynthesis' in window) {
        window.speechSynthesis.cancel(); // Cancel any ongoing speech
        let utterance = new SpeechSynthesisUtterance(message);
        utterance.pitch = 1.6; // High pitch for a child-like robot feel
        utterance.rate = 1.0;  // Normal speed
        window.speechSynthesis.speak(utterance);
    }
}
```

### Speech-To-Text (User Teaches Robot)
When the robot is waiting for user input, a voice recorder is unlocked on the dashboard:

```javascript
let recognition;
if ('webkitSpeechRecognition' in window) {
    recognition = new webkitSpeechRecognition();
    recognition.continuous = false;
    recognition.lang = 'en-US';

    recognition.onresult = function(event) {
        let transcript = event.results[0][0].transcript;
        console.log("Speech recognized: " + transcript);
        
        // Publish your explanation to the Vercel brain via MQTT
        mqttClient.publish("$mcp-response/robot_1/voice_answer", JSON.stringify({
            text: transcript
        }));
    };

    recognition.onerror = function(e) {
        console.error("Speech recognition error: ", e);
    };
}

function startListening() {
    if (recognition) {
        recognition.start();
        console.log("Listening for voice...");
    }
}
```
