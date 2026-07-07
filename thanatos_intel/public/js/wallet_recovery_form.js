/**
 * Investigation Case Extension - Aggiunge tab Wallet Recovery
 * Integra il Vue component nel desk Frappe
 */

/* ==================== BROWSER RSA ENCRYPTION ====================
 * Cifra il seed lato browser con la public key RSA-4096 del vault (RSA-OAEP
 * SHA-256), coerente con decrypt_input() del CLI offline. Il plaintext non
 * lascia mai il browser in chiaro: viaggia solo il ciphertext base64.
 */

function _b64FromBuffer(buffer) {
  const bytes = new Uint8Array(buffer);
  let binary = '';
  for (let i = 0; i < bytes.length; i++) binary += String.fromCharCode(bytes[i]);
  return window.btoa(binary);
}

function _bufferFromB64(b64) {
  const binary = window.atob(b64);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
  return bytes.buffer;
}

function _pemToDer(pem) {
  const body = pem
    .replace(/-----BEGIN PUBLIC KEY-----/, '')
    .replace(/-----END PUBLIC KEY-----/, '')
    .replace(/\s+/g, '');
  return _bufferFromB64(body);
}

// Importa la public key PEM (SubjectPublicKeyInfo) in WebCrypto
async function import_vault_public_key(pem) {
  return window.crypto.subtle.importKey(
    'spki',
    _pemToDer(pem),
    { name: 'RSA-OAEP', hash: 'SHA-256' },
    false,
    ['encrypt']
  );
}

// Cifra una stringa e restituisce base64(ciphertext)
async function rsa_encrypt_to_b64(pem, plaintext) {
  const key = await import_vault_public_key(pem);
  const data = new TextEncoder().encode(plaintext);
  const ct = await window.crypto.subtle.encrypt({ name: 'RSA-OAEP' }, key, data);
  return _b64FromBuffer(ct);
}

// Recupera la public key del vault (cache in-memory per la sessione)
let _vault_pubkey_cache = null;
function get_vault_public_key() {
  if (_vault_pubkey_cache) return Promise.resolve(_vault_pubkey_cache);
  return frappe.call({
    method: 'thanatos_intel.thanatos_recovery.api.recovery_api.get_vault_public_key'
  }).then(function (r) {
    _vault_pubkey_cache = r.message;
    return r.message;
  });
}

frappe.ui.form.on('Investigation Case', {
  refresh: function(frm) {
    // Aggiungi tab Wallet Recovery se non esiste
    if (!frm.get_active_tab) {
      console.log('Wallet Recovery tab support not available');
      return;
    }

    // Crea tab Wallet Recovery
    let wallet_recovery_tab = frm.fields_dict.wallet_recovery_tab;

    if (!wallet_recovery_tab) {
      frm.add_custom_button(__('Wallet Recovery'), function() {
        show_wallet_recovery_modal(frm);
      }, __('Tools'));
    }

    // Aggiungi section nel form
    frm.set_df_property('wallet_recovery_section', 'hidden', 0);
  },

  after_save: function(frm) {
    // Refresh recovery jobs list dopo il save del caso
    if (frm.doc.name) {
      load_recovery_jobs(frm);
    }
  }
});

/**
 * Modal Wallet Recovery Tool
 */
function show_wallet_recovery_modal(frm) {
  let d = new frappe.ui.Dialog({
    title: __('🔐 Wallet Recovery Tool'),
    fields: [
      {
        label: __('Recovery Jobs'),
        fieldname: 'recovery_jobs_section',
        fieldtype: 'Section Break'
      },
      {
        label: __('Job List'),
        fieldname: 'jobs_list',
        fieldtype: 'HTML'
      },
      {
        fieldname: 'col_break',
        fieldtype: 'Column Break'
      },
      {
        label: __('New Recovery Job'),
        fieldname: 'new_job_section',
        fieldtype: 'Section Break'
      },
      {
        label: __('Wallet Type'),
        fieldname: 'wallet_type',
        fieldtype: 'Select',
        options: ['BIP39 Seed', 'Electrum Seed', 'Ledger Passphrase'],
        reqd: 1
      },
      {
        label: __('Missing / Wrong Words'),
        fieldname: 'missing_words_count',
        fieldtype: 'Int',
        default: 1,
        description: __('Quante parole sono mancanti o sbagliate (0 se cerchi solo la passphrase)')
      },
      {
        label: __('Known Address (obbligatorio)'),
        fieldname: 'known_address',
        fieldtype: 'Data',
        reqd: 1,
        description: __('Un indirizzo noto del wallet (es. bc1...) o xpub. Serve a validare: senza, il recupero è impossibile.')
      },
      {
        fieldname: 'cb_params',
        fieldtype: 'Column Break'
      },
      {
        label: __('BIP39 Wordlist'),
        fieldname: 'wordlist_type',
        fieldtype: 'Select',
        options: ['english', 'italian', 'spanish', 'french', 'german'],
        default: 'english'
      },
      {
        label: __('Passphrase Candidates (Ledger)'),
        fieldname: 'passphrase_candidates',
        fieldtype: 'Small Text',
        description: __('Solo per Ledger/BIP39 con 25ª parola: una passphrase candidata per riga. Vuoto se non applicabile.')
      },
      {
        label: __('Seed Guess'),
        fieldname: 'seed_input',
        fieldtype: 'Small Text',
        reqd: 1,
        description: __('Miglior guess del seed a lunghezza piena (12/24 parole). Riempi le posizioni ignote con una parola BIP39 valida qualsiasi (es. "abandon"). Cifrato nel browser (RSA-4096): il testo in chiaro non lascia mai questa pagina.')
      }
    ],
    primary_action_label: __('🔐 Cifra e crea job'),
    primary_action(values) {
      if (!values.wallet_type || !values.seed_input || !values.known_address) {
        frappe.throw(__('Compila wallet type, known address e seed guess'));
      }
      if (!(window.crypto && window.crypto.subtle)) {
        frappe.throw(__('WebCrypto non disponibile: usa un browser moderno su HTTPS.'));
      }

      const seed = (values.seed_input || '').trim();
      d.disable_primary_action();
      frappe.dom.freeze(__('Cifratura e upload seed...'));

      let job_id = null;

      // 1) crea job con parametri  2) cifra RSA nel browser  3) upload ciphertext
      frappe.call({
        method: 'thanatos_intel.thanatos_recovery.api.recovery_api.create_recovery_job',
        args: {
          case_id: frm.doc.name,
          wallet_type: values.wallet_type,
          missing_words_count: values.missing_words_count || 0,
          wordlist_type: values.wordlist_type || 'english',
          known_address: values.known_address,
          passphrase_candidates: values.passphrase_candidates || ''
        }
      }).then(function (r) {
        if (!r.message) throw new Error('create_recovery_job vuoto');
        job_id = r.message.name;
        return get_vault_public_key();
      }).then(function (pem) {
        return rsa_encrypt_to_b64(pem, seed);
      }).then(function (ciphertext_b64) {
        return frappe.call({
          method: 'thanatos_intel.thanatos_recovery.api.recovery_api.upload_seed_input',
          args: { job_id: job_id, encrypted_seed_base64: ciphertext_b64 }
        });
      }).then(function () {
        frappe.dom.unfreeze();
        frappe.show_alert({ message: __('✅ Job {0} creato, seed cifrato e caricato', [job_id]), indicator: 'green' });
        d.hide();
        load_recovery_jobs(frm);
      }).catch(function (err) {
        frappe.dom.unfreeze();
        d.enable_primary_action();
        console.error('Wallet recovery encrypt/upload failed', err);
        frappe.msgprint({
          title: __('Errore'),
          message: __('Cifratura/upload seed fallito: {0}', [(err && err.message) || err]),
          indicator: 'red'
        });
      });
    }
  });

  // Load existing recovery jobs
  load_recovery_jobs(frm, d);

  d.show();
}

/**
 * Carica lista recovery jobs nel modal
 */
function load_recovery_jobs(frm, dialog) {
  frappe.call({
    method: 'frappe.client.get_list',
    args: {
      doctype: 'Wallet Recovery Job',
      filters: { case_id: frm.doc.name },
      fields: ['name', 'status', 'wallet_type', 'modified'],
      order_by: 'modified desc'
    },
    callback: function(r) {
      if (r.message && r.message.length > 0) {
        let html = '<table class="table table-sm">';
        html += '<thead><tr><th>Job ID</th><th>Type</th><th>Status</th><th>Modified</th><th>Action</th></tr></thead><tbody>';

        r.message.forEach(job => {
          let status_badge = get_status_badge(job.status);
          html += `<tr>
            <td><strong>${job.name}</strong></td>
            <td>${job.wallet_type}</td>
            <td>${status_badge}</td>
            <td>${frappe.utils.format_date(job.modified)}</td>
            <td><a onclick="open_recovery_job('${job.name}')" class="btn btn-xs btn-secondary">Open</a></td>
          </tr>`;
        });

        html += '</tbody></table>';

        if (dialog && dialog.fields_dict.jobs_list) {
          dialog.fields_dict.jobs_list.$wrapper.html(html);
        }
      } else {
        let html = '<p class="text-muted">No recovery jobs yet. Create one below.</p>';
        if (dialog && dialog.fields_dict.jobs_list) {
          dialog.fields_dict.jobs_list.$wrapper.html(html);
        }
      }
    }
  });
}

/**
 * Apri recovery job nel desk
 */
function open_recovery_job(job_id) {
  frappe.set_route('Form', 'Wallet Recovery Job', job_id);
}

/**
 * Status badge HTML
 */
function get_status_badge(status) {
  const colors = {
    'Draft': 'badge-secondary',
    'Uploaded': 'badge-info',
    'Processing': 'badge-warning',
    'Completed': 'badge-success',
    'Error': 'badge-danger',
    'Expired': 'badge-dark'
  };

  const color = colors[status] || 'badge-secondary';
  return `<span class="badge ${color}">${status}</span>`;
}

/**
 * Vue Component - Integrazione nel Wallet Recovery Job form
 */
frappe.ui.form.on('Wallet Recovery Job', {
  onload: function(frm) {
    // Setup custom UI
    setup_wallet_recovery_form(frm);
  },

  refresh: function(frm) {
    // Refresh UI based on status
    update_form_ui(frm);

    // Add custom buttons
    if (frm.doc.status === 'Uploaded') {
      frm.add_custom_button(__('Generate Command'), function() {
        generate_recovery_command(frm);
      }, __('Actions'));
    }

    if (frm.doc.status === 'Processing') {
      frm.add_custom_button(__('Upload Result'), function() {
        show_result_upload(frm);
      }, __('Actions'));
    }

    if (frm.doc.status === 'Completed') {
      frm.add_custom_button(__('Copy Download Link'), function() {
        copy_to_clipboard(frm.doc.result_vault_url);
        frappe.show_alert({ message: __('Link copied!'), indicator: 'green' });
      }, __('Share'));

      frm.add_custom_button(__('Share via Email'), function() {
        share_download_link(frm, 'email');
      }, __('Share'));

      frm.add_custom_button(__('Share via WhatsApp'), function() {
        share_download_link(frm, 'whatsapp');
      }, __('Share'));
    }
  },

  wallet_type: function(frm) {
    // Clear seed input when wallet type changes
    frm.set_value('seed_input_file', '');
  }
});

/**
 * Setup form UI
 */
function setup_wallet_recovery_form(frm) {
  // Hide fields based on status
  ['seed_input_file', 'processing_command', 'seed_output_file'].forEach(field => {
    frm.set_df_property(field, 'read_only', 0);
  });

  // Add file upload handler for seed input
  frm.fields_dict.seed_input_file.$wrapper.on('change', 'input[type="file"]', function(e) {
    const file = e.target.files[0];
    if (file) {
      upload_seed_input(frm, file);
    }
  });

  // Add file upload handler for result
  if (frm.fields_dict.seed_output_file) {
    frm.fields_dict.seed_output_file.$wrapper.on('change', 'input[type="file"]', function(e) {
      const file = e.target.files[0];
      if (file) {
        upload_recovery_result(frm, file);
      }
    });
  }
}

/**
 * Update form UI based on status
 */
function update_form_ui(frm) {
  const status = frm.doc.status;

  // Show/hide sections
  frm.set_df_property('seed_input_file', 'hidden', status !== 'Draft');
  frm.set_df_property('processing_command', 'hidden', status === 'Draft');
  frm.set_df_property('seed_output_file', 'hidden', status !== 'Processing');
  frm.set_df_property('result_vault_url', 'hidden', status !== 'Completed');

  frm.refresh_field('seed_input_file');
  frm.refresh_field('processing_command');
  frm.refresh_field('seed_output_file');
  frm.refresh_field('result_vault_url');
}

/**
 * Upload seed input
 */
function upload_seed_input(frm, file) {
  // Path per upload diretto di un file .enc GIÀ cifrato (RSA) fuori dal browser.
  // Il flusso normale (cifratura nel browser) passa dal modal.
  const reader = new FileReader();

  reader.onload = function(e) {
    const content = _b64FromBuffer(e.target.result); // base64 dei byte grezzi

    frappe.call({
      method: 'thanatos_intel.thanatos_recovery.api.recovery_api.upload_seed_input',
      args: {
        job_id: frm.doc.name,
        encrypted_seed_base64: content
      },
      callback: function(r) {
        if (r.message) {
          frm.set_value('status', 'Uploaded');
          frappe.show_alert({ message: __('✅ Seed uploaded'), indicator: 'green' });
        }
      }
    });
  };

  reader.readAsArrayBuffer(file);
}

/**
 * Generate CLI command
 */
function generate_recovery_command(frm) {
  frappe.call({
    method: 'thanatos_intel.thanatos_recovery.api.recovery_api.generate_cli_command',
    args: {
      job_id: frm.doc.name,
      parameters: JSON.stringify({
        missing_words_count: frm.doc.missing_words_count || 3,
        wordlist_type: frm.doc.wordlist_type || 'english'
      })
    },
    callback: function(r) {
      if (r.message) {
        frm.set_value('processing_command', r.message.command);
        frm.set_value('status', 'Processing');
        frm.refresh_field('processing_command');
        frappe.show_alert({ message: __('✅ Command generated'), indicator: 'green' });
      }
    }
  });
}

/**
 * Upload recovery result
 */
function show_result_upload(frm) {
  let d = new frappe.ui.Dialog({
    title: __('Upload Recovery Result'),
    fields: [
      {
        label: __('Result File (result.enc)'),
        fieldname: 'result_file',
        fieldtype: 'Attach',
        reqd: 1
      }
    ],
    primary_action_label: __('Upload'),
    primary_action(values) {
      upload_recovery_result(frm, values.result_file);
      d.hide();
    }
  });

  d.show();
}

function upload_recovery_result(frm, file_or_url) {
  // file_or_url = File (da input file) oppure URL del file .enc allegato,
  // già cifrato Fernet dalla recovery machine offline. Inviamo i byte reali.
  if (!file_or_url) {
    frappe.throw(__('Nessun file risultato selezionato'));
  }

  frappe.dom.freeze(__('Upload risultato...'));

  const buf_promise = (typeof file_or_url === 'string')
    ? fetch(file_or_url).then(function (resp) {
        if (!resp.ok) throw new Error('HTTP ' + resp.status + ' leggendo il file');
        return resp.arrayBuffer();
      })
    : file_or_url.arrayBuffer();

  buf_promise
    .then(function (buf) {
      return frappe.call({
        method: 'thanatos_intel.thanatos_recovery.api.recovery_api.upload_recovery_result',
        args: {
          job_id: frm.doc.name,
          encrypted_result_base64: _b64FromBuffer(buf)
        }
      });
    })
    .then(function (r) {
      frappe.dom.unfreeze();
      if (r.message) {
        frm.reload_doc();
        frappe.show_alert({ message: __('✅ Risultato caricato, link generato'), indicator: 'green' });
      }
    })
    .catch(function (err) {
      frappe.dom.unfreeze();
      console.error('upload_recovery_result failed', err);
      frappe.msgprint({
        title: __('Errore'),
        message: __('Upload risultato fallito: {0}', [(err && err.message) || err]),
        indicator: 'red'
      });
    });
}

/**
 * Share download link
 */
function share_download_link(frm, method) {
  const link = frm.doc.result_vault_url;

  if (method === 'email') {
    window.location.href = `mailto:?subject=Wallet Recovery Result&body=${encodeURIComponent(link)}`;
  } else if (method === 'whatsapp') {
    const msg = `Your seed recovery is ready. Download link (expires in 48h): ${link}`;
    window.open(`https://wa.me/?text=${encodeURIComponent(msg)}`, '_blank');
  }
}

/**
 * Utility: Copy to clipboard
 */
function copy_to_clipboard(text) {
  navigator.clipboard.writeText(text);
}
