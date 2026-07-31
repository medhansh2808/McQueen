# dataset logging

this folder contains the useful controls csv files from selected test sessions

camera frames are not included in the repo

some rows still contain the original relative paths for rgb depth and detection files because those files existed in the full local sessions

older sessions use this format

```text
timestamp,motor_pwm_sent,servo_angle_sent,camera_frame
```

newer goal 2 sessions use this format

```text
timestamp,motor_pwm_sent,servo_angle_sent,rgb_frame,depth_frame,detections_file
```
