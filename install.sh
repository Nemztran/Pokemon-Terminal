#!/usr/bin/env bash
set -euo pipefail
project_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
if ! command -v python3 >/dev/null 2>&1; then
    echo 'Python 3.9+ is required. See README.md.' >&2
    exit 1
fi
exec python3 "$project_dir/install.py" "$@"
