// Test sketch for examples/usb_serial_test.py.
// USB-Serial commands: "on" / "off" control the LED, anything else is echoed back.
// Sends "uptime N" once per second.
//
// ESP32-C3 (native USB): Tools -> USB CDC On Boot -> Enabled.
// STM32 (STM32duino): Tools -> USB support -> CDC (generic 'Serial' supersede U(S)ART).
// Arduino Uno (original or CH340 clone): no settings needed.

#ifndef LED_BUILTIN
#define LED_BUILTIN 8   // ESP32-C3 SuperMini; change for your board
#endif

void setup() {
  Serial.begin(115200);
  pinMode(LED_BUILTIN, OUTPUT);
}

void loop() {
  if (Serial.available()) {
    String cmd = Serial.readStringUntil('\n');
    cmd.trim();
    if (cmd == "on") {
      digitalWrite(LED_BUILTIN, HIGH);
      Serial.println("LED is ON");
    } else if (cmd == "off") {
      digitalWrite(LED_BUILTIN, LOW);
      Serial.println("LED is OFF");
    } else if (cmd.length() > 0) {
      Serial.print("echo: ");
      Serial.println(cmd);
    }
  }

  static unsigned long last = 0;
  if (millis() - last >= 1000) {
    last = millis();
    Serial.print("uptime ");
    Serial.println(last / 1000);
  }
}
