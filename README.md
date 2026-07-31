# McQueen

Build a vision only Full Self Driving RC car, by training a neural network on Human Demonstrations and a World Model, then distilling it onto an onboard edge computer for autonomous control.

## Current setup

an android phone sends steering and throttle commands to an arduino uno q over wifi

the uno q controls a 12 v brushed dc motor through a tb6612fng driver and an mg995 steering servo

the car starts its mcu and teleop services automatically

an oak d pro was integrated for rgb capture and dataset logging

stereo depth and yolo were also tested as an experimental goal 2 pipeline

an earlier esp32 controller is preserved in the repo as well

| folder | what's inside |
|---|---|
| `android` | kachow v8 phone controller |
| `uno_q` | current teleop code automatic services and experimental vision code |
| `laptop_logger` | laptop service that creates kachow dataset sessions |
| `esp32` | earlier esp32 controlled version |
| `oakd` | earlier oak d scripts |
| `cad` | camera mount servo horn and servo mount files |
| `dataset_logging` | controls csv files  |
| `docs` | setup and wiring notes |

## Control pins

| function | pin |
|---|---|
| motor ain1 | d7 |
| motor ain2 | d8 |
| motor pwm | d9 |
| servo signal | d10 |

## Contributors

Kartik Tagore  `@kt-fr`

Medhansh Abhilash  `@medhansh2808`

## Setup

see [`docs/setup.md`](docs/setup.md)

## Android apk

a ready to install debug apk is available under github releases
