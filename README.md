# esp32-s3 based shift light

BOM:
* Waveshare ESP32-S3-Zero
* 24 X WS2812B 5050 Neopixel-compatible LED ring
* SSD1306 128x64 oled module

## Game-specific configuration:

### Dirt Rally 2.0

Find the input configuration file, probably in
`C:\Users\%USERPROFILE%\Documents\My Games\DiRT Rally 2.0\hardwaresettings\hardware_settings_config.xml`

Find the stanza with a UDP port preconfigured to `127.0.0.1` and change it to the broadcast address for your computer's subnet.

For my example:

```
<udp enabled="true" extradata="3" ip="192.168.1.255" port="20777" delay="1" />
```

### EA WRC

Find the telemetry config file, probably in

`C:\Users\%USERPROFILE%\Documents\My Games\WRC\telemetry\config.json`

Like in DR2 above, change the configuration for wrc packets to your computer's subnet broadcast address. The following is my example:

```
      {
        "structure": "wrc",
        "packet": "session_update",
        "ip": "192.168.1.255",
        "port": 20777,
        "frequencyHz": 60,
        "bEnabled": true
      },
```
