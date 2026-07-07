#!/usr/bin/env bash
#
# Thanatos Recovery — installer OFFLINE della recovery machine.
# NON richiede internet: installa tutto dai wheel inclusi nel bundle.
#
# Uso (sulla macchina air-gapped):
#   ./install-offline.sh
#
# Target: Linux x86_64, Python 3.12 (i wheel sono per questo target).
# Per altri target vedi RUNBOOK.md -> "Rigenerare i wheel".

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV="$HERE/venv"

echo "== Thanatos Recovery — install offline =="

# 1) verifica python
if ! command -v python3 >/dev/null 2>&1; then
  echo "ERRORE: python3 non trovato. Installa Python 3.12 (offline: da .deb su USB)." >&2
  exit 1
fi
PYV="$(python3 -c 'import sys;print("%d.%d"%sys.version_info[:2])')"
echo "python3 rilevato: $PYV"
if [ "$PYV" != "3.12" ]; then
  echo "ATTENZIONE: i wheel sono per Python 3.12 (trovato $PYV)." >&2
  echo "Se l'install fallisce, rigenera i wheel (vedi RUNBOOK.md)." >&2
fi

# 2) crea venv (venv include pip via ensurepip, offline)
echo "-> creo virtualenv"
python3 -m venv "$VENV"

# 3) installa TUTTO dai wheel locali, senza rete
echo "-> installo i pacchetti dal wheelhouse (offline, no-index)"
"$VENV/bin/pip" install --no-index --find-links "$HERE/wheelhouse" --only-binary=:all: \
  -r "$HERE/btcrecover/requirements.txt" cryptography bip_utils >/dev/null

# 4) smoke test import
echo "-> verifico gli import"
"$VENV/bin/python" - <<'PY'
import cryptography, coincurve, bip_utils  # noqa
import importlib.util, os
p = os.path.join(os.path.dirname(__file__) if "__file__" in dir() else ".", "")
print("  cryptography", cryptography.__version__)
print("  OK: dipendenze importate")
PY

echo ""
echo "== Install completato =="
echo "Ora esegui il self-test (prova un recupero noto, offline):"
echo "   ./selftest.sh"
echo ""
echo "Per un recupero reale usa:"
echo "   THANATOS_BTCRECOVER_DIR=$HERE/btcrecover \\"
echo "   $VENV/bin/python $HERE/thanatos-recovery-cli --help"
