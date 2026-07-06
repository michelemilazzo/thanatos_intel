# 🧪 Manual QA Test Plan - Wallet Recovery Tool

**Test Date**: 2026-07-06  
**Product**: Thanatos Wallet Recovery Tool  
**Environment**: dev (thanatos.onekeyco.com)  
**Test Level**: End-to-End (E2E) UI & Integration Testing

---

## 📋 Pre-Test Setup

### Requirements
- [ ] Chrome/Firefox browser
- [ ] Thanatos account with "Investigator" role
- [ ] Existing Investigation Case (or create one)
- [ ] Test seed phrase (partial BIP39)
- [ ] Recovery machine setup (optional, for CLI test)

### Test Credentials
```
URL: https://thanatos.onekeyco.com/app/investigation-case
Role: Investigator or Investigation Manager
```

---

## 🧪 TEST SCENARIOS

### **Test 1: Navigation to Wallet Recovery Tool**

**Steps:**
1. Open https://thanatos.onekeyco.com/app/investigation-case
2. Click on any Investigation Case
3. Look for "Wallet Recovery" button/link in the Actions menu

**Expected Result:**
- ✅ "Wallet Recovery" option visible in Actions
- ✅ Clicking opens a modal dialog
- ✅ Modal shows "New Recovery Job" button
- ✅ List of existing recovery jobs (if any)

**Status**: [ ] PASS [ ] FAIL [ ] SKIP

**Notes**: _______________________________________________

---

### **Test 2: Create Recovery Job**

**Steps:**
1. In Wallet Recovery modal, click "+ New Recovery Job"
2. Verify form appears with:
   - Wallet Type dropdown
   - Seed Input textarea
   - Submit button

**Expected Result:**
- ✅ New job form renders
- ✅ Wallet Type field accepts (BIP39, Electrum, BIP38, Ledger)
- ✅ Form validation works (required fields)

**Status**: [ ] PASS [ ] FAIL [ ] SKIP

**Notes**: _______________________________________________

---

### **Test 3: Select Wallet Type (BIP39)**

**Steps:**
1. Click Wallet Type dropdown
2. Select "BIP39 Seed"
3. Form updates to show BIP39-specific fields

**Expected Result:**
- ✅ Dropdown shows all wallet types
- ✅ BIP39 Seed selectable
- ✅ Form updates without page reload

**Status**: [ ] PASS [ ] FAIL [ ] SKIP

**Notes**: _______________________________________________

---

### **Test 4: Enter Partial Seed**

**Steps:**
1. In Seed Input textarea, enter partial BIP39 seed:
   ```
   abandon ability able about above absolute absorb abstract abuse access accident account ???? ???? ????
   ```
2. Verify text is accepted

**Expected Result:**
- ✅ Textarea accepts text
- ✅ No character limit errors
- ✅ "????" placeholder recognized
- ✅ Text persists (no auto-clear)

**Status**: [ ] PASS [ ] FAIL [ ] SKIP

**Notes**: _______________________________________________

---

### **Test 5: Encrypt & Upload Seed**

**Steps:**
1. Click "🔐 Encrypt & Upload Seed" button
2. Wait for encryption to complete
3. Verify success message appears

**Expected Result:**
- ✅ Button shows loading indicator
- ✅ Success alert appears ("✅ Seed uploaded and encrypted")
- ✅ Form updates to show status "Uploaded"
- ✅ UI advances to next step

**Status**: [ ] PASS [ ] FAIL [ ] SKIP

**Notes**: _______________________________________________

---

### **Test 6: Configure Recovery Parameters**

**Steps:**
1. Verify "Step 2: Recovery Parameters" section appears
2. Check Missing Words Count field (default: 3)
3. Check Wordlist Type dropdown (default: english)
4. Change values if desired

**Expected Result:**
- ✅ Step 2 section visible
- ✅ Missing Words input accepts numbers (1-12)
- ✅ Wordlist dropdown shows: English, Italian, Spanish, French, German
- ✅ Values are retained when changed

**Status**: [ ] PASS [ ] FAIL [ ] SKIP

**Notes**: _______________________________________________

---

### **Test 7: Generate CLI Command**

**Steps:**
1. Click "Generate CLI Command" button
2. Wait for command generation
3. Verify command appears in code block

**Expected Result:**
- ✅ CLI command generated
- ✅ Command format correct:
   ```
   thanatos-recovery-cli \
     --job-id WRJ-YYYY-NNNN \
     --input-file /mnt/thanatos-box/recovery-vault/WRJ-YYYY-NNNN/seed_input.enc \
     --wallet-type bip39 \
     --missing-words 3 \
     --wordlist english \
     --output-file ...
   ```
- ✅ "Copy" button available
- ✅ Status advances to "Processing"

**Status**: [ ] PASS [ ] FAIL [ ] SKIP

**Notes**: _______________________________________________

---

### **Test 8: Copy CLI Command**

**Steps:**
1. Click 📋 "Copy" button below CLI command
2. Paste into text editor to verify
3. Check format is correct

**Expected Result:**
- ✅ Command copied to clipboard
- ✅ Success toast notification appears
- ✅ Pasted text matches on-screen command
- ✅ No newlines/formatting issues

**Status**: [ ] PASS [ ] FAIL [ ] SKIP

**Notes**: _______________________________________________

---

### **Test 9: Upload Recovery Result**

**Steps:**
1. Prepare encrypted result file (mock: any file for testing)
2. Click "Upload Result" or file upload area
3. Select file and upload
4. Verify success

**Expected Result:**
- ✅ File upload dialog opens
- ✅ File accepted
- ✅ Upload progress shown
- ✅ Success message: "✅ Recovery result uploaded!"
- ✅ Status changes to "Completed"

**Status**: [ ] PASS [ ] FAIL [ ] SKIP

**Notes**: _______________________________________________

---

### **Test 10: Download Link Generation**

**Steps:**
1. After result uploaded, verify download link appears
2. Check expiry timestamp
3. Verify link format

**Expected Result:**
- ✅ Download link visible in code block
- ✅ Link format: `https://thanatos.onekeyco.com/api/get_recovery_result?job_id=WRJ-...&token=...`
- ✅ Expiry shown: 48 hours from now
- ✅ "Copy Link" button available

**Status**: [ ] PASS [ ] FAIL [ ] SKIP

**Notes**: _______________________________________________

---

### **Test 11: Share Download Link**

**Steps:**
1. Click "Copy Link" button
2. Verify link copied
3. Click "Share via Email" button
4. Verify email client opens

**Expected Result:**
- ✅ Link copied to clipboard
- ✅ Success toast appears
- ✅ Email client opens with link in body
- ✅ Share via WhatsApp button works (opens WhatsApp Web)
- ✅ Share via Portal button shows confirmation

**Status**: [ ] PASS [ ] FAIL [ ] SKIP

**Notes**: _______________________________________________

---

### **Test 12: View Audit Log**

**Steps:**
1. Scroll down to "📋 Audit Log" section
2. Click to expand (if collapsible)
3. Verify log entries appear

**Expected Result:**
- ✅ Audit log visible
- ✅ Log entries timestamped
- ✅ Actions recorded (Job created, Seed uploaded, Result uploaded, etc.)
- ✅ Log is read-only (no edit capability)

**Status**: [ ] PASS [ ] FAIL [ ] SKIP

**Notes**: _______________________________________________

---

### **Test 13: Create New Recovery Job (Button)**

**Steps:**
1. After completing workflow, click "Start New Recovery" button
2. Verify new job form appears
3. Confirm previous job data is cleared

**Expected Result:**
- ✅ Button resets UI to Step 1
- ✅ Previous data cleared
- ✅ New job can be created immediately
- ✅ Modal stays open for multiple jobs

**Status**: [ ] PASS [ ] FAIL [ ] SKIP

**Notes**: _______________________________________________

---

### **Test 14: View Recovery Jobs List**

**Steps:**
1. Return to Investigation Case
2. Click "Wallet Recovery" again
3. Verify list shows all recovery jobs for this case

**Expected Result:**
- ✅ Jobs list displayed in table
- ✅ Columns: Job ID, Type, Status, Modified, Action
- ✅ Jobs sorted by most recent first
- ✅ "Open" button links to job details

**Status**: [ ] PASS [ ] FAIL [ ] SKIP

**Notes**: _______________________________________________

---

### **Test 15: Responsive Design (Mobile)**

**Steps:**
1. Resize browser to mobile width (375px)
2. Verify UI adapts
3. Check buttons are clickable
4. Verify form fields are usable

**Expected Result:**
- ✅ Layout responsive (no horizontal scroll)
- ✅ Buttons sized for touch
- ✅ Form fields readable
- ✅ Modal fits screen

**Status**: [ ] PASS [ ] FAIL [ ] SKIP

**Notes**: _______________________________________________

---

## 🐛 Bug Report Template

If issues found, report using this format:

```
**Bug #**: <number>
**Severity**: [ ] Critical [ ] High [ ] Medium [ ] Low
**Component**: <UI element>
**Steps to Reproduce**:
1. 
2. 
3. 

**Expected Result**: 

**Actual Result**: 

**Screenshot**: <if applicable>

**Environment**: dev, Chrome/Firefox, <date>
```

---

## ✅ Test Sign-Off

| Category | Result | Notes |
|----------|--------|-------|
| Navigation | [ ] ✅ [ ] ⚠️ [ ] ❌ | |
| Job Creation | [ ] ✅ [ ] ⚠️ [ ] ❌ | |
| Form Fields | [ ] ✅ [ ] ⚠️ [ ] ❌ | |
| Encryption/Upload | [ ] ✅ [ ] ⚠️ [ ] ❌ | |
| CLI Generation | [ ] ✅ [ ] ⚠️ [ ] ❌ | |
| Download Link | [ ] ✅ [ ] ⚠️ [ ] ❌ | |
| Sharing | [ ] ✅ [ ] ⚠️ [ ] ❌ | |
| Audit Log | [ ] ✅ [ ] ⚠️ [ ] ❌ | |
| Mobile/Responsive | [ ] ✅ [ ] ⚠️ [ ] ❌ | |

**Overall Result**: [ ] PASS [ ] FAIL (with issues)

**Tester Name**: ________________________  
**Date**: ________________________  
**Build/Commit**: 273c40f

---

## 📝 Notes & Observations

___________________________________________________________________

___________________________________________________________________

___________________________________________________________________

---

## 🎯 Next Steps

- [ ] Bug fixes (if any)
- [ ] Staff training session
- [ ] Client communication
- [ ] Production rollout
- [ ] Monitoring & support

---

**Test Document Version**: 1.0  
**Created**: 2026-07-06  
**Status**: Ready for Testing
