app_name = 'thanatos_intel'
app_title = 'Thanatos Intel'
app_version = '0.1.0'
app_description = 'Intelligence Investigation Platform MVP'
app_author = 'OneKeyCo'
app_author_email = 'info@onekeyco.com'
app_license = 'MIT'
app_icon = 'icon-bar-chart'
app_color = 'navy'
app_email = 'info@onekeyco.com'
app_docs = 'https://thanatos.onekeyco.com'
app_country = 'IT'

# Fixtures exported by the app.
# Roles, workspace and permission records will be added here after they are created and validated.
fixtures = []

# Document event hooks.
# Business logic stays inside each DocType controller for the MVP baseline.
doc_events = {}

scheduler_events = {
    'cron': {},
    'all': [],
    'daily': [],
    'daily_long': [],
    'weekly': [],
    'weekly_long': [],
    'monthly': [],
    'monthly_long': [],
}

website_route_rules = []

permission_query_conditions = {}

has_permission = {}
