#!/bin/zsh
set -euo pipefail

cd "$(dirname "$0")"

if [ ! -d ".venv" ]; then
  python3 -m venv .venv
fi

source .venv/bin/activate
pip install -r requirements.txt

if [ -f ".env.worker.local" ]; then
  set -a
  source ".env.worker.local"
  set +a
fi

python -m clipper_pipeline.hybrid_worker
