McQueen next-lab preparation bundle

This bundle contains only steps that are safe to prepare without the Jetson,
camera, servo/motor, or 4090 physically available.

Files:
- tools/preflight/laptop_lab_preflight.sh
- tools/preflight/jetson_repo_inspect.sh
- tools/preflight/gpu4090_preflight.sh
- tools/preflight/check_converter_contract.py
- docs/NEXT_LAB_RUNBOOK.md

The Jetson and 4090 scripts are intentionally inspection-only. They do not pull/reset
the Jetson repo, install packages, kill jobs, or start training.

Install into your repo:
  unzip -o ~/Downloads/mcqueen_next_lab_bundle.zip -d ~/McQueenWork/McQueen
