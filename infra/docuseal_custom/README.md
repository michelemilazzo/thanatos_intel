# Thanatos DocuSeal Custom Build

Fork build di [docusealco/docuseal](https://github.com/docusealco/docuseal)
con la validazione "firma troppo piccola o semplice" rilassata.

## Cosa cambia

Solo `app/javascript/submission_form/validate_signature.js`:

```diff
-    if (avgDeviation < 3 && skippedStraightLine < 2) {
+    if (avgDeviation < 0.05 && skippedStraightLine < 99) {
```

Effetto: il validatore accetta qualunque tratto disegnato sul canvas,
anche segni semplici (un trattino, una croce, un puntino con sotto-
lineatura). Si toglie il blocco UX che impediva la firma di chi non
fa svolazzi calligrafici.

## Build

```bash
ssh root@ai-mmos-core
cd /opt/thanatos-build
git clone https://github.com/docusealco/docuseal.git
cd docuseal
sed -i 's|avgDeviation < 3 && skippedStraightLine < 2|avgDeviation < 0.05 \&\& skippedStraightLine < 99|g' app/javascript/submission_form/validate_signature.js
docker build -t thanatos/docuseal:custom .
```

Il bundle webpack rigenerato (`form-*.js`) contiene la patch e si
propaga automaticamente a draw.js + signature_step.vue che la importano.

## Deploy

`infra/docker-compose.opensource.yml` punta a `thanatos/docuseal:custom`.

```bash
cd /opt/thanatos-oss
docker compose up -d --force-recreate docuseal
docker exec -u root thanatos-docuseal sh -c "chmod 777 /data/docuseal"  # Redis perms
```

Il volume `docuseal_data` è preservato (DB SQLite + attachments + cert).

## Rollback

```bash
sed -i 's|thanatos/docuseal:custom|docuseal/docuseal:latest|' /opt/thanatos-oss/docker-compose.yml
cd /opt/thanatos-oss && docker compose up -d docuseal
```
