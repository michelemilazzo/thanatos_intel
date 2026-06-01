app_name = "thanatos_intel"
app_title = "Thanatos Intel"
app_publisher = "Thanatos"
app_description = "Intelligence & crypto analysis tools: token liquidity testing, DEX screener, risk assessment"
app_email = "ops@thanatos.onekeyco.com"
app_license = "MIT"
app_version = "0.1.0"

app_icon = "octicon octicon-telescope"
app_color = "indigo"

# Includes in <head>
app_include_css = [
    "/assets/thanatos_intel/css/thanatos_intel.css"
]
app_include_js = [
    "/assets/thanatos_intel/js/thanatos_intel.js"
]

# DocTypes
doctype_js = {
    "Token Liquidity Test": "public/js/doctype_token_liquidity_test.js"
}

# Desk Pages
desk_pages = [
    "Thanatos Intel Dashboard"
]

# Sidebar
sidebar_items = [
    {
        "label": "Crypto Analysis",
        "items": [
            {
                "type": "doctype",
                "name": "Token Liquidity Test",
                "label": "Token Liquidity Tests"
            },
            {
                "type": "doctype",
                "name": "Blockchain",
                "label": "Blockchains"
            },
            {
                "type": "doctype",
                "name": "Token",
                "label": "Tokens"
            }
        ]
    }
]

# Fixtures
fixtures = [
    {"dt": "Blockchain", "filters": [["name", "in", ["Polygon", "Ethereum", "Arbitrum", "Base"]]]},
    {"dt": "Token", "filters": [["name", "in", ["USDT", "USDC", "WETH", "WMATIC"]]]},
]

# ERPNext required
required_apps = ["frappe"]
