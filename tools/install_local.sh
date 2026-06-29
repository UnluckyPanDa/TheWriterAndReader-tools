#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

python3 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python scripts/novel.py doctor

cat <<'MSG'

Next steps:
1. Activate the environment: . .venv/bin/activate
2. Create a story: python scripts/novel.py init-story --story my_story
3. Build context: python scripts/novel.py build-context --story my_story --chapter 1
4. Review locally: python scripts/novel.py review --story my_story --chapter 1
MSG
