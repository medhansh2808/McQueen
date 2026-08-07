# McQueen — Jetson Nano

Jetson Nano 2GB edge controller for McQueen.

Responsibilities:
- OAK-D RGB capture
- Android/phone control API
- Direct GPIO/PWM control of TB6612FNG and MG995
- Safety watchdog and E-stop handling
- Wi-Fi communication with the RTX inference/training PC

The Jetson does not perform model training.
Model training, LeRobot dataset handling, W&B logging, and initial inference run on the RTX PC.
