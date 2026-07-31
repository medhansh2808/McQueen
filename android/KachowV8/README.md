# Kachow Android V8

Final dual-control phone controller.

## Modes

### Joystick
- Independent X/Y axes
- Full top-right = full forward + full right
- Full bottom-right = full reverse + full right
- Proportional throttle
- Mild exponential, speed-sensitive steering

### RC Sliders
- Left vertical spring-return throttle
- Right horizontal spring-return steering
- True multi-touch

## Safety
- Mode switching only while disarmed
- 200 ms direction-neutral guard
- Command ramp through zero before reversing
- Brake keeps steering active and forces throttle to zero
- Existing ESP32 failsafe remains authoritative

## Dataset
The app sends the exact final commands to the laptop logger on UDP 5008 and controls recording via HTTP 8080.
