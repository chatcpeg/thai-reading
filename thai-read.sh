#!/usr/bin/env sh
# thai-read.sh - same arguments as thai_read.py, for macOS / Linux / Git Bash.
#   ./thai-read.sh --text "..." [--json]   |   ./thai-read.sh file.txt   |   ./thai-read.sh  (menu)
# Uses $PYTHON if set, else the first of python3 / python / py that really runs.
HERE="$(cd "$(dirname "$0")" && pwd)"
PY="${PYTHON:-}"
if [ -z "$PY" ]; then
  for c in python3 python py; do
    if "$c" -c 'import sys; assert sys.version_info >= (3, 8)' >/dev/null 2>&1; then PY="$c"; break; fi
  done
fi
if [ -z "$PY" ]; then echo "Python 3.8+ not found (set PYTHON=/path/to/python)" >&2; exit 127; fi
PYTHONUTF8=1 exec "$PY" "$HERE/thai_read.py" "$@"
