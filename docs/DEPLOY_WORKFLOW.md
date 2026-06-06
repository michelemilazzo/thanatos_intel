# Thanatos — Workflow dev → staging → prod

## Ambienti

| Ambiente | URL | Bench | Scopo |
|---|---|---|---|
| **Staging** | dev-thanatos.onekeyco.com | bench-0008 (Press) | Test prima di prod |
| **Produzione** | thanatos.onekeyco.com / www.thanatos.agency | bench-0008 (Press) | Live |

> Vincolo dominio: solo label singola sotto `onekeyco.com` (wildcard `*.onekeyco.com` già nel cert). NO terzo livello tipo `dev.thanatos.agency`.

## Branch Git

- **`dev`** → sviluppo. Push qui NON tocca produzione.
- **`main`** → produzione. Il deploy parte da qui.

## Ciclo completo

```
1. SVILUPPO        git checkout dev → modifiche → commit → git push origin dev
2. TEST            (le modifiche vanno testate; vedi nota sotto)
3. PROMOZIONE      merge dev → main → git push origin main
4. BUILD+DEPLOY    sudo -u frappe bash -c 'cd /home/frappe/mmos-press && \
                     env/bin/python /home/frappe/deploy_thanatos.py'
                   → crea release, build su f1, attende, create_deploy, bench
5. CANARY          migra PRIMA dev-thanatos al nuovo bench → verifica
6. PROMOTE PROD    se OK, migra thanatos.onekeyco.com allo stesso bench
```

## Perché NON push-to-deploy automatico globale

Press `is_push_to_deploy_enabled` monitora **tutte** le 14 app del Release Group,
incluse `frappe`/`erpnext`/`crm`/`drive`/`builder` su branch upstream attivi
(`version-16`, `develop`). Abilitarlo farebbe auto-deployare in prod anche i
commit upstream di terzi → instabilità non controllata.

Per questo si usa **`deploy_thanatos.py`**: aggiorna SOLO `thanatos_intel`,
le altre 13 app restano pinnate all'hash corrente.

## `deploy_thanatos.py` — cosa fa

Incapsula l'intero ciclo (prima manuale, ripetuto ~5 volte):
1. App Release dall'ultimo commit di thanatos_intel (branch main)
2. Deploy Candidate (altre app pinnate)
3. Build su f1 + attesa completamento (timeout 30min)
4. Sync Agent Job (callback Press spesso perso) + create_deploy
5. create_benches + process_bench_queue
6. Stampa il bench pronto → il `move_to_bench` del sito di prod resta MANUALE
   (unico passo che tocca il traffico live, richiede conferma)

## Migrazione sito a nuovo bench (passo 5-6)

```python
site = frappe.get_doc("Site", "<sito>")
site.move_to_bench("<nuovo-bench>", deactivate=False, skip_failing_patches=False)
# dopo FS_MOVED, sincronizzare il Press DB:
frappe.db.set_value("Site", "<sito>", "bench", "<nuovo-bench>")
frappe.db.set_value("Site", "<sito>", "status", "Active")
# clear cache nel container:
#   bench --site <sito> clear-website-cache && clear-cache
```

## Nota su "test live in secondi"

Lo staging Press riceve il deploy come prod (immagine immutabile), quindi NON
permette `git pull + reload` istantaneo. Serve come **canary**: deploy su
dev-thanatos prima di prod per intercettare regressioni.

Per iterazione UI/CSS rapidissima (secondi), in futuro: dev bench in
`developer_mode=1` con il codice bind-mounted (setup separato, non-Press).

## Gestione disco durante build (lezione appresa)

f1 può saturare durante il build (export image ~6GB). Prima di ogni build:
```bash
docker builder prune -a -f   # solo a build fermo
```
Le vecchie image bench su f1 sono ridondanti (già su ghcr, runtime altrove) e
si possono rimuovere — tranne quella della live corrente.
