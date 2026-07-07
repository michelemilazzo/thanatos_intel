#!/usr/bin/env bash
#
# Ricostruisce il bundle offline della recovery machine.
# Va eseguito su una macchina ONLINE con lo STESSO target della recovery machine
# (default: Linux x86_64, Python 3.12). Produce un tar.gz self-contained.
#
# Uso:
#   ./build-bundle.sh [output_dir]
#
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUT="${1:-/tmp/rbuild}"
BTCR_REPO="https://github.com/3rdIteration/btcrecover.git"
STAMP="$(date +%Y%m%d)"
BUNDLE="$OUT/thanatos-recovery-bundle"

echo "== Build recovery bundle =="
rm -rf "$BUNDLE" "$OUT/buildenv"
mkdir -p "$BUNDLE/wheelhouse"

# 1) btcrecover (source, senza .git)
git clone --depth 1 "$BTCR_REPO" "$BUNDLE/btcrecover"
rm -rf "$BUNDLE/btcrecover/.git"

# 2) CLI + script operatore (dallo stesso modulo)
cp "$HERE/../api/thanatos_recovery_cli.py" "$BUNDLE/thanatos-recovery-cli"
cp "$HERE/install-offline.sh" "$HERE/selftest.sh" "$HERE/selftest.py" "$HERE/RUNBOOK.md" "$BUNDLE/"
chmod +x "$BUNDLE/install-offline.sh" "$BUNDLE/selftest.sh" "$BUNDLE/thanatos-recovery-cli"

# 3) wheelhouse (tutti binari; crcmod -> wheel per evitare compilazione offline)
python3 -m venv "$OUT/buildenv"
"$OUT/buildenv/bin/pip" install -q --upgrade pip wheel
"$OUT/buildenv/bin/pip" download -q -d "$BUNDLE/wheelhouse" \
  -r "$BUNDLE/btcrecover/requirements.txt" cryptography bip_utils
if ls "$BUNDLE/wheelhouse"/*.tar.gz >/dev/null 2>&1; then
  for s in "$BUNDLE/wheelhouse"/*.tar.gz; do
    "$OUT/buildenv/bin/pip" wheel -q "$s" -w "$BUNDLE/wheelhouse" && rm -f "$s"
  done
fi
rm -rf "$OUT/buildenv"
find "$BUNDLE" -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true

# 4) tarball + checksum
TAR="$OUT/thanatos-recovery-bundle-linux-x86_64-py312-$STAMP.tar.gz"
tar -C "$OUT" -czf "$TAR" thanatos-recovery-bundle
( cd "$OUT" && sha256sum "$(basename "$TAR")" > "$(basename "$TAR").sha256" )
echo "OK -> $TAR"
cat "$TAR.sha256"
