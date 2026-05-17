# Thanatos Intel

Intelligence Investigation Platform MVP for Frappe/ERPNext.

## CI Status

GitHub Actions workflow: `Thanatos CI`

The repository runs automatic validation on every push to `main`:

- Python syntax validation
- JSON validation
- Frappe file structure validation
- pytest static test suite

## Objective

Thanatos Intel is a modular Frappe app for managing investigative cases, entities, evidence, OSINT checks, fraud intelligence, document analysis, cyber risk, corporate due diligence, pay-per-use billing and professional portals.

## App identity

- Repository: `michelemilazzo/thanatos_intel`
- Frappe app name: `thanatos_intel`
- Python package: `thanatos_intel`
- App title: `Thanatos Intel`
- Target framework: Frappe / ERPNext

## MVP v0.1 scope

The first version must remain simple and installable. It will focus on the core investigation workflow:

1. Investigation case management
2. Entity registry
3. Evidence vault
4. Chain of custody log
5. Risk score
6. Investigation report
7. Service catalogue
8. Investigation order
9. Portal-ready structure
10. Future OSINT connector placeholders

## Planned modules

- `thanatos_core` — cases, entities, evidence, reports and audit logs
- `thanatos_fraud` — fraud patterns, alerts, blacklist and watchlist
- `thanatos_documents` — document metadata, hashes and analysis jobs
- `thanatos_osint` — OSINT queries, providers and normalized results
- `thanatos_cyber` — IP/domain/URL/hash reputation and IOC records
- `thanatos_corporate` — corporate profiles, ownership and due diligence
- `thanatos_billing` — service SKUs, investigation orders and usage events
- `thanatos_portal` — client/professional portal pages

## Development rule

All changes must be committed to GitHub first. Deployment machines should pull from GitHub and should not be used as the source of truth.

## Install placeholder

```bash
bench get-app https://github.com/michelemilazzo/thanatos_intel.git
bench --site <site-name> install-app thanatos_intel
bench --site <site-name> migrate
```

## Status

Baseline v0.1 committed. Frappe scaffold, DocTypes, controllers, roles, workspace, install hook, permission helpers and CI tests are now present.
