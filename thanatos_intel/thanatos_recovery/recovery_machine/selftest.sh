#!/usr/bin/env bash
# Self-test offline: prova un recupero noto per certificare la macchina.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ ! -x "$HERE/venv/bin/python" ]; then
  echo "ERRORE: esegui prima ./install-offline.sh" >&2
  exit 1
fi
exec "$HERE/venv/bin/python" "$HERE/selftest.py"
