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

app_logo_url='/assets/thanatos_intel/images/thanatos-icon.svg'
brand_html='<img src="/assets/thanatos_intel/images/thanatos-logo.svg" alt="Thanatos Intel" style="height:32px"/>'
website_context={
 'favicon': '/assets/thanatos_intel/images/thanatos-icon.svg',
 'splash_image': '/assets/thanatos_intel/images/thanatos-logo.svg',
 'brand_html': '<img src="/assets/thanatos_intel/images/thanatos-logo.svg" alt="Thanatos Intel" style="height:32px"/>',
}

after_install='thanatos_intel.install.after_install'
fixtures=[
 'Role',
 {'doctype': 'Investigation Subscription Plan', 'filters': []},
 {'doctype': 'Service Catalog', 'filters': []},
 {'doctype': 'Infrastructure Cost', 'filters': []},
 {'doctype': 'News Category', 'filters': []},
 {'doctype': 'News Source', 'filters': []},
]

doc_events={
 'Infrastructure Cost': {
   'after_insert': 'thanatos_intel.billing.erp_sync.on_infrastructure_cost_save',
   'on_update': 'thanatos_intel.billing.erp_sync.on_infrastructure_cost_save',
 }
}
scheduler_events={
 'cron':{},
 'all':[],
 'hourly':['thanatos_intel.news.ingestion.hourly_ingest'],
 'daily':['thanatos_intel.news.ingestion.daily_case_digest'],
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
permission_query_conditions={}
has_permission={
 'Investigation Case':'thanatos_intel.permissions.can_read_thanatos_doc',
 'Investigation Entity':'thanatos_intel.permissions.can_read_thanatos_doc',
 'Investigation Evidence':'thanatos_intel.permissions.can_read_thanatos_doc',
 'Investigation Report':'thanatos_intel.permissions.can_read_thanatos_doc',
 'Risk Score':'thanatos_intel.permissions.can_read_thanatos_doc',
 'Chain Of Custody Event':'thanatos_intel.permissions.can_read_thanatos_doc'
}
