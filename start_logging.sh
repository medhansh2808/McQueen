#!/usr/bin/env bash
set -euo pipefail
curl -fsS -X POST http://127.0.0.1:8080/logging/start | jq .
