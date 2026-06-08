app_name='thanatos_intel'
app_title='Thanatos Intel'
app_version='0.1.0'
app_description='Intelligence Investigation Platform MVP'
app_author='OneKeyCo'
app_author_email='info@onekeyco.com'
app_license='MIT'
app_icon='icon-bar-chart'
app_color='navy'
app_email='info@onekeyco.com'
app_docs='https://thanatos.onekeyco.com'
app_country='IT'

app_logo_url='/assets/thanatos_intel/images/thanatos-icon-192.png'
app_include_css=['/assets/thanatos_intel/css/desk_chrome.css']
app_include_js=['/assets/thanatos_intel/js/bootstrap_jq.js',
                '/assets/thanatos_intel/js/desk_chrome.js',
                '/assets/thanatos_intel/js/fx_widget.js']
web_include_js=['/assets/thanatos_intel/js/fx_widget.js']
brand_html='<img src="/assets/thanatos_intel/images/thanatos-logo-mark.png" alt="Thanatos Intel" style="height:32px"/>'
website_context={
 'favicon': '/assets/thanatos_intel/images/thanatos-icon-192.png',
 'splash_image': '/assets/thanatos_intel/images/thanatos-logo-mark.png',
 'brand_html': '<img src="/assets/thanatos_intel/images/thanatos-logo-mark.png" alt="Thanatos Intel" style="height:32px"/>',
}

after_install='thanatos_intel.install.after_install'
after_migrate='thanatos_intel.install.after_migrate'
fixtures=[
 'Role',
 {'doctype': 'Investigation Subscription Plan', 'filters': []},
 {'doctype': 'Service Catalog', 'filters': []},
 {'doctype': 'News Category', 'filters': []},
 {'doctype': 'News Source', 'filters': []},
 {'doctype': 'Country Framework', 'filters': []},
 {'doctype': 'Number Card', 'filters': [['name', 'in', [
   'Casi aperti', 'Casi in lavorazione', 'Evidenze da custodire',
   'Mandati DDD attivi', 'OSINT job attivi', 'Clienti']]]},
 {'doctype': 'Dashboard Chart', 'filters': [['name', 'in', [
   'Casi per stato', 'Mandati DDD per fase', 'Nuovi casi nel tempo']]]},
 {'doctype': 'Custom Field', 'filters': [['name', 'in', [
   'Sales Invoice-custom_sb_ron', 'Sales Invoice-custom_eur_ron_rate',
   'Sales Invoice-custom_ron_ccy', 'Sales Invoice-custom_net_total_ron',
   'Sales Invoice-custom_grand_total_ron',
   'Quotation-custom_sb_ron', 'Quotation-custom_eur_ron_rate',
   'Quotation-custom_ron_ccy', 'Quotation-custom_net_total_ron',
   'Quotation-custom_grand_total_ron']]]},
]

doc_events={
 'Customer': {
   'validate': 'thanatos_intel.billing.case_billing.warn_duplicate_customer',
 },
 'Investigation Client': {
   'on_update': 'thanatos_intel.billing.case_billing.on_client_update',
 },
 'CRM Deal': {
   'on_update': 'thanatos_intel.billing.crm_pipeline.on_deal_update',
 },
 'Infrastructure Cost': {
   'after_insert': 'thanatos_intel.billing.erp_sync.on_infrastructure_cost_save',
   'on_update': 'thanatos_intel.billing.erp_sync.on_infrastructure_cost_save',
 },
 'Diplomatic Eligibility Case': {
   'after_insert': 'thanatos_intel.thanatos_ddd.audit.on_after_insert_case',
   'on_update': 'thanatos_intel.thanatos_ddd.audit.on_update_case',
 },
 'Communication': {
   'after_insert': 'thanatos_intel.integrations.intel_inbox.on_communication_insert',
 },
 'Investigation Report': {
   'before_save': 'thanatos_intel.integrations.intel_inbox.before_save_report',
   'on_update':   'thanatos_intel.integrations.intel_inbox.on_update_report',
 },
 'Investigation Case': {
   'after_insert': 'thanatos_intel.integrations.intel_inbox.ensure_case_folder_hook',
 },
 'Agency Mandate': {
   'validate': 'thanatos_intel.billing.billing_entity.stamp_ddd_billing_entity',
   'on_update': 'thanatos_intel.billing.ddd_billing.on_mandate_update',
 },
 'Revenue Distribution': {
   'validate': 'thanatos_intel.thanatos_core.currency.ron_accounting.apply_ron',
 },
 'Diplomatic Proforma': {
   'validate': [
     'thanatos_intel.thanatos_core.currency.ron_accounting.apply_ron',
     'thanatos_intel.billing.billing_entity.stamp_ddd_billing_entity',
   ],
 },
 'Usage Event': {
   'validate': 'thanatos_intel.thanatos_core.currency.ron_accounting.apply_ron',
 },
 'Investigation Subscription Plan': {
   'validate': 'thanatos_intel.thanatos_core.currency.ron_accounting.apply_ron',
 },
 'Party Payout': {
   'after_insert': 'thanatos_intel.billing.credits.on_party_payout_update',
   'on_update': 'thanatos_intel.billing.credits.on_party_payout_update',
 },
 'Sales Invoice': {
   'validate': 'thanatos_intel.thanatos_core.currency.ron_accounting.apply_ron_erp',
 },
 'Quotation': {
   'validate': 'thanatos_intel.thanatos_core.currency.ron_accounting.apply_ron_erp',
 },
}
scheduler_events={
 'cron':{},
 'all':[],
 'hourly':['thanatos_intel.news.ingestion.hourly_ingest',
           'thanatos_intel.thanatos_core.currency.converter.fetch_rates'],
 'daily':['thanatos_intel.news.ingestion.daily_case_digest',
          'thanatos_intel.thanatos_ddd.opensanctions_sync.daily_refresh'],
 'daily_long':[],
 'weekly':[],
 'weekly_long':[],
 'monthly':['thanatos_intel.billing.cost_invoicing.scheduled_monthly_cost_invoicing',
            'thanatos_intel.billing.erp_sync.scheduled_monthly_invoice_on_erp'],
 'monthly_long':[]
}
website_route_rules=[
 {'from_route': '/portal/case/<name>', 'to_route': 'portal/case'},
 {'from_route': '/news/categoria/<slug>', 'to_route': 'news/categoria'},
]
permission_query_conditions={
 'Investigation Case':'thanatos_intel.permissions.case_query_conditions',
 'Investigation Client':'thanatos_intel.permissions.client_query_conditions',
 'OSINT Job':'thanatos_intel.permissions.osint_job_query_conditions',
 'Investigation Evidence':'thanatos_intel.permissions.evidence_query_conditions',
 'Investigation Report':'thanatos_intel.permissions.report_query_conditions',
}
has_permission={
 'Investigation Case':'thanatos_intel.permissions.can_read_thanatos_doc',
 'Investigation Client':'thanatos_intel.permissions.can_read_client',
 'OSINT Job':'thanatos_intel.permissions.can_read_osint_job',
 'Investigation Entity':'thanatos_intel.permissions.can_read_thanatos_doc',
 'Investigation Evidence':'thanatos_intel.permissions.can_read_thanatos_doc',
 'Investigation Report':'thanatos_intel.permissions.can_read_thanatos_doc',
 'Risk Score':'thanatos_intel.permissions.can_read_thanatos_doc',
 'Chain Of Custody Event':'thanatos_intel.permissions.can_read_thanatos_doc'
}
# Jinja helpers — usabili in Print Format e portali:
#   {{ thanatos_fx(amount, "USD") }}
#   {{ thanatos_fx_block(amount) }}  -> tabella HTML multi-valuta
jinja={
 'methods':[
   'thanatos_intel.thanatos_core.currency.converter.jinja_fx',
   'thanatos_intel.thanatos_core.currency.converter.jinja_fx_block',
   'thanatos_intel.thanatos_core.currency.converter.convert_all',
   'thanatos_intel.permissions.is_full_access',
 ],
}
