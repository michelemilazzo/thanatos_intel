# MMOS THANATOS 2026
## MASTER SPECIFICATION FOR CODEX

Version 1.0
Classification: INTERNAL DEVELOPMENT
Project Code: MMOS-THANATOS-2026

## IMPORTANT ARCHITECTURE DECISION

The entire Thanatos project must be implemented as a single Frappe app named `thanatos_intel`.

Do not create multiple Frappe apps.

All functional areas must be implemented as internal modules/packages inside `thanatos_intel`.

The application must be compatible with Frappe/ERPNext v15 and later migration to v16.

The app must be suitable for installation with:

```bash
bench get-app thanatos_intel <repository_url>
bench --site erp.thanatos.ro install-app thanatos_intel
bench --site erp.thanatos.ro migrate
bench --site erp.thanatos.ro clear-cache
```

## 1. Project Overview

THANATOS is an international investigation, intelligence and recovery platform built on:

- Frappe Framework
- ERPNext
- MMOS AI Layer
- Docker
- REST API
- MariaDB
- Open Source Intelligence integrations
- Blockchain intelligence integrations

The objective is to create a unified platform capable of managing:

- private investigations
- corporate investigations
- due diligence
- AML reviews
- KYC/KYB
- asset tracing
- recovery actions
- commercial fraud investigations
- EN590 scams
- cryptocurrency tracing
- diplomatic passport due diligence workflows
- client portal
- legal document generation
- investigation reporting

## 2. Company Configuration

Company Name: `THANATOS INVESTIGAZIONI S.R.L.`

Tax ID: `RO46901022`

Registration: `J13/3515/26.09.2022`

Address:

```text
Str. Baba Novac nr.185
Constanta
Romania
```

Director: `Lorenzo Marrocu`

Platform: `platform.thanatos.ro`

ERP: `erp.thanatos.ro`

Currency: `EUR`

Default Language: `English`

Supported Languages:

- English
- Italian
- Romanian

## 3. Brand Identity

Colors:

- DARK: `#0A0E1A`
- NAVY: `#0D1B3E`
- GOLD: `#C8A96E`
- BLUE: `#1A3A6E`
- LIGHT: `#F4F4F0`

Font: `Helvetica`

Visual Style:

- corporate intelligence
- premium consulting
- international investigations
- intelligence agency appearance
- dark luxury theme

## 4. Single App Structure

The app name remains `thanatos_intel`.

All modules must be internal packages of `thanatos_intel`.

Canonical internal packages:

- `thanatos_intel.core`
- `thanatos_intel.legal_compliance`
- `thanatos_intel.cases`
- `thanatos_intel.evidence`
- `thanatos_intel.osint`
- `thanatos_intel.due_diligence`
- `thanatos_intel.crypto`
- `thanatos_intel.recovery`
- `thanatos_intel.documents`
- `thanatos_intel.kyc`
- `thanatos_intel.diplomatic`
- `thanatos_intel.portal`
- `thanatos_intel.ai`
- `thanatos_intel.compliance`
- `thanatos_intel.billing`
- `thanatos_intel.reports`

## 5. Core Doctypes

Investigation Case

Fields:

- case_number
- title
- client
- status
- priority
- investigator
- opening_date
- closing_date
- classification
- jurisdiction
- summary
- notes

Investigation Evidence

Fields:

- case
- evidence_type
- source
- hash
- upload_date
- chain_of_custody
- file

Investigation Subject

Fields:

- name
- surname
- company
- tax_number
- passport
- nationality
- risk_score

Investigation Asset

Fields:

- asset_type
- description
- country
- estimated_value
- owner

Investigation Event

Fields:

- date
- description
- operator
- case

## 6. Case Management Workflow

Lead

Mandate

KYC

Payment

Case Opening

Investigation

Evidence Collection

Analysis

Report

Recovery

Closure

## 7. Evidence Management

Support:

- PDF
- DOCX
- Images
- Videos
- Audio
- ZIP
- Blockchain exports
- Email archives

Features:

- SHA256 hashing
- Timestamp
- Chain of Custody
- Versioning
- Immutable Audit Log

## 8. OSINT Module

Functions:

- WHOIS
- DNS Lookup
- Reverse DNS
- Company Registry Search
- Court Registry Search
- Media Search
- News Search
- Social Search
- Dark Web Indicators
- Email Intelligence
- Phone Intelligence
- Domain Intelligence
- IP Intelligence
- Beneficial Ownership Search
- Link Analysis
- Graph Visualization

## 9. Due Diligence Module

Risk Categories:

- Low
- Medium
- High
- Critical

Checks:

- Company Verification
- UBO Verification
- PEP Screening
- Sanctions Screening
- Adverse Media
- Litigation Search
- Corporate Registry
- Financial Analysis
- AML Review
- Source of Wealth
- Source of Funds

## 10. Diplomatic Passport Module

Purpose:

Management of diplomatic passport requests and related services.

Workflow:

Application

Questionnaire

KYC

KYB

Video Identification

Risk Review

Mandate

Pro Forma Invoice

Payment

Submission

Monitoring

Closure

Questionnaire must include:

- Personal Data
- Passport Data
- Address
- Professional Background
- Skills
- Government Experience
- Military Experience
- Business Experience
- Previous Investigations
- Criminal Records Declaration
- Political Exposure Declaration
- Interest in Passport / ID Card / Driving License / Vehicle Registration / Consulate Opening / Embassy Opening / Special Diplomatic Appointment

## 11. Video Identification

Requirements:

- Remote Identification
- Face Matching
- Document Capture
- Liveness Detection
- Session Recording
- Audit Trail
- Storage of Evidence

## 12. KYC Module

Natural Person Document Types:

- Passport
- National ID
- Driving License
- Residence Permit
- Proof of Address

## 13. KYB Module

Company Checks:

- Certificate of Incorporation
- Shareholder Register
- Director Register
- UBO Register
- Tax Number
- Website Verification
- Business Activity Verification

## 14. Crypto Investigation Module

Supported Chains:

- Bitcoin
- Ethereum
- Tron
- BNB Chain
- Solana

Functions:

- Wallet Analysis
- Transaction Tracing
- Risk Scoring
- Exchange Attribution
- Sanctions Screening
- Mixer Detection
- Fraud Pattern Detection
- Case Linking

## 15. EN590 Fraud Module

Dedicated workflow for:

- Tank Storage Fraud
- Advance Fee Fraud
- Fake TSR
- Fake POP
- Fake SGS
- Fake Tank Farms
- Fake Refineries

Workflow:

- Case Opening
- Document Upload
- Fraud Analysis
- Risk Scoring
- Recovery Recommendation
- Legal Package
- Recovery Actions

## 16. Recovery Module

Types:

- Bank Recovery
- Crypto Recovery
- Commercial Fraud
- Asset Recovery
- Civil Recovery

Functions:

- Recovery Strategy
- Jurisdiction Mapping
- Legal Action Tracking
- Recovery Probability Engine
- Success Fee Calculation

## 17. Document Generator

Templates:

- Investigation Report
- Due Diligence Report
- Corporate Intelligence Report
- Fraud Assessment Report
- Recovery Report
- Mandate
- Power of Attorney
- Invoice
- Pro Forma
- Legal Notice
- AML Report
- Executive Summary

All templates must support:

- DOCX
- PDF
- HTML

## 18. Client Portal

Functions:

- Case Status
- Messages
- Invoices
- Payments
- Document Upload
- Report Download
- Electronic Signature
- Notifications

## 19. AI Agents

- Fraud Agent
- Due Diligence Agent
- OSINT Agent
- Recovery Agent
- AML Agent
- Crypto Agent
- Document Agent
- Investigator Assistant

All agents must operate through MMOS AI layer.

## 20. Role System

- Director
- Senior Investigator
- Investigator
- Analyst
- AML Officer
- Legal Partner
- External Consultant
- Client
- Read-only Auditor

## 21. Dashboards

- Director Dashboard
- Investigator Dashboard
- Client Dashboard

## 22. API Layer

- REST API
- JWT Authentication
- Webhook Support
- ERPNext Integration
- Document API
- Client API
- Case API
- Investigation API
- Recovery API

## 23. Security

- GDPR Compliance
- Audit Logging
- Role Based Access Control
- 2FA
- Encrypted Storage
- Encrypted Attachments
- Evidence Integrity Verification
- Chain of Custody Tracking

## 24. Reporting

- PDF Reports
- DOCX Reports
- Executive Reports
- Court-ready Reports
- Multilingual Reports
- Digital Signature Support

## 25. Deployment

- Docker Compose
- Production Ready
- ARM64 Compatible
- x86 Compatible
- Frappe v15+
- ERPNext v15+
- Multi-language
- Multi-company
- SaaS Ready

## 26. Romanian Legal Baseline

The entire platform must be built as a Romanian-law-first investigation system.

Primary applicable legal framework:

- Romanian Law No. 329/2003 regarding the profession of private detective
- Romanian Law No. 353/2004 amending and supplementing Law No. 329/2003
- Romanian Civil Code
- Romanian Criminal Code, where criminal fraud indicators are identified
- Romanian Criminal Procedure Code, where evidence preservation and authority reporting are relevant
- Romanian Law No. 190/2018 implementing GDPR in Romania
- Regulation EU 2016/679, General Data Protection Regulation
- Romanian Law No. 129/2019 for preventing and combating money laundering and terrorist financing
- Romanian company law and ONRC registration rules
- EU AML, sanctions, financial crime and data protection framework where cross-border matters are involved

Legal design rules:

- all mandates must be governed by Romanian law
- default court jurisdiction must be Tribunalul Constanta, Romania, unless overridden
- privacy notices must follow GDPR and Romanian Law 190/2018
- investigation activities must remain within the legal limits of private detective activity in Romania
- client onboarding must collect legal basis, consent and mandate before operational activity
- every evidence item must have lawful source, collection date, operator, retention basis and chain of custody
- every report must include limitation of use and confidentiality clauses
- every recovery case must clearly separate investigation activity from legal representation
- legal actions must be executed by licensed lawyers in the relevant jurisdiction
- Thanatos must not present itself as a court, police authority, prosecutor, regulator or financial institution

Mandatory legal disclaimer:

> THANATOS INVESTIGAZIONI S.R.L. operates as a Romanian private investigation company within the limits of applicable Romanian law. This report is prepared for informational, investigative and evidentiary support purposes only. It does not constitute legal advice, judicial finding, police report, financial advice or regulatory determination. Any legal action, court filing, criminal complaint or asset-freezing measure must be reviewed and filed by a qualified lawyer or competent authority in the relevant jurisdiction.

## 27. Legal Compliance Module

Required internal package:

- `thanatos_intel.legal_compliance`

Doctypes:

- Thanatos Legal Basis
- Thanatos Case Acceptance Checklist
- Thanatos Mandate Legal Review
- Thanatos GDPR Processing Record
- Thanatos Evidence Legality Review
- Thanatos AML Risk Review
- Thanatos Jurisdiction Review
- Thanatos Legal Disclaimer Template
- Thanatos Restricted Activity Rule
- Thanatos Data Retention Rule

The system must prevent submission of an Investigation Case unless:

- mandate is signed
- lawful basis is selected
- privacy notice is accepted
- case acceptance checklist is completed
- restricted activity check is passed
- Director approval is recorded

## 28. Long Term Roadmap

Phase 1

- Core Investigation Platform

Phase 2

- OSINT Intelligence

Phase 3

- Crypto Intelligence

Phase 4

- Recovery Platform

Phase 5

- Diplomatic Due Diligence

Phase 6

- AI Investigation Assistant

Phase 7

- International Partner Network

Phase 8

- Full Intelligence SaaS Platform

END OF MASTER SPECIFICATION
