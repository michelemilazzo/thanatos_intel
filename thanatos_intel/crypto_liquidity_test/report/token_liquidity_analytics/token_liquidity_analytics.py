import frappe
from frappe import _


def execute(filters=None):
    """Token Liquidity Analytics Report"""

    columns = get_columns()
    data = get_data(filters)

    return columns, data


def get_columns():
    return [
        {
            "label": _("Test Name"),
            "fieldname": "name",
            "fieldtype": "Link",
            "options": "Token Liquidity Test",
            "width": 150,
        },
        {
            "label": _("Token"),
            "fieldname": "token_symbol",
            "fieldtype": "Data",
            "width": 80,
        },
        {
            "label": _("Blockchain"),
            "fieldname": "blockchain",
            "fieldtype": "Data",
            "width": 100,
        },
        {
            "label": _("Price USD"),
            "fieldname": "token_price_usd",
            "fieldtype": "Currency",
            "width": 120,
        },
        {
            "label": _("Liquidity USD"),
            "fieldname": "pool_liquidity_usd",
            "fieldtype": "Currency",
            "width": 140,
        },
        {
            "label": _("Volume 24h USD"),
            "fieldname": "volume_24h_usd",
            "fieldtype": "Currency",
            "width": 140,
        },
        {
            "label": _("Slippage %"),
            "fieldname": "estimated_slippage_pct",
            "fieldtype": "Percent",
            "width": 100,
        },
        {
            "label": _("Status"),
            "fieldname": "liquidity_status",
            "fieldtype": "Data",
            "width": 100,
        },
        {
            "label": _("Liquidizable"),
            "fieldname": "is_liquidizable",
            "fieldtype": "Check",
            "width": 80,
        },
        {
            "label": _("Test Timestamp"),
            "fieldname": "test_timestamp",
            "fieldtype": "Datetime",
            "width": 140,
        },
        {
            "label": _("Analyst"),
            "fieldname": "user_email",
            "fieldtype": "Data",
            "width": 120,
        },
    ]


def get_data(filters):
    """Fetch test records with optional filters"""

    conditions = []

    if filters.get("date_from"):
        conditions.append(
            f"DATE(test_timestamp) >= '{filters.get('date_from')}'"
        )

    if filters.get("date_to"):
        conditions.append(
            f"DATE(test_timestamp) <= '{filters.get('date_to')}'"
        )

    if filters.get("blockchain"):
        conditions.append(
            f"blockchain = '{filters.get('blockchain')}'"
        )

    if filters.get("liquidity_status"):
        conditions.append(
            f"liquidity_status = '{filters.get('liquidity_status')}'"
        )

    where_clause = " AND ".join(conditions) if conditions else "1=1"

    data = frappe.db.sql(
        f"""
        SELECT
            name,
            token_symbol,
            blockchain,
            token_price_usd,
            pool_liquidity_usd,
            volume_24h_usd,
            estimated_slippage_pct,
            liquidity_status,
            is_liquidizable,
            test_timestamp,
            user_email
        FROM `tabToken Liquidity Test`
        WHERE {where_clause}
        ORDER BY test_timestamp DESC
        """,
        as_dict=True,
    )

    return data
