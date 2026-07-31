# setup

## hardware used

| part | current setup |
|---|---|
| controller | arduino uno q |
| motor driver | tb6612fng hw 166 |
| motor | 12 v brushed dc motor |
| steering | mg995 servo |
| camera | oak d pro ff |
| battery 1 | 3s 11.1 v 2200 mah lipo |
| battery 2 | 3s 11.1 v 3300 mah lipo |
| servo ubec | 5 v 3 a |
| camera ubec | 5 v 3 a |

battery 1 powers the uno q through vin the motor driver motor supply and the servo ubec

battery 2 powers the camera ubec

battery 1 uno q motor driver and servo grounds are common

## pins

| signal | uno q pin |
|---|---|
| tb6612 ain1 | d7 |
| tb6612 ain2 | d8 |
| tb6612 pwma | d9 |
| mg995 signal | d10 |

current steering calibration is 45 degrees left 80 degrees centre and 115 degrees right

## network

| item | value |
|---|---|
| car hotspot | kachow car |
| uno q address | 192.168.4.1 |
| laptop address | 192.168.4.2 |
| phone control udp | 5007 |
| control snapshot udp | 5008 |
| laptop logger http | 8080 |

## data flow

```text
phone -> uno q udp 5007 -> routerbridge -> mcu -> motor and servo
phone -> laptop http 8080 -> start and stop logging
uno q goal2 -> laptop http 8080 -> rgb depth detections and controls
```

## laptop logger

from the cloned repo run

```bash
cd laptop_logger
chmod +x install_laptop.sh
./install_laptop.sh
```

check it with

```bash
sudo systemctl status mcqueen-live-logger.service --no-pager
curl -s http://192.168.4.2:8080/status | python3 -m json.tool
```

## uno q teleop

copy `uno_q/teleop` to the uno q as `/home/arduino/McQueenUnoQTeleop`

on the uno q run

```bash
cd /home/arduino/McQueenUnoQTeleop
chmod +x scripts/*.sh
./scripts/install_and_compile.sh
./scripts/flash_mcu.sh
```

copy `uno_q/services` to the uno q then run

```bash
cd /path/to/services
chmod +x install_teleop_services.sh
./install_teleop_services.sh
```

check the services with

```bash
sudo systemctl status mcqueen-mcu.service --no-pager
sudo systemctl status mcqueen-teleop.service --no-pager
sudo journalctl -u mcqueen-teleop.service -n 30 --no-pager
```

## experimental goal 2

this part uses rgb stereo depth and yolo and is kept as experimental

it expects the laptop to use the static address `192.168.4.2`

it forces the oak d to usb 2 mode using `dai.UsbSpeed.HIGH` and rotates the camera streams by 180 degrees

copy `uno_q/vision/experimental` and `uno_q/services` to the uno q without changing their relative layout then run

```bash
cd /path/to/uno_q/vision/experimental
chmod +x install_goal2.sh
./install_goal2.sh
```

check it with

```bash
sudo systemctl status mcqueen-goal2.service --no-pager
sudo journalctl -u mcqueen-goal2.service -n 40 --no-pager
```

## android app

open `android/KachowV8` in android studio or build it from the terminal

```bash
cd android/KachowV8
cp local.properties.example local.properties
sed -i "s|/home/YOUR_USERNAME|$HOME|" local.properties
chmod +x gradlew
./gradlew assembleDebug
```

the debug apk is created at

```text
app/build/outputs/apk/debug/app-debug.apk
```
