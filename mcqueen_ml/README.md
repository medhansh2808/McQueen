# mcqueen_ml — dataset, training and deployment safety

Python package for the McQueen ML pipeline.

## Layout

- [dataset/](dataset/) — dataset schema and episode handling
- [training/](training/) — training entry points (e.g. `train_temporal_v2.py`)
- [deployment/](deployment/) — safety checks applied at inference time

## Related

- Trained artifacts and the action head: [models](../models)
- Realtime policy worker that consumes them: [realtime/rtx/policy_worker.py](../realtime/rtx/policy_worker.py)
- Full system overview: [docs/architecture.md](../docs/architecture.md)