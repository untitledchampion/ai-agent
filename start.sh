#!/bin/bash
cd "$(dirname "$0")"

# Load .env into current shell
export $(grep -v '^#' .env | xargs)

# Ensure PATH includes pip-installed packages
export PATH="$HOME/Library/Python/3.9/bin:$PATH"

exec python3 -m uvicorn agent.main:app --host 0.0.0.0 --port 8000 "$@"
