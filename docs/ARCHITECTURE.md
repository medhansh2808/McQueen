# McQueen architecture

## UNO Q

The UNO Q is responsible for:

- phone command reception,
- motor and steering control,
- OAK-D RGB/depth capture,
- lightweight episode recording,
- autonomous inference.

Its authoritative source is under `robot/uno_q/`.

## Laptop

The Ubuntu laptop is responsible for:

- syncing recorded episodes,
- validating the recording spool,
- converting recordings into LeRobotDataset v3,
- visualizing and reviewing datasets,
- training models,
- W&B experiment tracking,
- exporting models for the UNO Q.

## Dataset flow

1. Phone LOG starts/stops an episode.
2. UNO Q saves RGB, raw uint16 depth, actions and timestamps.
3. Laptop syncs the episode.
4. Validator checks synchronization and files.
5. Converter creates LeRobotDataset v3.
6. Training reads the LeRobot dataset.
7. W&B records configuration, metrics and checkpoints.
