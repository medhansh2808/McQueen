# models — action head and frozen-trunk adapters

Models and ONNX tooling for McQueen.

| File | Purpose |
|---|---|
| [action_adapter.py](action_adapter.py) | Action head + frozen-trunk adapter |
| [train_frozen_action.py](train_frozen_action.py) | Training entry point for the frozen-trunk head |
| [train_chestnut_lora.py](train_chestnut_lora.py) | LoRA fine-tuning of the chestnut trunk |
| [chestnut_pilot.py](chestnut_pilot.py) | Chestnut pilot wrapper |
| [convert_chestnut.py](convert_chestnut.py) | ONNX export for the chestnut pilot |
| [dump_chestnut_slices.py](dump_chestnut_slices.py) | ONNX I/O inspection |
| [dump_onnx_io.py](dump_onnx_io.py) | ONNX input/output dump |
| [eval_donkey_predictions.py](eval_donkey_predictions.py) | Evaluate donkey-format predictions |
| [bench_chestnut.py](bench_chestnut.py) | Latency benchmarks |
| [smoke_frozen_action.py](smoke_frozen_action.py) | Smoke test for the frozen action head |

## Related

- Datasets and training code: [mcqueen_ml](../mcqueen_ml)
- Inference at runtime: [realtime/rtx/policy_worker.py](../realtime/rtx/policy_worker.py)
- Model architecture details: [docs/architecture.md](../docs/architecture.md)