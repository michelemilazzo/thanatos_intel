#!/usr/bin/env bash
# Manutenzione pianificata Thanatos (prod bench-cli, host 167.233.35.84).
#
# Copertura a due livelli:
#  - nginx error_page 502/503/504 -> /var/www/maintenance/__maint_thanatos.html
#    Copre AUTOMATICAMENTE la finestra di restart di gunicorn (deploy normale):
#    nessun comando da lanciare, il pubblico vede la pagina brand invece del 502.
#  - Frappe maintenance_mode (questo script): per manutenzioni PIANIFICATE piu'
#    lunghe (migrate, operazioni DB) in cui vogliamo rifiutare attivamente il
#    traffico. Frappe risponde 503 -> nginx lo dipinge con la stessa pagina.
#
# Uso (sul server, come root):
#   ./maintenance.sh on    # attiva, il sito mostra la pagina di manutenzione
#   ./maintenance.sh off   # disattiva, torna live
#   ./maintenance.sh status

set -euo pipefail
BENCH=thanatos
SITE=thanatos.onekeyco.com
BIN=/home/frappe/bench-cli/bench

case "${1:-}" in
  on)
    sudo -u frappe "$BIN" -b "$BENCH" --site "$SITE" set-maintenance-mode on
    echo "Manutenzione ATTIVA su $SITE"
    ;;
  off)
    sudo -u frappe "$BIN" -b "$BENCH" --site "$SITE" set-maintenance-mode off
    echo "Manutenzione DISATTIVATA su $SITE"
    ;;
  status)
    grep -o '"maintenance_mode":[^,}]*' \
      "/home/frappe/bench-cli/benches/$BENCH/sites/$SITE/site_config.json" 2>/dev/null \
      || echo '"maintenance_mode": 0 (default)'
    ;;
  *)
    echo "uso: $0 {on|off|status}" >&2
    exit 1
    ;;
esac
