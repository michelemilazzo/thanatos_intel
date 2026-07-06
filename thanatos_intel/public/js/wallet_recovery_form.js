/**
 * Investigation Case Extension - Aggiunge tab Wallet Recovery
 * Integra il Vue component nel desk Frappe
 */

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
        options: ['BIP39 Seed', 'Electrum Seed', 'BIP38 Encrypted', 'Ledger Passphrase'],
        reqd: 1
      },
      {
        label: __('Seed Input (Partial)'),
        fieldname: 'seed_input',
        fieldtype: 'Text Editor',
        description: __('Use ???? for missing words')
      }
    ],
    primary_action_label: __('Create Recovery Job'),
    primary_action(values) {
      if (!values.wallet_type || !values.seed_input) {
        frappe.throw(__('Please fill wallet type and seed input'));
      }

      frappe.call({
        method: 'thanatos_intel.thanatos_recovery.api.recovery_api.create_recovery_job',
        args: { case_id: frm.doc.name },
        callback: function(r) {
          if (r.message) {
            frappe.msgprint(__('✅ Recovery Job Created: {0}', [r.message.name]));
            d.hide();
            load_recovery_jobs(frm);
          }
        }
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
  const reader = new FileReader();

  reader.onload = function(e) {
    const content = btoa(e.target.result); // Base64 encode

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

function upload_recovery_result(frm, file) {
  // In real scenario, read file and encrypt
  // For now, use file attachment system

  frappe.call({
    method: 'thanatos_intel.thanatos_recovery.api.recovery_api.upload_recovery_result',
    args: {
      job_id: frm.doc.name,
      encrypted_result_base64: btoa('mock_encrypted_result') // Mock for now
    },
    callback: function(r) {
      if (r.message) {
        frm.set_value('status', 'Completed');
        frm.set_value('result_vault_url', r.message.download_link);
        frm.set_value('result_expires_at', r.message.expires_at);
        frm.save();
        frappe.show_alert({ message: __('✅ Result uploaded!'), indicator: 'green' });
      }
    }
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
