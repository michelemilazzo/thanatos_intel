"""
Audit trail module for Thanatos Intel
Logs all token tests with full context for compliance
"""

import frappe
import json
from datetime import datetime


class AuditLogger:
    """Log all token liquidity tests for audit trail"""

    @staticmethod
    def log_test(doc):
        """Log a token liquidity test"""
        try:
            audit_entry = {
                "doctype": "Audit Log",
                "document": doc.name,
                "document_type": "Token Liquidity Test",
                "action": "Create",
                "timestamp": datetime.now(),
                "user": frappe.session.user,
                "data": {
                    "token_address": doc.token_address,
                    "token_symbol": doc.token_symbol,
                    "blockchain": doc.blockchain,
                    "test_amount": doc.test_amount,
                    "price": doc.token_price_usd,
                    "liquidity": doc.pool_liquidity_usd,
                    "volume_24h": doc.volume_24h_usd,
                    "slippage_pct": doc.estimated_slippage_pct,
                    "liquidity_status": doc.liquidity_status,
                    "is_liquidizable": doc.is_liquidizable,
                    "risk_assessment": doc.risk_assessment,
                    "data_sources": doc.data_sources,
                }
            }

            # Log to database
            frappe.db.insert({
                "doctype": "Token Test Audit Log",
                "test_name": doc.name,
                "token_symbol": doc.token_symbol,
                "blockchain": doc.blockchain,
                "test_data": json.dumps(audit_entry["data"]),
                "analyst": frappe.session.user,
                "verdict": "PASS" if doc.is_liquidizable else "FAIL",
                "risk_level": _get_risk_level(doc.liquidity_status),
            })

            frappe.db.commit()

        except Exception as e:
            frappe.log_error(
                f"Audit logging failed: {str(e)}",
                "Token Liquidity Audit"
            )


def _get_risk_level(liquidity_status):
    """Map liquidity status to risk level"""
    risk_map = {
        "Adequate": "Low",
        "Low": "Medium",
        "Insufficient": "High",
        "No Data": "Unknown",
    }
    return risk_map.get(liquidity_status, "Unknown")


def setup_audit_hooks():
    """Setup audit trail hooks"""
    frappe.db.commit()
