import frappe
from frappe.model.document import Document
from datetime import datetime
import requests
import json


class TokenLiquidityTest(Document):
    def validate(self):
        self.user_email = frappe.session.user

    def before_save(self):
        self.test_timestamp = datetime.now()
        if self.token_address and self.blockchain:
            self.run_liquidity_test()

    def run_liquidity_test(self):
        """Run comprehensive liquidity test on token"""
        try:
            result = test_token_liquidity(
                token_address=self.token_address,
                blockchain=self.blockchain,
                amount=self.test_amount,
            )

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
                self.data_sources = result.get("data_sources", "Multiple Sources")
        except Exception as e:
            frappe.log_error(
                f"Error running liquidity test: {str(e)}",
                "Token Liquidity Test Error"
            )
            self.risk_assessment = f"Test failed: {str(e)}"


def test_token_liquidity(token_address, blockchain, amount=100):
    """
    Test token liquidity using multiple data sources
    Returns dict with test results
    """
    result = {
        "symbol": "",
        "name": "",
        "price": 0,
        "liquidity": 0,
        "volume_24h": 0,
        "slippage_pct": 0,
        "liquidity_status": "No Data",
        "is_liquidizable": False,
        "risk_assessment": "",
        "data_sources": "Manual Input",
    }

    if blockchain.lower() != "polygon":
        result["risk_assessment"] = "Only Polygon support implemented"
        return result

    # Try DEX Screener API
    try:
        response = requests.get(
            f"https://api.dexscreener.com/latest/dex/tokens/{token_address}",
            timeout=10
        )

        if response.status_code == 200:
            data = response.json()

            if data.get("pairs"):
                pair = data["pairs"][0]
                result["symbol"] = pair.get("baseToken", {}).get("symbol", "???")
                result["name"] = pair.get("baseToken", {}).get("name", "Unknown")
                result["price"] = float(pair.get("priceUsd", 0))
                result["liquidity"] = float(
                    pair.get("liquidity", {}).get("usd", 0)
                )
                result["volume_24h"] = float(
                    pair.get("volume", {}).get("h24", 0)
                )
                result["data_sources"] = "DEX Screener"

                # Calculate liquidity status and slippage
                liquidity_value = result["liquidity"]
                test_value = amount * result["price"]

                if liquidity_value == 0:
                    result["liquidity_status"] = "Insufficient"
                    result["is_liquidizable"] = False
                    result["slippage_pct"] = 100
                    result[
                        "risk_assessment"
                    ] = "❌ ZERO LIQUIDITY - Token is not tradable"
                elif test_value > liquidity_value * 0.1:
                    result["liquidity_status"] = "Insufficient"
                    result["is_liquidizable"] = False
                    slippage = (test_value / liquidity_value) * 100 * 10
                    result["slippage_pct"] = min(slippage, 100)
                    result[
                        "risk_assessment"
                    ] = f"❌ ILLIQUID - Test amount {test_value:,.0f} USD is {test_value/liquidity_value:.1%} of pool liquidity. Extreme slippage expected."
                elif test_value > liquidity_value * 0.01:
                    result["liquidity_status"] = "Low"
                    result["is_liquidizable"] = False
                    slippage = (test_value / liquidity_value) * 100 * 5
                    result["slippage_pct"] = min(slippage, 50)
                    result[
                        "risk_assessment"
                    ] = f"⚠️  LOW LIQUIDITY - Significant slippage expected. Volume/liquidity ratio poor."
                elif result["volume_24h"] < 1000:
                    result["liquidity_status"] = "Low"
                    result["is_liquidizable"] = False
                    slippage = (test_value / liquidity_value) * 100
                    result["slippage_pct"] = slippage
                    result[
                        "risk_assessment"
                    ] = f"⚠️  LOW VOLUME - 24h volume only {result['volume_24h']:,.0f} USD, likely low liquidity"
                else:
                    result["liquidity_status"] = "Adequate"
                    result["is_liquidizable"] = True
                    slippage = (test_value / liquidity_value) * 100 * 0.5
                    result["slippage_pct"] = min(slippage, 5)
                    result[
                        "risk_assessment"
                    ] = "✅ LIQUIDIZABLE - Adequate liquidity detected"

                return result
    except Exception as e:
        frappe.log_error(f"DEX Screener API error: {str(e)}", "Token Liquidity Test")

    result["risk_assessment"] = "Unable to fetch liquidity data"
    return result


@frappe.whitelist()
def run_quick_test(token_address, blockchain="Polygon", amount=100):
    """API endpoint to run quick liquidity test"""
    return test_token_liquidity(token_address, blockchain, float(amount))
