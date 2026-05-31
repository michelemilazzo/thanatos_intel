# Thanatos Intel

Romanian-law-first intelligence, due diligence, recovery and client-portal platform for Frappe/ERPNext.

## Canonical spec

The master specification now lives in [`MASTER_SPECIFICATION.md`](./MASTER_SPECIFICATION.md).

Use that file as the source of truth for:

- single-app architecture
- Romanian legal baseline
- module boundaries
- compliance controls
- deployment and migration rules
- future build-pack expansion

## App identity

- Repository: `michelemilazzo/thanatos_intel`
- Frappe app name: `thanatos_intel`
- Python package: `thanatos_intel`
- App title: `Thanatos Intelligence Platform`
- Target framework: Frappe / ERPNext v15+

## Source-of-truth rule

This repository is the authoritative source for the app. Runtime benches should pull from GitHub or the Git checkout tracked in this repo, not from ad hoc edits on the deployment host.

## Install

```bash
bench get-app https://github.com/michelemilazzo/thanatos_intel.git
bench --site <site-name> install-app thanatos_intel
bench --site <site-name> migrate
bench --site <site-name> clear-cache
```

## Status

The app scaffold is present and installable. The current work is to align the codebase with the Romanian-law-first master specification and its internal package structure.
