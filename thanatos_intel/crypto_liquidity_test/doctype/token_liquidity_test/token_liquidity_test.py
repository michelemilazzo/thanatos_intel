import frappe
from frappe.model.document import Document
from datetime import datetime
from thanatos_intel.crypto_liquidity_test.api import TokenDataAggregator
from thanatos_intel.crypto_liquidity_test.audit import AuditLogger


class TokenLiquidityTest(Document):
    def validate(self):
        self.user_email = frappe.session.user

    def before_save(self):
        self.test_timestamp = datetime.now()
        if self.token_address and self.blockchain:
            self.run_liquidity_test()

    def after_insert(self):
        """Log test to audit trail after creation"""
        AuditLogger.log_test(self)

    def run_liquidity_test(self):
        """Run comprehensive liquidity test on token using multi-source aggregation"""
        try:
            aggregator = TokenDataAggregator(
                token_address=self.token_address,
                blockchain=self.blockchain,
                amount=self.test_amount,
            )
            result = aggregator.aggregate()

            if result:
                self.token_symbol = result.get("symbol", "")
                self.token_name = result.get("name", "")
                self.token_price_usd = result.get("price", 0)
                self.pool_liquidity_usd = result.get("liquidity", 0)
                self.volume_24h_usd = result.get("volume_24h", 0)
                self.output_theoretical = (
                    self.test_amount * result.get("price", 0)
                )

                slippage = result.get("slippage_pct", 0)
                self.estimated_slippage_pct = slippage

                self.output_real = self.output_theoretical * (
                    1 - slippage / 100
                )

                self.liquidity_status = result.get("liquidity_status", "No Data")
                self.is_liquidizable = result.get("is_liquidizable", False)
                self.risk_assessment = result.get("risk_assessment", "")
                self.data_sources = ", ".join(result.get("data_sources", []))
        except Exception as e:
            frappe.log_error(
                f"Error running liquidity test: {str(e)}",
                "Token Liquidity Test Error"
            )
            self.risk_assessment = f"Test failed: {str(e)}"


@frappe.whitelist()
def run_quick_test(token_address, blockchain="Polygon", amount=100):
    """API endpoint to run quick liquidity test"""
    aggregator = TokenDataAggregator(token_address, blockchain, float(amount))
    return aggregator.aggregate()
