# 👥 Staff Onboarding Guide - Wallet Recovery Tool

**Document**: Staff Training & Operating Procedures  
**Date**: 2026-07-06  
**Tool**: Wallet Recovery Tool for Thanatos  
**Audience**: Investigation Managers, Investigators, Technical Staff

---

## 📚 Table of Contents

1. [Overview](#overview)
2. [Getting Started](#getting-started)
3. [Step-by-Step Workflow](#step-by-step-workflow)
4. [Security & Best Practices](#security--best-practices)
5. [Troubleshooting](#troubleshooting)
6. [FAQs](#faqs)

---

## 📖 Overview

The **Wallet Recovery Tool** helps clients recover lost or partially-remembered cryptocurrency wallet seeds in a secure, offline manner. As staff, your role is to:

1. ✅ Guide clients through the seed submission process
2. ✅ Generate secure recovery commands
3. ✅ Execute recovery on an air-gapped machine
4. ✅ Return encrypted results to clients

**Key Principle**: Seed phrases are NEVER stored plaintext. All encryption is end-to-end.

---

## 🚀 Getting Started

### Access
- **URL**: https://thanatos.onekeyco.com/app/investigation-case
- **Role Required**: Investigator or Investigation Manager
- **Permissions**: Read/Write on Wallet Recovery Jobs

### First Time Setup
1. Log in to Thanatos with your account
2. Open any Investigation Case
3. Look for "Wallet Recovery" in the Actions menu
4. You should see a modal dialog

### Recovery Machine Setup
If you'll be performing recovery:
1. Obtain an air-gapped machine (no internet)
2. Install BTCRecover:
   ```bash
   pip install btcrecover cryptography pycryptodome
   ```
3. Copy the CLI tool:
   ```bash
   cp /usr/local/bin/thanatos-recovery-cli <recovery_machine>
   ```
4. Keep offline and secure

---

## 🧭 Step-by-Step Workflow

### **Phase 1: Client Onboarding**

**You will:**
1. Explain the recovery process to the client
2. Clarify what information is needed (partial seed, wallet type)
3. Explain security model (end-to-end encryption, offline recovery)

**Client provides:**
- Partial seed phrase (with ???? for missing words)
- Wallet type (BIP39, Electrum, etc.)
- Approximate number of missing/wrong words
- Preferred wordlist (English, Italian, etc.)

**Example**:
```
Client: "I have 11 words of my BIP39 seed, missing 3 in the middle"
You: "Perfect. I'll create a recovery job. Your seed will be encrypted with 
      RSA, then we'll run BTCRecover offline to find the missing words."
```

---

### **Phase 2: Create Recovery Job**

**In Thanatos:**

1. Open Investigation Case (the client's case)
2. Click "Wallet Recovery" → "+ New Recovery Job"
3. Fill out form:
   - **Wallet Type**: Select from dropdown (BIP39 Seed, Electrum Seed, etc.)
   - **Seed Input**: Paste client's partial seed (use ???? for missing)
   - **Missing Words Count**: How many words are missing/wrong (1-12)
   - **Wordlist**: BIP39 language (English, Italian, Spanish, etc.)

4. Click "🔐 Encrypt & Upload Seed"

**What happens:**
- Seed is encrypted with RSA 4096-bit
- Uploaded to secure vault (/mnt/thanatos-box/recovery-vault)
- Job ID is generated (WRJ-YYYY-NNNN)
- Status changes to "Uploaded"

**⚠️ Security Note**: Seed is encrypted immediately. Plaintext never stored.

---

### **Phase 3: Generate Recovery Command**

**In Thanatos:**

1. Review parameters (missing words, wordlist)
2. Click "Generate CLI Command"
3. Copy the command (click 📋 Copy button)

**Example command** (job IDs are `WRJ-00001`, `WRJ-00002`, …):
```bash
thanatos-recovery-cli \
  --job-id WRJ-00001 \
  --input-file /mnt/thanatos-box/recovery-vault/WRJ-00001/seed_input.enc \
  --private-key /mnt/thanatos-box/recovery-vault/keys/private.pem \
  --wallet-type bip39 \
  --missing-words 3 \
  --wordlist english \
  --output-file /mnt/thanatos-box/recovery-vault/WRJ-00001/seed_output.enc
```

The command is generated for you by the desk form ("Generate Command") — copy it as-is.

- `--private-key` decrypts the client's RSA-encrypted seed. The vault private key
  (`keys/private.pem`) must be copied to the air-gapped machine before running, and
  wiped after.
- `--wallet-type` accepts only `bip39` / `electrum` / `bip38` (the form maps the
  wallet type automatically).

**Keep Safe**: This command contains the encrypted seed location and the vault private key path. Don't share with the client.

---

### **Phase 4: Execute Recovery (Offline)**

**On Recovery Machine:**

1. **Prepare**:
   ```bash
   # Ensure machine is OFFLINE (disconnect from network)
   # Verify: no WiFi, no ethernet cable connected
   ```

2. **Copy encrypted seed**:
   ```bash
   # Transfer from Thanatos server to recovery machine via USB
   cp /vault/WRJ-2026-0001/seed_input.enc ~/recovery/
   ```

3. **Run command** (copy the vault `private.pem` to the machine first):
   ```bash
   thanatos-recovery-cli \
     --job-id WRJ-00001 \
     --input-file ~/recovery/seed_input.enc \
     --private-key ~/recovery/private.pem \
     --wallet-type bip39 \
     --missing-words 3 \
     --wordlist english \
     --output-file ~/recovery/seed_output.enc
   ```

4. **Wait**: BTCRecover will search (5 min to 1 hour depending on difficulty)

5. **Result** — two files are produced:
   ```
   ✅ Recovery complete. Result saved to: ~/recovery/seed_output.enc
      Fernet key saved to: ~/recovery/seed_output.enc.key
   ```
   - `seed_output.enc` → uploaded back to the vault (becomes the download link).
   - `seed_output.enc.key` → the decryption key. **Deliver it to the client on a
     SEPARATE secure channel** from the download link — the client needs both the
     `.enc` file and this key to read the recovered seed. Never send them together.
   - Wipe `private.pem` and both output files from the machine after delivery.

**⚠️ Critical**: Keep machine offline during entire process!

---

### **Phase 5: Upload Result**

**Back in Thanatos:**

1. Transfer encrypted result (USB) back to Thanatos server
2. In Wallet Recovery Job, upload result file
3. Status changes to "Completed"
4. Download link is generated automatically

**Download Link Format:**
```
https://thanatos.onekeyco.com/api/get_recovery_result?job_id=WRJ-2026-0001&token=abc123...
```

**Validity**: Link expires in 48 hours

---

### **Phase 6: Share with Client**

**Share the download link via:**
- 📧 Email (encrypted/secure channel)
- 📱 WhatsApp
- 🔐 Client Portal (most secure)

**⚠️ Important**: 
- Only share the download link, NOT the job details
- Remind client: link expires in 48 hours
- Client must download and keep secure

---

## 🔐 Security & Best Practices

### For Staff

| Rule | Why |
|------|-----|
| **Keep recovery machine offline** | Prevents seed leakage over network |
| **Use USB for file transfer** | Airgapped, no network exposure |
| **Don't log seeds anywhere** | System logs seed_output.enc path but never contents |
| **Clear cache after use** | Prevents data recovery from disk |
| **Verify vault directory permissions** | Only Frappe user should read/write |
| **Never share job credentials** | Only share download link with client |
| **Log all recovery attempts** | Audit trail for compliance |

### Checklist Before Recovery

- [ ] Recovery machine is offline (verified disconnected from network)
- [ ] BTCRecover installed and working
- [ ] Seed file encrypted (transferred via USB)
- [ ] Command copied correctly
- [ ] Expected runtime calculated (e.g., 3 words = ~30 min on standard CPU)
- [ ] Result file will be stored in ~/recovery/
- [ ] Machine will NOT be rebooted until result backed up

### After Recovery

- [ ] Delete encrypted seed from recovery machine
- [ ] Securely erase USB (shred or multiple-pass wipe)
- [ ] Log completion in Thanatos (audit trail)
- [ ] Verify result file deleted after download by client (48h expiry)
- [ ] Confirm client received link and downloaded successfully

---

## 🐛 Troubleshooting

### **Issue: "Seed not found after 1 hour"**

**Causes:**
1. Wrong number of missing words specified
2. Wrong wordlist language
3. Seed phrase has errors (typos)

**Solution:**
1. Create NEW job with different parameters
2. Try increasing missing words count
3. Ask client to double-check phrase spelling

### **Issue: "Download link expired"**

**Cause**: 48-hour TTL passed

**Solution:**
1. Create new recovery job (start over)
2. Recovery is needed again to regenerate link

### **Issue: "Recovery command fails to execute"**

**Causes:**
1. BTCRecover not installed
2. Encrypted seed file corrupted
3. Wrong file path in command

**Solution:**
1. Run: `btcrecover --help` to verify install
2. Re-download seed file from Thanatos
3. Copy command exactly as shown in UI

### **Issue: "Machine is too slow (recovery taking >1 hour)"**

**Causes:**
1. CPU is not powerful enough for brute-force
2. Too many missing words specified

**Solution:**
1. Use faster machine if available
2. Reduce missing words estimate if possible

---

## ❓ FAQs

### **Q: Can I connect to the internet during recovery?**
**A**: NO. Recovery machine MUST be offline. Internet = vulnerability.

### **Q: What if the seed is not found?**
**A**: Recovery failed. Client may have misremembered or seed phrase has errors. Discuss options with client.

### **Q: How long does recovery take?**
**A**: Depends on missing words:
- 1 word: ~1 minute
- 2 words: ~5 minutes
- 3 words: ~30 minutes
- 4+ words: 1+ hours

### **Q: Can I see the recovered seed?**
**A**: NO. Result is encrypted. Even you can't see it. Only client can decrypt with their key.

### **Q: What if client loses the download link?**
**A**: Recovery job is valid for 48 hours. You can regenerate link or create new job.

### **Q: Is this compliant with regulations?**
**A**: YES. Zero-plaintext storage, immutable audit logs, client-side encryption = compliant.

### **Q: What if the job is older than 48 hours?**
**A**: Files are auto-deleted. Recovery is not possible. Must start new job.

### **Q: Can multiple people work on same recovery?**
**A**: No. One recovery job = one recovery process. Create separate jobs for different clients.

### **Q: What if I accidentally share plaintext seed?**
**A**: Inform supervisor immediately. Seeds are encrypted so risk is low, but must report.

---

## 📞 Support & Escalation

| Issue | Contact | Time |
|-------|---------|------|
| Technical question | Tech Lead | Same day |
| Recovery failed | Supervisor | Same day |
| Client complaint | Manager | Same day |
| Security concern | CTO | URGENT |

**Tech Lead**: [contact info]  
**Manager**: [contact info]  
**CTO**: [contact info]

---

## 📋 Training Checklist

**Before you can perform recovery, you must:**

- [ ] Read this entire guide
- [ ] Complete hands-on walkthrough
- [ ] Pass security quiz (10 questions)
- [ ] Perform supervised recovery (1 job)
- [ ] Sign confidentiality agreement
- [ ] Get manager sign-off

**Date Completed**: ____________  
**Trainer Name**: ____________  
**Manager Approval**: ____________

---

## 🎓 Advanced Topics

### Multi-Word Recovery
For clients with 4+ missing words:
1. Split into 2 jobs (2-word each)
2. Combine results manually
3. Document approach in job notes

### Hardware Wallet Passphrase
If client lost hardware wallet passphrase:
1. Use BIP38 mode (different from BIP39)
2. Recovery takes 1-2 hours typically
3. Same process, different parameters

### Ledger Recovery
For Ledger device recovery:
1. Use "Ledger Passphrase" wallet type
2. Tool recovers passphrase only, not full seed
3. Client still needs device or backup

---

## ✅ Sign-Off

I have read and understand the Wallet Recovery Tool procedures.

**Staff Member Name**: ________________________

**Signature**: ________________________

**Date**: ________________________

**Manager**: ________________________

---

**Document Version**: 1.0  
**Last Updated**: 2026-07-06  
**Status**: Final - Ready for Training
