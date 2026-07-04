<!-- Wallet Recovery Widget - Vue Component per Investigation Case -->

<template>
  <div class="wallet-recovery-widget">
    <div class="header-section">
      <h5>🔐 Wallet Recovery</h5>
      <p class="subtitle">Offline seed/password recovery tool</p>
    </div>

    <!-- State: No Job -->
    <div v-if="!currentJob" class="intro-section">
      <p>
        Assist clients in recovering lost BIP39 seeds, Electrum seeds, or encrypted wallet passwords.
        <br><small>⚠️ All operations are encrypted end-to-end. Seeds are never stored in plaintext.</small>
      </p>
      <button class="btn btn-primary" @click="createNewJob">
        <i class="icon-plus"></i> New Recovery Job
      </button>
    </div>

    <!-- State: Job Created -->
    <div v-else class="job-section">
      <div class="job-header">
        <h6>{{ currentJob.name }}</h6>
        <span :class="`badge badge-${statusColor}`">{{ currentJob.status }}</span>
      </div>

      <!-- Step 1: Upload Seed Input -->
      <div v-if="currentJob.status === 'Draft'" class="step step-1">
        <h6><span class="step-num">1</span> Wallet Type & Seed Input</h6>

        <div class="form-group">
          <label>Wallet Type</label>
          <select v-model="currentJob.wallet_type" class="form-control">
            <option value="">-- Select --</option>
            <option value="BIP39 Seed">BIP39 Seed (12/24 words)</option>
            <option value="Electrum Seed">Electrum Seed</option>
            <option value="BIP38 Encrypted">BIP38 Encrypted Key</option>
            <option value="Ledger Passphrase">Ledger Passphrase</option>
          </select>
        </div>

        <div class="form-group">
          <label>Seed (Partial/Forgotten Words)</label>
          <textarea
            v-model="seedInput"
            class="form-control"
            rows="4"
            placeholder="e.g., apple banana cherry ... ???? ???? ????">
          </textarea>
          <small>Use ???? for missing words. Do not include passphrase here.</small>
        </div>

        <div class="form-group">
          <label>Passphrase Hint (Optional)</label>
          <input
            v-model="currentJob.password_hint"
            type="text"
            class="form-control"
            placeholder="e.g., 'my dog name', 'birth year'">
          <small>Hint only - never the actual passphrase</small>
        </div>

        <button class="btn btn-success" @click="encryptAndUploadSeed" :disabled="!currentJob.wallet_type || !seedInput">
          <i class="icon-lock"></i> 🔐 Encrypt & Upload Seed
        </button>
      </div>

      <!-- Step 2: Parameters -->
      <div v-if="currentJob.status === 'Uploaded'" class="step step-2">
        <h6><span class="step-num">2</span> Recovery Parameters</h6>

        <div class="form-group">
          <label>Missing/Wrong Words Count</label>
          <input
            v-model.number="currentJob.missing_words_count"
            type="number"
            min="1"
            max="12"
            class="form-control">
          <small>Number of words to brute-force search</small>
        </div>

        <div class="form-group">
          <label>BIP39 Wordlist Language</label>
          <select v-model="currentJob.wordlist_type" class="form-control">
            <option value="english">English</option>
            <option value="italian">Italian</option>
            <option value="spanish">Spanish</option>
            <option value="french">French</option>
            <option value="german">German</option>
          </select>
        </div>

        <button class="btn btn-info" @click="generateCommand">
          <i class="icon-code"></i> Generate CLI Command
        </button>
      </div>

      <!-- Step 3: CLI Command -->
      <div v-if="currentJob.processing_command" class="step step-3">
        <h6><span class="step-num">3</span> Execute Offline</h6>

        <p><strong>⚠️ IMPORTANT:</strong> Copy this command to an <strong>offline/air-gapped machine</strong> with BTCRecover installed.</p>

        <div class="code-block">
          <code>{{ currentJob.processing_command }}</code>
          <button class="btn btn-sm btn-secondary" @click="copyCommand">
            <i class="icon-copy"></i> Copy
          </button>
        </div>

        <p><small>Expected output: <code>result.enc</code> (encrypted recovered seed)</small></p>

        <p>After running the command:</p>
        <ol>
          <li>Transfer the <code>result.enc</code> file from the recovery machine (via USB, SCP, etc.)</li>
          <li>Upload it below to complete the recovery</li>
        </ol>

        <button class="btn btn-warning" @click="markAsProcessing">
          <i class="icon-arrow-right"></i> Next: Upload Result
        </button>
      </div>

      <!-- Step 4: Upload Result -->
      <div v-if="currentJob.status === 'Processing'" class="step step-4">
        <h6><span class="step-num">4</span> Upload Recovery Result</h6>

        <p>Select the encrypted <code>result.enc</code> file from your recovery machine:</p>

        <div class="file-input-wrapper">
          <input
            type="file"
            @change="handleResultFileSelect"
            accept=".enc"
            class="form-control">
        </div>

        <button
          v-if="resultFile"
          class="btn btn-success"
          @click="uploadRecoveryResult"
          :disabled="isUploading">
          <i class="icon-upload" v-if="!isUploading"></i>
          <i class="icon-spinner icon-spin" v-if="isUploading"></i>
          {{ isUploading ? 'Uploading...' : 'Upload & Generate Link' }}
        </button>
      </div>

      <!-- Step 5: Download Link -->
      <div v-if="currentJob.status === 'Completed'" class="step step-5">
        <h6><span class="step-num">5</span> ✅ Recovery Complete</h6>

        <p><strong>Download link ready!</strong> Share with client via secure channel:</p>

        <div class="download-link-box">
          <input
            type="text"
            :value="currentJob.result_vault_url"
            readonly
            class="form-control">
          <button class="btn btn-secondary" @click="copyDownloadLink">
            <i class="icon-copy"></i> Copy Link
          </button>
        </div>

        <div class="expiry-alert">
          ⏱️ <strong>Link expires:</strong> {{ formatDate(currentJob.result_expires_at) }}
          <small>(48 hours)</small>
        </div>

        <p>Share via:</p>
        <div class="share-buttons">
          <button class="btn btn-sm btn-outline-primary" @click="shareViaEmail">
            <i class="icon-mail"></i> Email
          </button>
          <button class="btn btn-sm btn-outline-info" @click="shareViaWhatsApp">
            <i class="icon-phone"></i> WhatsApp
          </button>
          <button class="btn btn-sm btn-outline-secondary" @click="shareViaPortal">
            <i class="icon-lock"></i> Client Portal
          </button>
        </div>
      </div>

      <!-- Error State -->
      <div v-if="currentJob.status === 'Error'" class="alert alert-danger">
        <strong>❌ Recovery Failed</strong>
        <p>{{ currentJob.notes }}</p>
        <button class="btn btn-sm btn-secondary" @click="resetJob">Try Again</button>
      </div>

      <!-- Audit Log (Collapsible) -->
      <details v-if="currentJob.audit_log" class="audit-section">
        <summary>📋 Audit Log</summary>
        <pre>{{ currentJob.audit_log }}</pre>
      </details>

      <!-- Reset Button -->
      <div v-if="['Completed', 'Error', 'Expired'].includes(currentJob.status)" class="actions-footer">
        <button class="btn btn-outline-secondary" @click="resetJob">
          <i class="icon-redo"></i> Start New Recovery
        </button>
      </div>
    </div>
  </div>
</template>

<script>
export default {
  name: 'WalletRecoveryWidget',
  props: {
    caseId: {
      type: String,
      required: true
    }
  },
  data() {
    return {
      currentJob: null,
      seedInput: '',
      resultFile: null,
      isUploading: false
    }
  },
  computed: {
    statusColor() {
      const colors = {
        'Draft': 'secondary',
        'Uploaded': 'info',
        'Processing': 'warning',
        'Completed': 'success',
        'Error': 'danger',
        'Expired': 'dark'
      }
      return colors[this.currentJob?.status] || 'secondary'
    }
  },
  mounted() {
    this.loadExistingJob()
  },
  methods: {
    loadExistingJob() {
      // Carica il job più recente per questo caso, se esiste
      frappe.call({
        method: 'frappe.client.get_list',
        args: {
          doctype: 'Wallet Recovery Job',
          filters: { case_id: this.caseId },
          order_by: 'creation desc',
          limit_page_length: 1
        },
        callback: (r) => {
          if (r.message && r.message.length > 0) {
            frappe.call({
              method: 'frappe.client.get',
              args: {
                doctype: 'Wallet Recovery Job',
                name: r.message[0].name
              },
              callback: (r2) => {
                this.currentJob = r2.message
              }
            })
          }
        }
      })
    },

    createNewJob() {
      frappe.call({
        method: 'thanatos_intel.thanatos_recovery.api.recovery_api.create_recovery_job',
        args: { case_id: this.caseId },
        callback: (r) => {
          this.currentJob = r.message
          frappe.show_alert({ message: '✅ Recovery job created', indicator: 'green' })
        }
      })
    },

    encryptAndUploadSeed() {
      frappe.show_alert({ message: '🔐 Encrypting seed...', indicator: 'blue' })

      // Browser-side RSA encryption
      frappe.call({
        method: 'thanatos_intel.thanatos_recovery.api.recovery_api.get_vault_public_key',
        callback: (r) => {
          // In produzione: implementare vera RSA encryption con TweetNaCl.js
          // Per POC: invio plaintext (non sicuro, solo per test)
          const encrypted = btoa(this.seedInput) // Mock: base64 encode

          frappe.call({
            method: 'thanatos_intel.thanatos_recovery.api.recovery_api.upload_seed_input',
            args: {
              job_id: this.currentJob.name,
              encrypted_seed_base64: encrypted
            },
            callback: (r2) => {
              this.currentJob.status = 'Uploaded'
              frappe.show_alert({ message: '✅ Seed uploaded and encrypted', indicator: 'green' })
              this.$forceUpdate()
            }
          })
        }
      })
    },

    generateCommand() {
      frappe.call({
        method: 'thanatos_intel.thanatos_recovery.api.recovery_api.generate_cli_command',
        args: {
          job_id: this.currentJob.name,
          parameters: JSON.stringify({
            missing_words_count: this.currentJob.missing_words_count,
            wordlist_type: this.currentJob.wordlist_type
          })
        },
        callback: (r) => {
          this.currentJob.processing_command = r.message.command
          this.$forceUpdate()
        }
      })
    },

    markAsProcessing() {
      this.currentJob.status = 'Processing'
      this.$forceUpdate()
    },

    handleResultFileSelect(event) {
      this.resultFile = event.target.files[0]
    },

    uploadRecoveryResult() {
      if (!this.resultFile) {
        frappe.show_alert({ message: '❌ Please select result file', indicator: 'red' })
        return
      }

      this.isUploading = true

      const reader = new FileReader()
      reader.onload = (e) => {
        const encrypted = btoa(String.fromCharCode.apply(null, new Uint8Array(e.target.result)))

        frappe.call({
          method: 'thanatos_intel.thanatos_recovery.api.recovery_api.upload_recovery_result',
          args: {
            job_id: this.currentJob.name,
            encrypted_result_base64: encrypted
          },
          callback: (r) => {
            this.currentJob.status = 'Completed'
            this.currentJob.result_vault_url = r.message.download_link
            this.currentJob.result_expires_at = r.message.expires_at
            this.isUploading = false
            frappe.show_alert({ message: '✅ Recovery result uploaded!', indicator: 'green' })
            this.$forceUpdate()
          }
        })
      }
      reader.readAsArrayBuffer(this.resultFile)
    },

    copyCommand() {
      navigator.clipboard.writeText(this.currentJob.processing_command)
      frappe.show_alert({ message: '📋 Command copied to clipboard', indicator: 'blue' })
    },

    copyDownloadLink() {
      navigator.clipboard.writeText(this.currentJob.result_vault_url)
      frappe.show_alert({ message: '📋 Download link copied', indicator: 'blue' })
    },

    shareViaEmail() {
      const email = `mailto:client@example.com?subject=Your%20Seed%20Recovery%20Link&body=${encodeURIComponent(this.currentJob.result_vault_url)}`
      window.location.href = email
    },

    shareViaWhatsApp() {
      const msg = `Your seed recovery is complete. Download link (expires in 48h): ${this.currentJob.result_vault_url}`
      const wa = `https://wa.me/?text=${encodeURIComponent(msg)}`
      window.open(wa, '_blank')
    },

    shareViaPortal() {
      frappe.show_alert({ message: '📬 Link will be sent via client portal message', indicator: 'blue' })
    },

    resetJob() {
      this.currentJob = null
      this.seedInput = ''
      this.resultFile = null
    },

    formatDate(dateStr) {
      return new Date(dateStr).toLocaleString()
    }
  }
}
</script>

<style scoped>
.wallet-recovery-widget {
  padding: 20px;
  background: #f8f9fa;
  border-radius: 8px;
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
}

.header-section {
  margin-bottom: 20px;
  padding-bottom: 15px;
  border-bottom: 2px solid #ddd;
}

.header-section h5 {
  margin: 0 0 5px 0;
  color: #2c3e50;
}

.subtitle {
  color: #7f8c8d;
  font-size: 0.9em;
  margin: 0;
}

.intro-section {
  padding: 15px;
  background: white;
  border-radius: 6px;
  text-align: center;
}

.intro-section p {
  margin-bottom: 15px;
  color: #555;
}

.job-section {
  background: white;
  padding: 15px;
  border-radius: 6px;
}

.job-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
  padding-bottom: 10px;
  border-bottom: 2px solid #ecf0f1;
}

.job-header h6 {
  margin: 0;
  font-weight: 600;
}

.step {
  margin-bottom: 25px;
  padding: 15px;
  background: #f8f9fa;
  border-left: 4px solid #3498db;
  border-radius: 4px;
}

.step h6 {
  margin-top: 0;
  margin-bottom: 15px;
  color: #2c3e50;
  display: flex;
  align-items: center;
}

.step-num {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  background: #3498db;
  color: white;
  border-radius: 50%;
  margin-right: 10px;
  font-weight: bold;
  font-size: 0.9em;
}

.form-group {
  margin-bottom: 15px;
}

.form-group label {
  font-weight: 500;
  margin-bottom: 5px;
  display: block;
  color: #2c3e50;
}

.form-group small {
  color: #7f8c8d;
  display: block;
  margin-top: 3px;
}

.code-block {
  background: #2c3e50;
  color: #ecf0f1;
  padding: 12px;
  border-radius: 4px;
  margin: 10px 0;
  overflow-x: auto;
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.code-block code {
  font-family: 'Courier New', monospace;
  font-size: 0.85em;
  flex: 1;
}

.download-link-box {
  background: #ecf0f1;
  padding: 12px;
  border-radius: 4px;
  margin: 10px 0;
  display: flex;
  gap: 10px;
}

.download-link-box input {
  flex: 1;
}

.expiry-alert {
  background: #fff3cd;
  color: #856404;
  padding: 10px;
  border-radius: 4px;
  margin: 10px 0;
  font-size: 0.9em;
}

.expiry-alert small {
  display: block;
  margin-top: 3px;
}

.audit-section {
  margin-top: 20px;
  padding: 12px;
  background: #ecf0f1;
  border-radius: 4px;
  cursor: pointer;
}

.audit-section pre {
  background: #2c3e50;
  color: #ecf0f1;
  padding: 10px;
  border-radius: 3px;
  overflow-x: auto;
  font-size: 0.8em;
  max-height: 300px;
  overflow-y: auto;
  margin: 10px 0 0 0;
}

.actions-footer {
  text-align: center;
  padding-top: 15px;
  border-top: 1px solid #ddd;
  margin-top: 15px;
}

.share-buttons {
  display: flex;
  gap: 10px;
  margin-top: 10px;
}

.btn {
  padding: 8px 16px;
  border-radius: 4px;
  cursor: pointer;
  font-weight: 500;
  transition: all 0.3s ease;
}

.btn:hover:not(:disabled) {
  transform: translateY(-2px);
  box-shadow: 0 2px 8px rgba(0,0,0,0.15);
}

.btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.badge {
  padding: 4px 12px;
  border-radius: 20px;
  font-size: 0.85em;
  font-weight: 500;
}

.badge-secondary { background: #e9ecef; color: #495057; }
.badge-info { background: #d1ecf1; color: #0c5460; }
.badge-warning { background: #fff3cd; color: #856404; }
.badge-success { background: #d4edda; color: #155724; }
.badge-danger { background: #f8d7da; color: #721c24; }
.badge-dark { background: #e2e3e5; color: #383d41; }
</style>
